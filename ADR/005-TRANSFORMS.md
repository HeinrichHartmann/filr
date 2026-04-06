# Metadata Transforms

Transforms create new document versions with updated metadata.

## 1. Motivation

Raw imports have minimal metadata. To organize documents into an archive, we need derived metadata like `category`, `archive_path`, `type`.

Transforms update metadata by creating new document versions. Documents remain immutable - we create new versions rather than mutating existing ones.

## 2. Design Principles

### 2.1 Documents are versioned

A document can have multiple versions over time:

```
doc_v1 (import)     ← no parent
   ↑
doc_v2 (classify)   ← parent: doc_v1
   ↑
doc_v3 (reclassify) ← parent: doc_v2
```

Each version is immutable. New versions link back to their parent.

### 2.2 Versions share blobs

When only metadata changes, versions reference the same blob:

```
doc_v1: blob_hash=abc, metadata={import_path: "invoice.pdf"}
doc_v2: blob_hash=abc, metadata={import_path: "invoice.pdf", category: "finance"}
```

No storage duplication for metadata-only changes.

### 2.3 No forward links

Documents are immutable, so no forward pointers. Only backlinks (parent).

To find the latest version, query by document identity and follow the chain, or use state.db index.

### 2.4 Transforms are logged events

Transform operations are persisted in the log with full provenance.

## 3. Document Identity

### 3.1 Version identity

Each document version is identified by:
- `drop_id` (or `transform_id`) - which log entry contains it
- `import_path` - path within that entry

### 3.2 Document lineage

A document's lineage is the chain of versions connected by parent links.

The "canonical" document is typically the latest version in the chain.

## 4. Transform Event Format

### 4.1 Log entry structure

```
_log/NNNN_transform/
  header.json       # transform metadata
  entries.jsonl     # new document versions
```

Note: No `blobs/` directory - transforms reference existing blobs.

### 4.2 header.json

```json
{
  "transform_id": "t_20260401_143211_a7c3e9f1",
  "created_at": "2026-04-01T14:32:11.123456Z",
  "source": "set-metadata",
  "message": "Classify tax documents",
  "actor": "hhartmann"
}
```

### 4.3 entries.jsonl

Each line is a new document version:

```json
{
  "import_path": "invoice.pdf",
  "blob_hash": "blake3:abc123...",
  "blob_size": 102400,
  "parent": {
    "drop_id": "d_20260401_143211_a7c3e9f1",
    "import_path": "invoice.pdf"
  },
  "category": "finance",
  "archive_path": "finance/invoices/2025/invoice.pdf"
}
```

Fields:
- `import_path`: document path (may be same as parent or renamed)
- `blob_hash`, `blob_size`: same as parent (content unchanged)
- `parent`: pointer to previous version
- Additional fields: new/updated metadata

### 4.4 Metadata inheritance

New version inherits all metadata from parent, then applies updates:

```
parent:  {import_path: "x.pdf", blob_hash: "abc", type: "pdf"}
update:  {category: "finance"}
result:  {import_path: "x.pdf", blob_hash: "abc", type: "pdf", category: "finance"}
```

## 5. Transform Operations

Transforms operate at **drop level**, not document level.

### 5.1 set-metadata

Update metadata fields on documents in a drop.

```bash
filr transform set <drop-id> [--filter <pattern>] --field key=value [...] [-m message]
```

Examples:

```bash
# Set field on all documents in drop
filr transform set d_20260401_143211_a7c3e9f1 \
  --field category=finance \
  -m "Classify as finance"

# Set multiple fields
filr transform set d_20260401_143211_a7c3e9f1 \
  --field category=finance/taxes \
  --field year=2025 \
  -m "Tax documents 2025"

# Filter to specific documents
filr transform set d_20260401_143211_a7c3e9f1 \
  --filter "*.pdf" \
  --field type=pdf

# Set archive_path using template (future)
filr transform set d_20260401_143211_a7c3e9f1 \
  --field archive_path="{category}/{year}/{import_name}"
```

### 5.2 Future operations

Not in v1:
- `infer`: auto-derive metadata from content/rules
- `--filter`: select subset of documents
- Template expansion for field values

