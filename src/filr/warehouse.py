"""Warehouse management - location resolution and initialization."""

import os
import tomllib
from datetime import UTC, datetime
from pathlib import Path

import tomli_w


def get_warehouse_root() -> Path:
    """Get the warehouse root directory.

    Resolution order:
    1. FILR_WAREHOUSE_ROOT environment variable
    2. Default: ~/.filr/warehouse

    Returns:
        Path: Resolved warehouse root directory
    """
    env_root = os.environ.get("FILR_WAREHOUSE_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()

    return Path.home() / ".filr" / "warehouse"


def warehouse_exists(root: Path) -> bool:
    """Check if a warehouse exists at the given root.

    Args:
        root: Warehouse root directory

    Returns:
        bool: True if config.toml exists
    """
    return (root / "config.toml").exists()


def init_warehouse(root: Path, name: str | None = None) -> None:
    """Initialize a new warehouse at the given root.

    Creates:
    - Root directory
    - config.toml with warehouse metadata
    - _log/ directory for transaction log
    - state.db with schema

    Args:
        root: Warehouse root directory
        name: Optional warehouse name (defaults to "main")

    Raises:
        FileExistsError: If warehouse already exists
    """
    if warehouse_exists(root):
        raise FileExistsError(f"Warehouse already exists at {root}")

    # Create directory structure
    root.mkdir(parents=True, exist_ok=True)
    log_dir = root / "_log"
    log_dir.mkdir(exist_ok=True)

    # Create config.toml
    config = {
        "warehouse": {
            "name": name or "main",
            "created_at": datetime.now(UTC).isoformat(),
        },
        "hash": {
            "algorithm": "blake3",
        },
    }

    config_path = root / "config.toml"
    with open(config_path, "wb") as f:
        tomli_w.dump(config, f)

    # Create state.db
    from . import db

    db.init_db(root / "state.db")


def load_config(root: Path) -> dict:
    """Load warehouse configuration.

    Args:
        root: Warehouse root directory

    Returns:
        dict: Parsed config.toml

    Raises:
        FileNotFoundError: If config.toml doesn't exist
    """
    config_path = root / "config.toml"
    if not config_path.exists():
        raise FileNotFoundError(f"No warehouse found at {root}")

    with open(config_path, "rb") as f:
        return tomllib.load(f)
