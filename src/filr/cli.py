"""filr CLI - Command-line interface for warehouse management."""

import sys
import click

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

    try:
        wh.init_warehouse(root, name)
        click.echo(f"Initialized warehouse at {root}")
        if name:
            click.echo(f"Warehouse name: {name}")
    except FileExistsError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@warehouse.command("stats")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def warehouse_stats(output_json):
    """Show warehouse summary statistics."""
    click.echo("Warehouse stats")


@warehouse.command("check")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def warehouse_check(output_json):
    """Run a full warehouse integrity and consistency check."""
    click.echo("Checking warehouse integrity")


@warehouse.command("log")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def warehouse_log(output_json):
    """Show the warehouse transaction log."""
    click.echo("Warehouse log")


@warehouse.command("rebuild")
def warehouse_rebuild():
    """Rebuild derived warehouse state from the transaction log."""
    click.echo("Rebuilding warehouse")


@drop.command("list")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def drop_list(output_json):
    """List all drops in the warehouse."""
    click.echo("Listing drops")


@drop.command("inspect")
@click.argument("drop_id")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def drop_inspect(drop_id, output_json):
    """Inspect one drop in detail."""
    click.echo(f"Inspecting drop: {drop_id}")


@drop.command("fs-import")
@click.argument("path", type=click.Path(exists=True))
@click.option("-m", "--message", help="Drop message")
@click.option("-H", "--header", "header_json", help="Additional JSON metadata")
def drop_fs_import(path, message, header_json):
    """Import filesystem content as a new drop."""
    click.echo(f"Importing from: {path}")


@drop.command("fs-export")
@click.argument("drop_id")
@click.argument("folder", type=click.Path())
def drop_fs_export(drop_id, folder):
    """Export a drop using the default filesystem realization."""
    click.echo(f"Exporting drop {drop_id} to {folder}")


@drop.command("export")
@click.argument("drop_id")
@click.argument("folder", type=click.Path())
def drop_export(drop_id, folder):
    """Export a drop in pure canonical CAS form."""
    click.echo(f"Exporting drop {drop_id} (CAS) to {folder}")


@document.command("head")
@click.argument("drop_url")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def document_head(drop_url, output_json):
    """Show formatted document metadata."""
    click.echo(f"Document head: {drop_url}")


@document.command("body")
@click.argument("drop_url")
def document_body(drop_url):
    """Print raw document body bytes."""
    click.echo(f"Document body: {drop_url}")


@document.command("show")
@click.argument("drop_url")
def document_show(drop_url):
    """Show metadata plus body in a human-oriented way."""
    click.echo(f"Document show: {drop_url}")


if __name__ == "__main__":
    main()
