"""End-to-end tests for drop list and inspect."""

import json

from filr.cli import main


def test_drop_list_empty(cli_runner, tmp_warehouse):
    """Test drop list with no drops."""
    cli_runner.invoke(main, ["warehouse", "init"])

    result = cli_runner.invoke(main, ["drop", "list"])
    assert result.exit_code == 0
    assert "No drops found" in result.output


def test_drop_list_shows_drops(cli_runner, tmp_warehouse, sample_files):
    """Test drop list shows imported drops."""
    cli_runner.invoke(main, ["warehouse", "init"])
    cli_runner.invoke(main, ["drop", "fs-import", str(sample_files), "-m", "first"])
    cli_runner.invoke(main, ["drop", "fs-import", str(sample_files), "-m", "second"])

    result = cli_runner.invoke(main, ["drop", "list"])
    assert result.exit_code == 0

    # Should show table header
    assert "Drop ID" in result.output
    assert "Created" in result.output
    assert "Docs" in result.output

    # Should show both drops
    assert "first" in result.output
    assert "second" in result.output


def test_drop_list_json(cli_runner, tmp_warehouse, sample_files):
    """Test drop list --json output."""
    cli_runner.invoke(main, ["warehouse", "init"])
    result_import = cli_runner.invoke(main, ["drop", "fs-import", str(sample_files), "-m", "test"])
    drop_id = result_import.output.strip()

    result = cli_runner.invoke(main, ["drop", "list", "--json"])
    assert result.exit_code == 0

    # Parse JSON
    drops = json.loads(result.output)
    assert isinstance(drops, list)
    assert len(drops) == 1

    # Check structure
    drop = drops[0]
    assert drop["drop_id"] == drop_id
    assert drop["message"] == "test"
    assert "created_at" in drop
    assert drop["document_count"] == 2
    assert drop["total_bytes"] > 0


def test_drop_list_multiple_drops_ordered(cli_runner, tmp_warehouse, sample_files):
    """Test that drop list shows drops in sequence order."""
    cli_runner.invoke(main, ["warehouse", "init"])

    # Import 3 drops
    result1 = cli_runner.invoke(main, ["drop", "fs-import", str(sample_files), "-m", "alpha"])
    result2 = cli_runner.invoke(main, ["drop", "fs-import", str(sample_files), "-m", "beta"])
    result3 = cli_runner.invoke(main, ["drop", "fs-import", str(sample_files), "-m", "gamma"])

    drop_id1 = result1.output.strip()
    drop_id2 = result2.output.strip()
    drop_id3 = result3.output.strip()

    # List as JSON to check order
    result = cli_runner.invoke(main, ["drop", "list", "--json"])
    drops = json.loads(result.output)

    assert len(drops) == 3
    assert drops[0]["drop_id"] == drop_id1
    assert drops[1]["drop_id"] == drop_id2
    assert drops[2]["drop_id"] == drop_id3


def test_drop_inspect_basic(cli_runner, tmp_warehouse, sample_files):
    """Test drop inspect shows detailed information."""
    cli_runner.invoke(main, ["warehouse", "init"])
    result_import = cli_runner.invoke(main, ["drop", "fs-import", str(sample_files), "-m", "test"])
    drop_id = result_import.output.strip()

    result = cli_runner.invoke(main, ["drop", "inspect", drop_id])
    assert result.exit_code == 0

    # Check output contains expected fields
    assert drop_id in result.output
    assert "Created:" in result.output
    assert "Message:         test" in result.output
    assert "Document count:  2" in result.output
    assert "Total bytes:" in result.output
    assert "Log location:" in result.output


def test_drop_inspect_json(cli_runner, tmp_warehouse, sample_files):
    """Test drop inspect --json output."""
    cli_runner.invoke(main, ["warehouse", "init"])
    result_import = cli_runner.invoke(
        main,
        [
            "drop",
            "fs-import",
            str(sample_files),
            "-m",
            "test message",
            "-H",
            '{"actor": "tester"}',
        ],
    )
    drop_id = result_import.output.strip()

    result = cli_runner.invoke(main, ["drop", "inspect", drop_id, "--json"])
    assert result.exit_code == 0

    # Parse JSON
    details = json.loads(result.output)

    # Check structure
    assert details["drop_id"] == drop_id
    assert "created_at" in details
    assert details["message"] == "test message"
    assert details["document_count"] == 2
    assert details["total_bytes"] > 0
    assert "header" in details
    assert "log_location" in details

    # Check header includes custom metadata
    assert details["header"]["actor"] == "tester"
    assert details["header"]["source"] == "fs-import"


def test_drop_inspect_not_found(cli_runner, tmp_warehouse):
    """Test drop inspect with non-existent drop_id."""
    cli_runner.invoke(main, ["warehouse", "init"])

    result = cli_runner.invoke(main, ["drop", "inspect", "d_20260101_000000_ffffffff"])
    assert result.exit_code != 0
    assert "Error" in result.output or "not found" in result.output.lower()


def test_drop_list_no_warehouse(cli_runner, tmp_warehouse):
    """Test drop list fails without warehouse."""
    result = cli_runner.invoke(main, ["drop", "list"])
    assert result.exit_code != 0
    assert "No warehouse found" in result.output or "Error" in result.output


def test_drop_inspect_no_warehouse(cli_runner, tmp_warehouse):
    """Test drop inspect fails without warehouse."""
    result = cli_runner.invoke(main, ["drop", "inspect", "d_20260101_000000_12345678"])
    assert result.exit_code != 0
    assert "No warehouse found" in result.output or "Error" in result.output


def test_drop_list_shows_document_count(cli_runner, tmp_warehouse, tmp_path):
    """Test drop list shows correct document count."""
    cli_runner.invoke(main, ["warehouse", "init"])

    # Create drops with different file counts
    single_file = tmp_path / "single.txt"
    single_file.write_text("single")

    multi_dir = tmp_path / "multi"
    multi_dir.mkdir()
    (multi_dir / "a.txt").write_text("a")
    (multi_dir / "b.txt").write_text("b")
    (multi_dir / "c.txt").write_text("c")

    cli_runner.invoke(main, ["drop", "fs-import", str(single_file), "-m", "one"])
    cli_runner.invoke(main, ["drop", "fs-import", str(multi_dir), "-m", "three"])

    result = cli_runner.invoke(main, ["drop", "list", "--json"])
    drops = json.loads(result.output)

    assert drops[0]["document_count"] == 1
    assert drops[0]["message"] == "one"

    assert drops[1]["document_count"] == 3
    assert drops[1]["message"] == "three"
