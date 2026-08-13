# Rationale: core cited query

## Context

The first useful slice must answer one real question from JobPilot's decision history and prove every factual sentence against the original source. A fluent answer without the expected record, choice, rejected alternative, or source trail is a product failure even when it sounds plausible.

The corpus is small and structured. Retrieval sophistication is not the main risk. The hard problems are preserving field identity and provenance through chunking, making stale versions visible, separating honest abstention from operational failure, and leaving enough evidence to assign a bad answer to one pipeline stage.

Adaptation already produces canonical records incrementally through source fingerprints. Those records do not yet preserve which original path and section supplied each canonical value. Query also introduces paid external calls and two derived stores, SQLite and Chroma. The design must keep those mutations explicit, recover record by record, and never require the original adapter or source corpus merely to rebuild the query index.

The current corpus has no supersession links. The generator still needs the behavior before data appears, because presenting an old decision as current is both accurate in isolation and wrong in use. This case can be built and inspected but cannot honestly claim JobPilot coverage.

## Options considered

### Option 1: Explicit ingestion with a versioned cited index

`adapt` produces canonical records and a provenance rich manifest. `ingest` explicitly spends for embeddings and writes record scoped versions. `query` reads only a compatible index and returns a fully traced result. (basis: specs 0001, 0002, 0003, 0005, and 0006; Command Query Separation; content addressed ingestion)

**Pros**:

- Billing, mutation, staleness, and recovery have distinct command boundaries.
- Rebuild needs records and a manifest, not the source corpus or adapter.
- Record scoped activation aligns partial failure with the fingerprint unit.

**Cons**:

- Users must run two explicit write steps, adapt then ingest.
- Freshness is relative to the latest adapter manifest. Raw source edits after the last adapt remain unknown.
- Provenance requires a breaking adapter and manifest change.

### Option 2: Synchronize automatically during every query

Query would discover sources, compare fingerprints, embed changes, and then retrieve. This gives the freshest possible answer from one command. (basis: the query workflow described in README.md; automatic cache refresh)

**Pros**:

- One user command covers source edits through answer generation.
- No separate stale index state is visible to the user.

**Cons**:

- A read command gains hidden billing and mutation side effects.
- Query latency and failure now include adapter discovery, source access, and embedding.
- Retrieval failure and synchronization failure become harder to distinguish.

### Option 3: Make adapt also build the query index

The existing adapt command would write canonical records and update vectors in one run. Query would remain read only. (basis: spec 0003, the existing adapt use case)

**Pros**:

- One explicit write command produces every derived artifact.
- Source fingerprints and index work occur in one process.

**Cons**:

- Reindexing after a model or chunk rule change requires adaptation even when the canonical records are already correct.
- Adapter failures and provider failures share one command and report.
- A machine holding only exported records cannot rebuild the index.

## Rationale

Option 1 keeps the trust boundaries legible. Adaptation answers what the source says. Ingestion answers what indexed version exists and what it cost to create. Query answers only from that version. This is the strongest fit for a product whose honest gaps matter more than command count. (basis: docs/scope/scope.md, Feature 9; Command Query Separation)

Whole record rechunking is chosen for correctness rather than small corpus convenience. A text identical chunk may have moved to another field or source section. Reusing its vector on content alone would silently attach stale identity and provenance. Rebuilding one changed record keeps the fingerprint, chunk metadata, and citation unit aligned. (basis: spec 0002, canonical field meanings; spec 0003, record scoped fingerprints; provenance preserving citations)

SQLite remains authoritative and Chroma remains derived because that split was already settled in the stack decision. Writing vectors first, activating SQLite second, and deleting old vectors last makes each crash point recoverable without full reembedding. The runner up, a complete collection swap, would make every small change a full rebuild. (basis: spec 0001; write new then activate then retire)

Rebuild is different from an incremental record update. It may replace every vector, so it builds a separate generation and switches one pointer only after full parity. This costs more disk during rebuild but preserves the last good query path if a provider or process fails. The lock database stays outside generations so recovery never replaces the lock that protects it. (basis: recoverable derived index updates)

The title and value path prefix improve retrieval without becoming evidence. Generation and debug receive the underlying field text only. Alternatives keep title and rejection reason together because separating them destroys their meaning and recreates the exact decoration failure the schema rejected. (basis: spec 0002, alternative and rationale rules)

The debug trace is part of the application result rather than CLI decoration. Feature 11 can therefore assert scores, ranks, facets, and verification verdicts directly. Full text is intentional because chunk boundary errors cannot be diagnosed from excerpts. Normal logs remain content free, and the user guide must warn that shared debug output contains decision records. (basis: docs/scope/scope.md, Features 9 and 11; observable pipelines)

The provisional relevance floor is `None`, not numeric zero. Cosine similarity may be negative, so zero would be an unmeasured active cutoff rather than a disabled one. Deterministic claim verification uses exact normalized containment only. Ordered token overlap was rejected because tokens from separate statements can appear in order and falsely support a combined claim. Every paraphrase therefore pays for entailment rather than bypassing the load bearing check. (basis: claim level verification; docs/scope/scope.md, Feature 11 calibration boundary)

Facet extraction happens before answer generation in a separate structured call. A generator allowed to declare the facets it later claims to cover can omit part of the question and still report success. Fixing facets first and checking them independently afterward costs one model call but keeps abstention meaningful. (basis: independent verification)

Supersession uses metadata notices rather than automatic successor retrieval. Generation receives only successor id, title, status, date, and the metadata evidence id, then is told that the predecessor changed and that it must not invent how. The application also renders the mandatory disclosure deterministically, so correctness does not depend on the model following a stylistic instruction. Old decisions stay answerable, while successor decision content requires independently retrieved successor chunks. JobPilot cannot exercise this today, so the spec uses the same honest untested disposition as the adapter winner ladder behavior that its current corpus could not reach. (basis: spec 0003, ladder step 4 disposition; supersession aware decision history)

The disclosure itself is deterministic and cites nonvector metadata evidence for `supersedes`. Asking the model to remember a notice would make a mandatory factual sentence depend on style, while forcing a chunk id would pretend structured metadata had been retrieved semantically. A distinct metadata citation keeps the sentence inside the same evidence contract. (basis: spec 0002, supersession; provenance preserving citations)

## References

**Project sources**:

- `AGENTS.md`, Clean Architecture, strict typing, error handling, and the Skateboard build approach.
- `docs/scope/scope.md`, Feature 9 transparency, incremental ingestion, supersession, provider module constraint, known answer, and Feature 11 evaluation boundary.
- `docs/specs/0001-stack-and-architecture.md`, OpenAI, SQLite, Chroma, chunking, generation, verification, and retrieval defaults.
- `docs/specs/0002-canonical-decision-record-schema.md`, field meanings, alternatives, rationale, evidence, and supersession.
- `docs/specs/0003-jsmastery-specs-adapter/`, fingerprints, manifest, JobPilot field mapping, panel alternatives, and the untested ladder step disposition.
- `docs/specs/0004-doctor-diagnostic/` and `docs/specs/0005-runtime-adapter-loading/`, established CLI exit and configuration conventions.
- `docs/specs/0006-adapter-conformance-test-adapter/`, complete adaptation result comparison and declarative conformance cases.
- `README.md`, user workflow and cited answer promise.

**Practices and standards**:

- Command Query Separation for explicit mutation and read boundaries.
- Content addressed incremental ingestion.
- Provenance preserving citations.
- Write new, activate, then retire for recoverable derived index updates.
- Structured generation with claim level entailment verification.
- Treat retrieved content as untrusted prompt input.
