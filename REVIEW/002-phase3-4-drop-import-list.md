# Review: Phase 3 & 4 - Drop Import, List, Inspect

**Commits:** ca54d4a (Phase 3), 94ea286 (Phase 4)
**Date:** 2026-04-01
**Reviewer:** Claude Opus

## Summary

Phase 3 implements the core `fs-import` pipeline with Merkle-tree integrity hashing and atomic writes.
Phase 4 adds `drop list` and `drop inspect` commands.

Combined: 19 new E2E tests, all passing.

## Files Changed

| File | Lines | Purpose |
|------|-------|---------|
| `src/filr/hash.py` | 85 | blake3 hashing utilities |
| `src/filr/drop.py` | 397 | Import, list, inspect logic |
| `src/filr/cli.py` | +97 | Wired up commands |
| `tests/e2e/test_drop_fs_import.py` | 226 | 9 import tests |
| `tests/e2e/test_drop_list_inspect.py` | 184 | 10 list/inspect tests |

## Verdict: **GOOD** - Solid implementation

### What's Good

**hash.py:**
- Chunked file reading (64KB) for large files
- Canonical JSON serialization (sorted keys, no whitespace)
- Clean parse_hash/verify_hash utilities

**drop.py:**
- Follows ADR-003 workflow exactly
- Merkle-tree style integrity hash
- Atomic write: temp folder → rename
- SQLite locking via `BEGIN EXCLUSIVE`
- `sorted(source_path.rglob("*"))` ensures deterministic ordering
- Proper separation: state.db for queries, _log for source of truth

**CLI:**
- Human-readable table with size formatting (B/KB/MB)
- JSON output for scripting
- Validates warehouse exists before operations
- Shows helpful "Run 'filr warehouse init' first" message

**Tests:**
- Comprehensive coverage of happy path and edge cases
- Windows path handling (`subdir/nested.txt` or `subdir\\nested.txt`)
- Tests both human and JSON output formats

### Issues

#### 1. `hash_dict` used on a list (minor)

```python
# drop.py:54
entries_hash = h.hash_dict(entries)  # entries is a list
```

Works correctly (json.dumps handles lists), but function name is misleading.

**Suggestion:** Rename to `hash_json` or add `hash_list` function.

#### 2. No explicit fsync before rename (low risk)

```python
# Write files...
temp_dir.rename(final_dir)  # Atomic, but are writes flushed?
```

On most filesystems, rename is atomic but doesn't guarantee prior writes are persisted. A crash between write and rename could leave partial data.

**Impact:** Low - SQLite would detect missing log entry on rebuild
**Suggestion:** Add `os.fsync()` on files before rename for extra safety (optional)

#### 3. Broad exception handling

```python
except Exception as e:
    click.echo(f"Error: {e}", err=True)
    sys.exit(1)
```

Catches all exceptions including KeyboardInterrupt, SystemExit.

**Suggestion:** Catch specific exceptions or use `except Exception as e:` only after more specific handlers.

#### 4. entries.jsonl not sorted by import_path

The entries are written in `sorted(rglob())` order, which is filesystem order (usually alphabetical). This is fine, but ADR-003 doesn't specify ordering. Consider documenting this.

### Test Coverage

| Area | Tests | Status |
|------|-------|--------|
| Log structure creation | 1 | Good |
| Header content | 1 | Good |
| Entries content | 1 | Good |
| Blob storage | 1 | Good |
| state.db updates | 1 | Good |
| Drop ID format | 1 | Good |
| Multiple imports | 1 | Good |
| Single file import | 1 | Good |
| Missing warehouse error | 1 | Good |
| Empty warehouse list | 1 | Good |
| List human output | 1 | Good |
| List JSON output | 1 | Good |
| Multiple drops ordering | 1 | Good |
| Inspect basic | 1 | Good |
| Inspect JSON | 1 | Good |
| Inspect missing drop | 1 | Good |
| Inspect missing warehouse | 1 | Good |
| Document count verification | 1 | Good |

### Success Criteria from PLAN.md

**Phase 3:**
```bash
filr drop fs-import /tmp/testdata -m "Test import"
# Prints: d_20260401_HHMMSS_XXXXXXXX ✓

ls ~/.filr/warehouse/_log/0001_drop/
# Shows: header.json  entries.jsonl  blobs/ ✓

cat header.json  # Shows correct metadata ✓
cat entries.jsonl  # Shows 2 lines ✓
ls blobs/  # Shows 2 hash-named files ✓
```

**Phase 4:**
```bash
filr drop list
# Shows table with drop_id, created_at, message, doc_count ✓

filr drop list --json
# Shows JSON array ✓

filr drop inspect <drop_id>
# Shows detailed info ✓
```

**All success criteria met.**

## Minor Suggestions

1. Add `hash_json()` or rename `hash_dict()` to avoid confusion
2. Consider adding fsync for extra durability (optional)
3. Document entries ordering in ADR-003

## Approved for merge

No blocking issues. Ready to proceed to Phase 5 & 6.
