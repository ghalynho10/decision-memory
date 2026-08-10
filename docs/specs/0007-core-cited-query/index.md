# 0007. Core cited query

**Date**: 2026-08-09
**Status**: In Progress

## Summary

Two explicit commands turn canonical decision records into a cited answer. `ingest` writes a versioned local index, while `query` only reads that index and either returns verified sentences with source citations or says `not enough evidence here`. Every result carries a complete trace, so stale data, retrieval, chunking, generation, and verification failures stay visible.

## Requirements

**User stories**:

1. As a developer, I want to ask why a project decision was made and receive an answer whose every factual sentence points back to the exact source.
2. As a maintainer, I want explicit, incremental ingestion so indexing cost and mutation never hide inside a read command.
3. As a reviewer, I want a structured trace that shows every retrieval and verification decision so a wrong answer can be assigned to one pipeline stage.
4. As a user with incomplete evidence, I want an honest abstention that can never be confused with a provider or storage failure.

**Acceptance criteria**:

1. **AC-1**: `decision-memory ingest [RECORDS_DIR] [--store PATH] [--rebuild] [--dry-run] [--debug]` and `decision-memory query QUESTION [--store PATH] [--allow-stale] [--debug]` are the only new CLI surfaces. Ingest consumes canonical record files plus their manifest. Answer evidence comes only from the local store. Query may also read the external manifest only to determine freshness, and `--allow-stale` permits query when it is absent. Neither command loads an adapter or requires the source corpus. The exact path precedence and store layout in **Feature design** apply. The application exposes `ingest_records(IngestRequest) -> IngestResult` and `query_index(QueryRequest) -> QueryResult` as plain, interface independent boundaries whose expected failures are returned, not raised.
2. **AC-2**: The adapter output manifest becomes schema version `2` in one breaking change. Every entry adds `record_digest`, `entry_digest`, and a `field_sources` map using the complete value path and provenance grammar in **Feature design**. The manifest adds a nonbinding absolute `source_root_hint`. `AdaptationResult`, the built in adapter, the starter adapter, runtime contract checks, every spec 0006 conformance case, the conformance comparison, the adapter author guide, and the contract documentation governed by specs 0003, 0005, and 0006 all change together. Older manifests fail clearly and instruct the user to run `adapt` again.
3. **AC-3**: Ingest validates manifest schema, entry digest, each canonical record, record digest, and complete required provenance before any provider call for that record. A digest mismatch reports a tampered derived record even when `adapt` previously reported the unchanged source as skipped. Missing provenance fails the record and names every value path. Validation continues through independent records in record id order. `--dry-run` needs no API key, makes no provider call or mutation, and reports action, evidence tokens, actual embedding input tokens, provider batch count, chunks, and every validation failure.
4. **AC-4**: Chunking preserves canonical field boundaries and follows the exact normalization, value path, aggregate text, paragraph, sentence, overlap, empty value, and oversize rules in **Feature design**. Chunkable content is `context`, `decision.chosen`, complete alternatives, `why`, `rationale_summary`, consequences, and retained `body` sections. Structured metadata is not embedded. Every chunk keeps deterministic chunk id, record id, fingerprint, aggregate value path, ordinal, token count, underlying text, and the deduplicated union of its source references.
5. **AC-5**: The exact versioned embedding prefix in **Feature design** adds record title and aggregate value path to the embedding input. Stored text, generation context, `IngestResult`, and debug output contain only underlying canonical content. The exact pipeline signature includes embedding model and dimensions, chunker and prefix versions, `tiktoken` encoding, target, overlap, and atomic rules. Any change forces explicit rebuild.
6. **AC-6**: SQLite is authoritative for index metadata, record state, canonical snapshots, tags, field sources, chunks, chunk sources, metadata evidence, and supersession links. Chroma stores one cosine vector per chunk id and locator metadata only. Query verifies every active SQLite chunk has a matching Chroma id, fingerprint, and generation before retrieval. Updates write every new vector, verify them, activate SQLite only afterward, and delete old vectors last. Inactive crash residue is excluded and later cleaned.
7. **AC-7**: Ingestion is incremental by adapter fingerprint and processes entries by record id. Added and changed records are embedded one record at a time in bounded batches. Unchanged records make no embedding call. Record local validation or provider failure is recorded and later records continue. Fatal manifest, lock, or store integrity failure stops the run. Removal intent becomes ineligible before vector deletion, so a failed removal can never serve old content. Successful removal leaves only a tombstone with record id, prior fingerprint, UTC removal time, and `absent_from_manifest`. Failed updates may retain and serve the prior version only through `--allow-stale`.
8. **AC-8**: Pipeline signature is compared before mutation in ingest and before question embedding in query. Normal ingest refuses mismatch and points to `ingest --rebuild`. Query always refuses mismatch, and `--allow-stale` cannot bypass it. Rebuild creates and verifies a new store generation, atomically switches the active generation pointer, and never replaces the separate lock database. Failure preserves the last good generation and leaves resumable inactive work. Rebuild needs only records and the manifest.
9. **AC-9**: The SQLite lock protocol in **Feature design** gives ingest an exclusive lock for the complete run and query a shared lock for the complete query. Multiple queries may run together. Lock wait is zero. Ingest stores the records manifest path hint, snapshots raw and semantic manifest digests, and rechecks raw bytes before declaring freshness. Query snapshots both digests at start and rechecks before return. A change makes the result drift: default query discards the answer and exits `1`, while `--allow-stale` returns it with complete warnings.
10. **AC-10**: The exact DTO and rendering contracts in **Feature design** apply. `QueryResult` always has state, sentences, citations, freshness, abstention stage, failure, and trace. Every factual answer sentence has markers. Chunk citations name chunk id. Deterministic supersession disclosures use metadata evidence citations without a chunk id. Source entries are deduplicated and sorted by the fixed rules, and name record id, evidence id, optional chunk id, value path, relative path, section, resolution, and freshness.
11. **AC-11**: Against JobPilot's real adapted specs, the exact query `Why was the private beta access gate added, and what was the alternative?` returns `answered`, cites `DM-0012`, states Panel 1 was which routes the gate covers, states Option B covering all four routes was chosen, and names Option A, `The two agent routes only (the original proposal)`, as rejected. The separately extracted why facet must be covered by a sentence entailed by a cited `DM-0012` chunk. The three named propositions are the objective live oracle; no extra exact wording is invented. A deterministic fake test locks the same structured propositions, while the live provider check remains a behavior integration test.
12. **AC-12**: Retrieval is semantic only. Chroma filters to SQLite supplied eligible generation, record id, and fingerprint tuples and returns up to 24 cosine candidates. Application sorting by raw distance then chunk id is deterministic within the returned set. It accepts the first 8. The provisional relevance floor is `null`, meaning disabled, so no candidate is excluded for similarity in Slice 1. Trace keeps the future `below_floor` disposition but does not emit it while the floor is null. It records user `filters: none`, internal eligibility, candidate and accepted limits, raw finite distance, `similarity = 1 - distance`, rank, full precision values, and `accepted` or `outside_top_8`. CLI displays scores to six decimal places. Empty eligible input abstains without an embedding call.
13. **AC-13**: The version 1 DTO schemas and enum values in **Feature design** are stable. `QueryResult.trace` exists for answered, abstained, and failed results and preserves data collected before failure. `--debug` controls display only and prints the fixed human sections in fixed order with complete chunk text. Trace includes freshness, candidate details, provider attempts, extracted facets, draft sentences, verification, coverage, citations, and terminal stage. Collections are tuples ordered by the rules in **Feature design**. Optional values are explicit `None`, never conditionally omitted.
14. **AC-14**: Failure triage is reviewer guidance over `IngestResult` and `QueryTrace`, not an automated runtime diagnosis. It applies only after the expected fact is proven present in the canonical record. Within that boundary, the first failing check assigns retrieval, chunking, generation, or claim verification and abstention exactly as defined in **Feature design**. Missing or wrong canonical content is an adaptation or ingestion failure outside this four stage chain.
15. **AC-15**: A separate structured call first extracts fixed question facets from the original question. Generation then receives those facets and returns structured answer sentences with cited chunk ids. The deterministic verifier passes only exact normalized containment. Every synthesis or paraphrase goes to model entailment. Unsupported sentences are removed. Independent coverage checks the original question, fixed facets, and remaining sentences. Uncovered facets cause exact `not enough evidence here`, exit `0`, stage `claim_verification`, and exact facet text in trace. All generation schemas, bounds, ids, verdicts, and failure rules follow **Feature design**.
16. **AC-16**: No eligible chunk, including a valid empty index, returns exact `not enough evidence here`, exit `0`, stage `retrieval`, without requiring an API key. Provider, schema, lock, manifest, or store failure is never abstention. Questions over the embedding model input limit are usage error `2`. Retryable provider failures use the exact three retry policy in **Feature design**. Structured model output gets one schema repair attempt, then fails operationally. Final failure exits `1` and names its stage.
17. **AC-17**: Freshness states are `current`, `drift`, `unknown`, and `incompatible`, with the exact reason enums in **Feature design**. Query reads the manifest path hint and compares semantic entries with the ledger. Missing manifest is `unknown`, not corruption. Default query refuses drift or unknown. `--allow-stale` permits only those manifest states, prints `WARNING: stale index`, and lists every reason. A citation using an older active snapshot is `stale_version`. Pipeline incompatibility is always fatal.
18. **AC-18**: Active supersession links create deterministic metadata evidence and structured `SupersessionNotice` values. When a predecessor chunk is retrieved, generation receives each immediate eligible successor's id, title, status, optional date, and no successor decision content. The prompt says the predecessor was later changed and forbids inventing how. The application independently guarantees disclosure by rendering a deterministic sentence that names each successor by id and title and cites the successor `supersedes` provenance. It does not describe successor decision content unless successor chunks were independently retrieved. Self links and cycles fail ingestion; multiple successors are sorted by id and all disclosed. Missing optional dates are allowed. JobPilot cannot exercise this path because the current adapter emits no links, matching spec 0003's untested ladder step disposition.
19. **AC-19**: `source_root_hint` is an absolute resolved corpus root string produced by adapt and included in semantic freshness. It need not exist at query time. Source paths are normalized POSIX relative paths with no absolute form, `..`, empty segment, or trailing slash. Resolution uses containment and exact case checks without following a symlink outside the hinted root. States are `resolved`, `missing`, `hint_unavailable`, and `invalid_relative_path`. Every citation returns the relative path. Any unresolved state is informative, not query failure.
20. **AC-20**: `OPENAI_API_KEY` is required only when the completed plan includes a provider call. It is validated after read only planning but before any store mutation. Dry run, unchanged or removal only ingest, and empty index abstention need no key. Other CLI commands remain usable without it. All embeddings live in one infrastructure module. Facet extraction, answer generation, entailment, and coverage live in one generation module. No provider classes exist. Prompts delimit source as untrusted, ignore embedded instructions, and expose no tools. Normal logs follow the allowlist in **Feature design**. Debug documentation warns that questions, drafts, chunks, citations, and paths may be sensitive.
21. **AC-21**: Exit `0` covers successful ingest, answer, or honest abstention. Exit `1` covers partial ingest, stale refusal, incompatible pipeline, provider failure, lock failure, malformed manifest, corrupt initialized store, or SQLite and Chroma mismatch. Exit `2` covers usage, including empty or overlimit question. Exit `3` covers a missing required records directory or missing store path. Missing manifest under an initialized store is freshness `unknown`, not exit `3`. Store format, SQLite integrity, active generation marker, active chunk count and id digest, and Chroma parity are checked before query. Normal ingest does not repair corruption. Explicit rebuild is recovery. Ruff, strict mypy, unit tests, and marked integrations pass.

