# Audit: Phase 5 & 7 - Stats, Log, Export

**Commits:** 5d37dea, d30311e, 6363d67
**Date:** 2026-04-01
**Auditor:** Claude Opus

## Summary

| Commit | Description | Tests |
|--------|-------------|-------|
| 5d37dea | Review feedback: hash_dict → hash_json | - |
| d30311e | Phase 5: Warehouse stats and log | +10 |
| 6363d67 | Phase 7: Drop export (CAS + fs) | +14 |

**Total tests: 49 passing**

## Critical Observation

**Phase 6 (rebuild & check) was skipped.**

PLAN.md specifies:
- Phase 5: warehouse stats, log
- Phase 6: warehouse rebuild, warehouse check
- (no Phase 7 defined)

The export functionality was labeled "Phase 7" but rebuild/check are missing. These are important for the durability promise.

## Phase 5 Audit: Stats & Log

### Implementation

**warehouse.py:**
- `get_stats()`: Queries state.db for aggregates, config.toml for metadata
- `get_log()`: Fetches applied_log entries in sequence order

**CLI:**
- `warehouse stats [--json]`: Shows root, name, counts, size
- `warehouse log [--json]`: Shows seq, entry_name, applied_at

### Verdict: Good

Clean implementation. Reads from state.db which is correct per design (state.db is the derived query layer).

## Phase 7 Audit: Export

### Implementation

**drop.py:**
- `export_drop()`: Copies header.json, entries.jsonl, blobs/ to target
- `fs_export_drop()`: Same + reconstructs root/ tree from import_path

### Code Quality

```python
# export_drop - simple and correct
shutil.copy2(log_location / "header.json", target_folder / "header.json")
shutil.copy2(log_location / "entries.jsonl", target_folder / "entries.jsonl")
shutil.copytree(source_blobs, target_blobs)
```

```python
# fs_export_drop - reconstructs tree
for line in f:
    entry = json.loads(line)
    import_path = entry["import_path"]
    target_file = root_dir / import_path
    target_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(blob_path, target_file)
```

### Test Coverage (Excellent)

14 tests with comprehensive roundtrip validation:

| Test | What it verifies |
|------|-----------------|
| CAS structure | header, entries, blobs exist |
| CAS blob content | byte-for-byte match with originals |
| CAS metadata | header fields preserved |
| FS structure | root/ tree exists |
| FS tree matches | directory tree identical to original |
| Single file | works with single files |
| Roundtrip reimport | import → export → reimport = same hashes |
| Nested directories | a/b/c/file.txt works |
| Empty files | 0-byte files handled |
| Special filenames | spaces, dashes, underscores |
| Large scale | 50 files across 10 directories |
| Error: drop not found | proper error handling |
| Error: target exists | prevents overwrite |

### Verdict: Excellent

The roundtrip tests are particularly valuable. They validate data integrity through the full cycle.

## Issues Found

### 1. Phase 6 Missing (Important)

`warehouse rebuild` and `warehouse check` are not implemented. Per ADR-003:

> `filr warehouse rebuild` must:
> 1. Read config.toml for hash algorithm
> 2. Replay _log/*.jsonl in sequence order
> 3. Rebuild state.db from the replayed state

This is important for the durability promise. If state.db gets corrupted, users can't recover.

**Status:** Must implement before v1 release

### 2. Review feedback addressed (Good)

Commit 5d37dea properly addressed the `hash_dict` naming issue:
- Renamed to `hash_json`
- Added type hint `dict | list`
- Kept `hash_dict` as deprecated alias

### 3. No fsync in export (Low risk)

Same pattern as import - no explicit fsync before completion. Low risk for export since it's not the source of truth.

### 4. MD5 used in tests (Fine)

Tests use MD5 for comparison. This is fine for testing (not security), but slightly inconsistent with using blake3 in production code.

## Test Run

```bash
$ pytest tests/ -v
============================== 49 passed in 0.60s ==============================
```

All tests pass.

## Recommendations

1. **Implement Phase 6 (rebuild & check)** before declaring v1 complete
2. Consider adding integration test that corrupts state.db then rebuilds
3. Add test that verifies `fs-import` → `fs-export` → `fs-import` produces identical drops

## Summary

| Phase | Status | Quality |
|-------|--------|---------|
| 5 (stats/log) | Complete | Good |
| 6 (rebuild/check) | **MISSING** | - |
| 7 (export) | Complete | Excellent |

**Overall: Good implementation, but Phase 6 is blocking for v1.**
