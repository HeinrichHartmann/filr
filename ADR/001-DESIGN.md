## 1. Purpose

The warehouse is a system for storing, organizing, and retrieving human-relevant document batches with strong provenance, replayability, and flexible filesystem materializations.

It is **not** primarily a filesystem.
It is **not** primarily a blob store.
It is **not** primarily an analytics data warehouse.

The cleanest current framing is:

> The warehouse is a history-aware store of immutable drops.
> A drop is an immutable provenance-bearing collection of immutable documents.
> A document is immutable metadata plus one blob body.
> Filesystem views are derived materializations of warehouse state.

---

## 2. Design principles

### 2.1 Small logical model

The logical model should stay as small as possible.

Scalability concerns matter, but they should constrain implementation choices rather than force premature logical abstractions.

### 2.2 Immutable logical objects

The core logical objects are immutable.

This makes provenance, replayability, and storage semantics much cleaner.

### 2.3 Provenance at human context boundaries

A drop is not just a storage package.
It is also a provenance unit that corresponds to a meaningful human or system context, such as:

* “this import batch”
* “this filing session”
* “this scanner upload”
* “this derived output batch”

### 2.4 Decouple semantics from storage layout

The logical model should not be tied too closely to any particular physical representation.

In particular:

* Unix files and directories are useful manifestations
* but they are not the logical model

### 2.5 No requirement for global materialization

The design must not require eager materialization of all documents, blobs, or views for normal operation.

This is an important implementation constraint, but not itself a logical concept.

---

## 3. Logical objects

## 3.1 Blob

A blob is immutable binary content.

Concise form:

[
\text{blob} = \text{bytes}
]

Properties:

* immutable
* binary
* fixed content once created
* suitable for content-addressed storage

A blob is a storage primitive, not the main semantic object.

---

## 3.2 Document

A document is an immutable logical object consisting of:

* a **header**: structured metadata
* a **body**: one blob

Concise form:

[
\text{document} = \text{header} + \text{body blob}
]

Properties:

* immutable
* semantically meaningful
* richer than a Unix file
* not fundamentally a pathname

A Unix file can often be coerced into a document, but only as a relatively poor document representation.

A document belongs to exactly one drop.

Documents inherit context from their parent drop for query purposes.

---

## 3.3 Drop

A drop is the first-class warehouse collection unit.

A drop consists of:

* a **drop header**
* a **collection of documents**

Concise form:

[
\text{drop} = \text{drop header} + [\text{document}]
]

Properties:

* immutable
* provenance-bearing
* context-bearing
* the natural unit of ingestion and derived output packaging

A drop represents a meaningful context boundary.
This is one of the most important current design decisions.

Examples:

* one scanner batch
* one filing session
* one imported folder snapshot
* one derived output batch

---

## 4. Identity and inheritance

### 4.1 Logical document identity

Documents are logically distinct objects.

A document belongs to exactly one drop.

If two drops contain what is semantically “the same file,” they still contain two logically distinct documents unless explicitly modeled otherwise later.

This keeps provenance simple and strong.

### 4.2 Physical deduplication

Physical deduplication is allowed and desirable.

Two logical documents may share:

* the same body blob
* possibly the same serialized metadata representation

But this is an implementation detail.

So:

* logical identity is not the same as physical storage identity
* physical deduplication does not collapse provenance

### 4.3 Metadata inheritance

Documents inherit queryable context from their parent drop.

This means selectors may range over:

* document-local metadata
* inherited drop metadata

This is a query convenience and a clean way to expose provenance context without mutating documents.

---

## 5. Canonical drop representation

The currently preferred canonical representation for a drop is:

```text
drop/
  header.json
  entries.jsonl        # or entries.sqlite
  blobs/
    <sha-keyed files>
```

This is currently the best canonical storage model.

---

## 5.1 `header.json`

`header.json` stores drop-level metadata.

Typical contents:

* drop id
* creation/import timestamp
* actor / author / source
* arbitrary drop-level metadata

This is the canonical drop header.

---

## 5.2 `entries.jsonl` or `entries.sqlite`

This stores the document collection for the drop.

Each entry represents one logical document and contains:

* document id
* blob reference
* document-local metadata

Conceptually:

```json
{
  "doc_id": "...",
  "blob_id": "sha256:...",
  "meta": { ... }
}
```

This is the canonical document index for the drop.

JSONL is attractive because it is:

* inspectable
* streamable
* simple
* in-band

