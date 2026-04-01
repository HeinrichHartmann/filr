"""End-to-end tests for drop fs-import."""

import json
import re
import sqlite3

from filr.cli import main


def test_drop_fs_import_creates_log_structure(cli_runner, tmp_warehouse, sample_files):
    """Test that fs-import creates proper log entry structure."""
    # Initialize warehouse
    cli_runner.invoke(main, ["warehouse", "init"])

    # Import files
    result = cli_runner.invoke(main, ["drop", "fs-import", str(sample_files), "-m", "test"])
    assert result.exit_code == 0

    # Extract drop_id from output
    drop_id = result.output.strip()
    assert drop_id.startswith("d_")

    # Verify log structure
    log_dir = tmp_warehouse / "_log"
    assert log_dir.exists()

    # Should have 0001_drop
    drop_dir = log_dir / "0001_drop"
    assert drop_dir.exists()
    assert (drop_dir / "header.json").exists()
    assert (drop_dir / "entries.jsonl").exists()
    assert (drop_dir / "blobs").is_dir()


def test_drop_fs_import_header_content(cli_runner, tmp_warehouse, sample_files):
    """Test that header.json contains correct metadata."""
    cli_runner.invoke(main, ["warehouse", "init"])
    result = cli_runner.invoke(
        main,
        [
            "drop",
            "fs-import",
            str(sample_files),
            "-m",
            "Test message",
            "-H",
            '{"actor": "test-user", "tags": ["test"]}',
        ],
    )
    assert result.exit_code == 0

    drop_dir = tmp_warehouse / "_log" / "0001_drop"
    with open(drop_dir / "header.json") as f:
        header = json.load(f)

    # System fields
    assert "drop_id" in header
    assert header["drop_id"].startswith("d_")
    assert "created_at" in header
    assert header["source"] == "fs-import"
    assert "import_root" in header

    # User fields
    assert header["message"] == "Test message"
    assert header["actor"] == "test-user"
    assert header["tags"] == ["test"]


def test_drop_fs_import_entries_content(cli_runner, tmp_warehouse, sample_files):
    """Test that entries.jsonl contains correct document entries."""
    cli_runner.invoke(main, ["warehouse", "init"])
    cli_runner.invoke(main, ["drop", "fs-import", str(sample_files)])

    drop_dir = tmp_warehouse / "_log" / "0001_drop"
    entries_path = drop_dir / "entries.jsonl"

    # Read entries
    entries = []
    with open(entries_path) as f:
        for line in f:
            entries.append(json.loads(line))

    # Should have 2 files (sample.txt, subdir/nested.txt)
    assert len(entries) == 2

    # Check entry structure
    for entry in entries:
        assert "import_path" in entry
        assert "import_name" in entry
        assert "blob_hash" in entry
        assert entry["blob_hash"].startswith("blake3:")
        assert "blob_size" in entry
        assert entry["blob_size"] > 0

    # Verify specific files
    paths = [e["import_path"] for e in entries]
    assert "sample.txt" in paths
    assert "subdir/nested.txt" in paths or "subdir\\nested.txt" in paths


def test_drop_fs_import_blobs_stored(cli_runner, tmp_warehouse, sample_files):
    """Test that blob files are stored correctly."""
    cli_runner.invoke(main, ["warehouse", "init"])
    cli_runner.invoke(main, ["drop", "fs-import", str(sample_files)])

    drop_dir = tmp_warehouse / "_log" / "0001_drop"
    blobs_dir = drop_dir / "blobs"

    # Read entries to get expected blob hashes
    entries_path = drop_dir / "entries.jsonl"
    blob_hashes = []
    with open(entries_path) as f:
        for line in f:
            entry = json.loads(line)
            blob_hash = entry["blob_hash"]
            # Extract hex digest after "blake3:"
            hex_digest = blob_hash.split(":")[1]
            blob_hashes.append(hex_digest)

    # Verify blobs exist
    for hex_digest in blob_hashes:
        blob_path = blobs_dir / hex_digest
        assert blob_path.exists()
        assert blob_path.is_file()
        assert blob_path.stat().st_size > 0