## Decision

**Chosen option**: Option 1, explicit ingestion with a versioned cited index

Adaptation produces canonical records and a provenance rich manifest. Explicit ingestion turns those artifacts into a record scoped SQLite and Chroma index. Query reads it through a fully traced, verified answer path. (basis: specs 0001, 0002, 0003, 0005, and 0006; Command Query Separation; content addressed ingestion)

No community implementation skill was selected. The offered search for a `tiktoken` Agent Skill or MCP server was declined.

## Feature design

### Scope boundaries

Included:

- Manifest schema version 2 and the adapter protocol work required for original source provenance.
- Explicit previewable ingestion, incremental record replacement, removals, rebuild, and recovery.
- Semantic retrieval, verified sentence generation, citations, abstention, and structured tracing.
- CLI display over two stable application functions.

Excluded:

- Lexical retrieval, score fusion, record diversity, and metadata filter inputs. Feature 10 owns them.
- Relevance floor calibration and the complete evaluation harness. Feature 11 owns them.
- MCP, HTTP, and web interfaces.
- Adapter execution from ingest or query.

### Path resolution and store layout

Project settings use the existing rule from spec 0005: find the nearest `.decision-memory.yml` from the current directory upward, stopping at the Git root. CLI input wins over config.

Records directory precedence is:

