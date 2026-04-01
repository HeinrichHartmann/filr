"""End-to-end tests for warehouse stats and log."""

import json

from filr.cli import main


def test_warehouse_stats_empty(cli_runner, tmp_warehouse):
    """Test warehouse stats with no drops."""
    cli_runner.invoke(main, ["warehouse", "init", "test"])

    result = cli_runner.invoke(main, ["warehouse", "stats"])
    assert result.exit_code == 0

    # Check output contains expected fields
    assert "Warehouse root:" in result.output
    assert "Warehouse name:    test" in result.output
    assert "Drop count:        0" in result.output
    assert "Document count:    0" in result.output
    assert "Total size:" in result.output


def test_warehouse_stats_with_drops(cli_runner, tmp_warehouse, sample_files):
    """Test warehouse stats with imported drops."""
    cli_runner.invoke(main, ["warehouse", "init", "test"])
    cli_runner.invoke(main, ["drop", "fs-import", str(sample_files), "-m", "first"])
    cli_runner.invoke(main, ["drop", "fs-import", str(sample_files), "-m", "second"])

    result = cli_runner.invoke(main, ["warehouse", "stats"])
    assert result.exit_code == 0

    # Check counts
    assert "Drop count:        2" in result.output
    assert "Document count:    4" in result.output  # 2 files per import x 2 imports
    assert "Total size:" in result.output


def test_warehouse_stats_json(cli_runner, tmp_warehouse, sample_files):
    """Test warehouse stats --json output."""
    cli_runner.invoke(main, ["warehouse", "init", "mywarehouse"])
    cli_runner.invoke(main, ["drop", "fs-import", str(sample_files)])

    result = cli_runner.invoke(main, ["warehouse", "stats", "--json"])
    assert result.exit_code == 0

    # Parse JSON
    stats = json.loads(result.output)

    # Check structure
    assert "warehouse_root" in stats
    assert stats["warehouse_name"] == "mywarehouse"
    assert stats["drop_count"] == 1
    assert stats["document_count"] == 2
    assert stats["total_bytes"] > 0
    assert "created_at" in stats


def test_warehouse_stats_no_warehouse(cli_runner, tmp_warehouse):
    """Test warehouse stats fails without warehouse."""
    result = cli_runner.invoke(main, ["warehouse", "stats"])
    assert result.exit_code != 0
    assert "Error" in result.output or "not found" in result.output.lower()


def test_warehouse_log_empty(cli_runner, tmp_warehouse):
    """Test warehouse log with no entries."""
    cli_runner.invoke(main, ["warehouse", "init"])

    result = cli_runner.invoke(main, ["warehouse", "log"])
    assert result.exit_code == 0
    assert "No log entries found" in result.output


def test_warehouse_log_with_entries(cli_runner, tmp_warehouse, sample_files):
    """Test warehouse log shows applied entries."""
    cli_runner.invoke(main, ["warehouse", "init"])
    cli_runner.invoke(main, ["drop", "fs-import", str(sample_files), "-m", "first"])
    cli_runner.invoke(main, ["drop", "fs-import", str(sample_files), "-m", "second"])

    result = cli_runner.invoke(main, ["warehouse", "log"])
    assert result.exit_code == 0

    # Check table header
    assert "Seq" in result.output
    assert "Entry Name" in result.output
    assert "Applied At" in result.output

    # Check entries
    assert "0001_drop" in result.output
    assert "0002_drop" in result.output


def test_warehouse_log_json(cli_runner, tmp_warehouse, sample_files):
    """Test warehouse log --json output."""
    cli_runner.invoke(main, ["warehouse", "init"])
    cli_runner.invoke(main, ["drop", "fs-import", str(sample_files)])

    result = cli_runner.invoke(main, ["warehouse", "log", "--json"])
    assert result.exit_code == 0

    # Parse JSON
    entries = json.loads(result.output)

    assert isinstance(entries, list)
    assert len(entries) == 1

    # Check structure
    entry = entries[0]
    assert entry["seq"] == 1
    assert entry["entry_name"] == "0001_drop"
    assert "applied_at" in entry


def test_warehouse_log_ordering(cli_runner, tmp_warehouse, sample_files):
    """Test warehouse log shows entries in sequence order."""
    cli_runner.invoke(main, ["warehouse", "init"])

    # Import 3 drops
    cli_runner.invoke(main, ["drop", "fs-import", str(sample_files)])
    cli_runner.invoke(main, ["drop", "fs-import", str(sample_files)])
    cli_runner.invoke(main, ["drop", "fs-import", str(sample_files)])

    result = cli_runner.invoke(main, ["warehouse", "log", "--json"])
    entries = json.loads(result.output)

    assert len(entries) == 3
    assert entries[0]["seq"] == 1
    assert entries[0]["entry_name"] == "0001_drop"
    assert entries[1]["seq"] == 2
    assert entries[1]["entry_name"] == "0002_drop"
    assert entries[2]["seq"] == 3
    assert entries[2]["entry_name"] == "0003_drop"


def test_warehouse_log_no_warehouse(cli_runner, tmp_warehouse):
    """Test warehouse log fails without warehouse."""
    result = cli_runner.invoke(main, ["warehouse", "log"])
    assert result.exit_code != 0
    assert "Error" in result.output or "not found" in result.output.lower()


def test_warehouse_stats_size_formatting(cli_runner, tmp_warehouse, tmp_path):
    """Test warehouse stats formats size correctly."""
    cli_runner.invoke(main, ["warehouse", "init"])

    # Create small file
    small_file = tmp_path / "small.txt"
    small_file.write_text("x" * 100)  # 100 bytes

    cli_runner.invoke(main, ["drop", "fs-import", str(small_file)])

    result = cli_runner.invoke(main, ["warehouse", "stats"])
    assert result.exit_code == 0
    # Should show bytes for small files
    assert "100 bytes" in result.output or "0." in result.output  # Might be KB
