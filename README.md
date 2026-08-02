# decision-memory

A local, cited RAG system that makes software decision history queryable.

Point it at a project's decision records and ask why something is built the way it is. Every answer comes back with citations to the source spec, commit, or file — or an honest "not enough evidence here" when the history does not support one.

> **Status: early development.** The design is settled (schema, adapter boundary, MVP scope); implementation is in progress. Nothing here is usable yet.

## The problem

During spec-driven or agentic development, the reasoning behind a system lives in scattered places: planning documents, generated specs, commit messages, pull requests, and conversations that vanish when the session ends. Months later the code tells you *what* it does. It rarely tells you:

- Why this database, this schema, this API shape?
- What problem invalidated the original design?
- Which alternatives were considered and rejected, and why?
- Which decisions is this feature standing on?
- If this breaks, which assumptions should be checked first?

Codebases accumulate answers to *what*. The *why* evaporates.

## The approach

Two ideas do most of the work here.

**Structured records, not just RAG over prose.** Each meaningful decision gets a small structured record: what was decided, what was rejected and why, what it cost, and what evidence backs it. Retrieval runs over those records rather than over raw documentation, which is what makes citations reliable instead of plausible.

**A generic core with project-specific adapters.** The retrieval engine knows nothing about any particular project's conventions. Adapters translate a project's native artifacts into a canonical record shape; the core only ever sees canonical records. Someone whose project looks nothing like yours writes an adapter, not a fork.

```
Sources (project-specific)
    ├── Adapters      translate artifacts that already exist
    └── Capture       create records directly, when nothing exists yet   [planned]
                ↓
    Canonical decision record
                ↓
    Generic RAG core     ingestion · hybrid retrieval · citation
```

## Canonical record

One record per decision, YAML frontmatter with an optional markdown body:

```yaml
id: DM-0014
title: Store document metadata separately from chunk embeddings
status: accepted                 # proposed | accepted | superseded | rejected
date: 2026-08-02
supersedes: DM-0009

context:
  problem: >
    Cross-document retrieval selects the wrong source before chunk retrieval
    begins, so citations point at plausible but wrong files.

decision:
  chosen: >
    Maintain a document catalog with typed metadata, and a separate chunk index.
  alternatives:
    - option: Vector search over all chunks only
      rejected_because: No way to filter before semantic search, so wrong-document errors stay invisible.

why:
  - Allows metadata filters before semantic search
  - Makes classification errors visible and correctable

consequences:
  positive: [Better source selection, Auditable retrieval path]
  negative: [More ingestion and metadata work per document]

evidence:
  - type: spec
    ref: docs/specs/0014-document-metadata/index.md
  - type: commit
    ref: abc123f

tags: [retrieval, data-model]
```

Three rules carry most of the value:

- **Rejected alternatives need a reason.** A list without `rejected_because` is decoration. "What did we already rule out" is the query that stops a team relitigating a settled decision.
- **Superseded records are never deleted.** "Why did we do it the old way, and what changed" is one of the most useful questions this system answers, and it is impossible without explicit supersession links.
- **Evidence must resolve.** Every reference points at a real file, spec, or commit. An uncited record is the exact failure mode this project exists to prevent.

## Adapters

An adapter turns project-native artifacts into canonical records. It reads; it never writes.

```
adapter.name              -> "jsmastery-specs"
adapter.discover(root)    -> source paths this adapter claims
adapter.parse(path)       -> canonical records (may be empty)
adapter.fingerprint(path) -> hash or mtime, for incremental re-ingestion
```

The first adapter targets specs from a spec-driven pipeline (`docs/specs/<n>-<name>/index.md`), mapping decision sections, options considered, and rationale onto the canonical shape. Provisional specs map to `proposed` rather than `accepted`, so a query never presents an unratified guess as settled fact.

## Scope

**MVP**

- Canonical record schema, with a validator
- First adapter, for spec-driven pipeline output
- Ingestion: parse, chunk prose fields, embed, index; metadata stays queryable as structured fields
- Hybrid retrieval: metadata filter, then keyword, then semantic
- Query interface (CLI) returning answers with resolving citations
- An explicit "not enough evidence" response
- Evaluation harness: fixed questions with known-correct sources, so retrieval changes are measured rather than guessed at

**Not in v1**

- Capture (creating records where no artifacts exist) — planned, see below
- MCP server and web UI — planned, see below
- Reconstructing history from a codebase that never recorded it
- Cross-repo querying
- Auto-approving generated records without human review

Built in Python. The CLI is one interface onto the retrieval core, not the product; the core keeps a clean query boundary so other interfaces can sit on top of it without touching retrieval logic.

## Planned: capture

Adapters only help projects that already produce decision-shaped artifacts. Capture is the on-ramp for everyone else: at the end of a working session it interviews for what was built, what was decided, what was rejected, and why, then writes a canonical record directly.

Deliberately deferred past v1. Interviewing well is harder than parsing, and validating retrieval against records that already exist is faster than building the record-creation path first and then discovering retrieval does not work.

## Planned: other interfaces

**MCP server** — exposes the query function as an MCP tool, so decision history is queryable from inside a coding agent, in the editor where the work is happening. This is where the day-to-day utility lives.

**Web UI** — a frontend over a thin HTTP layer on the core.

Both are wrappers, not rewrites. The retrieval core stays interface-agnostic.

## Prior art

[Token Saver](https://github.com/Marktechpost/Token-Saver) is a useful reference point: local-first, hybrid keyword and semantic retrieval, page-level citations, built as an MCP extension. It names cross-document source selection as its weaker area, which is the gap this project's structured records and metadata filtering are aimed at.

## License

TBD