def test_drop_fs_import_updates_state_db(cli_runner, tmp_warehouse, sample_files):
    """Test that state.db is updated with drop metadata."""
    cli_runner.invoke(main, ["warehouse", "init"])
    result = cli_runner.invoke(main, ["drop", "fs-import", str(sample_files), "-m", "test"])
    drop_id = result.output.strip()

    # Check applied_log
    conn = sqlite3.connect(tmp_warehouse / "state.db")
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM applied_log")
    rows = cursor.fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 1  # seq
    assert rows[0][1] == "0001_drop"  # entry_name

    # Check drops table
    cursor.execute("SELECT * FROM drops WHERE drop_id = ?", (drop_id,))
    row = cursor.fetchone()
    assert row is not None
    assert row[1] == 1  # seq
    assert row[4] == 2  # document_count (2 files)
    assert row[5] > 0  # total_bytes

    conn.close()


def test_drop_fs_import_drop_id_format(cli_runner, tmp_warehouse, sample_files):
    """Test that drop_id follows the correct format."""
    cli_runner.invoke(main, ["warehouse", "init"])
    result = cli_runner.invoke(main, ["drop", "fs-import", str(sample_files)])
    drop_id = result.output.strip()

    # Format: d_YYYYMMDD_HHMMSS_hash8
    pattern = r"^d_\d{8}_\d{6}_[a-f0-9]{8}$"
    assert re.match(pattern, drop_id), f"Invalid drop_id format: {drop_id}"


def test_drop_fs_import_multiple_drops(cli_runner, tmp_warehouse, sample_files):
    """Test that multiple imports create sequential log entries."""
    cli_runner.invoke(main, ["warehouse", "init"])

    # First import
    result1 = cli_runner.invoke(main, ["drop", "fs-import", str(sample_files), "-m", "first"])
    drop_id1 = result1.output.strip()

    # Second import
    result2 = cli_runner.invoke(main, ["drop", "fs-import", str(sample_files), "-m", "second"])
    drop_id2 = result2.output.strip()

    # Should have different drop_ids
    assert drop_id1 != drop_id2

    # Should have 0001_drop and 0002_drop
    log_dir = tmp_warehouse / "_log"
    assert (log_dir / "0001_drop").exists()
    assert (log_dir / "0002_drop").exists()

    # Check state.db
    conn = sqlite3.connect(tmp_warehouse / "state.db")
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM applied_log")
    assert cursor.fetchone()[0] == 2

    cursor.execute("SELECT COUNT(*) FROM drops")
    assert cursor.fetchone()[0] == 2

    conn.close()


def test_drop_fs_import_single_file(cli_runner, tmp_warehouse, tmp_path):
    """Test importing a single file (not a directory)."""
    cli_runner.invoke(main, ["warehouse", "init"])

    # Create single file
    test_file = tmp_path / "single.txt"
    test_file.write_text("single file content")

    result = cli_runner.invoke(main, ["drop", "fs-import", str(test_file)])
    assert result.exit_code == 0

    # Verify import
    drop_dir = tmp_warehouse / "_log" / "0001_drop"
    with open(drop_dir / "entries.jsonl") as f:
        entries = [json.loads(line) for line in f]

    assert len(entries) == 1
    assert entries[0]["import_path"] == "single.txt"
    assert entries[0]["import_name"] == "single.txt"


def test_drop_fs_import_no_warehouse(cli_runner, tmp_warehouse, sample_files):
    """Test that fs-import fails if warehouse doesn't exist."""
    # Don't initialize warehouse
    result = cli_runner.invoke(main, ["drop", "fs-import", str(sample_files)])

    assert result.exit_code != 0
    assert "No warehouse found" in result.output or "Error" in result.output
