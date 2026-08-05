# Decision Memory — MVP scope

A local, cited RAG system that makes software decision history queryable. Point it at a project's decision records and ask why something is built the way it is; get an answer with citations back to the source, or an honest "not enough evidence here."

This document defines the canonical schema, the adapter boundary, the MVP scope, and what is deliberately deferred.

---

## Design principle: the core knows nothing about your project

Three layers, and the separation between them is the whole architecture:

```
Sources (project-specific)
    ├── Adapters      read files that already exist, translate them
    └── Capture       create records directly when nothing exists yet   [v2]
                ↓
    Canonical decision record  ← the only contract that matters
                ↓
    Generic RAG core           ← ingestion, retrieval, citation
```

The core never sees a project's native format. It only ever sees canonical records. This is what keeps the tool usable by someone whose project looks nothing like yours: they write an adapter (or use capture), and the core is unchanged.

The first adapter targets specs produced by the jsmastery-pro-style pipeline (`docs/specs/<n>-<name>/index.md`). That adapter is the only pipeline-aware code in the system, and it is small — a parser, essentially.

---

## Canonical decision record

One record per decision unit — for the first adapter, that unit is a spec folder (see Record cardinality below). Stored as YAML frontmatter plus an optional markdown body, one file per record. The body holds source prose the schema had no field for, preserved rather than discarded; it is indexed like any other prose field, and carries its own provenance.

```yaml
id: DM-0014                      # stable, never reused
title: Store document metadata separately from chunk embeddings
status: accepted                 # proposed | accepted | superseded | rejected
date: 2026-08-02
supersedes: DM-0009              # optional
superseded_by: null              # set when a later record replaces this

context:
  problem: >
    Cross-document retrieval selects the wrong source document before
    chunk retrieval begins, so citations point at plausible but wrong files.
  triggering_change: >
    Queries needed to span bills, trips, and subscriptions at once.

decision:
  chosen: >
    Maintain a document catalog with typed metadata, and a separate chunk index.
  alternatives:
    - option: Vector search over all chunks only
      rejected_because: No way to filter before semantic search, so wrong-document errors stay invisible.
    - option: One vector collection per document type
      rejected_because: Forces single-label documents; a flight receipt is both travel and expense.

why:
  - Allows metadata filters before semantic search
  - Makes classification errors visible and correctable
  - Supports multiple categories per document

rationale_summary: >               # optional; the comparative synthesis prose,
                                    # distinct from the reasons list in `why`
  Vector search alone cannot filter before retrieval, so its wrong-document
  errors stay invisible; per-type collections fix filtering but force each
  document into a single label. A catalog plus a separate chunk index keeps
  filtering available without collapsing documents to one category.

consequences:
  positive:
    - Better source selection
    - Auditable retrieval path
  negative:
    - More ingestion and metadata work per document

evidence:                        # everything here must resolve to something real
  - type: spec
    ref: docs/specs/0014-document-metadata/index.md
  - type: commit
    ref: abc123f
  - type: file
    ref: lib/catalog.ts

tags: [retrieval, data-model]
```

### Record cardinality

**One canonical record per spec folder for v1.** A single spec often contains more than one decision, but splitting them requires deciding where one decision ends and the next begins, how sub-IDs are assigned, and whether shared context is duplicated — real normalization work, not parsing. v1 treats a spec folder as one decision bundle and accepts the coarseness. If retrieval turns out to suffer because bundled decisions blur together, splitting becomes its own scoped piece of work, not something discovered mid-build.

### Field requiredness

| Field | v1 status |
| --- | --- |
| `id`, `title`, `status`, `decision.chosen`, `evidence` | required |
| `context.problem` | required if the source states one, else absent |
| `why`, `rationale_summary` | optional; at least one required (see field rules) |
| `decision.alternatives` | optional |
| `date`, `tags`, `consequences`, `context.triggering_change` | optional |
| `supersedes`, `superseded_by` | optional; unmapped by the first adapter |

A field being absent is a valid record. A field being *silently* absent because the adapter had no rule for it is not — the validator warns on any field the adapter attempted and failed to populate, so parse gaps stay visible rather than looking like genuine absences in the source.

### Field rules

**`id`** is stable and never reused, so citations stay valid across renames.

**`status`** carries real weight. A `superseded` record must still be retrievable — "why did we do it the old way, and what changed" is one of the most valuable queries this system answers. Superseded records are never deleted.

**`alternatives` require a `rejected_because`.** An alternatives list without reasons is decoration. This field is where most of the actual value lives at query time, because "what did we already rule out" is the question that stops a team relitigating a settled decision.

