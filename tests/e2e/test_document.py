"""End-to-end tests for document commands."""

import json

from filr.cli import main


def test_document_head_basic(cli_runner, tmp_warehouse, sample_files):
    """Test document head shows metadata."""
    cli_runner.invoke(main, ["warehouse", "init"])
    result_import = cli_runner.invoke(
        main, ["drop", "fs-import", str(sample_files), "-m", "test drop"]
    )
    drop_id = result_import.output.strip()

    # Find a document in the drop
    log_dir = tmp_warehouse / "_log" / "0001_drop"
    entries_path = log_dir / "entries.jsonl"
    with open(entries_path) as f:
        first_entry = json.loads(f.readline())
        import_path = first_entry["import_path"]

    # Test document head
    drop_url = f"drop://{drop_id}/{import_path}"
    result = cli_runner.invoke(main, ["document", "head", drop_url])

    assert result.exit_code == 0
    assert "Import path:" in result.output
    assert "Blob hash:" in result.output
    assert "Blob size:" in result.output
    assert "Drop ID:" in result.output
    assert drop_id in result.output
    assert "test drop" in result.output


def test_document_head_json(cli_runner, tmp_warehouse, sample_files):
    """Test document head --json output."""
    cli_runner.invoke(main, ["warehouse", "init"])
    result_import = cli_runner.invoke(main, ["drop", "fs-import", str(sample_files)])
    drop_id = result_import.output.strip()

    # Find a document
    log_dir = tmp_warehouse / "_log" / "0001_drop"
    entries_path = log_dir / "entries.jsonl"
    with open(entries_path) as f:
        first_entry = json.loads(f.readline())
        import_path = first_entry["import_path"]

    # Test JSON output
    drop_url = f"drop://{drop_id}/{import_path}"
    result = cli_runner.invoke(main, ["document", "head", drop_url, "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["import_path"] == import_path
    assert "blob_hash" in data
    assert "blob_size" in data
    assert data["drop_id"] == drop_id


def test_document_body_roundtrip(cli_runner, tmp_warehouse, sample_files, tmp_path):
    """Test document body outputs identical bytes."""
    cli_runner.invoke(main, ["warehouse", "init"])
    result_import = cli_runner.invoke(main, ["drop", "fs-import", str(sample_files)])
    drop_id = result_import.output.strip()

    # Find a document
    log_dir = tmp_warehouse / "_log" / "0001_drop"
    entries_path = log_dir / "entries.jsonl"
    with open(entries_path) as f:
        first_entry = json.loads(f.readline())
        import_path = first_entry["import_path"]

    # Original file
    original_file = sample_files / import_path

    # Extract with document body
    drop_url = f"drop://{drop_id}/{import_path}"
    result = cli_runner.invoke(main, ["document", "body", drop_url])

    assert result.exit_code == 0

    # Compare bytes
    original_bytes = original_file.read_bytes()
    extracted_bytes = result.output_bytes

    assert extracted_bytes == original_bytes


def test_document_body_binary(cli_runner, tmp_warehouse, tmp_path):
    """Test document body works with binary files."""
    cli_runner.invoke(main, ["warehouse", "init"])

    # Create binary file with null bytes
    binary_file = tmp_path / "binary.dat"
    binary_content = b"\x00\x01\x02\x03\xff\xfe\xfd"
    binary_file.write_bytes(binary_content)

    result_import = cli_runner.invoke(main, ["drop", "fs-import", str(binary_file)])
    drop_id = result_import.output.strip()

    # Extract with document body
    drop_url = f"drop://{drop_id}/binary.dat"
    result = cli_runner.invoke(main, ["document", "body", drop_url])

    assert result.exit_code == 0
    assert result.output_bytes == binary_content


def test_document_show_text(cli_runner, tmp_warehouse, tmp_path):
    """Test document show displays text content."""
    cli_runner.invoke(main, ["warehouse", "init"])

    # Create text file
    text_file = tmp_path / "readme.txt"
    text_content = "This is a test file.\nWith multiple lines.\n"
    text_file.write_text(text_content)

    result_import = cli_runner.invoke(main, ["drop", "fs-import", str(text_file)])
    drop_id = result_import.output.strip()

    # Show document
    drop_url = f"drop://{drop_id}/readme.txt"
    result = cli_runner.invoke(main, ["document", "show", drop_url])

    assert result.exit_code == 0
    assert "--- Metadata ---" in result.output
    assert "Import path: readme.txt" in result.output
    assert "--- Content ---" in result.output
    assert "This is a test file" in result.output
    assert "With multiple lines" in result.output


def test_document_show_binary(cli_runner, tmp_warehouse, tmp_path):
    """Test document show handles binary gracefully."""
    cli_runner.invoke(main, ["warehouse", "init"])

    # Create binary file with null bytes
    binary_file = tmp_path / "binary.dat"
    binary_file.write_bytes(b"\x00\x01\x02\x03\xff\xfe\xfd")

    result_import = cli_runner.invoke(main, ["drop", "fs-import", str(binary_file)])
    drop_id = result_import.output.strip()

    # Show document
    drop_url = f"drop://{drop_id}/binary.dat"
    result = cli_runner.invoke(main, ["document", "show", drop_url])

    assert result.exit_code == 0
    assert "--- Metadata ---" in result.output
    assert "--- Content ---" in result.output
    assert "(Binary content - use 'document body' to extract)" in result.output


def test_document_invalid_url(cli_runner, tmp_warehouse):
    """Test error on malformed drop:// URL."""
    cli_runner.invoke(main, ["warehouse", "init"])

    # Test various invalid URLs
    result1 = cli_runner.invoke(main, ["document", "head", "invalid://url"])
    assert result1.exit_code != 0
    assert "Error" in result1.output or "Invalid" in result1.output

    result2 = cli_runner.invoke(main, ["document", "head", "drop://"])
    assert result2.exit_code != 0
    assert "Error" in result2.output or "Invalid" in result2.output

    result3 = cli_runner.invoke(main, ["document", "head", "drop://drop_id_only"])
    assert result3.exit_code != 0
    assert "Error" in result3.output or "Invalid" in result3.output


def test_document_drop_not_found(cli_runner, tmp_warehouse):
    """Test error when drop doesn't exist."""
    cli_runner.invoke(main, ["warehouse", "init"])

    # Non-existent drop
    drop_url = "drop://d_20260401_000000_ffffffff/file.txt"
    result = cli_runner.invoke(main, ["document", "head", drop_url])

    assert result.exit_code != 0
    assert "Error" in result.output
    assert "not found" in result.output.lower()


def test_document_path_not_found(cli_runner, tmp_warehouse, sample_files):
    """Test error when path doesn't exist in drop."""
    cli_runner.invoke(main, ["warehouse", "init"])
    result_import = cli_runner.invoke(main, ["drop", "fs-import", str(sample_files)])
    drop_id = result_import.output.strip()

    # Non-existent path in valid drop
    drop_url = f"drop://{drop_id}/nonexistent_file.txt"
    result = cli_runner.invoke(main, ["document", "head", drop_url])

    assert result.exit_code != 0
    assert "Error" in result.output
    assert "not found" in result.output.lower()
