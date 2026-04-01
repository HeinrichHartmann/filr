"""Database operations for warehouse state tracking."""

import sqlite3
from pathlib import Path

# Schema from ADR-003
SCHEMA = """
CREATE TABLE IF NOT EXISTS applied_log (
    seq INTEGER PRIMARY KEY,
    entry_name TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS drops (
    drop_id TEXT PRIMARY KEY,
    seq INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    message TEXT,
    document_count INTEGER,
    total_bytes INTEGER
);
"""


def init_db(db_path: Path) -> None:
    """Initialize state.db with schema.

    Args:
        db_path: Path to state.db file
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Get a connection to the state database.

    Args:
        db_path: Path to state.db file

    Returns:
        sqlite3.Connection: Database connection
    """
    return sqlite3.connect(db_path)