**`evidence` must resolve, and it means supporting artifacts, not citation provenance.** Every entry points at a real file, commit, or spec, and an adapter that cannot produce at least one should warn rather than emit a record with an empty list. But `evidence` answers "what backs this decision up" — the commits that implemented it, the files it produced. "Where did this specific sentence come from" is a different question, tracked per chunk at ingestion (source path plus section), not here. A record whose `rationale_summary` came from `rationale.md` must cite `rationale.md`, not the folder's `index.md`, or the tool's central promise fails on its first multi-file record.

**`why` is separate from `decision.chosen` on purpose.** What was decided and why it was decided answer different queries, and collapsing them makes retrieval worse.

**`rationale_summary` is separate from `why` on purpose, and the distinction is about content shape, not file location.** `why` is a list of discrete reasons; `rationale_summary` is connected comparative prose weighing the chosen option against the alternatives. Either may appear in `index.md` or in a `rationale.md`, and an adapter classifies by what the content *is*, never by which file it came from. At least one of the two must be populated for a record to be valid; a decision with no recorded reasoning at all is exactly what this system exists to surface as a gap, so the validator warns rather than accepting it quietly.

---

## Adapter interface

An adapter turns some project-native artifact into zero or more canonical records. The interface allows many; the first adapter emits at most one per spec folder, and zero when a spec contains no decision.

```
adapter.name          -> string, e.g. "jsmastery-specs"
adapter.discover(root) -> list of source paths this adapter claims
adapter.parse(path)    -> list of canonical records (may be empty)
adapter.fingerprint(path) -> hash or mtime, for incremental re-ingestion
```

`fingerprint` is what makes re-ingestion incremental rather than a full rebuild every time a spec is added. Worth having from the start; retrofitting it later means re-embedding everything. **It fingerprints every file contributing to a record, not just the entry file** — a record built from `index.md` plus `rationale.md` must re-ingest when either changes, or edits to rationale content silently never reach the index.

Adapters never write. They read and translate. Anything that creates records is capture, not an adapter.

### First adapter: `jsmastery-specs`

Reads `docs/specs/<n>-<name>/index.md` (and `rationale.md` where a directory spec has one) and maps:

| Canonical field | Source |
| --- | --- |
| `id` | spec number, prefixed |
| `title` | spec title |
| `status` | spec status line (`Assumed` maps to `proposed`) |
| `date` | spec date line, when present |
| `context.problem` | spec problem statement |
| `context.triggering_change` | not available from this source; left absent |
| `decision.chosen` | the Decision section |
| `decision.alternatives` | Options considered section |
| `why` | itemized reason statements in the Rationale section, wherever found |
| `rationale_summary` | connected comparative prose in the Rationale section, wherever found |
| `consequences` | Consequences section, when present |
| `evidence` | every file contributing to the record, plus any commits it references |
| `tags` | not available from this source; left absent (see Query 2) |
| `supersedes`, `superseded_by` | not available from this source; left absent (see Query 5) |

Note the `Assumed` mapping: that pipeline's assumed-spec lifecycle means some specs record a provisional decision that was never explicitly ratified. Those map to `proposed`, not `accepted`, so a query never presents a guess as a settled decision.

### Degradation policy

Real specs are messy, so the adapter needs a stated response to each way they break. It never invents content to fill a gap; it emits a diagnostic and produces the most complete valid record it can.

| Source condition | Adapter behavior |
| --- | --- |
| Rationale is a list only | populate `why`, leave `rationale_summary` absent |
| Rationale is prose only | populate `rationale_summary`, leave `why` absent |
| Rationale has both | populate both, no duplication between them |
| Rationale absent entirely | leave both absent, warn — this record is a reasoning gap |
| Both files carry overlapping rationale | `index.md` wins, `rationale.md` supplies only what `index.md` lacks |
| An alternative has no `rejected_because` | keep the option, leave the reason null, warn — never invent one |
| No Decision section found | emit no record, warn — there is no decision here to record |

The last row matters: an adapter that produces a record from a spec with no decision in it manufactures decision history, which is worse than missing it.

---

## MVP scope

**In:**

1. Canonical record schema, as above, with a validator.
2. The `jsmastery-specs` adapter.
3. Ingestion: parse records, chunk the prose fields, embed, index. Metadata (status, tags, date, id) stays queryable as structured fields, not just embedded text. **Chunking invariant:** canonical field boundaries are the retrieval unit. A long field may be subdivided, but every subchunk keeps its record id, its field identity, and its source provenance (path plus section). `/architect` decides token thresholds, subdivision boundaries, overlap, list-item granularity, and how a chunk is reassembled into its parent record — but not whether to preserve field boundaries, which is settled here.
4. Hybrid retrieval: structured metadata filters, lexical retrieval, and semantic retrieval, all three available. The goal is that a structured filter can constrain the candidate set before semantic similarity gets to choose, since that is what prevents confidently citing the wrong document. Exact ordering and whether stages run as a pipeline or fuse their scores is an `/architect` decision, not settled here.
5. A query interface (CLI to start) that returns an answer plus citations resolving to real paths.
6. An explicit "not enough evidence" response when retrieval finds nothing that supports an answer.
7. An evaluation harness: a fixed set of questions with known-correct source documents, so retrieval changes can be measured rather than guessed at.