1. Positional `RECORDS_DIR`.
2. Config `output`.
3. `<configured corpus_root>/.decision-memory/records`.

No value after precedence is usage error `2`. A resolved path that is absent or not a directory is exit `3`.

Store directory precedence is:

1. `--store PATH`.
2. `<configured corpus_root>/.decision-memory/query-index`.
3. `<nearest Git root>/.decision-memory/query-index`.
4. `<current directory>/.decision-memory/query-index` when no config or Git root exists.

The store format version is `1`. Its complete layout is:

```text
query-index/
  FORMAT
  ACTIVE
  lock.sqlite3
  generations/
    <generation-id>/
      records.sqlite3
      generation.json
      chroma/
```

`FORMAT` contains `1` plus LF. `ACTIVE` contains one generation id plus LF and is replaced with an atomic same directory rename. A generation id is a lowercase UUID hex value. `generation.json` contains immutable format version, generation id, initial pipeline signature, and creation time. Mutable manifest and chunk integrity values live in SQLite and update in the same transaction that activates a record. `lock.sqlite3` is never placed inside or replaced with a generation.

Ingest stores the absolute records manifest path as a hint in SQLite. Query uses it for freshness only. Missing evidence files or a missing manifest never changes the stored answer evidence.

### Adapter output contract

`AdaptationResult.field_sources` maps an exact value path to one or more `SourceReference` values. Canonical object members use fixed dot names. List members use zero based brackets. The grammar is `name((.name)|(\[[0-9]+\]))*`, and only paths listed below are valid. Canonical field names contain no dot or bracket, so no escape form exists.

Valid populated source paths are:

- `title`, `context.problem`, `context.triggering_change`, `decision.chosen`, `rationale_summary`, and `supersedes`.
- `why[n]`, `consequences.positive[n]`, and `consequences.negative[n]`.
- `decision.alternatives[n].title` and `decision.alternatives[n].rejection_reason`.
- `body[n]`, one logical retained H2 section in source order. The adapter emits the section text under this logical path even though the canonical record serializes one combined `body` string.

Empty or absent values need no source. Every populated chunkable leaf, the title used by the embedding prefix, and populated `supersedes` require at least one source. References are normalized, deduplicated, and sorted by path then section. `path` follows **AC-19**. `section` is a nonempty exact heading without Markdown markers. The reserved value `preamble` identifies source metadata before the first H2.

An alternative chunk uses aggregate path `decision.alternatives[n]` and unions the title and rejection reason sources. A body chunk keeps its `body[n]` path through subdivision.

Manifest schema version 2 adds:

| Location | Field | Meaning |
|---|---|---|
| Manifest | `schema_version: 2` | Exact manifest grammar version |
| Manifest | `source_root_hint: str` | Absolute resolved corpus root at adapt time, informative and allowed not to resolve later |
| Manifest entry | `record_digest: str` | SHA256 over a stable JSON form of the canonical record |
| Manifest entry | `entry_digest: str` | SHA256 over all retrieval relevant entry fields, including provenance |
| Manifest entry | `field_sources: dict[str, list[SourceReference]]` | Exact original provenance for canonical values |

Canonical JSON is UTF8 without BOM or trailing LF. It uses NFC Unicode, LF line endings, keys sorted by code point, compact separators, JSON strings for dates, explicit `null` for absent scalar or object fields, and `[]` for empty lists. The canonical record mapping includes every spec 0002 field. SHA256 is lowercase 64 character hex.

`record_digest` hashes canonical record JSON. `entry_digest` hashes canonical JSON containing id, fingerprint, contributing files, record path, record digest, and the normalized field source map. The semantic manifest digest hashes schema version, adapter version, source root hint, and entries sorted by id. It excludes `generated_at`, skips, and collisions. A separate raw digest hashes the exact manifest bytes for concurrent mutation detection.

Adapter version remains part of the source fingerprint. A mapping or provenance behavior change requires an adapter version change. Ingest recomputes record and entry digests rather than trusting declared values.

### Data model

| Entity | Key | Required fields | Nullable fields and rules |
|---|---|---|---|
| `IndexMetadata` | singleton integer id `1` | store format, SQLite schema version, generation id, pipeline signature, semantic and raw manifest digests, active chunk count, sorted active chunk id digest, records manifest path hint, last ingest UTC time, source root hint | either path hint may not resolve after a move |
| `RecordState` | record id | state, action, desired entry digest | desired fingerprint, active fingerprint, record path, failure code, indexed UTC time, removed UTC time, removal reason vary by state |
| `RecordSnapshot` | record id, unique | active fingerprint, record digest, title, status, canonical JSON | date, supersedes, and other optional canonical fields follow spec 0002 |
| `RecordTag` | record id plus tag, unique | tag | FK to active snapshot, cascade delete |
| `FieldSource` | record id plus value path plus path plus section, unique | value path, source path, section | FK to active snapshot, cascade delete |
| `Chunk` | chunk id | generation id, record id, active fingerprint, value path, ordinal, text, token count | unique generation plus record id plus fingerprint plus value path plus ordinal |
| `ChunkSource` | chunk id plus path plus section, unique | source path, section | FK to chunk, cascade delete |
| `SupersessionLink` | predecessor id plus successor id, unique | both record ids | derived from active snapshots only; successor is the record whose `supersedes` value names predecessor |
| `MetadataEvidence` | evidence id | kind, record id, value path, text | source references required, no vector |

