"""Shared test fixtures for filr tests."""

import pytest
from click.testing import CliRunner


@pytest.fixture
def cli_runner():
    """Provide a Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def tmp_warehouse(tmp_path, monkeypatch):
    """Create a temporary warehouse for testing.

    Sets FILR_WAREHOUSE_ROOT to a temporary directory and yields the path.
    """
    warehouse_root = tmp_path / "warehouse"
    monkeypatch.setenv("FILR_WAREHOUSE_ROOT", str(warehouse_root))
    return warehouse_root


@pytest.fixture
def sample_files(tmp_path):
    """Create sample test files.

    Creates a directory structure:
    - sample.txt (top level)
    - subdir/nested.txt (nested file)
    """
    data = tmp_path / "data"
    data.mkdir()
    (data / "sample.txt").write_text("hello world")
    (data / "subdir").mkdir()
    (data / "subdir" / "nested.txt").write_text("nested content")
    return data
