"""End-to-end tests for warehouse initialization."""

import sqlite3
import tomllib
from pathlib import Path

from filr.cli import main


def test_warehouse_init_creates_structure(cli_runner, tmp_warehouse):
    """Test that warehouse init creates the expected directory structure."""
    # Run init command
    result = cli_runner.invoke(main, ["warehouse", "init", "test"])

    assert result.exit_code == 0
    assert "Initialized warehouse" in result.output
    assert str(tmp_warehouse) in result.output

    # Verify directory structure
    assert tmp_warehouse.exists()
    assert (tmp_warehouse / "config.toml").exists()
    assert (tmp_warehouse / "state.db").exists()
    assert (tmp_warehouse / "_log").is_dir()


def test_warehouse_init_config_toml(cli_runner, tmp_warehouse):
    """Test that config.toml has correct structure and content."""
    result = cli_runner.invoke(main, ["warehouse", "init", "test"])
    assert result.exit_code == 0

    # Parse config.toml
    config_path = tmp_warehouse / "config.toml"
    with open(config_path, "rb") as f:
        config = tomllib.load(f)

    # Verify structure
    assert "warehouse" in config
    assert config["warehouse"]["name"] == "test"
    assert "created_at" in config["warehouse"]

    assert "hash" in config
    assert config["hash"]["algorithm"] == "blake3"


def test_warehouse_init_state_db_schema(cli_runner, tmp_warehouse):
    """Test that state.db has correct schema."""
    result = cli_runner.invoke(main, ["warehouse", "init", "test"])
    assert result.exit_code == 0

    # Check database schema
    conn = sqlite3.connect(tmp_warehouse / "state.db")
    cursor = conn.cursor()

    # Get table names
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}

    assert "applied_log" in tables
    assert "drops" in tables

    # Verify applied_log schema
    cursor.execute("PRAGMA table_info(applied_log)")
    columns = {row[1] for row in cursor.fetchall()}
    assert "seq" in columns
    assert "entry_name" in columns
    assert "applied_at" in columns

    # Verify drops schema
    cursor.execute("PRAGMA table_info(drops)")
    columns = {row[1] for row in cursor.fetchall()}
    assert "drop_id" in columns
    assert "seq" in columns
    assert "created_at" in columns
    assert "message" in columns
    assert "document_count" in columns
    assert "total_bytes" in columns

    conn.close()


def test_warehouse_init_default_name(cli_runner, tmp_warehouse):
    """Test warehouse init without specifying a name."""
    result = cli_runner.invoke(main, ["warehouse", "init"])
    assert result.exit_code == 0

    config_path = tmp_warehouse / "config.toml"
    with open(config_path, "rb") as f:
        config = tomllib.load(f)

    assert config["warehouse"]["name"] == "main"


def test_warehouse_init_already_exists(cli_runner, tmp_warehouse):
    """Test that init fails if warehouse already exists."""
    # First init succeeds
    result = cli_runner.invoke(main, ["warehouse", "init", "test"])
    assert result.exit_code == 0

    # Second init fails
    result = cli_runner.invoke(main, ["warehouse", "init", "test"])
    assert result.exit_code != 0
    assert "Error:" in result.output
    assert "already exists" in result.output.lower()


def test_warehouse_init_with_env_var(cli_runner, tmp_path, monkeypatch):
    """Test warehouse location resolution via FILR_WAREHOUSE_ROOT."""
    custom_location = tmp_path / "custom" / "warehouse"
    monkeypatch.setenv("FILR_WAREHOUSE_ROOT", str(custom_location))

    result = cli_runner.invoke(main, ["warehouse", "init", "custom"])
    assert result.exit_code == 0

    # Verify created at custom location
    assert custom_location.exists()
    assert (custom_location / "config.toml").exists()