SQLite may be attractive for larger drops or faster indexed access.

These should be treated as equivalent logical representations of the same drop contents.

---

## 5.3 `blobs/`

`blobs/` stores the physical blob bodies, keyed by content hash.

This is the canonical body store for the drop’s documents.

Properties:

* content-addressed
* immutable
* dedup-friendly

---

## 6. Why this representation is preferred

This representation aligns directly with the logical model:

* drop = header + documents
* document = metadata + blob reference
* blob = immutable bytes

It is cleaner than using a Unix tree as the canonical representation, because it does not confuse:

* logical document identity
* physical file layout
* user-facing filesystem materialization

Filesystem trees remain useful, but they are better treated as derived views.

---

## 7. Filesystem views

There is **no single canonical archive filesystem**.

Instead, the warehouse may expose **zero or more filesystem views**.

A filesystem view is a derived materialization of selected warehouse documents into a target directory.

These views exist because users and ordinary tools need normal files in normal folders.

This is an important practical capability, but it is not the canonical warehouse representation.

---

## 7.1 Filesystem view definition

A filesystem view is defined by:

* a **selector**
* a **path mapping**
* a **target directory**
* an **ordering / collision rule**
* an **update policy**

Conceptually:

[
V = (S, P, T, O, U)
]

where:

* (S) = selector
* (P) = path mapping
* (T) = target root
* (O) = ordering / collision rule
* (U) = update policy

---

## 7.2 Selector

A selector chooses which documents are in scope.

A selector ranges over effective metadata, including:

* document-local metadata
* inherited drop metadata

A selector is conceptually a predicate over metadata.

---

## 7.3 Path mapping

A path mapping is a pure function from effective document metadata to:

* a relative filesystem path
* or a null/sentinel value meaning “do not materialize”

Conceptually:

[
P : \text{effective metadata} \to \text{path} \cup {\bot}
]

Properties:

* pure
* deterministic
* may omit documents
* need not be injective

If multiple documents map to the same path, collisions are resolved by a stable ordering rule.

---

## 7.4 Target directory

A view materializes into some concrete target directory on a machine.

Examples:

* a passport folder
* a records folder
* a photos folder
* a bookstore folder
* any topic-specific working set

There is no requirement that all warehouse content be visible under one global root.

---

## 7.5 Ordering and collision rule

Because multiple documents may map to the same target path, a filesystem view needs a deterministic ordering rule.

A reasonable default is:

* process documents in warehouse order
* within each drop, process documents in entry order
* last writer wins

The exact rule can be refined later, but deterministic order is required.

---

## 7.6 Update policy

Filesystem views should generally be **pull-based** rather than push-based.

That means:

* warehouse state changes do not need to eagerly rewrite all targets
* views can become stale
* the user or system refreshes them explicitly

This is operationally simpler and more reliable.

Push-based updating may exist later, but should not be assumed as the core model.

---

## 8. History and provenance

We are not resolving transforms yet.

But the cleanly understood part is this:

* the warehouse has history
* drops are provenance-bearing units
* replayability matters
* later derived outputs should also likely be packaged as drops

For now, the stable statement is:

> Warehouse history is fundamentally tied to the appearance of immutable drops over time.

The exact formal model of transforms, derivations, and document version evolution remains open.

---

## 9. Explicit non-goals for this snapshot

This document intentionally does **not** define:

* the final transform model
* document version graphs
* metadata evolution semantics
* nested drops
* tree-based logical structures
* global canonical document identity across drops
* full temporal database schema
* view refresh protocol details
* update notifications
* archive commit/writeback semantics

These are important, but not yet clean enough.

---

## 10. Current clean summary

The design currently understood cleanly is:

* **blob** = immutable bytes
* **document** = immutable metadata + one blob body
* **drop** = immutable metadata + collection of immutable documents
* documents belong to exactly one drop
* documents inherit queryable context from their parent drop
* physical deduplication is allowed, but does not collapse logical identity
* the preferred canonical drop representation is:

```text
header.json
entries.jsonl/sqlite
blobs/sha-keyed-files
```

* filesystem access happens through zero or more derived filesystem views
* there is no single canonical archive root
* filesystem views are defined by selector + path mapping + target + update policy
* filesystem views are convenience materializations, not canonical storage

---

## 11. One-sentence design statement

> filr / DWH is a history-aware store of immutable drops, where each drop contains immutable documents over immutable blobs, and where user-facing filesystem access is provided through derived filesystem views rather than a single canonical archive tree.


