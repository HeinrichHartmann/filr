# filr v1 Implementation Plan

This plan covers the minimal viable implementation. Each phase has explicit success criteria.

## Phase 1: Project Setup

**Goal:** Runnable CLI skeleton with `filr --help` working.

**Tasks:**
1. Update `pyproject.toml` with dependencies (click, blake3)
2. Create package structure: `src/filr/`
3. Create `src/filr/cli.py` with click entry point
4. Create `src/filr/__init__.py`
5. Wire up entry point in pyproject.toml

**Success criteria:**
```bash
uv pip install -e .
filr --help
# Shows: Usage: filr [OPTIONS] COMMAND [ARGS]...
# Shows: Commands: warehouse, drop, document
```

## Phase 2: Warehouse Init

**Goal:** `filr warehouse init` creates warehouse structure.

**Tasks:**
1. Create `src/filr/warehouse.py` with warehouse location logic
2. Implement `FILR_WAREHOUSE_ROOT` env var support
3. Default to `~/.filr/warehouse`
4. Create `warehouse init` command that:
   - Creates warehouse directory
   - Creates `config.toml` with name, created_at, hash algorithm
   - Creates empty `_log/` directory
   - Creates empty `state.db` with schema

**Success criteria:**
```bash
export FILR_WAREHOUSE_ROOT=/tmp/test-warehouse
filr warehouse init "test"
# Exit code 0

ls /tmp/test-warehouse/
# Shows: config.toml  state.db  _log/

cat /tmp/test-warehouse/config.toml
# Shows: [warehouse]
#        name = "test"
#        created_at = "..."
#        [hash]
#        algorithm = "blake3"

sqlite3 /tmp/test-warehouse/state.db ".tables"
# Shows: applied_log  drops
```

## Phase 3: Drop fs-import (Core)

**Goal:** `filr drop fs-import` creates a drop in the log.

**Tasks:**
1. Create `src/filr/drop.py` with drop logic
2. Create `src/filr/hash.py` with blake3 hashing
3. Implement fs-import:
   - Acquire lock on state.db
   - Scan source directory, compute blob hashes
   - Allocate next sequence number
   - Compute drop integrity hash
   - Generate drop_id
   - Write to temp folder `_log/_tmp_NNNN_drop/`
   - Write `header.json`, `entries.jsonl`, copy blobs
   - Rename to `_log/NNNN_drop/`
   - Update state.db (applied_log, drops)
   - Print drop_id

**Success criteria:**
```bash
# Setup
mkdir -p /tmp/testdata
echo "hello" > /tmp/testdata/file1.txt
echo "world" > /tmp/testdata/sub/file2.txt

# Import
filr drop fs-import /tmp/testdata -m "Test import"
# Prints: d_20260401_HHMMSS_XXXXXXXX

# Verify log structure
ls ~/.filr/warehouse/_log/
# Shows: 0001_drop/

ls ~/.filr/warehouse/_log/0001_drop/
# Shows: header.json  entries.jsonl  blobs/

cat ~/.filr/warehouse/_log/0001_drop/header.json
# Shows JSON with: drop_id, created_at, source="fs-import", message="Test import"

cat ~/.filr/warehouse/_log/0001_drop/entries.jsonl
# Shows 2 lines, each with: import_path, import_name, blob_hash, blob_size

ls ~/.filr/warehouse/_log/0001_drop/blobs/
# Shows 2 files named by hash

# Verify state.db updated
sqlite3 ~/.filr/warehouse/state.db "SELECT * FROM drops"
# Shows 1 row with drop_id
```

## Phase 4: Drop List & Inspect

**Goal:** `filr drop list` and `filr drop inspect` work.

**Tasks:**
1. Implement `drop list` reading from state.db
2. Implement `drop inspect` reading drop header + computing stats
3. Add `--json` flag to both

**Success criteria:**
```bash
filr drop list
# Shows table with: drop_id, created_at, message, doc_count

filr drop list --json
# Shows JSON array

filr drop inspect d_20260401_HHMMSS_XXXXXXXX
# Shows: drop_id, created_at, message, document_count, total_bytes

filr drop inspect d_20260401_HHMMSS_XXXXXXXX --json
# Shows JSON object
```

## Phase 5: Warehouse Stats & Log

**Goal:** `filr warehouse stats` and `filr warehouse log` work.

**Tasks:**
1. Implement `warehouse stats` aggregating from state.db
2. Implement `warehouse log` showing applied_log entries
3. Add `--json` flag to both

**Success criteria:**
```bash
filr warehouse stats
# Shows: warehouse root, name, drop count, document count, total size

filr warehouse log
# Shows: seq, entry_name, applied_at for each log entry
```

## Phase 6: Warehouse Rebuild & Check

**Goal:** `filr warehouse rebuild` and `filr warehouse check` work.

**Tasks:**
1. Implement `warehouse rebuild`:
   - Delete state.db
   - Recreate with schema
   - Enumerate `_log/` in order
   - Parse each drop, verify integrity, insert into state.db
2. Implement `warehouse check`:
   - Verify no sequence gaps
   - For each drop: verify header, entries, blob hashes
   - Verify state.db matches log

**Success criteria:**
```bash
# Rebuild test
rm ~/.filr/warehouse/state.db
filr warehouse rebuild
# Exit code 0
filr drop list
# Shows same drops as before

# Check test (clean)
filr warehouse check
# Exit code 0, prints "OK" or similar

# Check test (corrupted)
echo "corrupt" > ~/.filr/warehouse/_log/0001_drop/blobs/SOMEHASH
filr warehouse check
# Exit code 1, prints error about hash mismatch
```

## Not in Initial Implementation

These are explicitly deferred:
- `drop fs-export` and `drop export`
- `document head`, `document body`, `document show`
- Complex error handling
- Progress bars for large imports

## Implementation Notes

**For the implementer:**

1. Use `click` for CLI with command groups
2. Use `blake3` library for hashing
3. Use `sqlite3` stdlib for state.db
4. Use `json` stdlib for header.json
5. Use `pathlib` throughout
6. Keep functions small and testable
7. Write E2E tests as you go (see ADR-004)

**File structure:**
```
src/filr/
  __init__.py
  cli.py          # Click commands
  warehouse.py    # Warehouse operations
  drop.py         # Drop operations
  hash.py         # Hashing utilities
  db.py           # SQLite operations
```

**Order of implementation:**
1. Phase 1 → Phase 2 → Phase 3 → run manual tests
2. Phase 4 → Phase 5 → run manual tests
3. Phase 6 → comprehensive testing
