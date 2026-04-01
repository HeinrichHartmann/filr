"""End-to-end tests for warehouse rebuild and check."""

import json

from filr.cli import main

# ========== Rebuild Tests ==========


def test_warehouse_rebuild_basic(cli_runner, tmp_warehouse, sample_files):
    """Test that warehouse rebuild recreates state.db from log."""
    cli_runner.invoke(main, ["warehouse", "init"])
    cli_runner.invoke(main, ["drop", "fs-import", str(sample_files), "-m", "test"])

    # Delete state.db
    state_db = tmp_warehouse / "state.db"
    state_db.unlink()

    # Rebuild
    result = cli_runner.invoke(main, ["warehouse", "rebuild"])
    assert result.exit_code == 0
    assert "rebuilt successfully" in result.output.lower()

    # Verify state.db exists
    assert state_db.exists()


def test_warehouse_rebuild_preserves_drops(cli_runner, tmp_warehouse, sample_files):
    """Test that rebuild preserves all drop data."""
    cli_runner.invoke(main, ["warehouse", "init"])

    # Import 3 drops
    result1 = cli_runner.invoke(main, ["drop", "fs-import", str(sample_files), "-m", "first"])
    drop_id1 = result1.output.strip()

    result2 = cli_runner.invoke(main, ["drop", "fs-import", str(sample_files), "-m", "second"])
    drop_id2 = result2.output.strip()

    result3 = cli_runner.invoke(main, ["drop", "fs-import", str(sample_files), "-m", "third"])
    drop_id3 = result3.output.strip()

    # Get original drop list
    result_before = cli_runner.invoke(main, ["drop", "list", "--json"])
    drops_before = json.loads(result_before.output)

    # Delete and rebuild
    (tmp_warehouse / "state.db").unlink()
    cli_runner.invoke(main, ["warehouse", "rebuild"])

    # Get rebuilt drop list
    result_after = cli_runner.invoke(main, ["drop", "list", "--json"])
    drops_after = json.loads(result_after.output)

    # Compare
    assert len(drops_after) == len(drops_before) == 3
    assert drops_after[0]["drop_id"] == drop_id1
    assert drops_after[1]["drop_id"] == drop_id2
    assert drops_after[2]["drop_id"] == drop_id3
    assert drops_after[0]["message"] == "first"
    assert drops_after[1]["message"] == "second"
    assert drops_after[2]["message"] == "third"


def test_warehouse_rebuild_empty(cli_runner, tmp_warehouse):
    """Test rebuild with empty warehouse (no drops)."""
    cli_runner.invoke(main, ["warehouse", "init"])

    # Delete and rebuild
    (tmp_warehouse / "state.db").unlink()
    result = cli_runner.invoke(main, ["warehouse", "rebuild"])

    assert result.exit_code == 0
    assert (tmp_warehouse / "state.db").exists()


def test_warehouse_rebuild_stats_match(cli_runner, tmp_warehouse, sample_files):
    """Test that stats match after rebuild."""
    cli_runner.invoke(main, ["warehouse", "init"])
    cli_runner.invoke(main, ["drop", "fs-import", str(sample_files)])

    # Get stats before rebuild
    result_before = cli_runner.invoke(main, ["warehouse", "stats", "--json"])
    stats_before = json.loads(result_before.output)

    # Delete and rebuild
    (tmp_warehouse / "state.db").unlink()
    cli_runner.invoke(main, ["warehouse", "rebuild"])

    # Get stats after rebuild
    result_after = cli_runner.invoke(main, ["warehouse", "stats", "--json"])
    stats_after = json.loads(result_after.output)

    # Compare key stats
    assert stats_after["drop_count"] == stats_before["drop_count"]
    assert stats_after["document_count"] == stats_before["document_count"]
    assert stats_after["total_bytes"] == stats_before["total_bytes"]


# ========== Check Tests ==========