**Out, for v1:**

- Capture (planned, see below)
- MCP server interface (planned, see below)
- Web UI (planned, see below)
- Reconstructing historical decisions from a codebase that never recorded them
- Multi-project or cross-repo querying
- Auto-generating decision records without human review

### The first five queries

These define done for the MVP. Each must return a cited answer against real spec data, or an honest no-evidence response.

1. Why was the private beta access gate added, and what was the alternative?
2. What decisions affect resume generation? — *semantic recall test, not a structured one.* The first adapter maps no tags, so "affects" has no structured definition here. The harness fixes a known-correct set of records by hand and measures whether retrieval finds them. If this proves too imprecise to score, the fix is mapping tags, not loosening the question.
3. Which decisions are still provisional rather than ratified?
4. What was decided about how server-side and browser-side database clients are separated, and why?
5. What changed the original approach to storing uploaded files? — *expected to return "not enough evidence" in v1.* The first adapter maps no supersession links, so this query tests the abstention path rather than retrieval. Kept deliberately: an honest no-evidence answer where the data genuinely does not support one is a real MVP behavior worth proving. It becomes a retrieval test once supersession is mapped.

Query 3 is the one worth keeping even though it looks like a metadata filter rather than a retrieval question — it is the cheapest early proof that `status` survived ingestion intact, which is easy to get wrong and hard to notice later. It only proves `status`; the harness covers `id`, `date`, and `tags` with their own filter assertions rather than assuming one field's survival implies the rest.

**Two harness assertions beyond the five queries**, both covering things the queries alone would let regress silently:

- **A `rationale_summary` assertion.** At least one fixture question whose correct answer requires the comparative synthesis specifically, and cannot be answered from the `why` list. Without it, the field can fail at parse, chunk, embed, retrieve, or generate and every headline query still passes.
- **An incremental ingestion assertion.** Change a `rationale.md`, re-ingest, confirm the record's chunks updated. This is the cheapest test of the multi-file fingerprint rule, and the failure it catches is invisible otherwise.

---

## Validation data

Use an existing project's real specs as the first dataset rather than synthetic records. Real specs have the messiness that breaks parsers: inconsistent headings, missing rationale sections, specs that were never ratified, decisions recorded across two files instead of one.

This is a build-order choice, not a design coupling. The core stays generic; a real project just happens to be the first thing an adapter is pointed at.

**One thing to decide before starting:** whether the initial corpus is large enough to evaluate retrieval meaningfully. A dozen specs is enough to prove the pipeline runs end to end. It is probably not enough to tell whether hybrid retrieval beats plain semantic search. If the corpus is thin, either accept that retrieval quality stays unevaluated in v1, or backfill records from git history first — but backfilling is its own project, and it should be a conscious choice rather than something discovered halfway in.

---

## Parked for v2: capture

For projects with no existing decision-shaped artifacts, capture creates canonical records directly. Instead of parsing a file, it interviews at the end of a working session: what was built, what was decided, what alternatives were considered, why this one.

This is the on-ramp for anyone not already running a structured pipeline, and it is what makes the tool useful beyond people who already have specs. It is deliberately not in v1 for two reasons:

- Interviewing well is harder than parsing. Asking one question at a time, never inventing an answer, and knowing when a session produced no decision worth recording is real design work.
- Validating retrieval against records that already exist is faster than building the thing that creates records and then discovering retrieval does not work.

Ship the adapter, prove retrieval, then build capture against a schema that has already been tested.

---

## Parked for v2: additional interfaces

The CLI is one interface onto the retrieval core, not the product itself. Two others are likely after v1.

**MCP server.** Exposes the query function as an MCP tool, making decision history queryable from inside a coding agent — asking "why is this built this way" in the editor where the work is happening. The smaller of the two to build, and where the day-to-day utility actually lives.

**Web UI.** A frontend over a thin HTTP layer on the Python core. More work than the MCP wrapper, and mostly portfolio value rather than utility.

**Implication for v1, and this one is a real constraint rather than a note:** keep the query interface a clean function boundary, roughly

```
query(question, filters) -> Answer(text, citations)
```

with no CLI-specific formatting leaking into retrieval logic. It costs nothing to hold this line now. Retrofitting it later means untangling presentation from business logic across the whole core.

---

## Stack

**Python.** The RAG ecosystem is Python-first by a wide margin: embedding models, vector stores, chunking, and evaluation tooling all have mature Python implementations and thinner ports elsewhere. Local-first is a goal here, which pushes the same direction, since local embedding and inference options are strongest in Python.

Dependency management with `uv`.

No TypeScript in v1. If the web UI happens later it brings its own frontend stack, talking to the Python core over HTTP rather than replacing any of it.