SQLite uses `TEXT` for ids, enums, digests, canonical JSON, and RFC3339 timestamps, and `INTEGER` for ordinals and token counts. Timestamps use an injected UTC clock and serialize with microseconds plus `Z`. Foreign keys are on. All tables and indexes are created in one schema version 1 migration. Unknown store or SQLite schema versions refuse.

`RecordState` to `RecordSnapshot` is one to zero or one. A removed tombstone has no snapshot. A failed removal may keep the snapshot for recovery audit but it is ineligible. `RecordSnapshot` to tags, field sources, chunks, and metadata evidence is one to many. Canonical snapshots store the exact canonical JSON described above. Record paths are relative to `RECORDS_DIR` and must be one normalized filename from the manifest.

Chroma collection `decision_chunks_v1` is created with cosine distance. Vector metadata is exactly generation id, record id, active fingerprint, value path, and ordinal. Upsert by deterministic chunk id is idempotent. Before activation, ingest fetches every requested id and confirms count and metadata. Valid cosine distance is finite and between `0.0` and `2.0`; another value is store failure.

### State transitions

Legal transitions are:

| From | To |
|---|---|
| `current` | `current`, `stale_changed`, `pending_removal` |
| `pending_addition` | `current`, `failed` |
| `stale_changed` | `current`, `failed`, `pending_removal` |
| `pending_removal` | `removed`, `failed` |
| `failed` | `pending_addition`, `stale_changed`, `pending_removal` |
| `removed` | `removed`, `pending_addition` |

Desired and active fingerprints explain failed states. A failed addition has no active fingerprint. A failed update has differing desired and active fingerprints and may serve the old version only through `--allow-stale`. A manifest absence always moves any existing or failed record through pending removal. Successful removal deletes content and records `absent_from_manifest`.

Required state fields and serving eligibility are:

| State | Required values | Eligible for query |
|---|---|---|
| `current` | desired equals active, snapshot present | yes |
| `pending_addition` | desired present, active absent | no |
| `stale_changed` | desired and active differ, snapshot present | no while ingest lock is held |
| `pending_removal` | desired absent, active may remain for cleanup | never |
| `failed` addition | desired present, active absent, failure code | never |
| `failed` update | desired and active differ, snapshot present, failure code | only with `--allow-stale` |
| `failed` removal | desired absent, active may remain, failure code | never |
| `failed` unchanged validation | desired equals active, snapshot present, failure code | only with `--allow-stale` |
| `removed` | desired and active absent, removed time and reason | never |

Ingest computes actions in record id order. It validates every planned record before mutation. When a provider call is planned, it validates the API key before it writes desired states. It then persists desired state before record work, activates successes independently, records local failures, and continues. Global freshness is current only when every manifest entry is current, every removal completed, the manifest remained unchanged, and no record has a failure.

Cleanup rules are fixed. Inactive orphan cleanup runs after integrity checks and before paid record work. Failure there stops ingest before embedding. Old vector deletion after successful activation is best effort but visible. If it fails, the new record remains valid, ingest exits `1`, and the next run retries cleanup. A vector is expected crash residue, rather than corruption, only when its generation or fingerprint is not eligible. A missing or mismatched vector for an eligible SQLite chunk is corruption.

### Chunking and embedding

The chunker walks canonical values in schema order. Empty strings after outer whitespace trimming produce no chunk. It normalizes CRLF and CR to LF but otherwise preserves underlying text. Metadata remains queryable in SQLite and is copied to Chroma only when retrieval needs it.

A blank line contains only zero or more spaces or tabs before LF. A run of one or more blank lines delimits paragraphs. Leading and trailing blank lines are discarded, while nonblank line content and single line breaks inside a paragraph are preserved. Stored chunks join packed paragraphs with exactly two LF characters. Packing adds the next complete paragraph when the result is at most 400 tokens. A paragraph over 400 tokens splits after `.`, `?`, or `!`, followed by zero or more ASCII single quotes, ASCII double quotes, right single quotes, right double quotes, closing parentheses, closing brackets, or closing braces, and then one or more whitespace characters or end of text. It packs complete sentences by the same rule. A single sentence over 400 tokens stays one chunk. Any complete embedding input over the pinned 8191 token model limit fails the record.

Overlap copies the largest complete trailing sentence sequence whose embedding input is at most 15 percent of the preceding chunk token count. It joins copied sentences with one space and copied paragraphs with two LF characters. If no complete sentence fits, overlap is empty.

An alternative forms one atomic chunk because title and rejection reason have meaning only together. Its exact text is `Alternative: <title>` and, when populated, LF plus `Rejected because: <reason>`. Its aggregate path is `decision.alternatives[n]`, and its sources are the sorted union of both leaf paths. A missing rejection reason leaves only the title line and preserves the existing validation warning.

Each logical body section is `body[n]`. Its underlying text is exact heading text rendered as `## <heading>`, two LF characters, then the section body. It selects only that section's source references before long prose subdivision.

The embedding input format version is `embedding-prefix-v1`:

```text
Record title: <title>
Value path: <aggregate-value-path>

<underlying-chunk-text>
```

All newlines are LF. For this prefix only, every run of title whitespace is collapsed to one ASCII space and outer title whitespace is removed. Value paths contain only the declared grammar, and chunk text is inserted literally after line ending normalization, so no further escaping occurs. Canonical title is required, so no missing title format exists. This prefix is never stored as evidence text.

Chunk id is `ch_` plus lowercase SHA256 hex over canonical JSON for the array `["chunk-v1", generation_id, record_id, record_fingerprint, aggregate_value_path, ordinal]`.