## 6. Resolving Documents

### 6.1 URL resolution

URLs resolve to the **specific version** in that entry. No forward resolution.

```
drop://d_20260401_.../invoice.pdf        # original version in drop
transform://t_20260401_.../invoice.pdf   # version in transform
```

`drop://` always returns the original import version. Documents are immutable with no forward links, so we cannot "follow" to later versions from a URL.

### 6.2 Querying latest version

To find the latest version of a document, query state.db by original identity:

```sql
SELECT * FROM document_versions
WHERE original_drop_id = ? AND original_import_path = ?
```

This returns the current (latest) version location and effective metadata.

### 6.3 state.db index

```sql
CREATE TABLE document_versions (
    -- Original identity (stable key)
    original_drop_id TEXT NOT NULL,
    original_import_path TEXT NOT NULL,

    -- Current version location
    current_entry_id TEXT NOT NULL,     -- drop_id or transform_id
    current_import_path TEXT NOT NULL,
    blob_hash TEXT NOT NULL,

    -- Effective metadata (JSON)
    metadata TEXT NOT NULL,

    -- Version tracking
    version_count INTEGER DEFAULT 1,

    PRIMARY KEY (original_drop_id, original_import_path)
);
```

Views use this index to find latest versions when materializing.

## 7. Workflow Example

```bash
# 1. Import raw documents
filr drop fs-import ~/Downloads/taxes -m "2025 tax docs"
# d_20260401_143211_a7c3e9f1

# 2. View drop contents
filr drop inspect d_20260401_143211_a7c3e9f1
# Documents: invoice.pdf, receipt.jpg, statement.pdf

# 3. View original document (no category yet)
filr document head drop://d_20260401_143211_a7c3e9f1/invoice.pdf
# import_path: invoice.pdf
# blob_hash: blake3:abc...

# 4. Transform entire drop: set metadata
filr transform set d_20260401_143211_a7c3e9f1 \
  --field category=finance/taxes \
  --field year=2025 \
  -m "Tax classification"
# t_20260401_150000_def456

# 5. View original (unchanged - URLs don't forward resolve)
filr document head drop://d_20260401_143211_a7c3e9f1/invoice.pdf
# import_path: invoice.pdf
# blob_hash: blake3:abc...
# (still no category - this is the original version)

# 6. View transformed version directly
filr document head transform://t_20260401_150000_def456/invoice.pdf
# import_path: invoice.pdf
# blob_hash: blake3:abc...
# category: finance/taxes
# year: 2025
# parent: drop://d_20260401_.../invoice.pdf

# 7. List transforms
filr transform list
# seq  transform_id                      message
# 2    t_20260401_150000_def456          Tax classification

# 8. Query latest version (via state.db, not URL)
filr document latest d_20260401_143211_a7c3e9f1/invoice.pdf
# current_entry: t_20260401_150000_def456
# metadata: {category: "finance/taxes", year: "2025", ...}
```

## 8. Log Structure

```
_log/
  0001_drop/              # import
    header.json
    entries.jsonl         # original documents
    blobs/
  0002_transform/         # classification
    header.json
    entries.jsonl         # new versions (no blobs/)
  0003_drop/              # another import
    header.json
    entries.jsonl
    blobs/
  0004_transform/         # more classification
    header.json
    entries.jsonl
```

Transforms don't have `blobs/` - they reference blobs from parent documents.

## 9. Integrity

### 9.1 Transform validation

When applying a transform:
1. Verify parent document exists
2. Verify blob_hash matches parent (content unchanged)
3. Write transform entry
4. Update state.db index

### 9.2 Rebuild

On rebuild:
1. Replay drops (create documents)
2. Replay transforms (create versions, link parents)
3. Build document_versions index

If transform references non-existent parent → error.

## 10. state.db Schema Updates