def test_warehouse_check_clean(cli_runner, tmp_warehouse, sample_files):
    """Test warehouse check passes on clean warehouse."""
    cli_runner.invoke(main, ["warehouse", "init"])
    cli_runner.invoke(main, ["drop", "fs-import", str(sample_files)])

    result = cli_runner.invoke(main, ["warehouse", "check"])
    assert result.exit_code == 0
    assert "OK" in result.output or "passed" in result.output.lower()


def test_warehouse_check_empty(cli_runner, tmp_warehouse):
    """Test warehouse check passes on empty warehouse."""
    cli_runner.invoke(main, ["warehouse", "init"])

    result = cli_runner.invoke(main, ["warehouse", "check"])
    assert result.exit_code == 0


def test_warehouse_check_corrupted_blob(cli_runner, tmp_warehouse, sample_files):
    """Test warehouse check detects corrupted blob."""
    cli_runner.invoke(main, ["warehouse", "init"])
    cli_runner.invoke(main, ["drop", "fs-import", str(sample_files)])

    # Corrupt a blob
    blobs_dir = tmp_warehouse / "_log" / "0001_drop" / "blobs"
    blob_files = list(blobs_dir.iterdir())
    assert len(blob_files) > 0

    # Overwrite first blob with garbage
    blob_files[0].write_bytes(b"CORRUPTED CONTENT")

    # Check should fail
    result = cli_runner.invoke(main, ["warehouse", "check"])
    assert result.exit_code != 0
    assert "FAILED" in result.output or "error" in result.output.lower()
    assert "hash mismatch" in result.output.lower() or "mismatch" in result.output.lower()


def test_warehouse_check_missing_blob(cli_runner, tmp_warehouse, sample_files):
    """Test warehouse check detects missing blob."""
    cli_runner.invoke(main, ["warehouse", "init"])
    cli_runner.invoke(main, ["drop", "fs-import", str(sample_files)])

    # Delete a blob
    blobs_dir = tmp_warehouse / "_log" / "0001_drop" / "blobs"
    blob_files = list(blobs_dir.iterdir())
    blob_files[0].unlink()

    # Check should fail
    result = cli_runner.invoke(main, ["warehouse", "check"])
    assert result.exit_code != 0
    assert "missing blob" in result.output.lower() or "missing" in result.output.lower()


def test_warehouse_check_missing_header(cli_runner, tmp_warehouse, sample_files):
    """Test warehouse check detects missing header.json."""
    cli_runner.invoke(main, ["warehouse", "init"])
    cli_runner.invoke(main, ["drop", "fs-import", str(sample_files)])

    # Delete header.json
    header_path = tmp_warehouse / "_log" / "0001_drop" / "header.json"
    header_path.unlink()

    # Check should fail
    result = cli_runner.invoke(main, ["warehouse", "check"])
    assert result.exit_code != 0
    assert "missing header" in result.output.lower() or "header.json" in result.output.lower()


def test_warehouse_check_missing_entries(cli_runner, tmp_warehouse, sample_files):
    """Test warehouse check detects missing entries.jsonl."""
    cli_runner.invoke(main, ["warehouse", "init"])
    cli_runner.invoke(main, ["drop", "fs-import", str(sample_files)])

    # Delete entries.jsonl
    entries_path = tmp_warehouse / "_log" / "0001_drop" / "entries.jsonl"
    entries_path.unlink()

    # Check should fail
    result = cli_runner.invoke(main, ["warehouse", "check"])
    assert result.exit_code != 0
    assert "missing entries" in result.output.lower() or "entries.jsonl" in result.output.lower()


def test_warehouse_check_json_output(cli_runner, tmp_warehouse, sample_files):
    """Test warehouse check --json output."""
    cli_runner.invoke(main, ["warehouse", "init"])
    cli_runner.invoke(main, ["drop", "fs-import", str(sample_files)])

    # Clean check
    result = cli_runner.invoke(main, ["warehouse", "check", "--json"])
    assert result.exit_code == 0

    data = json.loads(result.output)
    assert "ok" in data
    assert data["ok"] is True
    assert data["errors"] == []