`tiktoken` is a new direct dependency. The encoding is `cl100k_base`. Embeddings use `text-embedding-3-small` with 1536 dimensions. Pipeline signature is lowercase SHA256 hex over canonical JSON containing signature schema `1`, model, dimensions, encoding, chunker version `field-boundary-v1`, prefix version, target `400`, overlap string `0.15`, paragraph and sentence rule version, and atomic path set. Model aliases are stored exactly as configured. Embedding requests process one record at a time, in batches capped at 64 chunks and 50,000 input tokens. The runner up was cross record batching, rejected because provider failure would no longer align with the record state machine.

### Ingestion consistency and recovery

`ingest --dry-run` previews spend. It never calls OpenAI. `adapt --dry-run` previews derived record writes. The matching flag name means no writes in both commands, but each protects a different side effect.

Dry run reports both token views because the title and value path prefix is billable input but is not evidence. For each record it reports action, result, failure code, chunk count, evidence token count, embedding input token count, and batch count. Records sort by id. Validation continues after record local failures.

The write order for a changed record is fixed:

1. Validate the record, digest, and provenance.
2. Build the complete chunk plan.
3. Embed all chunks under the desired fingerprint.
4. Write every new Chroma vector without making it eligible.
5. In one SQLite transaction, write the snapshot and chunks and switch the active fingerprint.
6. Delete old Chroma vectors last.

Any crash before step 5 leaves inert orphan vectors. Any crash after step 5 leaves eligible new vectors plus ineligible old vectors. The next ingest removes either kind of orphan. Delete first is forbidden.

Rebuild never changes the active generation in place. It creates or resumes an inactive generation only when its pipeline signature and semantic manifest digest match the requested rebuild. Every record must succeed. It then checks SQLite integrity, active chunk count and sorted id digest, and every active Chroma locator. Only a complete generation may replace `ACTIVE` through atomic rename. Failure leaves the old generation active and the inactive generation resumable.

A separate SQLite lock database lives in the store and is never rebuilt. It uses `journal_mode=DELETE`, `foreign_keys=ON`, and `busy_timeout=0`, with one `lock_guard` row. Query runs `BEGIN`, then selects that row to establish and hold a shared lock. Ingest runs `BEGIN EXCLUSIVE`, then selects the row and holds the transaction for the full run. A lock conflict returns immediately. The authoritative generation database may commit each record independently because its file is distinct from the lock database.

Store initialization creates `FORMAT`, the lock database, and a staging generation under the exclusive lock. It writes `ACTIVE` only after parity checks. A store with `FORMAT` but without a valid active generation is corrupt initialized state, exit `1`. A wholly absent `--store` path on query is exit `3`.

### Retrieval and answer generation

Before any provider call, query verifies store format, SQLite integrity, generation metadata, active chunk count and id digest, and Chroma presence plus locator metadata for every active SQLite chunk. Extra inactive vectors are allowed and excluded.

If no eligible chunk exists, query abstains before key validation or question embedding. Otherwise it rejects a question whose `cl100k_base` count exceeds 8191 tokens, then validates the key and embeds the question as written. SQLite supplies every eligible generation, record id, and fingerprint tuple as Chroma's internal filter. Chroma returns at most 24 cosine candidates. The application rejects nonfinite or out of range distances, sorts the returned set by raw distance then chunk id, and ranks from one. It accepts the first eight because `relevance_floor` is `None`. The `below_floor` enum remains reserved for Feature 11.

The generation concern runs three structured stages. First, facet extraction sees only the original question and returns the fixed facets. Second, answer generation sees those facets plus accepted chunk text, provenance, and record metadata. Third, after sentence verification, coverage sees the original question, fixed facets, and remaining sentences.

Schemas are version `1`:

- `FacetSet`: one to eight unique facets ordered as they appear in the question. Each has id `F1` through `F8` and nonempty text.
- `DraftAnswer`: zero to twelve sentences. Each has id `S1` through `S12`, nonempty text that parses as exactly one sentence, and one to eight unique known chunk ids.
- `EntailmentVerdict`: `supported` or `unsupported`, plus a nonempty reason. It has no confidence score.
- `CoverageVerdict`: one row per fixed facet with `covered: bool`, nonempty reason, and supporting sentence ids when covered. It cannot add or remove facets.

Unknown or duplicate ids, wrong bounds, empty required values, repeated text, multiple sentence text, or a missing facet row is schema failure. One repair request includes only the validation error and original structured task. A second malformed response is operational failure.

The deterministic shortcut normalizes candidate sentence and chunk text with Unicode NFKC, case folding, line ending normalization, and whitespace collapse while preserving punctuation and numbers. It passes only when the complete normalized sentence is a substring of one cited chunk. It never rejects. Every other sentence goes to entailment with all cited chunks kept as separate labeled evidence blocks. Unsupported sentences are removed.

Coverage is independent of draft generation and checks both the original question and the fixed facet set. Any uncovered facet abstains and its exact id and text enter the trace.

For every retrieved predecessor, generation receives an ordered `SupersessionNotice` for each immediate eligible successor. The notice contains only successor id, title, status, optional date, and metadata evidence id. It contains no successor context, decision, rationale, alternatives, consequences, or body. The prompt requires saying that the predecessor was later changed, forbids guessing how it changed, and permits successor decision detail only from independently retrieved successor chunks.

Disclosure does not depend on model output. The application renders `This decision was later changed by <title> (<id>).` for each notice sorted by successor id. It cites `MetadataEvidence` derived from that successor's `supersedes` value and source references. Multiple successors produce multiple sentences. A successor may omit date. A cycle fails every involved record during ingestion. A missing predecessor is allowed but creates no disclosure until that predecessor exists. Chains disclose immediate links only.

All OpenAI SDK access is concentrated in `infrastructure/openai_embeddings.py` and `infrastructure/openai_generation.py`. The latter owns facet extraction, answer generation, entailment, and facet coverage because all are one generation concern. Application code receives narrow callables. Provider classes and provider selection protocols are forbidden.

### Trace and failure triage

All DTOs are frozen dataclasses using tuples, never mutable lists. Optional fields are present as `None`. Expected input, provider, lock, and store failures return a result. Only programming errors may raise past the application boundary.

Fixed enums are:

