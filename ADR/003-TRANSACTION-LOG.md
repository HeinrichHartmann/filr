# filr Transaction Log Specification (v1)

This document specifies the canonical transaction log format for filr warehouses.

---

## 1. Design principles

### 1.1 Never lose data

The transaction log COPIES import data. Each log entry is self-contained.

This accepts storage overhead in exchange for:
* No cross-references that could break
* Each entry independently verifiable
* Simple backup/restore of individual entries
* No logical bugs can corrupt referenced data

### 1.2 Write log first, then apply

All mutations follow this order:

1. Write complete log entry to `_log/`
2. Update `state.db` to mark entry as applied
3. Update derived state (indexes, caches)

If crash occurs between 1 and 2: log entry exists but isn't applied → replay on restart.
If crash occurs between 2 and 3: derived state is stale → rebuild from log.

### 1.3 Type from filename

Log entry type is encoded in the folder name:

```
NNNN_drop
```

Future types would be `NNNN_view`, `NNNN_archive`, etc.
Versioning via name: `drop2`, `drop3`.

### 1.4 Infer from filesystem

No separate manifest file. The log IS the folder structure.
Enumerate `_log/` to discover all entries.

---

## 2. Warehouse layout

```text
~/.filr/warehouse/
  config.toml           # warehouse configuration (canonical)
  state.db              # applied log tracking + derived indexes
  _log/                 # transaction log (canonical, append-only)
    0001_drop/          # first log entry: a drop
      header.json
      entries.jsonl
      blobs/
        <hash>
    0002_drop/          # second log entry: another drop
      header.json
      entries.jsonl
      blobs/
        <hash>
```

### Canonical vs derived

| Path | Canonical? | Description |
|------|------------|-------------|
| `config.toml` | Yes | Warehouse config, set at init |
| `_log/` | Yes | Append-only transaction log |
| `state.db` | No | Derived; tracks applied entries + indexes |

`config.toml` + `_log/` is sufficient to rebuild everything.

---

## 3. Configuration

### `config.toml`

```toml
[warehouse]
name = "main"
created_at = "2026-04-01T10:00:00Z"

[hash]
algorithm = "blake3"
```

### Hash algorithm

Default: `blake3`

Fixed at warehouse creation. Cannot be changed.

---

## 4. Log entry format

### 4.1 Naming

```text
NNNN_<type>
```

* `NNNN` — zero-padded sequence number (4+ digits)
* `<type>` — entry type (`drop` for v1)

Examples:
```
0001_drop
0002_drop
0003_drop
```

### 4.2 Sequence numbers

* Start at 1
* Strictly increasing, no gaps
* Zero-padded for filesystem sorting (minimum 4 digits)
* If > 9999 entries, use more digits: `00001_drop`, etc.

### 4.3 Drop entry structure

```text
NNNN_drop/
  header.json       # drop metadata
  entries.jsonl     # document list
  blobs/            # content-addressed blobs
    <hash>
    <hash>
```

This is the canonical/pure representation (CAS form), not a filesystem tree.

---

## 5. Drop format

### 5.1 `header.json`

```json
{
  "drop_id": "d_20260401_143211_a7c3e9f1",
  "created_at": "2026-04-01T14:32:11.123456Z",
  "source": "fs-import",
  "import_root": "/Users/hhartmann/Downloads/taxes",
  "message": "Tax documents 2025",
  "actor": "hhartmann",
  "tags": ["finance", "taxes"]
}
```

**System fields** (generated, cannot override):
* `drop_id`
* `created_at`
* `source`
* `import_root` (for fs-import)

**User fields** (via `--header`):
* `message`
* `actor`
* `tags`
* Any additional JSON

### 5.2 `entries.jsonl`

One line per document:

```json
{"import_path": "2025/invoice.pdf", "import_name": "invoice.pdf", "blob_hash": "blake3:a7c3e9f1...", "blob_size": 102400}
{"import_path": "2025/receipt.pdf", "import_name": "receipt.pdf", "blob_hash": "blake3:b8d4f0a2...", "blob_size": 51200}
```

Fields:

| Field | Type | Description |
|-------|------|-------------|
| `import_path` | string | Relative path from import root |
| `import_name` | string | Filename |
| `blob_hash` | string | `{algorithm}:{hex}` |
| `blob_size` | integer | Bytes |
| `mime_type` | string? | Optional |