def test_warehouse_check_json_with_errors(cli_runner, tmp_warehouse, sample_files):
    """Test warehouse check --json output with errors."""
    cli_runner.invoke(main, ["warehouse", "init"])
    cli_runner.invoke(main, ["drop", "fs-import", str(sample_files)])

    # Corrupt a blob
    blobs_dir = tmp_warehouse / "_log" / "0001_drop" / "blobs"
    blob_files = list(blobs_dir.iterdir())
    blob_files[0].write_bytes(b"CORRUPTED")

    # Check with errors
    result = cli_runner.invoke(main, ["warehouse", "check", "--json"])
    assert result.exit_code != 0

    data = json.loads(result.output)
    assert "ok" in data
    assert data["ok"] is False
    assert len(data["errors"]) > 0


def test_warehouse_check_sequence_gap(cli_runner, tmp_warehouse, sample_files):
    """Test warehouse check detects sequence gaps."""
    cli_runner.invoke(main, ["warehouse", "init"])
    cli_runner.invoke(main, ["drop", "fs-import", str(sample_files)])
    cli_runner.invoke(main, ["drop", "fs-import", str(sample_files)])

    # Rename 0002_drop to 0003_drop (creating a gap)
    log_dir = tmp_warehouse / "_log"
    (log_dir / "0002_drop").rename(log_dir / "0003_drop")

    # Check should detect gap
    result = cli_runner.invoke(main, ["warehouse", "check"])
    assert result.exit_code != 0
    assert "gap" in result.output.lower() or "sequence" in result.output.lower()


def test_warehouse_check_state_db_mismatch(cli_runner, tmp_warehouse, sample_files):
    """Test warehouse check detects state.db / log mismatch."""
    cli_runner.invoke(main, ["warehouse", "init"])
    cli_runner.invoke(main, ["drop", "fs-import", str(sample_files)])

    # Delete state.db applied_log entries without rebuilding
    import sqlite3

    conn = sqlite3.connect(tmp_warehouse / "state.db")
    conn.execute("DELETE FROM applied_log")
    conn.commit()
    conn.close()

    # Check should detect mismatch
    result = cli_runner.invoke(main, ["warehouse", "check"])
    assert result.exit_code != 0
    assert "mismatch" in result.output.lower() or "applied_log" in result.output.lower()


# ========== Integration Tests ==========


def test_rebuild_then_check(cli_runner, tmp_warehouse, sample_files):
    """Test that rebuild followed by check succeeds."""
    cli_runner.invoke(main, ["warehouse", "init"])
    cli_runner.invoke(main, ["drop", "fs-import", str(sample_files)])

    # Delete and rebuild
    (tmp_warehouse / "state.db").unlink()
    result_rebuild = cli_runner.invoke(main, ["warehouse", "rebuild"])
    assert result_rebuild.exit_code == 0

    # Check should pass
    result_check = cli_runner.invoke(main, ["warehouse", "check"])
    assert result_check.exit_code == 0


def test_check_after_corruption_rebuild_fixes(cli_runner, tmp_warehouse, sample_files):
    """Test that corrupting state.db and rebuilding fixes issues."""
    cli_runner.invoke(main, ["warehouse", "init"])
    cli_runner.invoke(main, ["drop", "fs-import", str(sample_files)])

    # Corrupt state.db (delete entries)
    import sqlite3

    conn = sqlite3.connect(tmp_warehouse / "state.db")
    conn.execute("DELETE FROM drops")
    conn.commit()
    conn.close()

    # Check should detect mismatch
    result_check1 = cli_runner.invoke(main, ["warehouse", "check"])
    assert result_check1.exit_code != 0

    # Rebuild should fix
    (tmp_warehouse / "state.db").unlink()
    cli_runner.invoke(main, ["warehouse", "rebuild"])

    # Check should now pass
    result_check2 = cli_runner.invoke(main, ["warehouse", "check"])
    assert result_check2.exit_code == 0
