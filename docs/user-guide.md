# User guide

Deeper reference for people already running the tool. The [README](../README.md) covers what this is and how to get started; this doc covers the record schema, the pipeline internals, and how to debug a bad answer.

## Questions this tool answers well

Questions shaped as "why", "what was decided", "what changed", and "what was rejected":

- Why was X built this way?
- What was decided about a topic?
- What was chosen over what, and why?
- Which decisions are still provisional?
- What changed the earlier approach to Y?

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

rationale_summary: >
  Vector search alone cannot filter before retrieval, so its wrong-document
  errors stay invisible; per-type collections fix filtering but force each
  document into a single label. A catalog plus a separate chunk index keeps
  filtering available without collapsing documents to one category.

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

Four rules carry most of the value:

- **Rejected alternatives need a reason.** A list without `rejected_because` is decoration. "What did we already rule out" is the query that stops a team relitigating a settled decision.
- **`why` and `rationale_summary` are separate on purpose.** `why` is a list of discrete reasons; `rationale_summary` is the connected prose weighing the chosen option against the alternatives. At least one must be present.
- **Superseded records are never deleted.** The schema supports `supersedes`/`superseded_by`; the first adapter does not populate them yet, so that query returns an honest "not enough evidence" until a source records supersession.
- **Evidence must resolve.** Every reference points at a real file, spec, or commit backing the decision. An uncited record is the failure mode this project exists to prevent. Each retrieved chunk also carries its own source path, so an answer built from one part of a record cites exactly the file that part came from.

## Adapters

An adapter turns project-native artifacts into canonical records. It reads; it never writes.

```
adapter.name              -> "jsmastery-specs"
adapter.discover(root)    -> the sources this adapter claims, plus skips and id collisions
adapter.parse(spec)       -> a record (or none), with violations, attempted fields, and unresolved mentions
adapter.fingerprint(spec) -> hash over every contributing file, for incremental re-ingestion
```

The first adapter targets specs from a spec-driven pipeline (`docs/specs/<n>-<name>/index.md`, plus a sibling `rationale.md`), mapping decision sections, options considered, and rationale onto the canonical shape. Provisional specs map to `proposed` rather than `accepted`, so a query never presents an unratified guess as settled fact.

Adapters degrade rather than guess. A missing rejection reason is recorded as missing, not invented. A section that turns out to be a pointer rather than content is detected and skipped, not stored as if it were the content. A source with no decision in it produces no record at all. Every one of these emits a warning naming what was dropped and why.

### Using it on a project it was not built for

**`doctor`** reads an unfamiliar corpus and reports what is actually there: file counts, common H2 headings, and documents grouped by their exact heading set. It makes no mapping claims and produces no records; it tells you whether a built-in adapter fits before you write anything.

**Built-in adapters** for common formats (MADR, plain ADR) are planned, versioned like `madr@1`, calibrated against real repositories rather than a format's documentation. On a corpus that only partly fits, they adapt what matches and report the rest as skipped.

**Runtime loading** lets a third-party adapter be used by module path, so writing one means writing your own package rather than forking this one. A minimal starter template and guide live in `examples/starter-adapter/`. `.decision-memory.yml` persists the adapter, corpus root, and output directory per project.

**`test-adapter`** runs a conformance suite against any adapter, including format-drift fixtures (malformed input, wrong headings, missing fields), and confirms no confident record comes out.

## Using the query index

`adapt` produces canonical records. `ingest` turns them into a versioned local index (SQLite plus a vector store) that `query` reads.

### Preview the cost before you pay

OpenAI calls cost money. `ingest --dry-run` reads the records, plans every chunk, and reports per record the evidence tokens, the embedding input tokens (the embedding prefix is billed input but is not evidence), and the provider batch count, without calling the provider, writing anything, or needing an API key:

```bash
uv run decision-memory ingest <records-dir> --dry-run
```

A real `ingest` needs `OPENAI_API_KEY` only when the plan actually embeds a record. A dry run, an ingest where every record is unchanged, a removal-only ingest, and an empty-index abstention never call the provider. When a real ingest needs the key and it is missing, it refuses before writing anything to the store.

### Ingest is incremental

Run `ingest` again after `adapt` and only changed and new records are reembedded. Unchanged records are validated, not reembedded. Records removed from the manifest become tombstones. When a record fails (a tampered digest, missing provenance, or a provider error), the rest continue and the run reports the failure.

### Narrowing a query with filters

`query` accepts repeatable metadata filters that constrain the candidate set before retrieval, so a filter can never be silently overridden by a plausible semantic match:

```bash
uv run decision-memory query "question" --record-id DM-0012 --record-id DM-0013
uv run decision-memory query "question" --status accepted --tag billing
uv run decision-memory query "question" --value-path 'body[*]'
```

