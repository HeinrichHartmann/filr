"""filr CLI - Command-line interface for warehouse management."""

import json
import sys
from pathlib import Path

import click

from . import document as doc_mod
from . import drop as drop_mod
from . import warehouse as wh


@click.group()
@click.version_option()
def main():
    """filr - A history-aware store of immutable drops for document management.

    Manage warehouses, drops, and documents through a clean CLI interface.
    """
    pass


@main.group()
def warehouse():
    """Manage warehouse operations."""
    pass


@main.group()
def drop():
    """Manage drop operations."""
    pass


@main.group()
def document():
    """Inspect documents."""
    pass


@warehouse.command("init")
@click.argument("name", required=False)
def warehouse_init(name):
    """Initialize a warehouse at the resolved warehouse root."""
    root = wh.get_warehouse_root()
    actual_name = name or "main"

    try:
        wh.init_warehouse(root, name)
        click.echo(f"Initialized warehouse at {root}")
        click.echo(f"Warehouse name: {actual_name}")
    except FileExistsError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@warehouse.command("stats")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def warehouse_stats(output_json):
    """Show warehouse summary statistics."""
    warehouse_root = wh.get_warehouse_root()

    try:
        stats = wh.get_stats(warehouse_root)

        if output_json:
            click.echo(json.dumps(stats, indent=2))
        else:
            # Human-readable format
            click.echo(f"Warehouse root:    {stats['warehouse_root']}")
            click.echo(f"Warehouse name:    {stats['warehouse_name']}")
            click.echo(f"Created:           {stats['created_at']}")
            click.echo(f"Drop count:        {stats['drop_count']}")
            click.echo(f"Document count:    {stats['document_count']}")

            # Format total bytes
            total_bytes = stats["total_bytes"]
            if total_bytes < 1024:
                size_str = f"{total_bytes} bytes"
            elif total_bytes < 1024 * 1024:
                size_str = f"{total_bytes / 1024:.2f} KB"
            elif total_bytes < 1024 * 1024 * 1024:
                size_str = f"{total_bytes / (1024 * 1024):.2f} MB"
            else:
                size_str = f"{total_bytes / (1024 * 1024 * 1024):.2f} GB"

            click.echo(f"Total size:        {size_str}")

    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@warehouse.command("check")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def warehouse_check(output_json):
    """Run a full warehouse integrity and consistency check."""
    warehouse_root = wh.get_warehouse_root()

    try:
        errors = wh.check(warehouse_root)

        if output_json:
            result = {"errors": errors, "ok": len(errors) == 0}
            click.echo(json.dumps(result, indent=2))
            sys.exit(0 if len(errors) == 0 else 1)
        else:
            if not errors:
                click.echo("OK - Warehouse integrity check passed")
                sys.exit(0)
            else:
                click.echo(f"FAILED - Found {len(errors)} error(s):", err=True)
                for error in errors:
                    click.echo(f"  - {error}", err=True)
                sys.exit(1)

    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@warehouse.command("log")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def warehouse_log(output_json):
    """Show the warehouse transaction log."""
    warehouse_root = wh.get_warehouse_root()

    try:
        entries = wh.get_log(warehouse_root)

        if output_json:
            click.echo(json.dumps(entries, indent=2))
        else:
            # Human-readable table
            if not entries:
                click.echo("No log entries found")
                return

            # Header
            click.echo(f"{'Seq':>4}  {'Entry Name':<20}  {'Applied At'}")
            click.echo("-" * 60)

            # Rows
            for entry in entries:
                seq = entry["seq"]
                entry_name = entry["entry_name"]
                applied_at = entry["applied_at"][:19]  # Truncate timestamp

                click.echo(f"{seq:>4}  {entry_name:<20}  {applied_at}")

    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@warehouse.command("rebuild")
