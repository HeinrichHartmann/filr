# filr Project Status

**Date:** 2026-04-01
**Purpose:** Comprehensive status summary for context transfer to another LLM

## 1. What is filr?

filr is a **document warehouse** - a history-aware store of immutable drops.

**Core concepts:**
- **Blob**: Immutable binary content (content-addressed, blake3 hashed)
- **Document**: Immutable metadata + one blob body
- **Drop**: Immutable collection of documents with provenance (like a git commit)
- **Filesystem views**: Derived materializations, NOT the source of truth

**One-sentence summary:**
> filr is a history-aware store of immutable drops, where each drop contains immutable documents over immutable blobs, and where user-facing filesystem access is provided through derived filesystem views rather than a single canonical archive tree.

**Key design principle:** The transaction log (`_log/`) is canonical. Everything else (state.db, filesystem views) is derived and rebuildable.

## 2. Implementation Status

### Completed (v1 Core)

| Phase | Feature | Tests | Status |
|-------|---------|-------|--------|
| 1 | CLI skeleton | - | Done |
| 2 | `warehouse init` | 8 | Done |
| 3 | `drop fs-import` | 16 | Done |
| 4 | `drop list`, `drop inspect` | 11 | Done |
| 5 | `warehouse stats`, `warehouse log` | 10 | Done |
| 6 | `warehouse rebuild`, `warehouse check` | 6 | Done |
| 7 | `drop export`, `drop fs-export` | 14 | Done |
| 8 | `document head/body/show` | 9 | Done |

**Total: 74 tests passing**

### Source Files

```
src/filr/
  __init__.py
  cli.py          # Click commands (all v1 commands implemented)
  warehouse.py    # Warehouse operations (init, stats, log, rebuild, check)
  drop.py         # Drop operations (fs-import, list, inspect, export, fs-export)
  document.py     # Document resolution (head, body, show)
  hash.py         # Blake3 hashing utilities
  db.py           # SQLite operations for state.db
```

### Working CLI

```bash
# Warehouse commands
filr warehouse init [name]
filr warehouse stats [--json]
filr warehouse log [--json]
filr warehouse rebuild
filr warehouse check [--json]

# Drop commands
filr drop list [--json]
filr drop inspect <drop-id> [--json]
filr drop fs-import <path> [-m MESSAGE] [-H HEADER_JSON]
filr drop export <drop-id> <folder>      # CAS form
filr drop fs-export <drop-id> <folder>   # filesystem tree

# Document commands
filr document head <drop-url> [--json]
filr document body <drop-url>
filr document show <drop-url>
```

## 3. Architecture Decision Records (ADRs)

### ADR-001: Design Principles
- Blob/Document/Drop hierarchy
- Documents are immutable, belong to exactly one drop
- Physical deduplication allowed, doesn't collapse logical identity
- Filesystem views are derived, not canonical
- No single canonical archive root

### ADR-002: v1 CLI Specification
- `filr <noun> <verb>` structure (warehouse/drop/document)
- Drop ID format: `d_YYYYMMDD_HHMMSS_hash8`
- Document URLs: `drop://<drop-id>/<import-path>`
- No deletion, no queries, no transforms in v1

### ADR-003: Transaction Log
- Self-contained log entries (Git-like)
- Each drop copies blobs into `_log/NNNN_drop/blobs/`
- Write log first, then apply to state.db
- Type encoded in folder name: `NNNN_drop`
- Merkle-tree integrity hash
- Atomic writes via temp folder + rename

**Warehouse layout:**
```
~/.filr/warehouse/
  config.toml           # canonical: warehouse config
  state.db              # derived: applied log tracking + indexes
  _log/                 # canonical: append-only transaction log
    0001_drop/
      header.json
      entries.jsonl
      blobs/<hash>
    0002_drop/
      ...
```

### ADR-004: Testing Strategy
- Three tiers: E2E workflows, CLI structure, unit tests
- E2E tests are backbone (import/export roundtrips, rebuild, integrity)
- Fewer high-confidence tests over many fragile unit tests
- pytest with fixtures for temporary warehouses

### ADR-005: Transforms (IN PROGRESS - NOT IMPLEMENTED)
- Transforms create new document versions with updated metadata
- Parent backlinks (no forward links)
- Transforms operate at drop level, not document level
- `archive_path` attribute determines filesystem position
- `drop://` URLs resolve to original version only

**Proposed triage workflow:**
```bash
# Import
filr drop fs-import ~/Downloads/taxes -m "Tax docs"

# Classify (sets archive_path on all docs in drop)
filr transform set d_... --field archive_path="finance/taxes/{import_name}"

# Materialize (creates filesystem view)
filr view materialize ~/Archive
```

