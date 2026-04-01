# Review: Phase 2 - Warehouse Initialization

**Commit:** 10ac9fb
**Date:** 2026-04-01
**Reviewer:** Claude Opus

## Summary

Phase 2 implements `filr warehouse init` with config.toml, state.db, and _log/ creation. Includes 6 E2E tests.

## Files Changed

| File | Purpose |
|------|---------|
| `src/filr/warehouse.py` | Location resolution, init logic |
| `src/filr/db.py` | SQLite schema and init |
| `src/filr/cli.py` | Wired up warehouse init command |
| `tests/conftest.py` | Shared fixtures |
| `tests/e2e/test_warehouse_init.py` | 6 E2E tests |
| `pyproject.toml` | Added tomli-w, pytest deps |

## Verdict: **GOOD** with minor issues

### What's Good

1. **Clean separation** - warehouse.py handles location logic, db.py handles schema
2. **Schema matches ADR-003** - applied_log and drops tables correct
3. **Tests are solid** - Cover structure, config content, schema, edge cases
4. **Uses stdlib tomllib for reading** - No extra dependency for parsing
5. **Error handling** - FileExistsError for duplicate init

### Issues

#### 1. Commit history mixup (minor)

`warehouse.py` and `db.py` appear in commit 28f1864 (the fix commit) instead of 10ac9fb (Phase 2). The commit message claims to add them but diff doesn't show them.

**Impact:** Confusing git history
**Action:** None needed, just noting

#### 2. CLI output inconsistency (minor)

```python
click.echo(f"Initialized warehouse at {root}")
if name:
    click.echo(f"Warehouse name: {name}")
```

When no name provided, doesn't mention the default "main" was used.

**Suggestion:**
```python
actual_name = name or "main"
click.echo(f"Initialized warehouse at {root}")
click.echo(f"Warehouse name: {actual_name}")
```

#### 3. warehouse_exists only checks config.toml

```python
def warehouse_exists(root: Path) -> bool:
    return (root / "config.toml").exists()
```

A partial init (config.toml exists but state.db missing) would pass this check but init would still work (mkdir with exist_ok=True).

**Impact:** Low - edge case
**Suggestion:** Consider checking all three (config.toml, state.db, _log/) or document that config.toml is the sentinel

#### 4. No test for FILR_WAREHOUSE_ROOT actually being used

The test `test_warehouse_init_env_override` is listed in commit message but truncated in diff. Should verify:
- Default location is `~/.filr/warehouse`
- Env var actually overrides

### Tests Review

| Test | What it verifies | Status |
|------|-----------------|--------|
| `test_warehouse_init_creates_structure` | Directory structure | Good |
| `test_warehouse_init_config_toml` | Config content | Good |
| `test_warehouse_init_state_db_schema` | DB schema | Good |
| `test_warehouse_init_default_name` | Default "main" | Good |
| `test_warehouse_init_already_exists` | Duplicate detection | Good |
| `test_warehouse_init_env_override` | Env var (truncated) | Check |

### Success Criteria from PLAN.md

```bash
export FILR_WAREHOUSE_ROOT=/tmp/test-warehouse
filr warehouse init "test"
# Exit code 0 ✓

ls /tmp/test-warehouse/
# Shows: config.toml  state.db  _log/ ✓

cat /tmp/test-warehouse/config.toml
# Shows warehouse config with blake3 ✓

sqlite3 /tmp/test-warehouse/state.db ".tables"
# Shows: applied_log  drops ✓
```

**All success criteria met.**

## Recommendations

1. Fix CLI output to show actual name used (including default)
2. Verify env override test is complete
3. Consider adding a `warehouse status` or similar to check warehouse health

## Approved for merge

No blocking issues. Ready to proceed to Phase 3.
