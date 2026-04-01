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


def get_stats(root: Path) -> dict:
    """Get warehouse statistics.

    Args:
        root: Warehouse root directory

    Returns:
        dict: Statistics including:
            - warehouse_root: Path to warehouse
            - warehouse_name: Name from config
            - drop_count: Number of drops
            - document_count: Total number of documents
            - total_bytes: Total size in bytes
            - created_at: Warehouse creation timestamp

    Raises:
        FileNotFoundError: If warehouse doesn't exist
    """
    if not warehouse_exists(root):
        raise FileNotFoundError(f"No warehouse found at {root}")

    # Load config
    config = load_config(root)

    # Query state.db for aggregated stats
    from . import db

    db_path = root / "state.db"
    conn = db.get_connection(db_path)

    try:
        cursor = conn.cursor()

        # Count drops
        cursor.execute("SELECT COUNT(*) FROM drops")
        drop_count = cursor.fetchone()[0]

        # Sum documents and bytes
        cursor.execute("SELECT SUM(document_count), SUM(total_bytes) FROM drops")
        row = cursor.fetchone()
        document_count = row[0] or 0
        total_bytes = row[1] or 0

        return {
            "warehouse_root": str(root),
            "warehouse_name": config["warehouse"]["name"],
            "drop_count": drop_count,
            "document_count": document_count,
            "total_bytes": total_bytes,
            "created_at": config["warehouse"]["created_at"],
        }

    finally:
        conn.close()


def get_log(root: Path) -> list[dict]:
    """Get warehouse transaction log.

    Args:
        root: Warehouse root directory

    Returns:
        list[dict]: List of log entries with:
            - seq: Sequence number
            - entry_name: Log entry name (e.g. "0001_drop")
            - applied_at: Timestamp when applied

    Raises:
        FileNotFoundError: If warehouse doesn't exist
    """
    if not warehouse_exists(root):
        raise FileNotFoundError(f"No warehouse found at {root}")

    from . import db

    db_path = root / "state.db"
    conn = db.get_connection(db_path)

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT seq, entry_name, applied_at FROM applied_log ORDER BY seq")

        entries = []
        for row in cursor.fetchall():
            entries.append({"seq": row[0], "entry_name": row[1], "applied_at": row[2]})

        return entries

    finally:
        conn.close()