## 4. Commit History

```
a881e5b Phase 8: Implement document commands
8fdc919 Add PLAN-2 for document commands and release prep
557822a Phase 6: Implement warehouse rebuild and check
2378d26 Add audit for Phase 5 & 7 (stats, log, export)
6363d67 Implement Phase 7: Drop export with extensive roundtrip validation
d30311e Implement Phase 5: Warehouse stats and log
5d37dea Address review feedback: Rename hash_dict to hash_json
b902142 Add review for Phase 3 & 4 (import, list, inspect)
94ea286 Implement Phase 4: Drop list and inspect
ca54d4a Implement Phase 3: Drop fs-import core functionality
837cdb5 Add pre-commit hooks for tests and linting
3aa3618 Fix CLI output to show warehouse name consistently
91bf9db Add review for Phase 2 warehouse init
10ac9fb Implement Phase 2: Warehouse initialization
28f1864 Fix -h flag conflict and add .gitignore
24ac951 Add implementation plan for v1
8e95826 Implement Phase 1: CLI skeleton with command structure
```

## 5. Design Decisions Made During Implementation

### Drop ID Hash
- Merkle-tree style: `hash(header_hash || entries_hash || blob_hash_1 || ...)`
- `drop_id` excluded from hash input (would be circular)
- First 8 hex chars used in ID

### Atomic Imports
- Write to `_log/_tmp_NNNN_drop/`
- Atomic rename to `_log/NNNN_drop/`
- Exclusive lock on state.db during import

### No Concurrent Imports
- Global lock prevents race conditions
- Simplifies sequence number allocation

### Flag Conflict Fix
- `-h` conflicts with `--help`
- Changed to `-H` for `--header` option

## 6. What's NOT Implemented Yet

### From ADR-002 (should be in v1 but deferred):
- None - all v1 CLI commands are implemented

### From ADR-005 (future):
- `filr transform set` - metadata transforms
- `filr view materialize` - filesystem views
- `archive_path` attribute
- Document versioning / parent links
- fs-view workflow for triage

### Explicitly out of scope:
- Query language
- Metadata transformations
- Document mutation
- Drop deletion
- Multi-warehouse management
- Remote sync / federation

## 7. Open Design Questions

### Triage Workflow
How do users classify documents quickly after import?

**Options discussed:**
1. **Batch transforms**: `transform set --field archive_path="..."` on entire drops
2. **Filters**: `--filter "*.pdf"` to select subsets
3. **fs-view**: Create working directory, organize in Finder, sync changes back
4. **Manifest file**: Generate JSONL, edit, apply
5. **Mount (NFS/FUSE)**: Virtual filesystem that tracks changes (complex, fragile)

**Current recommendation:** Simple batch transforms + filters for v1. fs-view or manifest for v2.

### archive_path Semantics
- Full path including filename: `finance/taxes/2025/w2.pdf`
- Template expansion: `{import_name}`, `{drop_date}`, `{ext}`
- Documents without archive_path excluded from materialized views

## 8. File Inventory

```
ADR/
  001-DESIGN.md           # Core design principles
  002-V1-CLI.md           # CLI specification
  003-TRANSACTION-LOG.md  # Log format and integrity
  004-TESTING-STRATEGY.md # Testing approach
  005-TRANSFORMS.md       # Metadata transforms (in progress)

PLAN.md                   # Phases 1-6 implementation plan
PLAN-2.md                 # Phases 8-9 (document commands, release)

REVIEW/
  002-phase-2-init.md     # Phase 2 audit
  003-phase5-7-stats-log-export.md  # Phase 5,7 audit

src/filr/                 # Implementation
tests/e2e/                # End-to-end tests (74 passing)
```

## 9. How to Continue

### Immediate next steps:
1. Write README.md with installation and usage
2. Tag v0.1.0 release
3. Begin ADR-005 implementation (transforms)

### For transforms implementation:
1. Add `transforms` table to state.db schema
2. Implement `filr transform set <drop-id> --field key=value`
3. Implement `document_versions` table for tracking latest versions
4. Add `filr view materialize` for filesystem views

### Key invariants to maintain:
- Transaction log is canonical, state.db is derived
- Drops and documents are immutable
- `warehouse rebuild` must always work
- `warehouse check` must detect corruption

## 10. Context for LLM

When working on this codebase:

1. **Read ADRs first** - they define the design constraints
2. **Run tests often** - `uv run pytest tests/`
3. **Maintain immutability** - never mutate log entries
4. **Write log first** - then update state.db
5. **Use blake3** - not sha256 or other hashes
6. **Template expansion** - `{import_name}` patterns for archive_path

The codebase is clean and well-tested. The main work remaining is the transform/view layer for organizing documents after import.
