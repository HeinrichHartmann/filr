# filr Testing Strategy

**Status:** Accepted
**Date:** 2026-04-01

## 1. Context

filr makes strong promises: durability, provenance, rebuildability, integrity. We need a testing strategy that verifies these promises hold, not just that code runs.

Testing should:
1. Verify the product works as advertised
2. Ensure CLI structure matches ADR-002 specification
3. Catch regressions in core algorithms (hashing, integrity)
4. Be maintainable and not overly coupled to implementation

## 2. Decision

We use **pytest** with three tiers of tests.

### Tier 1: End-to-End Workflow Tests (Backbone)

These are the most important tests. They exercise natural user flows and verify the properties we advertise.

**Characteristics:**
- Test complete workflows, not individual functions
- Use the CLI as entry point
- Create real temporary warehouses
- Verify observable outcomes

**Core test cases:**

```python
def test_import_export_roundtrip(tmp_warehouse, sample_files):
    """Import files, export by drop_id, verify identical content."""
    result = run_cli(["drop", "fs-import", sample_files, "-m", "test"])
    drop_id = extract_drop_id(result.output)

    run_cli(["drop", "fs-export", drop_id, "restored/"])

    assert files_identical(sample_files, "restored/root/")

def test_cas_export_roundtrip(tmp_warehouse, sample_files):
    """Import, CAS export, verify canonical structure."""
    result = run_cli(["drop", "fs-import", sample_files, "-m", "test"])
    drop_id = extract_drop_id(result.output)

    run_cli(["drop", "export", drop_id, "exported/"])

    assert Path("exported/header.json").exists()
    assert Path("exported/entries.jsonl").exists()
    assert Path("exported/blobs").is_dir()

def test_rebuild_from_log(tmp_warehouse, sample_files):
    """Delete state.db, rebuild, verify consistency."""
    run_cli(["drop", "fs-import", sample_files, "-m", "test"])

    # Nuke derived state
    Path("state.db").unlink()

    # Rebuild
    run_cli(["warehouse", "rebuild"])

    # Verify
    result = run_cli(["warehouse", "check"])
    assert result.exit_code == 0

def test_integrity_check_detects_corruption(tmp_warehouse, sample_files):
    """Corrupt a blob, verify check fails."""
    result = run_cli(["drop", "fs-import", sample_files, "-m", "test"])
    drop_id = extract_drop_id(result.output)

    # Corrupt a blob
    blob_files = list(Path("_log/0001_drop/blobs").iterdir())
    blob_files[0].write_bytes(b"corrupted")

    # Check should fail
    result = run_cli(["warehouse", "check"])
    assert result.exit_code != 0
    assert "integrity" in result.output.lower() or "mismatch" in result.output.lower()

def test_document_inspection(tmp_warehouse, sample_files):
    """Import, inspect document via drop:// URL."""
    result = run_cli(["drop", "fs-import", sample_files, "-m", "test"])
    drop_id = extract_drop_id(result.output)

    # Get document metadata
    url = f"drop://{drop_id}/sample.txt"
    result = run_cli(["document", "head", url, "--json"])
    assert result.exit_code == 0

    meta = json.loads(result.output)
    assert "blob_hash" in meta
    assert "import_path" in meta

def test_drop_list_and_inspect(tmp_warehouse, sample_files):
    """Import multiple drops, list them, inspect one."""
    run_cli(["drop", "fs-import", sample_files, "-m", "first"])
    run_cli(["drop", "fs-import", sample_files, "-m", "second"])

    result = run_cli(["drop", "list", "--json"])
    drops = json.loads(result.output)
    assert len(drops) == 2

    result = run_cli(["drop", "inspect", drops[0]["drop_id"], "--json"])
    assert result.exit_code == 0
```

**Coverage targets:**
- Import → log entry created with blobs
- fs-export → reconstructs original tree
- export → produces canonical CAS structure
- rebuild → state.db recreated from log
- check → detects corruption
- document commands → resolve drop:// URLs

### Tier 2: CLI Structure Tests

Ensure all advertised commands exist with correct arguments.

**Generated from ADR-002 spec:**