| Enum | Values |
|---|---|
| `IngestState` | `completed`, `partial`, `failed` |
| `RecordAction` | `added`, `updated`, `unchanged`, `removed`, `failed` |
| `QueryState` | `answered`, `abstained`, `failed` |
| `FreshnessState` | `current`, `drift`, `unknown`, `incompatible` |
| `StaleReason` | `record_added`, `record_changed`, `record_removed`, `manifest_unavailable`, `manifest_changed_during_query`, `failed_ingest` |
| `CandidateDisposition` | `accepted`, `below_floor`, `outside_top_8` |
| `AbstentionStage` | `retrieval`, `claim_verification` |
| `ProviderOutcome` | `success`, `retryable_failure`, `final_failure`, `schema_failure` |
| `CitationKind` | `chunk`, `supersession` |
| `ResolutionState` | `resolved`, `missing`, `hint_unavailable`, `invalid_relative_path` |
| `CitationFreshness` | `current`, `stale_version` |

Core DTO fields are:

| DTO | Fields |
|---|---|
| `IngestRequest` | `records_dir: Path`, `store_dir: Path`, `rebuild: bool`, `dry_run: bool` |
| `ChunkPlan` | `chunk_id`, `record_id`, `fingerprint`, `value_path`, `ordinal`, `text`, `evidence_token_count`, `embedding_input_token_count`, ordered sources |
| `RecordIngestResult` | `record_id`, action, state, desired fingerprint, active fingerprint, ordered chunk plan, batch count, failure code |
| `IngestResult` | schema version, state, exit code, store path, semantic and raw manifest digests, ordered record results, provider attempts, failure |
| `QueryRequest` | `question: str`, `store_dir: Path`, `allow_stale: bool` |
| `AnswerSentence` | sentence id, text, ordered citation ids |
| `Citation` | citation id, kind, evidence id, record id, optional chunk id, value path, relative path, section, resolution, freshness |
| `SupersessionNotice` | predecessor id, successor id, successor title, successor status, optional successor date, metadata evidence id |
| `QueryResult` | schema version, state, exit code, ordered sentences, ordered citations, freshness, optional abstention stage, trace, optional failure |
| `Failure` | stable code, stage, sanitized detail |

Trace DTOs are version `1`. `QueryTrace` always holds:

- Freshness: state, stored and running pipeline signatures, records manifest path and availability, start and end semantic plus raw digests, per record desired and active fingerprints, and stale reasons sorted by record id then enum.
- Retrieval: question, user `filters: none`, internal eligibility tuples sorted by record id, candidate limit, accepted limit, optional floor, every candidate, raw distance, similarity, rank, disposition, full chunk text, and provenance.
- Generation: fixed facets, supersession notices, draft sentences, and cited chunk ids.
- Verification: containment result, model verdict when called, removed sentences, coverage rows, and uncovered facets.
- Providers: concern, attempt number, elapsed milliseconds from a monotonic clock, and outcome. Attempts remain after a fatal failure.
- Result: query state, optional abstention stage, citations, and stale markers.

Candidate order is rank order. Citations allocate `C1`, `C2`, and so on by first sentence use. A chunk with several source references expands to one citation per reference. The source list deduplicates by kind, evidence id, relative path, and section, preserving first use. Within one sentence citation ids sort numerically.

Human rendering is fixed and is not JSON. Normal ingest prints `plan: added N, updated N, unchanged N, removed N, failed N`, then one record line in id order, then `result: <state>` and `output: <store>`. Dry run appends `dry run, no provider calls or writes`. Debug adds complete chunk plan rows after each record.

Normal query prints `WARNING: stale index` first when applicable, then each answer sentence followed by markers such as `[C1]` or `[C1,C2]`, then `Sources`, then citation rows in id order. Abstention prints only the exact abstention text after any stale warning. Failure prints `error <stage> <code>: <sanitized detail>`.

Query debug appends these sections in order: `Freshness`, `Retrieval`, `Facets`, `Draft`, `Verification`, `Providers`, `Citations`, `Result`. Field labels follow DTO field order. Floats display with six decimal places. Full chunk text prints between explicit `chunk text begin` and `chunk text end` lines.

The diagnostic chain is reviewer guidance and runs backward from a bad answer only after the fact is confirmed in the canonical record:

| First failing check | Assigned stage | Evidence |
|---|---|---|
| Correct indexed chunk was not accepted | Retrieval | Candidate ranks, scores, floor, and dispositions |
| Expected canonical value is absent or malformed in the index plan | Chunking | `IngestResult.chunk_plan` text, boundaries, value path, and provenance |
| Correct chunks were accepted but draft sentence is missing or wrong | Generation | Accepted chunk ids, facets, and draft sentences |
| Supported draft was removed or a covered facet was rejected | Claim verification or abstention | Sentence verdicts and uncovered facets |

If the canonical record itself is wrong or missing the fact, the failure belongs to adaptation or ingestion and is outside the four stage chain. Store integrity errors also produce no answer and remain operational errors. Runtime does not emit an automated diagnosis field because it has no expected fact oracle.

### Freshness and source resolution

At query start, pipeline mismatch produces `incompatible`. A missing manifest produces `unknown` with `manifest_unavailable`. A present semantic manifest equal to the stored digest and with no failed record produces `current`. Entry differences produce `drift` reasons by record id: absent from stored ledger is `record_added`, differing entry digest is `record_changed`, absent from current manifest is `record_removed`, and a recorded failed attempt is `failed_ingest`.

Query reads and hashes the manifest again before returning. Raw byte change adds `manifest_changed_during_query`. It reparses the end manifest when possible so the trace can show end semantic differences. Under default freshness policy it discards any completed answer and returns failed stale refusal. Under `--allow-stale` it returns the completed answer with warning and both start and end state.

Citation resolution first validates the stored relative POSIX path. It rejects absolute paths, `..`, empty segments, and trailing slash as `invalid_relative_path`. Without a usable absolute root hint it returns `hint_unavailable`. With a root, it joins path segments, verifies lexical and resolved containment, rejects a symlink escape, and checks exact entry case at every segment. An existing regular file is `resolved`; a directory or absent entry is `missing`. Resolution never changes answer state.

### API surface