def warehouse_rebuild():
    """Rebuild derived warehouse state from the transaction log."""
    warehouse_root = wh.get_warehouse_root()

    try:
        click.echo(f"Rebuilding warehouse at {warehouse_root}...")
        wh.rebuild(warehouse_root)
        click.echo("Warehouse rebuilt successfully")
        sys.exit(0)

    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@drop.command("list")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def drop_list(output_json):
    """List all drops in the warehouse."""
    warehouse_root = wh.get_warehouse_root()

    if not wh.warehouse_exists(warehouse_root):
        click.echo(f"Error: No warehouse found at {warehouse_root}", err=True)
        sys.exit(1)

    try:
        drops = drop_mod.list_drops(warehouse_root)

        if output_json:
            click.echo(json.dumps(drops, indent=2))
        else:
            # Human-readable table
            if not drops:
                click.echo("No drops found")
                return

            # Header
            click.echo(f"{'Drop ID':<36} {'Created':<20} {'Docs':>6} {'Size':>10} Message")
            click.echo("-" * 100)

            # Rows
            for d in drops:
                drop_id = d["drop_id"]
                created = d["created_at"][:19]  # Truncate timestamp
                doc_count = d["document_count"]
                total_bytes = d["total_bytes"]
                message = d.get("message") or ""

                # Format size
                if total_bytes < 1024:
                    size_str = f"{total_bytes}B"
                elif total_bytes < 1024 * 1024:
                    size_str = f"{total_bytes / 1024:.1f}KB"
                else:
                    size_str = f"{total_bytes / (1024 * 1024):.1f}MB"

                click.echo(f"{drop_id:<36} {created:<20} {doc_count:>6} {size_str:>10} {message}")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@drop.command("inspect")
@click.argument("drop_id")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def drop_inspect(drop_id, output_json):
    """Inspect one drop in detail."""
    warehouse_root = wh.get_warehouse_root()

    if not wh.warehouse_exists(warehouse_root):
        click.echo(f"Error: No warehouse found at {warehouse_root}", err=True)
        sys.exit(1)

    try:
        details = drop_mod.inspect_drop(warehouse_root, drop_id)

        if output_json:
            click.echo(json.dumps(details, indent=2))
        else:
            # Human-readable format
            click.echo(f"Drop ID:         {details['drop_id']}")
            click.echo(f"Created:         {details['created_at']}")
            if details.get("message"):
                click.echo(f"Message:         {details['message']}")
            click.echo(f"Document count:  {details['document_count']}")
            click.echo(f"Total bytes:     {details['total_bytes']}")
            click.echo(f"Log location:    {details['log_location']}")

            # Show additional header fields
            header = details["header"]
            extra_fields = {
                k: v for k, v in header.items() if k not in ["drop_id", "created_at", "message"]
            }
            if extra_fields:
                click.echo("\nAdditional metadata:")
                for key, value in extra_fields.items():
                    click.echo(f"  {key}: {value}")

    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@drop.command("fs-import")
@click.argument("path", type=click.Path(exists=True))
@click.option("-m", "--message", help="Drop message")
@click.option("-H", "--header", "header_json", help="Additional JSON metadata")
def drop_fs_import(path, message, header_json):
    """Import filesystem content as a new drop."""
    warehouse_root = wh.get_warehouse_root()

    if not wh.warehouse_exists(warehouse_root):
        click.echo(f"Error: No warehouse found at {warehouse_root}", err=True)
        click.echo("Run 'filr warehouse init' first", err=True)
        sys.exit(1)

    try:
        source_path = Path(path)
        drop_id = drop_mod.fs_import(warehouse_root, source_path, message, header_json)
        click.echo(drop_id)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@drop.command("fs-export")
@click.argument("drop_id")
@click.argument("folder", type=click.Path())
def drop_fs_export(drop_id, folder):
    """Export a drop using the default filesystem realization."""
    warehouse_root = wh.get_warehouse_root()

    if not wh.warehouse_exists(warehouse_root):
        click.echo(f"Error: No warehouse found at {warehouse_root}", err=True)
        sys.exit(1)

    try:
        target_folder = Path(folder)
        drop_mod.fs_export_drop(warehouse_root, drop_id, target_folder)
        click.echo(f"Exported drop {drop_id} to {folder}")
        click.echo(f"Filesystem tree in: {folder}/root/")
    except FileExistsError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@drop.command("export")
