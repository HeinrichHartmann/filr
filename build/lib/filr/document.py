"""Document operations - URL parsing and content resolution."""

import json
from pathlib import Path

from . import drop as drop_mod


def parse_drop_url(url: str) -> tuple[str, str]:
    """Parse drop:// URL into (drop_id, import_path).

    Args:
        url: Drop URL in format drop://<drop_id>/<import_path>

    Returns:
        tuple[str, str]: (drop_id, import_path)

    Raises:
        ValueError: If URL format is invalid

    Examples:
        >>> parse_drop_url("drop://d_20260401_143211_a7c3e9f1/invoice.pdf")
        ("d_20260401_143211_a7c3e9f1", "invoice.pdf")

        >>> parse_drop_url("drop://d_20260401_143211_a7c3e9f1/path/to/file.txt")
        ("d_20260401_143211_a7c3e9f1", "path/to/file.txt")
    """
    if not url.startswith("drop://"):
        raise ValueError(f"Invalid drop URL: must start with 'drop://' (got: {url})")

    # Remove drop:// prefix
    remainder = url[7:]

    # Split on first /
    parts = remainder.split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid drop URL: must be drop://<drop_id>/<import_path> (got: {url})")

    drop_id, import_path = parts

    if not drop_id:
        raise ValueError(f"Invalid drop URL: empty drop_id (got: {url})")
    if not import_path:
        raise ValueError(f"Invalid drop URL: empty import_path (got: {url})")

    return drop_id, import_path


def resolve_document(warehouse_root: Path, drop_id: str, import_path: str) -> dict:
    """Resolve document from drop.

    Args:
        warehouse_root: Warehouse root directory
        drop_id: Drop ID
        import_path: Document import path within drop

    Returns:
        dict: Document metadata with:
            - import_path: Document import path
            - import_name: Document filename
            - blob_hash: Content hash
            - blob_size: Size in bytes
            - blob_path: Absolute path to blob file
            - drop_header: Full drop header

    Raises:
        ValueError: If drop not found or document not found in drop
    """
    # Get drop details
    try:
        details = drop_mod.inspect_drop(warehouse_root, drop_id)
    except ValueError as e:
        raise ValueError(f"Drop not found: {drop_id}") from e

    log_location = Path(details["log_location"])
    entries_path = log_location / "entries.jsonl"

    # Find document in entries
    with open(entries_path) as f:
        for line in f:
            entry = json.loads(line)
            if entry["import_path"] == import_path:
                # Found it - build result
                from . import hash as h

                blob_hash = entry["blob_hash"]
                _, hex_digest = h.parse_hash(blob_hash)
                blob_path = log_location / "blobs" / hex_digest

                if not blob_path.exists():
                    raise ValueError(
                        f"Blob file not found for document: {import_path} (blob: {hex_digest})"
                    )

                # Read drop header
                header_path = log_location / "header.json"
                with open(header_path) as hf:
                    drop_header = json.load(hf)

                return {
                    "import_path": entry["import_path"],
                    "import_name": entry["import_name"],
                    "blob_hash": blob_hash,
                    "blob_size": entry["blob_size"],
                    "blob_path": str(blob_path),
                    "drop_header": drop_header,
                }

    # Document not found
    raise ValueError(f"Document not found in drop {drop_id}: {import_path}")
