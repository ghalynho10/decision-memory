# decision-memory

A local, cited RAG system that makes software decision history queryable.

Point it at a project's decision records and ask why something is built the way it is. Every answer comes back with citations to the source spec, commit, or file — or an honest "not enough evidence here" when the history does not support one.

> **Status: early development.** `adapt` turns a project's decision specs into validated records; `ingest` builds a versioned local query index from them; `query` answers with citations or an honest abstention. Adapter work (a `doctor` diagnostic, runtime adapter loading, a conformance suite, and built-in ADR adapters) makes the tool usable on a corpus it was not built for.

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

Three rules carry most of the value:

- **Rejected alternatives need a reason.** A list without `rejected_because` is decoration. "What did we already rule out" is the query that stops a team relitigating a settled decision.
- **`why` and `rationale_summary` are separate on purpose.** `why` is a list of discrete reasons; `rationale_summary` is the connected prose weighing the chosen option against the alternatives. At least one must be present. Collapsing them loses whichever gets flattened into the other.
- **Superseded records are never deleted.** "Why did we do it the old way, and what changed" is one of the most useful questions this system aims to answer. The schema supports it with `supersedes`/`superseded_by`; the first adapter does not populate them yet, so that query returns an honest "not enough evidence" until a source actually records supersession.
- **Evidence must resolve.** Every reference points at a real file, spec, or commit backing the decision. An uncited record is the exact failure mode this project exists to prevent — and separately, each retrieved chunk carries its own source path, so an answer built from one part of a record cites exactly the file that part came from.

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

Three pieces make that practical, in the order they help:

**`doctor`** reads an unfamiliar corpus and reports what is actually there: how many markdown files, the most common H2 headings, and documents grouped by their exact heading set, with samples. It makes no mapping claims and produces no records. It exists so you can tell whether a built-in adapter fits before writing anything.

**Built-in adapters** for common formats (MADR, plain ADR) ship with the tool and are versioned (`madr@1`), so many projects never write an adapter at all. They are calibrated against real repositories rather than a format's documentation, because a format's spec and a format's actual use are not the same thing. On a corpus that only partly fits, they adapt what matches and report the rest as skipped — never a thin record standing in for a document they could not read.

**Runtime loading** lets a third-party adapter be used by module path, so writing one means writing your own package rather than forking this one. A minimal starter template and a short guide come with it; `.decision-memory.yml` persists the adapter, corpus root, and output directory per project.

**`test-adapter`** runs a conformance suite against any adapter, including format-drift fixtures — deliberately malformed input, wrong headings, missing fields — and confirms no confident record comes out. This is what makes the anti-fabrication guarantees checkable rather than merely promised.

## Scope

**MVP**

- Canonical record schema, with a validator
- First adapter, for spec-driven pipeline output
- `doctor`, runtime adapter loading, a conformance suite, and built-in ADR adapters
- Ingestion: parse, chunk on canonical field boundaries, embed, index; metadata stays queryable as structured fields
- Hybrid retrieval: structured filters, keyword, and semantic search, with filtering able to constrain the candidate set before semantic similarity chooses among it
- Query interface (CLI) returning answers with resolving citations
- An explicit "not enough evidence" response, plus a debug view showing which records were retrieved, their scores, and why an answer was refused
- Evaluation harness: fixed questions with known-correct sources, so retrieval changes are measured rather than guessed at

**Not in v1**

- Capture (creating records where no artifacts exist) — planned, see below
- Declarative adapters: a YAML mapping file instead of Python, for formats simple enough not to need branching logic
- MCP server and web UI — planned, see below
- Reconstructing history from a codebase that never recorded it
- Cross-repo querying
- Auto-approving generated records without human review

Built in Python. The CLI is one interface onto the retrieval core, not the product; the core keeps a clean query boundary so other interfaces can sit on top of it without touching retrieval logic.

## Planned: capture

Adapters only help projects that already produce decision-shaped artifacts. Capture is the on-ramp for everyone else: at the end of a working session it interviews for what was built, what was decided, what was rejected, and why, then writes a canonical record directly.