```python
CLI_SPEC = {
    "warehouse init": {"args": ["name?"]},
    "warehouse stats": {"options": ["--json"]},
    "warehouse check": {"options": ["--json"]},
    "warehouse log": {"options": ["--json"]},
    "warehouse rebuild": {},
    "drop list": {"options": ["--json"]},
    "drop inspect": {"args": ["drop-id"], "options": ["--json"]},
    "drop fs-import": {"args": ["path"], "options": ["-m", "-h"]},
    "drop fs-export": {"args": ["drop-id", "folder"]},
    "drop export": {"args": ["drop-id", "folder"]},
    "document head": {"args": ["drop-url"], "options": ["--json"]},
    "document body": {"args": ["drop-url"]},
    "document show": {"args": ["drop-url"]},
}

@pytest.mark.parametrize("command,spec", CLI_SPEC.items())
def test_command_exists(command, spec):
    """Command exists and --help works."""
    result = run_cli(command.split() + ["--help"])
    assert result.exit_code == 0
```

### Tier 3: Unit Tests (Sparingly)

Only for isolated algorithms where correctness matters.

**Candidates:**
- `compute_hash()` — blake3 computation
- `compute_drop_hash()` — Merkle tree integrity hash
- `parse_drop_id()` — ID format parsing
- `parse_drop_url()` — drop:// URL parsing

```python
def test_compute_hash():
    assert compute_hash(b"hello").startswith("blake3:")

def test_drop_id_format():
    drop_id = "d_20260401_143211_a7c3e9f1"
    parsed = parse_drop_id(drop_id)
    assert parsed.date == "20260401"
    assert parsed.time == "143211"
    assert parsed.hash == "a7c3e9f1"

def test_drop_url_parsing():
    url = "drop://d_20260401_143211_a7c3e9f1/path/to/file.pdf"
    parsed = parse_drop_url(url)
    assert parsed.drop_id == "d_20260401_143211_a7c3e9f1"
    assert parsed.path == "path/to/file.pdf"

def test_merkle_hash_deterministic():
    """Same inputs produce same hash."""
    blobs = [b"content1", b"content2"]
    hash1 = compute_drop_hash(header={}, entries=[], blob_hashes=[compute_hash(b) for b in blobs])
    hash2 = compute_drop_hash(header={}, entries=[], blob_hashes=[compute_hash(b) for b in blobs])
    assert hash1 == hash2
```

## 3. Test Infrastructure

### Fixtures

```python
@pytest.fixture
def tmp_warehouse(tmp_path, monkeypatch):
    """Create a temporary warehouse for testing."""
    monkeypatch.setenv("FILR_WAREHOUSE_ROOT", str(tmp_path / "warehouse"))
    run_cli(["warehouse", "init"])
    yield tmp_path / "warehouse"

@pytest.fixture
def sample_files(tmp_path):
    """Create sample test files."""
    data = tmp_path / "data"
    data.mkdir()
    (data / "sample.txt").write_text("hello world")
    (data / "subdir").mkdir()
    (data / "subdir/nested.txt").write_text("nested content")
    return data
```

### Helpers

```python
def run_cli(args: list[str]) -> Result:
    """Run filr CLI and return result."""
    from click.testing import CliRunner
    from filr.cli import main
    runner = CliRunner()
    return runner.invoke(main, args)

def extract_drop_id(output: str) -> str:
    """Extract drop_id from CLI output."""
    import re
    match = re.search(r'd_\d{8}_\d{6}_[a-f0-9]{8}', output)
    return match.group(0) if match else None

def files_identical(dir1: Path, dir2: Path) -> bool:
    """Check two directories have identical file content."""
    ...
```

## 4. Directory Structure

```
tests/
├── conftest.py              # Shared fixtures
├── e2e/                     # Tier 1: End-to-end workflow tests
│   ├── test_import_export.py
│   ├── test_rebuild.py
│   ├── test_integrity.py
│   └── test_document.py
├── cli/                     # Tier 2: CLI structure tests
│   └── test_cli_structure.py
├── unit/                    # Tier 3: Unit tests
│   ├── test_hash.py
│   └── test_parsing.py
└── testdata/                # Sample files for testing
    └── ...
```

## 5. Running Tests

```bash
# All tests
pytest

# Just E2E (slower, thorough)
pytest tests/e2e/

# Just CLI structure (fast)
pytest tests/cli/

# Just unit (fast)
pytest tests/unit/

# With coverage
pytest --cov=filr
```

## 6. Trade-offs

We prefer fewer, higher-confidence tests over many fragile unit tests.

An E2E test that verifies "import then rebuild then export produces identical files" is worth more than 20 unit tests of internal functions.

The state.db intentionally has no document index, so we don't test document queries — that's not a v1 feature.
