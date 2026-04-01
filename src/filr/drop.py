"""Drop operations - importing and managing immutable document collections."""

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from . import db
from . import hash as h


def generate_drop_id(timestamp: datetime, integrity_hash: str) -> str:
    """Generate drop ID from timestamp and integrity hash.

    Format: d_YYYYMMDD_HHMMSS_hash8

    Args:
        timestamp: UTC timestamp
        integrity_hash: Drop integrity hash (blake3:hex)

    Returns:
        str: Drop ID
    """
    _, hex_digest = h.parse_hash(integrity_hash)
    hash8 = hex_digest[:8]

    date_str = timestamp.strftime("%Y%m%d")
    time_str = timestamp.strftime("%H%M%S")

    return f"d_{date_str}_{time_str}_{hash8}"


def compute_drop_integrity_hash(header: dict, entries: list[dict]) -> str:
    """Compute Merkle-tree style integrity hash for a drop.

    Hash structure:
    - hash(header_without_drop_id)
    - hash(entries_content)
    - individual blob hashes
    - final hash = hash(header_hash + entries_hash + blob_hash_1 + blob_hash_2 + ...)

    Args:
        header: Drop header dict (drop_id will be excluded from hash)
        entries: List of entry dicts

    Returns:
        str: Integrity hash in format "blake3:hexdigest"
    """
    # Hash header without drop_id (circular dependency)
    header_for_hash = {k: v for k, v in header.items() if k != "drop_id"}
    header_hash = h.hash_dict(header_for_hash)

    # Hash entries content (canonical JSON of entire list)
    entries_hash = h.hash_dict(entries)

    # Collect blob hashes in order
    blob_hashes = [entry["blob_hash"] for entry in entries]

    # Combine all hashes
    combined = header_hash + entries_hash + "".join(blob_hashes)
    return h.hash_bytes(combined.encode("utf-8"))


def scan_directory(source_path: Path) -> list[dict]:
    """Scan a directory and collect file metadata for import.

    Args:
        source_path: Source file or directory to scan

    Returns:
        list[dict]: List of file entries with:
            - source_path: Absolute path to source file
            - import_path: Relative path from import root
            - import_name: Filename
            - blob_hash: Content hash
            - blob_size: Size in bytes
    """
    entries = []

    if source_path.is_file():
        # Single file import
        blob_hash = h.hash_file(source_path)
        blob_size = source_path.stat().st_size

        entries.append(
            {
                "source_path": source_path,
                "import_path": source_path.name,
                "import_name": source_path.name,
                "blob_hash": blob_hash,
                "blob_size": blob_size,
            }
        )
    else:
        # Directory import
        for file_path in sorted(source_path.rglob("*")):
            if file_path.is_file():
                relative_path = file_path.relative_to(source_path)
                blob_hash = h.hash_file(file_path)
                blob_size = file_path.stat().st_size

                entries.append(
                    {
                        "source_path": file_path,
                        "import_path": str(relative_path),
                        "import_name": file_path.name,
                        "blob_hash": blob_hash,
                        "blob_size": blob_size,
                    }
                )

    return entries


def get_next_sequence(warehouse_root: Path) -> int:
    """Get the next sequence number for a log entry.

    Args:
        warehouse_root: Warehouse root directory

    Returns:
        int: Next sequence number
    """
    log_dir = warehouse_root / "_log"
    if not log_dir.exists():
        return 1

    # Find highest existing sequence number
    max_seq = 0
    for entry in log_dir.iterdir():
        if entry.is_dir() and "_drop" in entry.name:
            # Extract sequence from NNNN_drop
            parts = entry.name.split("_", 1)
            if parts[0].isdigit():
                max_seq = max(max_seq, int(parts[0]))

    return max_seq + 1


