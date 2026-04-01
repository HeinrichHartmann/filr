"""End-to-end tests for drop export and fs-export with comprehensive roundtrip validation."""

import hashlib
import json
from pathlib import Path

from filr.cli import main


def compute_file_md5(path: Path) -> str:
    """Compute MD5 hash of file for comparison."""
    hasher = hashlib.md5()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def compare_directory_trees(dir1: Path, dir2: Path) -> tuple[bool, str]:
    """Compare two directory trees recursively.

    Returns:
        tuple: (is_identical, error_message)
    """
    # Get all files in both directories
    files1 = {f.relative_to(dir1): f for f in dir1.rglob("*") if f.is_file()}
    files2 = {f.relative_to(dir2): f for f in dir2.rglob("*") if f.is_file()}

    # Check for missing files
    missing_in_dir2 = files1.keys() - files2.keys()
    if missing_in_dir2:
        return False, f"Files missing in dir2: {missing_in_dir2}"

    extra_in_dir2 = files2.keys() - files1.keys()
    if extra_in_dir2:
        return False, f"Extra files in dir2: {extra_in_dir2}"

    # Compare content of each file
    for rel_path in files1.keys():
        hash1 = compute_file_md5(files1[rel_path])
        hash2 = compute_file_md5(files2[rel_path])
        if hash1 != hash2:
            return False, f"Content mismatch: {rel_path}"

    return True, ""


# ========== CAS Export Tests ==========


def test_drop_export_cas_structure(cli_runner, tmp_warehouse, sample_files):
    """Test that export creates correct CAS structure."""
    cli_runner.invoke(main, ["warehouse", "init"])
    result = cli_runner.invoke(main, ["drop", "fs-import", str(sample_files)])
    drop_id = result.output.strip()

    export_dir = tmp_warehouse / "exported_cas"
    result = cli_runner.invoke(main, ["drop", "export", drop_id, str(export_dir)])
    assert result.exit_code == 0

    # Verify structure
    assert (export_dir / "header.json").exists()
    assert (export_dir / "entries.jsonl").exists()
    assert (export_dir / "blobs").is_dir()


def test_drop_export_cas_blob_content_matches(cli_runner, tmp_warehouse, sample_files):
    """Test that exported blobs have identical content to originals."""
    cli_runner.invoke(main, ["warehouse", "init"])
    result = cli_runner.invoke(main, ["drop", "fs-import", str(sample_files)])
    drop_id = result.output.strip()

    export_dir = tmp_warehouse / "exported_cas"
    cli_runner.invoke(main, ["drop", "export", drop_id, str(export_dir)])

    # Read entries to find blobs
    with open(export_dir / "entries.jsonl") as f:
        entries = [json.loads(line) for line in f]

    # Verify each blob matches original file
    for entry in entries:
        import_path = entry["import_path"]
        blob_hash = entry["blob_hash"]
        hex_digest = blob_hash.split(":")[1]

        # Original file
        original_file = sample_files / import_path
        # Exported blob
        exported_blob = export_dir / "blobs" / hex_digest

        # Compare content
        assert original_file.read_bytes() == exported_blob.read_bytes()