### 5.3 `blobs/`

Content-addressed blob storage within the drop:

```text
blobs/
  a7c3e9f1b2d4e6f8...    # full hash as filename
  b8d4f0a2c3e5f7a9...
```

Each blob is the raw file content. Hash is the full hash (not truncated).

**Note:** Blobs are duplicated across drops. This is intentional — each log entry is self-contained.

---

## 6. Drop ID format

```text
d_{YYYYMMDD}_{HHMMSS}_{hash8}
```

| Component | Description |
|-----------|-------------|
| `d_` | Fixed prefix |
| `YYYYMMDD` | UTC date |
| `HHMMSS` | UTC time |
| `hash8` | First 8 hex chars of drop content hash |

Hash input: `hash(header.json || entries.jsonl)` in canonical form.

Example: `d_20260401_143211_a7c3e9f1`

---

## 7. State tracking

### 7.1 `state.db`

SQLite database tracking:

1. **Last applied log entry** — enables crash recovery
2. **Derived indexes** — for fast queries (optional in v1)

### 7.2 Schema

```sql
CREATE TABLE applied_log (
    seq INTEGER PRIMARY KEY,
    entry_name TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE drops (
    drop_id TEXT PRIMARY KEY,
    seq INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    message TEXT,
    document_count INTEGER,
    total_bytes INTEGER
);

-- Future: document index, blob index, etc.
```

### 7.3 Applied log tracking

When a log entry is applied:

```sql
INSERT INTO applied_log (seq, entry_name, applied_at)
VALUES (1, '0001_drop', '2026-04-01T14:32:11Z');
```

On startup or rebuild:
1. Scan `_log/` for all entries
2. Compare with `applied_log`
3. Apply any unapplied entries in sequence order

---

## 8. Import workflow

`filr drop fs-import <path>` does:

1. **Scan source** — enumerate files, compute hashes
2. **Allocate sequence** — next seq = max(existing) + 1
3. **Generate drop_id** — from timestamp + content hash
4. **Write log entry atomically**:
   - Create `_log/NNNN_drop/` folder
   - Write `header.json`
   - Write `entries.jsonl`
   - Copy blobs to `blobs/`
   - fsync
5. **Apply to state.db**:
   - Insert into `applied_log`
   - Insert into `drops`
6. **Print drop_id**

If crash after step 4 but before step 5: log entry exists, will be applied on next startup.

---

## 9. Rebuild workflow

`filr warehouse rebuild` does:

1. Delete `state.db`
2. Create fresh `state.db` with schema
3. Enumerate `_log/` in sequence order
4. For each entry:
   - Parse header.json, entries.jsonl
   - Verify blob hashes
   - Insert into `applied_log`
   - Update derived tables
5. Report success/errors

After rebuild, warehouse is in consistent state derived purely from log.

---

## 10. Integrity verification

`filr warehouse check` does:

1. Verify `_log/` sequence has no gaps
2. For each log entry:
   - Verify header.json parses
   - Verify entries.jsonl parses
   - Verify all referenced blobs exist
   - Verify blob hashes match content
3. Verify `state.db` is consistent with log
4. Report any issues

---

## 11. Future log entry types

v1 only has `drop`. Future types:

| Type | Purpose |
|------|---------|
| `archive` | Hide a drop from default views |
| `annotate` | Add metadata to existing drop |
| `view` | Define a filesystem view |

Each would have its own folder structure within `_log/NNNN_<type>/`.

---

## 12. Why not deduplicate blobs?

Deduplication could be added later as an optimization layer:

```text
~/.filr/warehouse/
  _log/           # canonical, self-contained entries
  _dedup/         # optional: shared blob storage
```

But the log itself remains self-contained. Dedup would be:
* A cache/optimization
* Rebuildable from log
* Not canonical

For v1, we accept the storage overhead for simplicity and robustness.

---

## 13. Summary

```text
_log/
  0001_drop/        # self-contained drop
    header.json
    entries.jsonl
    blobs/
  0002_drop/        # another self-contained drop
    header.json
    entries.jsonl
    blobs/
```

* Log entries are self-contained (Git-like)
* Type encoded in folder name
* Write log first, then apply
* `state.db` tracks applied entries
* Rebuild from log always works
* Storage overhead accepted for robustness