```sql
-- Track latest version of each document
CREATE TABLE document_versions (
    original_drop_id TEXT NOT NULL,
    original_import_path TEXT NOT NULL,
    current_entry_id TEXT NOT NULL,  -- drop_id or transform_id
    current_import_path TEXT NOT NULL,
    blob_hash TEXT NOT NULL,
    metadata TEXT NOT NULL,          -- JSON of effective metadata
    version_count INTEGER DEFAULT 1,
    PRIMARY KEY (original_drop_id, original_import_path)
);

-- Track all versions for history
CREATE TABLE document_history (
    entry_id TEXT NOT NULL,          -- drop_id or transform_id
    import_path TEXT NOT NULL,
    parent_entry_id TEXT,
    parent_import_path TEXT,
    seq INTEGER NOT NULL,
    PRIMARY KEY (entry_id, import_path)
);

-- Track transforms
CREATE TABLE transforms (
    transform_id TEXT PRIMARY KEY,
    seq INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    source TEXT NOT NULL,
    message TEXT,
    entry_count INTEGER
);
```

## 11. CLI Commands

### 11.1 Transform commands

```bash
# Set metadata on all docs in drop (creates new versions)
filr transform set <drop-id> --field key=value [...] [-m message]

# List transforms
filr transform list [--json]

# Inspect transform
filr transform inspect <transform-id> [--json]
```

### 11.2 View commands (fs-transform)

```bash
# Create view with archive_path prefix
filr fs-view create [--prefix <path-prefix>]
# Creates .filr-view.json in current directory

# Merge drop into view (sets archive_path = prefix + import_path)
filr drop merge <drop-id>
# Documents appear in filesystem, tracked in .filr-view.json

# Show what changed since last commit
filr fs-view status

# Commit changes as transform
filr fs-view commit [-m message]

# Discard view (no transform)
filr fs-view discard
```

### 11.3 Document queries

```bash
# Query latest version of a document
filr document latest <drop-id>/<import-path>
```

## 12. Triage Workflow

The core question: how do users classify documents quickly?

### 12.1 v1 Workflow (Batch-Only)

In v1, transforms apply to ALL documents in a drop. This works for homogeneous imports:

```bash
# Import all 2025 tax documents together
filr drop fs-import ~/Downloads/2025-taxes -m "2025 tax documents"
# d_20260401_143211_a7c3e9f1

# Classify the entire drop
filr transform set d_20260401_143211_a7c3e9f1 \
  --field category=finance/taxes \
  --field year=2025 \
  -m "Tax classification"
```

For mixed content, users must **pre-sort before import**:

```bash
# Import W2s separately
filr drop fs-import ~/Downloads/w2s -m "W2 forms"
filr transform set d_... --field category=finance/taxes/w2

# Import receipts separately
filr drop fs-import ~/Downloads/receipts -m "receipts"
filr transform set d_... --field category=finance/receipts
```

This shifts the burden to import time but keeps v1 simple.

### 12.2 v2 Workflow Options

For mixed-content drops, we need one of:

**Option A: Filter flag**
```bash
# Select subset by glob pattern
filr transform set d_... --filter "*.pdf" --field type=document
filr transform set d_... --filter "w2*" --field category=finance/taxes/w2
```

**Option B: Interactive TUI**
```bash
filr triage d_...
# Opens TUI showing documents
# User navigates with arrows, assigns categories with shortcuts
# [j/k] next/prev  [c] set category  [y] set year  [Enter] confirm
```

**Option C: Manifest file**
```bash
# Generate manifest with one line per document
filr transform manifest d_... > triage.jsonl

# User edits manifest (or external tool edits it)
# Each line: {"import_path": "...", "category": "...", "year": "..."}

# Apply manifest
filr transform apply d_... triage.jsonl -m "Triage complete"
```

**Option D: fs-view workflow**
```bash
# Create view with prefix context
mkdir Finance && cd Finance
filr fs-view create --prefix finance/
# Creates .filr-view.json

# Merge drops into view
filr drop merge d_20260401_...
# Documents appear: ./invoice.pdf, ./receipt.jpg, ./statement.pdf
# Each gets archive_path = "finance/" + import_path

# User organizes with Finder / mv / any tool
mkdir taxes && mv invoice.pdf taxes/
mkdir expenses && mv receipt.jpg expenses/

# Commit captures organization as transform
filr fs-view commit -m "Organized finance docs"
# invoice.pdf → taxes/invoice.pdf
# Creates transform: archive_path = "finance/taxes/invoice.pdf"
```