Deliberately deferred past v1. Interviewing well is harder than parsing, and validating retrieval against records that already exist is faster than building the record-creation path first and then discovering retrieval does not work.

## Planned: declarative adapters

For formats simple enough not to need branching logic, an adapter should be a YAML mapping file rather than a Python package — sections to fields, with light transforms. The engine keeps stub detection, warn-never-invent, evidence resolution, and attempted-field reporting as its own guarantees, so an author cannot configure them away.

It has a stated ceiling rather than a hidden one: real branching logic (the kind the first adapter needed to work out which option actually won) cannot be expressed in config, and those formats are pointed back at a Python adapter rather than guessed at.

Best built after a second hand-written adapter exists. A config schema designed against one format encodes that format's assumptions, so a second real adapter to design against derisks the schema considerably — it is a strong reason to sequence that way, not a hard prerequisite.

## Planned: other interfaces

**MCP server** — exposes the query function as an MCP tool, so decision history is queryable from inside a coding agent, in the editor where the work is happening. This is where the day-to-day utility lives.

**Web UI** — a frontend over a thin HTTP layer on the core.

Both are wrappers, not rewrites. The retrieval core stays interface-agnostic.

## Prior art

[Token Saver](https://github.com/Marktechpost/Token-Saver) is a useful reference point: local-first, hybrid keyword and semantic retrieval, page-level citations, built as an MCP extension. It names cross-document source selection as its weaker area, which is the gap this project's structured records and metadata filtering are aimed at.

## License

TBD

## User guide

### What this tool is for

decision-memory answers one kind of question about one project: **why is it built this way?** It reads the project's recorded decision history and answers from that history, with citations you can check, or an honest "not enough evidence here" when the history does not support an answer.

It is not a general assistant. It does not guess, and it only knows what was written down. If a decision was never recorded, the tool cannot answer from it.

### The workflow

1. **Look** at what the project actually contains, if you have not adapted it before (coming in a later release):

   ```bash
   uv run decision-memory doctor <project-path>
   ```

   Reports file counts, common headings, and how documents group by structure — enough to tell whether a built-in adapter fits.

2. **Adapt** turns the project's decision specs into canonical records:

   ```bash
   uv run decision-memory adapt <project-path>
   ```

   Use `--dry-run` to preview without writing anything. Records land in `.decision-memory/records/` inside the project. Read the report: skipped sources, unresolved references, and fields the adapter tried and failed to fill are all listed there, and they are the fastest signal that a corpus does not fit the adapter you chose.

3. **Ingest** builds a local query index from the adapted records:

   ```bash
   uv run decision-memory ingest <records-dir>
   ```

   Use `--dry-run` first to preview the provider spend without calling it.

4. **Query** asks a question about that index:

   ```bash
   uv run decision-memory query "why was the private beta gate added?"
   ```

### Questions this tool answers well

Questions shaped as "why", "what was decided", "what changed", and "what was rejected":

- Why was X built this way?
- What was decided about a topic?
- What was chosen over what, and why?
- Which decisions are still provisional?
- What changed the earlier approach to Y?

### What an answer looks like

Every answer comes with citations to the source specs it came from, so you can verify the claim. When nothing in the records supports an answer, the tool says so plainly. "Not enough evidence here" is a correct answer, not a failure.

A refusal you did not expect is worth inspecting rather than accepting: the debug view shows which records were retrieved, how they scored, and whether the answer was refused because nothing relevant came back or because no claim could be traced to a source. That distinction matters — the first means the history genuinely does not cover your question, the second means something went wrong.

The quality of the answer depends entirely on the quality of the records, so run `adapt` first and validate the output before you ask.

## Using the query index

`adapt` produces canonical records. `ingest` turns them into a versioned local index (SQLite plus a vector store) that `query` reads. The three commands together answer questions with citations.

### Preview the cost before you pay

OpenAI calls cost money. `ingest --dry-run` reads the records, plans every chunk, and reports per record the evidence tokens, the embedding input tokens (the embedding prefix is billed input but is not evidence), and the provider batch count, without calling the provider, writing anything, or needing an API key:

```bash
uv run decision-memory ingest <records-dir> --dry-run
```

A real `ingest` needs `OPENAI_API_KEY` only when the plan actually embeds a record. A dry run, an ingest where every record is unchanged, a removal only ingest, and an empty index abstention never call the provider. When a real ingest needs the key and it is missing, it refuses before writing anything to the store.

### Ingest is incremental

Run `ingest` again after `adapt` and only changed and new records are reembedded. Unchanged records are validated, not reembedded. Records removed from the manifest become tombstones. When a record fails (a tampered digest, missing provenance, or a provider error), the rest continue and the run reports the failure.

### Ask

```bash
uv run decision-memory query "why was the private beta gate added?"
```

Every factual sentence carries a citation marker such as `[C1]`, and a `Sources` list names each citation's record, chunk, value path, relative path, and section. When no eligible chunk supports an answer, the tool prints exactly `not enough evidence here` and exits 0. That is an honest abstention, never a failure.

### Stale index warnings

The index remembers the manifest it was built from. If you `adapt` again but do not re-ingest, the index is stale. `query` refuses by default and tells you to re-ingest; `query --allow-stale` reads it anyway and prints `WARNING: stale index` with the reasons (a record added, changed, or removed, a failed ingest, or the manifest changed mid query). A citation backed by an older version of a record is marked `stale version`.

### Moved index

The store remembers the absolute corpus root as a hint, so a citation's relative path can be resolved back to a file at query time. If the corpus moved, the hint may no longer resolve: each citation reports whether its source resolved, is missing, had no hint, or was an invalid relative path. An unresolved path is informative, not an error, and the relative path is always shown.

### Debug output is sensitive

`query --debug` prints the full trace: retrieved chunks with their scores, extracted facets, draft sentences, verification verdicts, provider attempts, citations, and full chunk text. It may include private project data. Treat debug output as sensitive when you paste it into an issue.

### Rebuild and recovery

If the pipeline configuration changed (the embedding model, the chunker, or the token encoding), the index no longer matches. Normal ingest and query refuse and tell you to rebuild:

```bash
uv run decision-memory ingest <records-dir> --rebuild
```

A rebuild stages a fresh generation, verifies it completely, then switches to it atomically. If it fails, the previous good index stays active. `--rebuild` needs only the records and their manifest, not the original corpus or an adapter.

### Exit codes

- `0` a successful ingest, an answered query, or an honest abstention
- `1` a partial ingest, stale refusal, pipeline mismatch, provider failure, lock conflict, malformed manifest, or corrupt store
- `2` invalid usage, including an empty question
- `3` a missing records directory or missing store path

### When an answer is wrong: the triage map

The four stage chain is reviewer guidance for working backward from a bad answer. It applies only after you have confirmed the fact really is in the canonical record; if the record itself is wrong or missing the fact, the failure belongs to adaptation or ingestion, not this chain. Work backward from the answer:

| First failing check | Stage |
|---|---|
| A correct indexed chunk was not accepted | Retrieval (candidate ranks, scores, floor, dispositions) |
| An expected canonical value is absent or malformed in the index plan | Chunking (chunk text, boundaries, value path, provenance) |
| Correct chunks were accepted but a draft sentence is missing or wrong | Generation (accepted chunk ids, facets, draft sentences) |
| A supported draft was removed or a covered facet was rejected | Claim verification or abstention (sentence verdicts, uncovered facets) |

### Supersession

A record can declare that it supersedes an earlier one. When a query retrieves the earlier decision, the answer includes a deterministic sentence, `This decision was later changed by <title> (<id>).`, cited to the successor's record, without inventing how it changed. A self link or a cycle between records fails ingestion. The built in jsmastery adapter does not currently populate supersedes, so this path is built and tested against synthetic data but not yet exercised against a real corpus.
