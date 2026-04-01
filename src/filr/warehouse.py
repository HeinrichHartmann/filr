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


def rebuild(root: Path) -> None:
    """Rebuild derived warehouse state from the transaction log.

    Workflow:
    1. Delete state.db
    2. Create fresh state.db with schema
    3. Enumerate _log/ in sequence order
    4. For each entry: parse, verify, insert into state.db
    5. Report success/errors

    Args:
        root: Warehouse root directory

    Raises:
        FileNotFoundError: If warehouse doesn't exist
    """
    if not warehouse_exists(root):
        raise FileNotFoundError(f"No warehouse found at {root}")

    import json

    from . import db

    db_path = root / "state.db"
    log_dir = root / "_log"

    # Delete existing state.db
    if db_path.exists():
        db_path.unlink()

    # Create fresh state.db with schema
    db.init_db(db_path)

    # Enumerate _log/ entries in order
    if not log_dir.exists():
        return  # No log entries

    # Find all drop entries
    drop_entries = []
    for entry_dir in log_dir.iterdir():
        if (
            entry_dir.is_dir()
            and "_drop" in entry_dir.name
            and not entry_dir.name.startswith("_tmp")
        ):
            # Extract sequence from NNNN_drop
            parts = entry_dir.name.split("_", 1)
            if parts[0].isdigit():
                seq = int(parts[0])
                drop_entries.append((seq, entry_dir))

    # Sort by sequence
    drop_entries.sort(key=lambda x: x[0])

    # Process each entry
    conn = db.get_connection(db_path)
    try:
        for seq, entry_dir in drop_entries:
            # Parse header
            header_path = entry_dir / "header.json"
            if not header_path.exists():
                raise ValueError(f"Missing header.json in {entry_dir}")

            with open(header_path) as f:
                header = json.load(f)

            drop_id = header.get("drop_id")
            created_at = header.get("created_at")
            message = header.get("message")

            # Parse entries
            entries_path = entry_dir / "entries.jsonl"
            if not entries_path.exists():
                raise ValueError(f"Missing entries.jsonl in {entry_dir}")

            entries = []
            total_bytes = 0
            with open(entries_path) as f:
                for line in f:
                    entry = json.loads(line)
                    entries.append(entry)
                    total_bytes += entry.get("blob_size", 0)

            # Insert into applied_log
            conn.execute(
                "INSERT INTO applied_log (seq, entry_name, applied_at) VALUES (?, ?, ?)",
                (seq, entry_dir.name, created_at),
            )

            # Insert into drops
            conn.execute(
                """
                INSERT INTO drops (drop_id, seq, created_at, message, document_count, total_bytes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (drop_id, seq, created_at, message, len(entries), total_bytes),
            )

        conn.commit()

    finally:
        conn.close()


def check(root: Path) -> list[str]:
    """Run integrity and consistency checks on the warehouse.

    Checks:
    1. No sequence gaps in _log/
    2. For each log entry: header parses, entries parse, blobs exist and match hashes
    3. state.db consistent with log

    Args:
        root: Warehouse root directory

    Returns:
        list[str]: List of error messages (empty if all checks pass)

    Raises:
        FileNotFoundError: If warehouse doesn't exist
    """
    if not warehouse_exists(root):
        raise FileNotFoundError(f"No warehouse found at {root}")

    import json

    from . import db
    from . import hash as h

    errors = []
    log_dir = root / "_log"

    if not log_dir.exists():
        # No log entries yet, that's okay
        return errors

    # Find all drop entries
    drop_entries = []
    for entry_dir in log_dir.iterdir():
        if (
            entry_dir.is_dir()
            and "_drop" in entry_dir.name
            and not entry_dir.name.startswith("_tmp")
        ):
            parts = entry_dir.name.split("_", 1)
            if parts[0].isdigit():
                seq = int(parts[0])
                drop_entries.append((seq, entry_dir))

    if not drop_entries:
        return errors

    drop_entries.sort(key=lambda x: x[0])

    # Check for sequence gaps
    expected_seq = 1
    for seq, _ in drop_entries:
        if seq != expected_seq:
            errors.append(f"Sequence gap: expected {expected_seq}, found {seq}")
        expected_seq = seq + 1

    # Check each log entry
    for _, entry_dir in drop_entries:
        # Check header.json
        header_path = entry_dir / "header.json"
        if not header_path.exists():
            errors.append(f"Missing header.json in {entry_dir.name}")
            continue

        try:
            with open(header_path) as f:
                header = json.load(f)
        except Exception as e:
            errors.append(f"Failed to parse header.json in {entry_dir.name}: {e}")
            continue

        # Check entries.jsonl
        entries_path = entry_dir / "entries.jsonl"
        if not entries_path.exists():
            errors.append(f"Missing entries.jsonl in {entry_dir.name}")
            continue

        try:
            with open(entries_path) as f:
                entries = [json.loads(line) for line in f]
        except Exception as e:
            errors.append(f"Failed to parse entries.jsonl in {entry_dir.name}: {e}")
            continue

        # Check blobs
        blobs_dir = entry_dir / "blobs"
        if not blobs_dir.exists():
            errors.append(f"Missing blobs/ directory in {entry_dir.name}")
            continue

        for entry in entries:
            blob_hash = entry.get("blob_hash")
            if not blob_hash:
                errors.append(f"Entry missing blob_hash in {entry_dir.name}")
                continue

            # Parse hash
            try:
                _, hex_digest = h.parse_hash(blob_hash)
            except Exception as e:
                errors.append(f"Invalid blob_hash format in {entry_dir.name}: {e}")
                continue

            blob_path = blobs_dir / hex_digest

            # Check blob exists
            if not blob_path.exists():
                errors.append(f"Missing blob {hex_digest} in {entry_dir.name}")
                continue

            # Verify blob hash
            try:
                actual_hash = h.hash_file(blob_path)
                if actual_hash != blob_hash:
                    errors.append(
                        f"Blob hash mismatch in {entry_dir.name}: {hex_digest} "
                        f"(expected {blob_hash}, got {actual_hash})"
                    )
            except Exception as e:
                errors.append(f"Failed to hash blob {hex_digest} in {entry_dir.name}: {e}")

    # Check state.db consistency
    db_path = root / "state.db"
    if not db_path.exists():
        errors.append("state.db not found")
        return errors

    conn = db.get_connection(db_path)
    try:
        cursor = conn.cursor()

        # Check applied_log matches _log/
        cursor.execute("SELECT seq, entry_name FROM applied_log ORDER BY seq")
        db_entries = cursor.fetchall()

        if len(db_entries) != len(drop_entries):
            errors.append(
                f"applied_log count mismatch: {len(db_entries)} in db, {len(drop_entries)} in _log/"
            )

        for (db_seq, db_name), (log_seq, log_dir) in zip(db_entries, drop_entries, strict=False):
            if db_seq != log_seq:
                errors.append(f"applied_log sequence mismatch: {db_seq} != {log_seq}")
            if db_name != log_dir.name:
                errors.append(f"applied_log name mismatch: {db_name} != {log_dir.name}")

        # Check drops table matches _log/
        cursor.execute("SELECT COUNT(*) FROM drops")
        drops_count = cursor.fetchone()[0]

        if drops_count != len(drop_entries):
            errors.append(
                f"drops table count mismatch: {drops_count} in db, {len(drop_entries)} in _log/"
            )

        # Verify each drop from _log/ exists in drops table
        for _, entry_dir in drop_entries:
            header_path = entry_dir / "header.json"
            if header_path.exists():
                try:
                    with open(header_path) as f:
                        header = json.load(f)
                    drop_id = header.get("drop_id")
                    if drop_id:
                        cursor.execute("SELECT COUNT(*) FROM drops WHERE drop_id = ?", (drop_id,))
                        if cursor.fetchone()[0] == 0:
                            errors.append(
                                f"Drop {drop_id} from {entry_dir.name} not found in drops table"
                            )
                except Exception:
                    pass  # Already reported header parsing errors earlier

    finally:
        conn.close()

    return errors