def test_drop_export_cas_metadata_intact(cli_runner, tmp_warehouse, sample_files):
    """Test that exported header and entries match warehouse."""
    cli_runner.invoke(main, ["warehouse", "init"])
    result = cli_runner.invoke(
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
    drop_id = result.output.strip()

    export_dir = tmp_warehouse / "exported_cas"
    cli_runner.invoke(main, ["drop", "export", drop_id, str(export_dir)])

    # Read exported header
    with open(export_dir / "header.json") as f:
        header = json.load(f)

    assert header["drop_id"] == drop_id
    assert header["message"] == "test message"
    assert header["actor"] == "tester"
    assert header["source"] == "fs-import"


# ========== Filesystem Export Tests ==========


def test_drop_fs_export_structure(cli_runner, tmp_warehouse, sample_files):
    """Test that fs-export creates correct filesystem structure."""
    cli_runner.invoke(main, ["warehouse", "init"])
    result = cli_runner.invoke(main, ["drop", "fs-import", str(sample_files)])
    drop_id = result.output.strip()

    export_dir = tmp_warehouse / "exported_fs"
    result = cli_runner.invoke(main, ["drop", "fs-export", drop_id, str(export_dir)])
    assert result.exit_code == 0

    # Verify structure
    assert (export_dir / "header.json").exists()
    assert (export_dir / "entries.jsonl").exists()
    assert (export_dir / "root").is_dir()


def test_drop_fs_export_filesystem_tree_matches(cli_runner, tmp_warehouse, sample_files):
    """Test that fs-export reconstructs original filesystem tree exactly."""
    cli_runner.invoke(main, ["warehouse", "init"])
    result = cli_runner.invoke(main, ["drop", "fs-import", str(sample_files)])
    drop_id = result.output.strip()

    export_dir = tmp_warehouse / "exported_fs"
    cli_runner.invoke(main, ["drop", "fs-export", drop_id, str(export_dir)])

    # Compare original with exported root/
    exported_root = export_dir / "root"
    is_identical, error = compare_directory_trees(sample_files, exported_root)

    assert is_identical, f"Filesystem trees don't match: {error}"


def test_drop_fs_export_single_file(cli_runner, tmp_warehouse, tmp_path):
    """Test fs-export with single file import."""
    cli_runner.invoke(main, ["warehouse", "init"])

    single_file = tmp_path / "single.txt"
    single_file.write_text("single file content")

    result = cli_runner.invoke(main, ["drop", "fs-import", str(single_file)])
    drop_id = result.output.strip()

    export_dir = tmp_path / "exported"
    cli_runner.invoke(main, ["drop", "fs-export", drop_id, str(export_dir)])

    # Verify exported file
    exported_file = export_dir / "root" / "single.txt"
    assert exported_file.exists()
    assert exported_file.read_text() == "single file content"


# ========== Roundtrip Tests ==========


def test_roundtrip_fs_export_reimport_identical(cli_runner, tmp_warehouse, sample_files):
    """Test import → fs-export → re-import produces identical hashes."""
    cli_runner.invoke(main, ["warehouse", "init"])

    # First import
    result1 = cli_runner.invoke(main, ["drop", "fs-import", str(sample_files), "-m", "first"])
    drop_id1 = result1.output.strip()

    # Export
    export_dir = tmp_warehouse / "exported"
    cli_runner.invoke(main, ["drop", "fs-export", drop_id1, str(export_dir)])

    # Re-import from exported root/
    exported_root = export_dir / "root"
    result2 = cli_runner.invoke(main, ["drop", "fs-import", str(exported_root), "-m", "second"])
    _drop_id2 = result2.output.strip()  # Verify import succeeds

    # Compare entries from both drops
    log_dir = tmp_warehouse / "_log"

    with open(log_dir / "0001_drop" / "entries.jsonl") as f:
        entries1 = [json.loads(line) for line in f]

    with open(log_dir / "0002_drop" / "entries.jsonl") as f:
        entries2 = [json.loads(line) for line in f]

    # Should have same number of documents
    assert len(entries1) == len(entries2)

    # All blob hashes should match (same content)
    hashes1 = sorted([e["blob_hash"] for e in entries1])
    hashes2 = sorted([e["blob_hash"] for e in entries2])
    assert hashes1 == hashes2


def test_roundtrip_nested_directories(cli_runner, tmp_warehouse, tmp_path):
    """Test roundtrip with deeply nested directory structure."""
    cli_runner.invoke(main, ["warehouse", "init"])

    # Create nested structure
    source = tmp_path / "source"
    (source / "a" / "b" / "c").mkdir(parents=True)
    (source / "a" / "file1.txt").write_text("file1")
    (source / "a" / "b" / "file2.txt").write_text("file2")
    (source / "a" / "b" / "c" / "file3.txt").write_text("file3")

    # Import
    result = cli_runner.invoke(main, ["drop", "fs-import", str(source)])
    drop_id = result.output.strip()

    # Export
    export_dir = tmp_path / "exported"
    cli_runner.invoke(main, ["drop", "fs-export", drop_id, str(export_dir)])

    # Compare
    exported_root = export_dir / "root"
    is_identical, error = compare_directory_trees(source, exported_root)
    assert is_identical, f"Nested directory roundtrip failed: {error}"


def test_roundtrip_empty_files(cli_runner, tmp_warehouse, tmp_path):
    """Test roundtrip with empty files."""
    cli_runner.invoke(main, ["warehouse", "init"])

    source = tmp_path / "source"
    source.mkdir()
    (source / "empty.txt").write_text("")
    (source / "nonempty.txt").write_text("content")

    result = cli_runner.invoke(main, ["drop", "fs-import", str(source)])
    drop_id = result.output.strip()

    export_dir = tmp_path / "exported"
    cli_runner.invoke(main, ["drop", "fs-export", drop_id, str(export_dir)])

    exported_root = export_dir / "root"
    is_identical, error = compare_directory_trees(source, exported_root)
    assert is_identical, f"Empty file roundtrip failed: {error}"


def test_roundtrip_special_filenames(cli_runner, tmp_warehouse, tmp_path):
    """Test roundtrip with special characters in filenames."""
    cli_runner.invoke(main, ["warehouse", "init"])

    source = tmp_path / "source"
    source.mkdir()
    (source / "file with spaces.txt").write_text("spaces")
    (source / "file-with-dashes.txt").write_text("dashes")
    (source / "file_with_underscores.txt").write_text("underscores")

    result = cli_runner.invoke(main, ["drop", "fs-import", str(source)])
    drop_id = result.output.strip()

    export_dir = tmp_path / "exported"
    cli_runner.invoke(main, ["drop", "fs-export", drop_id, str(export_dir)])

    exported_root = export_dir / "root"
    is_identical, error = compare_directory_trees(source, exported_root)
    assert is_identical, f"Special filename roundtrip failed: {error}"


# ========== Error Handling Tests ==========


def test_export_drop_not_found(cli_runner, tmp_warehouse):
    """Test export with non-existent drop."""
    cli_runner.invoke(main, ["warehouse", "init"])

    result = cli_runner.invoke(
        main, ["drop", "export", "d_20260101_000000_ffffffff", str(tmp_warehouse / "out")]
    )
    assert result.exit_code != 0
    assert "Error" in result.output or "not found" in result.output.lower()


def test_export_target_exists(cli_runner, tmp_warehouse, sample_files):
    """Test export fails if target folder exists."""
    cli_runner.invoke(main, ["warehouse", "init"])
    result = cli_runner.invoke(main, ["drop", "fs-import", str(sample_files)])
    drop_id = result.output.strip()

    # Create target folder
    export_dir = tmp_warehouse / "exported"
    export_dir.mkdir()

    result = cli_runner.invoke(main, ["drop", "export", drop_id, str(export_dir)])
    assert result.exit_code != 0
    assert "Error" in result.output or "exists" in result.output.lower()


def test_fs_export_target_exists(cli_runner, tmp_warehouse, sample_files):
    """Test fs-export fails if target folder exists."""
    cli_runner.invoke(main, ["warehouse", "init"])
    result = cli_runner.invoke(main, ["drop", "fs-import", str(sample_files)])
    drop_id = result.output.strip()

    # Create target folder
    export_dir = tmp_warehouse / "exported"
    export_dir.mkdir()

    result = cli_runner.invoke(main, ["drop", "fs-export", drop_id, str(export_dir)])
    assert result.exit_code != 0
    assert "Error" in result.output or "exists" in result.output.lower()


# ========== Large-scale Roundtrip Test ==========


def test_roundtrip_multiple_files_large_scale(cli_runner, tmp_warehouse, tmp_path):
    """Test roundtrip with many files to ensure scalability."""
    cli_runner.invoke(main, ["warehouse", "init"])

    # Create 50 files in various directories
    source = tmp_path / "source"
    for i in range(10):
        dir_path = source / f"dir{i}"
        dir_path.mkdir(parents=True)
        for j in range(5):
            file_path = dir_path / f"file{j}.txt"
            file_path.write_text(f"content_{i}_{j}")

    # Import
    result = cli_runner.invoke(main, ["drop", "fs-import", str(source)])
    drop_id = result.output.strip()

    # Export
    export_dir = tmp_path / "exported"
    cli_runner.invoke(main, ["drop", "fs-export", drop_id, str(export_dir)])

    # Compare
    exported_root = export_dir / "root"
    is_identical, error = compare_directory_trees(source, exported_root)
    assert is_identical, f"Large-scale roundtrip failed: {error}"

    # Re-import and verify hashes
    result2 = cli_runner.invoke(main, ["drop", "fs-import", str(exported_root)])
    _drop_id2 = result2.output.strip()  # Verify import succeeds

    # Compare blob hashes
    log_dir = tmp_warehouse / "_log"
    with open(log_dir / "0001_drop" / "entries.jsonl") as f:
        entries1 = [json.loads(line) for line in f]
    with open(log_dir / "0002_drop" / "entries.jsonl") as f:
        entries2 = [json.loads(line) for line in f]

    hashes1 = sorted([e["blob_hash"] for e in entries1])
    hashes2 = sorted([e["blob_hash"] for e in entries2])
    assert hashes1 == hashes2, "Blob hashes don't match after large-scale roundtrip"