| Surface | Kind | Key inputs | Key outputs | Auth | Key errors |
|---|---|---|---|---|---|
| `ingest_records(request)` | application function | records directory, store directory, rebuild, dry run | per record actions, complete chunk plans, freshness, exit code | local user | invalid manifest, digest mismatch, missing provenance, provider failure, lock conflict, corrupt store |
| `query_index(request)` | application function | question, store directory, allow stale | answer state, sentences, citations, freshness, trace, exit code | local user | empty question, stale refusal, pipeline mismatch, provider failure, lock conflict, corrupt store |
| `decision-memory ingest` | CLI | optional records and store paths, rebuild, dry run, debug | summary or complete plan | local user | exits 1, 2, or 3 per table below |
| `decision-memory query` | CLI | question, optional store path, allow stale, debug | cited answer or exact abstention | local user | exits 1, 2, or 3 per table below |

An empty or whitespace question is invalid usage. There is no arbitrary character limit, but encoded input may not exceed the embedding model token limit. No filter parameter exists in Slice 1.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Successful ingest, answered query, or honest retrieval or verification abstention |
| `1` | Partial ingest, stale refusal, pipeline mismatch, provider failure, lock conflict, malformed manifest, corrupt or inconsistent store |
| `2` | Invalid command usage, including an empty or overlimit question |
| `3` | Missing or invalid required records or store directory |

### Value sourcing

| Action | Value produced or displayed | Source |
|---|---|---|
| Ingest plan | add, change, unchanged, remove | manifest entries and fingerprints compared with `RecordState` |
| Ingest plan | tamper result | recomputed record and entry canonical digests compared with manifest values |
| Ingest plan | evidence and embedding token counts plus batches | canonical record, exact prefix, chunk rules, `cl100k_base`, and batch caps |
| Ingest result | freshness and stale record list | desired and active fingerprints plus manifest digest |
| Rebuild | active generation | complete staging generation after SQLite and Chroma parity verification |
| Query | pipeline compatibility | running pipeline signature compared with `IndexMetadata.pipeline_signature` |
| Query | manifest freshness | manifest path hint, start and end raw plus semantic digests, entries, and index ledger |
| Query | candidate score and disposition | eligible Chroma cosine distance, null floor, returned set limits 24 and 8, and returned set ordering |
| Query | fixed facets | separate structured extraction from the original question |
| Query | draft sentences | structured generation constrained by fixed facets and accepted chunks |
| Query | sentence support | exact normalized containment or generation module entailment |
| Query | uncovered facets | independent coverage over original question, fixed facets, and verified sentences |
| Query | chunk citations | accepted chunk ids joined to SQLite chunk, record, and source rows |
| Query | supersession citations | deterministic `MetadataEvidence` from successor `supersedes` value and provenance |
| Query | path resolution state | stored source root hint joined to corpus relative source path and checked at read time |
| Query | stale warning and citation mark | global manifest drift and cited record desired versus active fingerprint |
| Query | supersession notice | active `SupersessionLink` plus successor metadata and field source provenance |
| Query | abstention stage | first terminal evidence stage, `retrieval` or `claim_verification` |

### Key invariants

- Query never mutates the index, runs an adapter, or embeds corpus content.
- `--allow-stale` covers manifest drift only. It never bypasses pipeline incompatibility or corruption.
- Chroma searches only the active record id and fingerprint pairs supplied by SQLite. Orphan and retired vectors never enter the candidate pool.
- Activate only after all new vectors exist. Delete old vectors last.
- Removal intent is ineligible before cleanup begins. A failed removal never serves old content.
- Rebuild activates only a complete parity checked generation and never destroys the last good one.
- A changed record is rechunked and reembedded as a whole. Text equality cannot reuse a chunk whose field identity or provenance may have changed.
- A citation points to exactly the text generation received. The embedding prefix is never displayed as chunk text.
- Every chunkable value has original source provenance. Missing provenance fails the record.
- A provider failure is never abstention.
- The relevance floor is `None`, a deliberate disabled cutoff. It is not numeric zero.
- Deterministic verification passes exact normalized containment only. It never uses token overlap.
- Facets are fixed before answer generation and independently checked afterward.
- Supersession metadata never licenses invented successor decision details.
- Debug traces contain full decision text. Normal logs do not.

### Security model

This is a local, single user CLI with no authentication or authorization layer. Canonical records and questions may contain private project data. They are sent to OpenAI only by explicit ingest or query commands. Prompts delimit record content as untrusted evidence, tell the model to ignore instructions inside it, and expose no tools. Source text is never heuristically stripped or rewritten before generation or citation.

Normal logs use an allowlist: operation, stage, stable result or failure code, record id, chunk id, count, duration, attempt number, and provider HTTP status class. They exclude SDK exception messages and tracebacks, questions, source text, drafts, answers, citation paths, manifest and source root hints, API keys, and provider payloads. CLI errors use application sanitized detail rather than raw SDK text.

Debug output intentionally contains questions, source chunks, drafts, citations, and paths. It should be treated as sensitive when copied into an issue or bug report. No regulated compliance scope is inferred for this feature.

### Configuration required

- `OPENAI_API_KEY`: required only when an ingest or query plan contains an OpenAI call, validated before any store mutation.

The settled defaults from spec 0001 remain in force: `text-embedding-3-small` with 1536 dimensions for embeddings, `gpt-4o` for facet extraction and answer generation, `gpt-4o-mini` for entailment and coverage, and temperature 0 for generation calls. Provider model aliases are recorded in traces and results because hosted output is not byte deterministic.

Each provider call has a 60 second whole request timeout. Connection errors, timeouts, HTTP 408, 409, 429, and 500 through 599 receive up to three retries after 0.5, 1.0, then 2.0 seconds, with no jitter. The initial call plus retries means at most four attempts. Authentication, permission, not found, invalid request, and other 400 responses do not retry. Structured schema failure gets one repair request and no further schema retry. The application records only the sanitized class and status.

### Critical test scenarios

