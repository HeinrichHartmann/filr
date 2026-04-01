"""Hashing utilities using blake3."""

from pathlib import Path

import blake3


def hash_bytes(data: bytes) -> str:
    """Compute blake3 hash of bytes.

    Args:
        data: Bytes to hash

    Returns:
        str: Hash in format "blake3:hexdigest"
    """
    hasher = blake3.blake3(data)
    return f"blake3:{hasher.hexdigest()}"


def hash_file(path: Path) -> str:
    """Compute blake3 hash of a file.

    Args:
        path: Path to file

    Returns:
        str: Hash in format "blake3:hexdigest"
    """
    hasher = blake3.blake3()
    with open(path, "rb") as f:
        while chunk := f.read(65536):  # 64KB chunks
            hasher.update(chunk)
    return f"blake3:{hasher.hexdigest()}"


def hash_dict(data: dict) -> str:
    """Compute blake3 hash of a dict (via JSON serialization).

    Args:
        data: Dictionary to hash

    Returns:
        str: Hash in format "blake3:hexdigest"

    Note:
        Uses canonical JSON serialization (sorted keys, no whitespace)
    """
    import json

    serialized = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hash_bytes(serialized.encode("utf-8"))


def verify_hash(data: bytes, expected_hash: str) -> bool:
    """Verify that data matches expected hash.

    Args:
        data: Data to verify
        expected_hash: Expected hash in format "blake3:hexdigest"

    Returns:
        bool: True if hash matches
    """
    actual_hash = hash_bytes(data)
    return actual_hash == expected_hash


def parse_hash(hash_str: str) -> tuple[str, str]:
    """Parse a hash string into algorithm and digest.

    Args:
        hash_str: Hash in format "algorithm:hexdigest"

    Returns:
        tuple: (algorithm, hexdigest)

    Raises:
        ValueError: If hash format is invalid
    """
    if ":" not in hash_str:
        raise ValueError(f"Invalid hash format: {hash_str}")

    parts = hash_str.split(":", 1)
    return parts[0], parts[1]