@click.argument("drop_id")
@click.argument("folder", type=click.Path())
def drop_export(drop_id, folder):
    """Export a drop in pure canonical CAS form."""
    warehouse_root = wh.get_warehouse_root()

    if not wh.warehouse_exists(warehouse_root):
        click.echo(f"Error: No warehouse found at {warehouse_root}", err=True)
        sys.exit(1)

    try:
        target_folder = Path(folder)
        drop_mod.export_drop(warehouse_root, drop_id, target_folder)
        click.echo(f"Exported drop {drop_id} (CAS) to {folder}")
        click.echo("Structure: header.json, entries.jsonl, blobs/")
    except FileExistsError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@document.command("head")
@click.argument("drop_url")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def document_head(drop_url, output_json):
    """Show formatted document metadata."""
    warehouse_root = wh.get_warehouse_root()

    try:
        # Parse URL
        drop_id, import_path = doc_mod.parse_drop_url(drop_url)

        # Resolve document
        doc = doc_mod.resolve_document(warehouse_root, drop_id, import_path)

        if output_json:
            # JSON output
            output = {
                "import_path": doc["import_path"],
                "import_name": doc["import_name"],
                "blob_hash": doc["blob_hash"],
                "blob_size": doc["blob_size"],
                "drop_id": doc["drop_header"]["drop_id"],
                "drop_message": doc["drop_header"].get("message"),
                "drop_created_at": doc["drop_header"]["created_at"],
            }
            click.echo(json.dumps(output, indent=2))
        else:
            # Human-readable format
            click.echo(f"Import path:  {doc['import_path']}")
            click.echo(f"Import name:  {doc['import_name']}")
            click.echo(f"Blob hash:    {doc['blob_hash']}")
            click.echo(f"Blob size:    {doc['blob_size']}")
            click.echo(f"Drop ID:      {doc['drop_header']['drop_id']}")
            if doc["drop_header"].get("message"):
                click.echo(f"Drop message: {doc['drop_header']['message']}")
            click.echo(f"Drop created: {doc['drop_header']['created_at']}")

    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@document.command("body")
@click.argument("drop_url")
def document_body(drop_url):
    """Print raw document body bytes."""
    warehouse_root = wh.get_warehouse_root()

    try:
        # Parse URL
        drop_id, import_path = doc_mod.parse_drop_url(drop_url)

        # Resolve document
        doc = doc_mod.resolve_document(warehouse_root, drop_id, import_path)

        # Read blob and output to stdout (binary mode)
        blob_path = Path(doc["blob_path"])
        with open(blob_path, "rb") as f:
            sys.stdout.buffer.write(f.read())

    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@document.command("show")
@click.argument("drop_url")
def document_show(drop_url):
    """Show metadata plus body in a human-oriented way."""
    warehouse_root = wh.get_warehouse_root()

    try:
        # Parse URL
        drop_id, import_path = doc_mod.parse_drop_url(drop_url)

        # Resolve document
        doc = doc_mod.resolve_document(warehouse_root, drop_id, import_path)

        # Show metadata
        click.echo("--- Metadata ---")
        click.echo(f"Import path: {doc['import_path']}")
        click.echo(f"Import name: {doc['import_name']}")
        click.echo(f"Blob size:   {doc['blob_size']}")
        click.echo(f"Blob hash:   {doc['blob_hash']}")
        click.echo(f"Drop ID:     {doc['drop_header']['drop_id']}")
        if doc["drop_header"].get("message"):
            click.echo(f"Drop message: {doc['drop_header']['message']}")

        # Try to show content
        click.echo("\n--- Content ---")
        blob_path = Path(doc["blob_path"])

        # Read first 4KB to detect if binary
        with open(blob_path, "rb") as f:
            sample = f.read(4096)

        # Simple heuristic: if null bytes present, treat as binary
        if b"\x00" in sample:
            click.echo("(Binary content - use 'document body' to extract)")
        else:
            # Try to decode as text
            try:
                with open(blob_path, encoding="utf-8") as f:
                    content = f.read(2048)  # Read first 2KB
                    click.echo(content)
                    if len(content) >= 2048:
                        click.echo("\n(Content truncated - use 'document body' for full content)")
            except UnicodeDecodeError:
                click.echo("(Binary content - use 'document body' to extract)")

    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