- Happy path: adapt and ingest JobPilot, then run query 1 and assert the three exact propositions, separately supported why facet, sentence citations, source list, and complete trace, verifies **AC-1**, **AC-10**, **AC-11**, **AC-12**, and **AC-13**.
- Incremental update: change one manifest record, ingest, and prove only that record was rechunked and embedded while all other vector ids stay unchanged, verifies **AC-7**.
- Removal after failure: fail an update, remove the record from the next manifest, fail vector deletion, and prove its old snapshot is immediately ineligible before eventual cleanup and tombstoning, verifies **AC-7**.
- Crash ordering: interrupt before and after SQLite activation and prove only one complete version is eligible, verifies **AC-6** and **AC-9**.
- Staleness: drift one record, prove default refusal, then use `--allow-stale` and assert both the global warning and per citation stale marker, verifies **AC-17**.
- Manifest race: change the external manifest during query and prove default discards the completed answer while `--allow-stale` returns it with start and end drift evidence, verifies **AC-9** and **AC-17**.
- Pipeline mismatch and rebuild: change any signature input, prove both read paths refuse, fail a staging rebuild, prove the old generation remains active, then complete and atomically activate a parity checked generation, verifies **AC-8** and **AC-21**.
- Verification: route the ordered token counterexample through entailment rather than the deterministic shortcut, remove one unsupported sentence, then prove independently extracted uncovered facets cause abstention while provider failure exits `1`, verifies **AC-15** and **AC-16**.
- Provider planning: prove dry run, unchanged or removal only ingest, and empty index abstention need no key, while a paid plan rejects a missing key before any mutation, verifies **AC-3**, **AC-16**, and **AC-20**.
- Injection: place model instructions in a cited chunk and prove the answer follows the query contract without altering the cited source text, verifies **AC-20**.
- Conformance: run the built in and starter adapters through every updated schema version 2 case, verifies **AC-2** and **AC-3**.
- Untested current corpus case: inspect the built supersession notice path, but record that JobPilot cannot exercise it because its adapter emits no links, verifies the stated disposition in **AC-18**.

## Build plan

The project uses Skateboard delivery. The first milestone establishes one real JobPilot answer through every layer. Later milestones harden freshness, recovery, and diagnostics without replacing that path.

1. - [x] Extend the adapter result and output manifest to schema version 2 with exact field sources, record and entry digests, semantic plus raw manifest digests, and a source root hint. Update the built in adapter, starter adapter, runtime checks, all spec 0006 conformance fixtures and comparisons, the author guide, and the contract documentation governed by specs 0003, 0005, and 0006 in the same milestone, satisfies **AC-2**, **AC-3**, and **AC-19**.
2. - [x] Add `openai`, `chromadb`, and the new direct `tiktoken` dependency. Build canonical encodings, value paths, deterministic chunk ids and prefix, store generations, exact SQLite schema, Chroma parity checks, pipeline signature, result DTOs, and the two centralized OpenAI modules, satisfies **AC-4**, **AC-5**, **AC-6**, **AC-8**, **AC-10**, **AC-13**, and **AC-20**.
3. - [x] Deliver the smallest usable whole: ingest JobPilot records into one active generation, semantically retrieve 24 candidates with the disabled null floor, extract facets independently, generate and verify structured sentences, and return query 1 with its exact cited answer through both application functions and fixed CLI rendering, satisfies **AC-1**, **AC-10**, **AC-11**, **AC-12**, **AC-15**, and **AC-16**.
4. - [x] Add dry run spend preview, record scoped incremental add and update, removals and tombstones, per record batching, partial failure retention, explicit rebuild, and manifest plus pipeline freshness checks, satisfies **AC-3**, **AC-7**, **AC-8**, **AC-17**, and **AC-21**.
5. - [x] Add the exact shared and exclusive SQLite lock protocol, generation activation ordering, orphan cleanup, manifest mutation checks on ingest and query, provider retry classification, full SQLite and Chroma parity, and corrupt store recovery, satisfies **AC-6**, **AC-8**, **AC-9**, **AC-16**, and **AC-21**.
6. Complete the always present ingest and query traces, CLI debug rendering, source resolution state, stale answer markers, and the four stage failure triage map, satisfies **AC-13**, **AC-14**, **AC-17**, and **AC-19**.
7. Add supersession notices and prompt constraints without automatic successor retrieval. Record the JobPilot limitation as untested rather than claiming live coverage, satisfies **AC-18**.
8. Finish user documentation, including explicit billing commands, `--dry-run`, moved index citations, stale warnings, full debug data sensitivity, error meanings, and recovery. Run Ruff, strict mypy, unit tests, and marked OpenAI plus Chroma integration tests, satisfies **AC-1**, **AC-20**, and **AC-21**.

## Consequences

**Positive**:

- Every answer claim has exact stored evidence and original source provenance.
- Explicit ingestion makes billing and mutation visible and lets query stay a read operation.
- Record scoped activation preserves paid successful work without exposing partial versions.
- The structured trace lets Feature 11 test the application directly instead of parsing CLI prose.

**Negative / tradeoffs**:

- The adapter protocol and manifest break again. Every adapter and conformance fixture must migrate before ingestion can use it.
- SQLite and Chroma create a two store consistency problem that requires strict activation order, orphan cleanup, and an explicit rebuild path.
- Full debug output can be large and may expose sensitive decision text when shared.
- Whole record reembedding spends more than content only chunk reuse, in exchange for keeping identity and provenance correct.
- `tiktoken` becomes the first new dependency added specifically by this feature.
- Query performs a complete active chunk parity check before retrieval. This is deliberate correctness work at the expected corpus size and may need measured optimization later.

**Neutral**:

- A `None` relevance floor disables similarity filtering and moves calibration to Feature 11 as planned. Slice 1 retrieval abstention therefore means no eligible candidate, not a measured low similarity decision.
- Source path resolution is informative. An index moved to another machine remains queryable even when the original files are absent.
- The current JobPilot corpus cannot prove supersession behavior.

## Follow-up

- [ ] Feature 11 must replace the disabled `None` relevance floor with a measured value and may revisit candidate limit 24.
- [ ] A later feature may add an explicit source root override if moved indexes need clickable citations more often than the stored hint provides.

## Rationale

Reasoning, options, and references: see [rationale.md](rationale.md).
