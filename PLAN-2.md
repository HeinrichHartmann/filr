# filr v1 Implementation Plan (Part 2)

Continuation of PLAN.md. Document commands and release prep.

## Phase 8: Document Commands

**Goal:** `filr document head/body/show` resolve drop:// URLs and output document content.

**Tasks:**
1. Create `src/filr/document.py` with URL parsing and resolution
2. Implement `parse_drop_url()` to extract drop_id and path
3. Implement `resolve_document()` to find document in drop
4. Wire up CLI commands

### 8.1 URL Parsing

Parse `drop://<drop-id>/<import-path>` URLs.

```python
def parse_drop_url(url: str) -> tuple[str, str]:
    """Parse drop:// URL into (drop_id, import_path)."""
    # drop://d_20260401_143211_a7c3e9f1/path/to/file.pdf
    # Returns: ("d_20260401_143211_a7c3e9f1", "path/to/file.pdf")
```

### 8.2 Document Resolution

Find document entry and blob in warehouse.

```python
def resolve_document(warehouse_root: Path, drop_id: str, import_path: str) -> dict:
    """Resolve document from drop.

    Returns:
        dict with: import_path, import_name, blob_hash, blob_size,
                   blob_path (absolute), drop_header
    """
```

### 8.3 CLI Commands

**`filr document head <drop-url> [--json]`**

Show document metadata.

```bash
filr document head drop://d_20260401_143211_a7c3e9f1/invoice.pdf
# Output:
# Import path:  invoice.pdf
# Blob hash:    blake3:a7c3e9f1...
# Blob size:    102400
# Drop ID:      d_20260401_143211_a7c3e9f1
# Drop message: Tax documents

filr document head drop://d_20260401_143211_a7c3e9f1/invoice.pdf --json
# {"import_path": "invoice.pdf", "blob_hash": "blake3:...", ...}
```

**`filr document body <drop-url>`**

Output raw blob bytes to stdout.

```bash
filr document body drop://d_20260401_143211_a7c3e9f1/invoice.pdf > restored.pdf
# Raw bytes written to stdout (no newline, no formatting)
```

**`filr document show <drop-url>`**

Show metadata + content preview.

```bash
filr document show drop://d_20260401_143211_a7c3e9f1/readme.txt
# --- Metadata ---
# Import path: readme.txt
# Blob size:   1234
#
# --- Content ---
# This is the file content...
# (truncated if binary or too long)
```

**Success criteria:**
```bash
# Setup
filr warehouse init
filr drop fs-import ~/test -m "test"
# Outputs: d_20260401_HHMMSS_XXXXXXXX

# Test head
filr document head drop://d_20260401_HHMMSS_XXXXXXXX/file.txt
# Shows metadata

filr document head drop://d_20260401_HHMMSS_XXXXXXXX/file.txt --json
# Shows JSON

# Test body (roundtrip)
filr document body drop://d_20260401_HHMMSS_XXXXXXXX/file.txt > /tmp/restored.txt
diff ~/test/file.txt /tmp/restored.txt
# No diff = identical

# Test show
filr document show drop://d_20260401_HHMMSS_XXXXXXXX/file.txt
# Shows metadata + content

# Error cases
filr document head drop://invalid/path
# Error: Drop not found

filr document head drop://d_20260401_HHMMSS_XXXXXXXX/nonexistent.txt
# Error: Document not found in drop
```

## Phase 9: README and Release Prep

**Goal:** Documentation and cleanup for v1 release.

**Tasks:**
1. Write README.md with:
   - Overview / what filr is
   - Installation
   - Quick start example
   - Command reference
   - Design principles (link to ADRs)
2. Verify all commands work end-to-end
3. Clean up any TODOs in code
4. Tag v0.1.0

**Success criteria:**
```bash
# Fresh install works
uv pip install .
filr --version
# 0.1.0

# README quick start works as documented
```

## Test Plan for Phase 8

```python
# tests/e2e/test_document.py

def test_document_head_basic(cli_runner, tmp_warehouse, sample_files):
    """Test document head shows metadata."""

def test_document_head_json(cli_runner, tmp_warehouse, sample_files):
    """Test document head --json output."""

def test_document_body_roundtrip(cli_runner, tmp_warehouse, sample_files):
    """Test document body outputs identical bytes."""

def test_document_body_binary(cli_runner, tmp_warehouse):
    """Test document body works with binary files."""

def test_document_show_text(cli_runner, tmp_warehouse, sample_files):
    """Test document show displays text content."""

def test_document_show_binary(cli_runner, tmp_warehouse):
    """Test document show handles binary gracefully."""

def test_document_invalid_url(cli_runner, tmp_warehouse):
    """Test error on malformed drop:// URL."""

def test_document_drop_not_found(cli_runner, tmp_warehouse):
    """Test error when drop doesn't exist."""

def test_document_path_not_found(cli_runner, tmp_warehouse, sample_files):
    """Test error when path doesn't exist in drop."""
```

## File Structure After Phase 8

```
src/filr/
  __init__.py
  cli.py          # All commands wired up
  warehouse.py    # Warehouse operations
  drop.py         # Drop operations
  document.py     # NEW: Document resolution
  hash.py         # Hashing utilities
  db.py           # SQLite operations
```