### 12.3 fs-view Design

The view workflow captures filesystem organization as metadata.

**View manifest** (`.filr-view.json`):
```json
{
  "prefix": "finance/",
  "created_at": "2026-04-01T15:00:00Z",
  "documents": [
    {"drop_id": "d_...", "import_path": "invoice.pdf", "blob_hash": "blake3:abc...", "view_path": "invoice.pdf"},
    {"drop_id": "d_...", "import_path": "receipt.jpg", "blob_hash": "blake3:def...", "view_path": "receipt.jpg"}
  ]
}
```

**Merge operation**:
1. Read drop entries
2. Copy blobs to view directory (using import_path as filename)
3. Add to .filr-view.json with `view_path = import_path`
4. Initial `archive_path = prefix + import_path`

**Commit algorithm**:
1. Read view manifest
2. Scan filesystem, build map: `blob_hash → current_path`
3. For each document:
   - Find where blob ended up (match by hash, not name)
   - Compute `archive_path = prefix + current_relative_path`
   - If changed from initial: include in transform
4. Generate transform with all changes

**Key design points**:

- **Prefix context**: `--prefix finance/` means all docs in this view get `archive_path` starting with `finance/`

- **Merge adds drops**: Multiple drops can be merged into one view. Each merge adds more documents.

- **Match by content**: Blobs matched by hash, so renames work correctly.

- **Working copy**: View is ephemeral. Transform is canonical. Discard view when done.

- **New files ignored**: Adding files to view doesn't import them. Use `filr drop fs-import`.

- **Deleted files**: Error by default, `--allow-missing` to skip.

**Example transform entries after commit**:
```json
{"import_path": "invoice.pdf", "blob_hash": "blake3:abc...",
 "parent": {"drop_id": "d_...", "import_path": "invoice.pdf"},
 "archive_path": "finance/taxes/invoice.pdf"}
{"import_path": "receipt.jpg", "blob_hash": "blake3:def...",
 "parent": {"drop_id": "d_...", "import_path": "receipt.jpg"},
 "archive_path": "finance/expenses/receipt.jpg"}
```

### 12.4 View implementation options

**v1: Explicit sync (simple)**
- View creates real files (copies)
- User makes changes in Finder/terminal
- `fs-view status` scans filesystem, detects changes
- `fs-view commit` creates transform
- Pro: Simple to implement
- Con: Requires manual status/commit

**v2: FSEvents/inotify (medium)**
- Background daemon watches view directory
- Changes tracked in real-time
- Commit bundles accumulated changes
- Pro: No manual scanning
- Con: Daemon complexity, edge cases

**v3: FUSE/NFS mount (seamless)**
- Virtual filesystem mounted at view path
- All operations intercepted and logged
- Unmount (or commit) creates transform
- Pro: Seamless Finder integration
- Con: FUSE complexity, macOS code signing

For v1, explicit sync is sufficient. Users run `fs-view status` to see changes, `fs-view commit` to record them.

### 12.5 Why fs-view is the right choice

- **Natural UX**: Users already know Finder/file managers
- **Visual**: See documents, preview content, drag-and-drop
- **Prefix context**: `--prefix finance/` establishes where docs belong
- **Merge model**: Explicitly add drops to view
- **Flexible**: Works with any tool (Finder, mv, scripts)
- **Composable**: View → external processing → commit

## 13. Summary

- Transforms create new document versions with updated metadata
- Versions are immutable with parent backlinks (no forward links)
- Blob storage is shared (no duplication for metadata changes)
- Transforms operate at drop level: `filr transform set <drop-id>`
- `drop://` URLs resolve to original version only (no forward resolution)
- state.db indexes latest versions for fast queries
- **Primary triage UX**: `filr fs-view create` → `drop merge` → organize in Finder → `fs-view commit`
- View prefix establishes `archive_path` context
- Blobs matched by hash, so renames/moves are tracked correctly
- v1: explicit sync; v2+: FSEvents or FUSE mount for seamless integration