def fs_import(
    warehouse_root: Path,
    source_path: Path,
    message: str | None = None,
    header_json: str | None = None,
) -> str:
    """Import filesystem content as a new drop.

    Workflow:
    1. Acquire lock on state.db
    2. Scan source directory, compute blob hashes
    3. Allocate next sequence number
    4. Compute drop integrity hash
    5. Generate drop_id
    6. Write to temp folder _log/_tmp_NNNN_drop/
    7. Rename to _log/NNNN_drop/
    8. Update state.db (applied_log, drops)
    9. Release lock
    10. Return drop_id

    Args:
        warehouse_root: Warehouse root directory
        source_path: Source file or directory to import
        message: Optional drop message
        header_json: Optional JSON string with additional metadata

    Returns:
        str: Drop ID

    Raises:
        FileNotFoundError: If source path doesn't exist
    """
    if not source_path.exists():
        raise FileNotFoundError(f"Source path not found: {source_path}")

    # Parse user-provided header
    user_header = {}
    if header_json:
        user_header = json.loads(header_json)
    if message:
        user_header["message"] = message

    # Scan source and compute blob hashes
    entries = scan_directory(source_path)

    # Acquire lock and proceed with import
    db_path = warehouse_root / "state.db"
    conn = db.get_connection(db_path)

    try:
        # Lock database for exclusive access
        conn.execute("BEGIN EXCLUSIVE")

        # Allocate sequence number
        seq = get_next_sequence(warehouse_root)

        # Create timestamp
        timestamp = datetime.now(UTC)

        # Build drop header (without drop_id yet)
        header = {
            "created_at": timestamp.isoformat(),
            "source": "fs-import",
            "import_root": str(source_path.resolve()),
            **user_header,
        }

        # Compute drop integrity hash
        entries_for_hash = [
            {
                "import_path": e["import_path"],
                "import_name": e["import_name"],
                "blob_hash": e["blob_hash"],
                "blob_size": e["blob_size"],
            }
            for e in entries
        ]
        integrity_hash = compute_drop_integrity_hash(header, entries_for_hash)

        # Generate drop_id and add to header
        drop_id = generate_drop_id(timestamp, integrity_hash)
        header["drop_id"] = drop_id

        # Write to temporary folder
        log_dir = warehouse_root / "_log"
        log_dir.mkdir(parents=True, exist_ok=True)

        temp_dir = log_dir / f"_tmp_{seq:04d}_drop"
        temp_dir.mkdir(exist_ok=True)

        # Write header.json
        header_path = temp_dir / "header.json"
        with open(header_path, "w") as f:
            json.dump(header, f, indent=2)

        # Write entries.jsonl
        entries_path = temp_dir / "entries.jsonl"
        with open(entries_path, "w") as f:
            for entry in entries_for_hash:
                f.write(json.dumps(entry) + "\n")

        # Copy blobs
        blobs_dir = temp_dir / "blobs"
        blobs_dir.mkdir(exist_ok=True)

        for entry in entries:
            source_file = entry["source_path"]
            _, hex_digest = h.parse_hash(entry["blob_hash"])
            blob_path = blobs_dir / hex_digest

            # Copy blob (dedup happens naturally if hash already exists)
            if not blob_path.exists():
                shutil.copy2(source_file, blob_path)

        # Atomic rename
        final_dir = log_dir / f"{seq:04d}_drop"
        temp_dir.rename(final_dir)

        # Update state.db
        conn.execute(
            "INSERT INTO applied_log (seq, entry_name, applied_at) VALUES (?, ?, ?)",
            (seq, f"{seq:04d}_drop", timestamp.isoformat()),
        )

        total_bytes = sum(e["blob_size"] for e in entries)
        conn.execute(
            """
            INSERT INTO drops (drop_id, seq, created_at, message, document_count, total_bytes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                drop_id,
                seq,
                timestamp.isoformat(),
                user_header.get("message"),
                len(entries),
                total_bytes,
            ),
        )

        conn.commit()

        return drop_id

    finally:
        conn.close()


def list_drops(warehouse_root: Path) -> list[dict]:
    """List all drops in the warehouse.

    Args:
        warehouse_root: Warehouse root directory

    Returns:
        list[dict]: List of drop metadata dicts with:
            - drop_id
            - created_at
            - message (optional)
            - document_count
            - total_bytes
    """
    db_path = warehouse_root / "state.db"
    conn = db.get_connection(db_path)

    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT drop_id, created_at, message, document_count, total_bytes
            FROM drops
            ORDER BY seq
            """
        )

        drops = []
        for row in cursor.fetchall():
            drops.append(
                {
                    "drop_id": row[0],
                    "created_at": row[1],
                    "message": row[2],
                    "document_count": row[3],
                    "total_bytes": row[4],
                }
            )

        return drops

    finally:
        conn.close()


def inspect_drop(warehouse_root: Path, drop_id: str) -> dict:
    """Inspect a drop in detail.

    Args:
        warehouse_root: Warehouse root directory
        drop_id: Drop ID to inspect

    Returns:
        dict: Drop details including:
            - drop_id
            - created_at
            - message (if present)
            - document_count
            - total_bytes
            - header (full drop header)
            - log_location (path to drop in _log)

    Raises:
        ValueError: If drop not found
    """
    # Get basic info from state.db
    db_path = warehouse_root / "state.db"
    conn = db.get_connection(db_path)

    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT seq, created_at, message, document_count, total_bytes
            FROM drops
            WHERE drop_id = ?
            """,
            (drop_id,),
        )

        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Drop not found: {drop_id}")

        seq = row[0]
        log_location = warehouse_root / "_log" / f"{seq:04d}_drop"

    finally:
        conn.close()

    # Read full header from log
    header_path = log_location / "header.json"
    if not header_path.exists():
        raise ValueError(f"Drop header not found at {header_path}")

    with open(header_path) as f:
        header = json.load(f)

    # Build result
    result = {
        "drop_id": drop_id,
        "created_at": header.get("created_at"),
        "message": header.get("message"),
        "document_count": row[3],
        "total_bytes": row[4],
        "header": header,
        "log_location": str(log_location),
    }

    return result
