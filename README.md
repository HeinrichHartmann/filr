# filr

A history-aware store of immutable drops for document archival.

## What It Does

filr stores documents in **drops** - immutable, provenance-bearing batches. Each drop captures a meaningful context ("this import", "this scanner batch") with full metadata.

- **Durable**: Append-only transaction log is the source of truth
- **Rebuildable**: Derived state can be reconstructed from the log
- **Verifiable**: Content-addressed blobs with integrity checking

## Quick Start

```bash
# Initialize warehouse
filr warehouse init

# Import files as a drop
filr drop fs-import ~/Downloads/taxes -m "Tax documents 2025"
# d_20260401_143211_a7c3e9f1

# List drops
filr drop list

# Export drop back to filesystem
filr drop fs-export d_20260401_143211_a7c3e9f1 ./restored/

# Verify integrity
filr warehouse check
```

## Commands

```bash
# Warehouse management
filr warehouse init [name]
filr warehouse stats [--json]
filr warehouse check [--json]
filr warehouse log [--json]
filr warehouse rebuild

# Drop operations
filr drop list [--json]
filr drop inspect <drop-id> [--json]
filr drop fs-import <path> [-m MESSAGE]
filr drop fs-export <drop-id> <folder>
filr drop export <drop-id> <folder>      # canonical CAS format

# Document inspection
filr document head <drop-url> [--json]
filr document body <drop-url>
filr document show <drop-url>
```

Document URLs: `drop://<drop-id>/<path>` (e.g., `drop://d_20260401_143211_a7c3e9f1/invoice.pdf`)

## Installation

```bash
make install
```

Requires [uv](https://github.com/astral-sh/uv).

## Design

See [ADR/001-DESIGN.md](ADR/001-DESIGN.md) for the full design document.