Values use OR within one option and AND across options. Statuses normalize to `proposed`, `accepted`, `superseded`, or `rejected`; record ids, tags, and value paths stay case sensitive. A value path is either an exact chunk path (`why[0]`) or one of the fixed selectors `decision.alternatives[*]`, `why[*]`, `consequences.positive[*]`, `consequences.negative[*]`, and `body[*]`, which match exactly one indexed leaf. A malformed filter value (an empty value, an unknown status, or a bad path) is a usage error, exit `2`. A well formed filter that matches no chunk is not an error: the query honestly abstains with `not enough evidence here` and makes no provider call. Filters apply to one query only and never persist.

### Hybrid retrieval

Every query first applies the filters, then runs BM25 lexical and cosine semantic retrieval over the same accepted chunks. The two rank lists are combined with reciprocal rank fusion (no raw score is compared across scales), and a two pass diversity rule keeps at most two chunks per record so an answer can cite several relevant decisions, not one dominating record. The fixed limits (24 candidates, 8 accepted, fusion constant 60, diversity cap 2) are recorded in the debug trace and can be recalibrated without rebuilding embeddings.

### Stale index warnings

The index remembers the manifest it was built from. If you `adapt` again but do not re-ingest, the index is stale. `query` refuses by default and tells you to re-ingest; `query --allow-stale` reads it anyway and prints `WARNING: stale index` with the reasons. A citation backed by an older version of a record is marked `stale version`.

### Moved index

The store remembers the absolute corpus root as a hint, so a citation's relative path can be resolved back to a file at query time. If the corpus moved, the hint may no longer resolve: each citation reports whether its source resolved, is missing, had no hint, or was an invalid relative path.

### Debug output is sensitive

`query --debug` prints the full trace in a fixed order: Freshness, Filter, Lexical, Semantic, Fusion, Diversity, Settings, Facets, Draft, Verification, Providers, Citations, and Result. The retrieval sections show every active chunk, its filter state and reasons, lexical scores and ranks, semantic distances, fused scores and ranks, and the diversity decision, plus the pinned retrieval settings. It may include private project data, so treat it as sensitive before pasting it into an issue. When a retrieval integrity failure occurs (a scorer error, a missing or extra vector, a misaligned semantic response, or a nonfinite score), the command exits `1` and `--debug` renders only the sections that completed before the failure.

### Rebuild and recovery

If the pipeline configuration changed (embedding model, chunker, token encoding), the index no longer matches. The same is true when the store format changed: format 2 pins the cosine metric and stores each chunk id as vector metadata so semantic search can restrict to exactly the accepted chunks. Normal ingest and query refuse and tell you to rebuild:

```bash
uv run decision-memory ingest <records-dir> --rebuild
```

A rebuild stages a fresh generation, verifies it completely, then switches to it atomically. If it fails, the previous good index stays active. It recomputes derived vectors and may repeat embedding spend; the canonical records and chunk text are preserved. `--rebuild` needs only the records and their manifest, not the original corpus or an adapter. A store in an older format cannot be queried until it is rebuilt.

### Exit codes

- `0` a successful ingest, an answered query, or an honest abstention
- `1` a partial ingest, stale refusal, pipeline mismatch, provider failure, lock conflict, malformed manifest, corrupt store, or retrieval integrity failure
- `2` invalid usage, including an empty question or a malformed filter value
- `3` a missing records directory or missing store path

### When an answer is wrong: the triage map

Reviewer guidance for working backward from a bad answer. It applies only after you've confirmed the fact really is in the canonical record; if the record itself is wrong or missing the fact, the failure belongs to adaptation or ingestion, not this chain.

| First failing check | Stage |
|---|---|
| A correct indexed chunk was filtered out or not accepted | Retrieval (Filter states and reasons, Lexical scores and ranks, Semantic distances and ranks, Fusion scores, Diversity dispositions) |
| An expected canonical value is absent or malformed in the index plan | Chunking (chunk text, boundaries, value path, provenance) |
| Correct chunks were accepted but a draft sentence is missing or wrong | Generation (accepted chunk ids, facets, draft sentences) |
| A supported draft was removed or a covered facet was rejected | Claim verification or abstention (sentence verdicts, uncovered facets) |

### Supersession

A record can declare that it supersedes an earlier one. When a query retrieves the earlier decision, the answer includes a deterministic sentence, `This decision was later changed by <title> (<id>).`, cited to the successor's record, without inventing how it changed. A self link or a cycle between records fails ingestion. The built-in jsmastery adapter does not currently populate `supersedes`, so this path is built and tested against synthetic data but not yet exercised against a real corpus.
