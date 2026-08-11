# 0008. Reliable multi source retrieval

**Date**: 2026-08-11
**Status**: Proposed

## Summary

Every query first applies explicit metadata constraints, then searches the remaining decision chunks with both keyword and semantic retrieval. Reciprocal rank fusion combines the two rankings without pretending their raw scores share one scale. A two pass diversity rule makes room for several relevant records, while a complete trace shows where every active chunk stopped.

## Requirements

**User stories**:

1. As a developer, I want questions about an area to surface several directly relevant decisions, including explicit decisions not to include something.
2. As a user, I want typed metadata constraints so I can narrow evidence without hidden query interpretation.
3. As a reviewer, I want every filter, retrieval, fusion, and diversity decision recorded so I can assign a miss to one stage.
4. As a user asking beyond the indexed corpus, I want an honest abstention rather than a plausible answer built from adjacent evidence.

**Acceptance criteria**:

1. **AC-1**: `decision-memory query` adds repeatable `--record-id`, `--status`, `--tag`, and `--value-path` options. `QueryRequest.filters: QueryFilters` is required for every application caller. The CLI constructs an empty `QueryFilters` when no filter option is supplied. Filters apply to one query only and never persist in `.decision-memory.yml`. Normal cited answer rendering stays unchanged.
2. **AC-2**: `QueryFilters` holds sorted, unique tuples for record ids, statuses, tags, and value path selectors. Values use OR within one field and AND across fields. Surrounding whitespace is removed. Status is normalized to the lowercase closed values `proposed`, `accepted`, `superseded`, and `rejected`. Record ids, tags, and value paths remain case sensitive. Empty values, unknown statuses, and malformed value path selectors are usage errors with exit `2`. A valid value that matches nothing is not a usage error.
3. **AC-3**: Value path filters accept an exact active chunk value path or one of the complete fixed selectors `decision.alternatives[*]`, `why[*]`, `consequences.positive[*]`, `consequences.negative[*]`, and `body[*]`. A selector matches the entire canonical path only. `[*]` matches exactly one ASCII decimal index with grammar `0|[1-9][0-9]*`; it does not match descendants. Thus `body[*]` matches `body[0]`, but not `body[01]` or `body[0].text`. No other wildcard, glob, or regular expression form is valid.
4. **AC-4**: The command holds the existing shared query lock while infrastructure reads every active chunk and its record status and tags in one SQLite read transaction. Application filtering receives that immutable snapshot and produces one `FilterRow` per active chunk even when no filters are present. State is the closed enum `accepted` or `excluded`. Exclusion reasons are the unique closed values `record_id`, `status`, `tag`, and `value_path`, sorted in that order, and every failed constraint is reported. A record with missing status fails every nonempty status constraint. When no chunk is accepted, query returns `not enough evidence here`, exit `0`, stage `retrieval`, without embedding the question or calling any generation provider.
5. **AC-5**: Lexical retrieval uses `rank_bm25.BM25Okapi` with library defaults over the accepted chunk text, rebuilt in memory for each query. It receives the original question. The exact `lexical-tokenizer-v1` algorithm and stopword vocabulary are defined below. Every accepted chunk gets a lexical trace row and finite raw BM25 score. Dispositions use this precedence: no query token intersects the chunk tokens gives `no_term_match`; otherwise a score less than or equal to zero gives `nonpositive_score`; otherwise positive rows sort by score descending then chunk id and receive ranks starting at `1`; ranks 1 through 24 are `ranked`, and later positive ranks are `outside_top_24`. Only `ranked` rows contribute to fusion.
6. **AC-6**: Store format `2` creates the Chroma collection with immutable cosine distance metadata and stores `chunk_id` as locator metadata. Semantic retrieval receives the original question, uses an `$in` constraint over the exact accepted ids, requests `n_results` equal to the accepted count, and requires exactly one unique result for every accepted id and no other id. Infrastructure returns positionally aligned plain chunk ids and distances. Application validates every distance as finite and within `[0, 2]`, computes similarity as `1 - distance`, sorts all eligible rows by distance ascending then chunk id, and assigns ranks starting at `1`. Semantic disposition is `ranked` for ranks 1 through 24 and `outside_top_24` thereafter. Only `ranked` rows contribute to fusion. Missing, duplicate, extra, misaligned, or invalid rows are operational failures.
7. **AC-7**: Reciprocal rank fusion runs over the union of the ranked lexical and semantic rows. For each chunk, `fused_score` is the sum of `1 / (60 + rank)` for each present contribution. A missing contribution adds zero. Fused candidates sort by score descending then chunk id. Raw BM25 score, lexical rank, semantic rank, distance, similarity, fused score, and fused rank remain available. No raw score normalization or cross scale comparison occurs.
8. **AC-8**: Diversity accepts at most eight chunks. The breadth pass walks fused rank from `1` upward. Before eight accepts, a candidate below the two per record cap gets `breadth_disposition: accepted`, `selection_pass: breadth`, the next one based final rank, and final disposition `accepted`; a candidate at the cap gets `breadth_disposition: record_cap` and is deferred. As soon as eight are accepted, every unvisited candidate gets `breadth_disposition: accepted_limit_reached`, no selection pass or final rank, and final disposition `outside_top_8`. If breadth exhausts the input below eight, fill revisits only `record_cap` candidates in fused order and accepts them until eight or exhaustion. A fill accept retains `breadth_disposition: record_cap`, gets `selection_pass: fill`, the next final rank, and final disposition `accepted`; an unfilled deferred row has no selection pass or final rank and disposition `outside_top_8`. Final rank is the one based append order of the context sent to generation.
9. **AC-9**: A retriever with no ranked candidates contributes nothing and the other retriever continues through the same fusion path. If the ranked union is empty after a nonempty filter result, query abstains at retrieval, preserves both complete traces, and makes no generation call. Any semantic embedding attempt remains in provider trace. A scorer exception, nonfinite score, duplicate chunk id, invalid or misaligned semantic response, missing stored chunk, or semantic id outside the accepted set raises typed `RetrievalFailure`. It carries the closed terminal stage `filter`, `lexical`, `semantic`, `fusion`, or `diversity` plus the partial trace completed before failure. The CLI renders that trace only in debug mode, exits `1`, and never packages the anomaly as abstention or `QueryResult`.
10. **AC-10**: `QueryResult` and `QueryTrace` advance to schema version `2`, with no version `1` execution path. Successful answers and expected abstentions produce `QueryResult`; operational retrieval failures do not. The retrieval trace has fixed `Filter`, `Lexical`, `Semantic`, `Fusion`, and `Diversity` sections after `Freshness`, followed by the existing generation, verification, provider, citation, and result sections. Filter, lexical, and semantic row collections sort by chunk id. Fused candidates sort by fused rank, with chunk id as the tie rule already applied. Diversity accepted ids sort by final rank. It retains every pre fusion exclusion and every fused candidate. Settings record tokenizer version, stopword set identifier and digest, BM25 variant and parameters, lexical and semantic limits, reciprocal rank fusion constant, accepted limit, diversity cap, collection metric, and the still disabled `None` relevance floor. These query settings do not enter the ingestion pipeline signature.
11. **AC-11**: Facet extraction stays after retrieval. No model rewrites the question or infers structured query types. Generation, containment, entailment, coverage, citations, supersession disclosure, freshness, locking, source resolution, provider retry rules, and normal answer rendering retain spec 0007 behavior. An embedding or generation provider failure remains exit `1`.
12. **AC-12**: Store format advances to `2`. SQLite schema remains version `1`. Chroma stores `chunk_id` with the existing locator metadata and pins cosine distance, so a format `1` store refuses query and points to `ingest --rebuild`. Rebuild preserves canonical records, chunk text, and embedding pipeline inputs but recomputes all derived vectors. It may repeat provider spend and may produce numerically different embeddings from the same inputs.
13. **AC-13**: Against one rebuilt JobPilot index, the exact query `What decisions affect resume generation?` returns an answered, multi record result citing `DM-0004`, `DM-0014`, and `DM-0019`. It states that resume generation runs on demand from the saved profile and stores the produced PDF, that projects are deliberately excluded from generated resumes, and that resume quality adds ATS guidance plus deterministic guards for unsupported numbers and em dash output. Each statement cites the record that supports it. Incidental mentions do not satisfy this oracle.
14. **AC-14**: Against that same index, the exact query `What was decided about separating server side and browser side database clients, and why?` returns `not enough evidence here`, exit `0`, with either retrieval or claim verification as the terminal abstention stage. It never returns a cited answer. The evidence exists in JobPilot `context/library-docs.md` and `context/code-standards.md`, which the built in adapter intentionally does not ingest. This feature does not expand adapter scope or replace the query.
15. **AC-15**: Live verification runs query 2 and query 4 five consecutive times each against one rebuilt index. Every query 2 run satisfies AC-13. Every query 4 run satisfies AC-14. Any unsupported cited answer blocks completion and is fixed at the stage identified by the trace. Five passing runs are a smoke gate against the known intermittent pattern, not a measured reliability rate.
16. **AC-16**: `rank_bm25` is an infrastructure dependency. `ActiveChunkDescriptor` is an immutable application DTO containing chunk id, record id, title, optional status, sorted tags, value path, fingerprint, ordinal, text, and provenance. `IndexReader.active_chunks()` returns a chunk id sorted tuple with exactly one descriptor for each active SQLite chunk from the one transaction snapshot. `IndexReader.semantic_search(embedding, accepted_chunk_ids)` returns a plain `SemanticMatches` value containing positionally aligned id and distance tuples. The injected `LexicalScorer(query_tokens, document_tokens)` receives token tuples in chunk id order and returns one positional float per document. Application checks identity, cardinality, duplicates, and finite values before pure filtering, rank assignment, fusion, diversity, and trace construction. No application module imports `rank_bm25`, Chroma, OpenAI, Typer, or Pydantic.
17. **AC-17**: Ruff, strict mypy, the unit suite, marked Chroma integration tests, and the ten live JobPilot query runs pass. Tests cover the exact tokenizer vectors and stopword digest, every closed enum, ordering rule, failure boundary, filter combination, single contribution path, store format refusal, and zero provider filter abstention.

## Decision

**Chosen option**: Option 1, fix the existing query path with filtered parallel retrieval and reciprocal rank fusion

Apply explicit metadata constraints in SQLite, run BM25 and Chroma over the same accepted chunks, fuse their ranks, then apply record diversity before the existing generation and verification path. (basis: specs 0001 and 0007; reciprocal rank fusion; SQLite as the authoritative store)

No community implementation skill shaped this decision. `rank_bm25` was already chosen by spec 0001, so this feature does not select a new provider or tool.

## Feature design

### Scope boundaries

Included:

1. Explicit record id, status, tag, and value path constraints.
2. Local BM25 retrieval, semantic retrieval, reciprocal rank fusion, and two pass record diversity.
3. Store format `2`, query DTO schema `2`, and full stage traces.
4. The query 2 multi record oracle and query 4 honest abstention oracle.

Excluded:

1. Natural language filter inference or model generated search rewrites.
2. Structured query types for alternatives, lineage, or supersession traversal.
3. Date filters and range semantics.
4. Relevance floor calibration, reliability rates, and the reusable evaluation harness.
5. Any expansion of the built in adapter beyond `docs/specs/`.
6. A broad redesign of generation or claim verification.

### Data model

The query DTO target is:

```text
QueryRequest 1 to 1 QueryFilters
QueryTrace 1 to 1 RetrievalTrace
RetrievalTrace 1 to 1 FilterTrace
RetrievalTrace 1 to 1 LexicalTrace
RetrievalTrace 1 to 1 SemanticTrace
RetrievalTrace 1 to 1 FusionTrace
RetrievalTrace 1 to 1 DiversityTrace
FilterTrace 1 to many FilterRow, keyed by chunk_id
LexicalTrace 1 to many LexicalRow, keyed by chunk_id
SemanticTrace 1 to many SemanticRow, keyed by chunk_id
FusionTrace 1 to many FusedCandidate, keyed by chunk_id
RetrievalFailure 1 to 1 PartialQueryTrace
```

`QueryFilters` fields are `record_ids`, `statuses`, `tags`, and `value_paths`, each a sorted tuple.

`ActiveChunkDescriptor` holds chunk id, record id, record title, optional record status, sorted record tags, value path, fingerprint, ordinal, text, and provenance. It is the immutable input snapshot for application retrieval.

`FilterRow` holds chunk id, record id, optional record status, sorted record tags, value path, filter state, and ordered exclusion reasons.

`LexicalRow` holds chunk id, finite BM25 score, optional rank, and the closed lexical disposition. `SemanticRow` holds chunk id, rank, finite distance, similarity, and the closed semantic disposition `ranked` or `outside_top_24`.

`FusedCandidate` retains the existing record id, value path, fingerprint, ordinal, text, and provenance. It adds optional lexical and semantic contributions, fused score, fused rank, breadth disposition, optional selection pass, optional final rank, and final disposition. One chunk appears once in fusion.

`DiversityTrace` holds accepted chunk ids in final rank order and the fixed accepted limit and record cap. Candidate level diversity facts live only on `FusedCandidate`, so two trace objects cannot disagree about one chunk.

`PartialQueryTrace` contains Freshness plus optional Filter, Lexical, Semantic, Fusion, and Diversity sections, followed by provider attempts. A completed section is retained, while the failing section and every later section are absent rather than synthesized as empty. `RetrievalFailure` is not a result DTO. It is a typed application exception containing the closed terminal retrieval stage and this partial trace.

All values are in memory query results. The existing SQLite snapshot, tag, and chunk tables remain authoritative. No new persistent table or SQLite migration exists.

### Retrieval stages

The fixed stage order is:

```text
active SQLite chunks
    to explicit filter
    to lexical BM25 and semantic Chroma retrieval
    to reciprocal rank fusion
    to two pass record diversity
    to existing generation and verification
```

Lexical retrieval rebuilds its small in memory corpus per query from accepted chunk text. Semantic retrieval embeds the question only after filtering proves that at least one chunk is eligible. Chroma retrieves every accepted vector under the exact id constraint. Application validates the returned set, sorts every semantic candidate locally, and only then cuts the contributing ranks to 24. This deliberately avoids relying on Chroma ordering at a tied limit boundary.

Reciprocal rank fusion uses ranks starting at `1` and constant `60`:

```text
fused_score = lexical contribution + semantic contribution
lexical contribution = 1 / (60 + lexical_rank), or 0 when absent
semantic contribution = 1 / (60 + semantic_rank), or 0 when absent
```

Constant `60`, the limits `24` and `8`, and diversity cap `2` are provisional query settings. Feature 11 may calibrate them without rebuilding stored embeddings.

### Lexical tokenizer

`lexical-tokenizer-v1` is the following exact algorithm:

1. Normalize the input with Unicode NFC.
2. Apply Python `str.lower()` once. Do not case fold or remove accents.
3. Scan Unicode code points from left to right. A letter in any Unicode `L` category or an ASCII decimal digit starts or extends a token. Combining marks in Unicode categories `Mn`, `Mc`, or `Me` extend an existing token and are otherwise discarded. ASCII apostrophe `'` and right single quotation mark `’` extend a token only when immediately preceded and followed by a letter or ASCII decimal digit. Every other code point ends the current token. Underscore and hyphen are therefore separators.
4. Remove an entire token only when it exactly equals one of the 171 words in `lexical-stopwords-v1.txt`. The file is the normative sorted `lexical-stopwords-v1` vocabulary. It is the active Snowball English list with `no`, `not`, and `nor` removed so negation remains searchable.
5. Apply no stemming. Preserve token order and duplicates for BM25.

Normative examples show the step 3 tokens and the final tokens after stopword removal:

```text
Input             Step 3 tokens       Final tokens
Server-side       server, side         server, side
don't retry       don't, retry         retry
DM-0019           dm, 0019             dm, 0019
Cafe plus U+0301  café                  café
O’Reilly          o’reilly              o’reilly
_why_not_         why, not              not
```

The stopword digest is `fe2b3373712ce97c07caa0da916d1e2bc8bff4f3ba44a109ad059bd8f2459db6`. It is SHA256 over the 171 UTF8 words in ascending code point order, joined by LF with no trailing LF. A tokenizer rule or vocabulary change requires a new tokenizer and vocabulary identifier.

### Interface surface

```text
Surface
decision-memory query

Inputs
QUESTION
--store PATH
--allow-stale
--debug
--record-id TEXT, repeatable
--status STATUS, repeatable
--tag TEXT, repeatable
--value-path SELECTOR, repeatable

Outputs
The existing cited answer, exact abstention, or expected failure
Schema version 2 QueryResult
Five fixed retrieval debug sections

Errors
Exit 2 for malformed filter usage
Exit 1 for provider, scorer, store, or retrieval integrity failure
Exit 0 for a valid empty filter result or evidence abstention
```

```text
Surface
query_index(request, dependencies)

Inputs
QueryRequest with required QueryFilters
IndexReader.active_chunks() returning the one transaction ActiveChunkDescriptor snapshot
IndexReader.semantic_search(embedding, accepted_chunk_ids) returning plain aligned ids and distances
Injected LexicalScorer(query_tokens, document_tokens) returning one positional score per document
Existing embedding, generation, manifest, and source callables

Outputs
QueryResult schema version 2 with complete QueryTrace

Errors
Expected answer and abstention states remain values in QueryResult
RetrievalFailure carries terminal stage and partial trace and never becomes QueryResult
Programming errors may raise
```

### Value sourcing

```text
Produced value                  Source
Normalized filters              Repeated CLI values or QueryRequest.filters, then the AC-2 rules
Active chunk set                One SQLite read transaction under the existing shared query lock
Filter exclusion reasons        Each active chunk compared with every nonempty QueryFilters tuple
Lexical raw score               rank_bm25 BM25Okapi over accepted chunk text and original question tokens
Lexical disposition and rank    Token intersection, then score, then positive rank using the AC-5 precedence
Semantic distance               One cosine Chroma result for every accepted chunk_id
Semantic similarity             1 minus the validated Chroma distance
Semantic rank                   All eligible distances sorted locally ascending then chunk_id
Fused score and rank            The AC-7 reciprocal rank formula and chunk_id tie rule
Breadth disposition             The ordered AC-8 state transition over fused candidates
Final rank                      One based append order from breadth accepts, then fill accepts
Final accepted chunks           Fused breadth accepts followed by deferred fill accepts
Retrieval settings trace        Fixed query constants, actual BM25 parameters, tokenizer version, and stopword digest
Stopword set digest             Pinned AC-5 digest of lexical-stopwords-v1.txt
Query 2 oracle                  JobPilot DM-0004, DM-0014, and DM-0019 canonical chunks
Query 4 abstention oracle       Absence from adapted records, confirmed against the excluded JobPilot context files
```

### Key invariants

1. SQLite alone decides eligibility. Chroma only enforces the accepted chunk ids that application supplies.
2. A user constraint is never ignored. Malformed input fails, while a valid empty match abstains.
3. Every active chunk appears in FilterTrace, including unconstrained accepted chunks.
4. Every accepted chunk appears in both retriever traces. Every semantic row has a real distance and rank, including rows outside top 24.
5. One chunk appears at most once in fusion and once in final accepted context.
6. BM25 and cosine raw values are never compared or normalized against each other.
7. A retriever failure is never treated as no evidence or wrapped in QueryResult.
8. Provider calls remain absent when filtering proves no eligible evidence.
9. Query settings are traced but do not invalidate embeddings.
10. Query 4 remains an abstention oracle. The corpus is not reshaped to make the test pass.
11. Chroma never decides the semantic top 24 boundary. Application sorts all eligible distances locally.

### Security model

This remains a local single user CLI with no authentication or authorization layer. Lexical retrieval is local and sends no new data outside the machine. Existing OpenAI question and source handling remains unchanged. Normal logs remain content free. Debug output contains every active chunk in filter and retrieval traces, so it remains sensitive and grows with corpus size. No new secret or regulated compliance scope applies.

### Critical test scenarios

1. Multi source happy path: query 2 accepts evidence from `DM-0004`, `DM-0014`, and `DM-0019` and returns the three required cited decisions, verifies **AC-5** through **AC-13**.
2. Empty filter: a valid tag with no matching record returns retrieval abstention without an embedding or generation call, verifies **AC-2** through **AC-4**.
3. Filter combinations: repeated values use OR within one field and AND across fields, with every failed constraint reported in fixed order, verifies **AC-2** through **AC-4**.
4. Contribution asymmetry: no positive lexical row still lets semantic rows use the same fusion path, and a pure application fixture proves either contribution may be absent, verifies **AC-7** and **AC-9**.
5. Diversity: three strong chunks from one record and relevant chunks from two other records prove the breadth pass, fill pass, and all dispositions, verifies **AC-8**.
6. Semantic determinism and integrity: more than 24 eligible rows tie at the boundary, local chunk id order selects the same 24 every time, and an extra or missing Chroma id raises `RetrievalFailure` with partial trace and exit `1`, verifies **AC-6**, **AC-9**, and **AC-10**.
7. Store migration: format `1` refuses query, a format `2` rebuild succeeds, and SQLite schema stays at `1`, verifies **AC-12**.
8. Corpus boundary: query 4 abstains without a cited answer and names the actual terminal stage in trace, verifies **AC-14**.
9. Live smoke gate: five consecutive runs of each defining query meet their oracle against one rebuilt store, verifies **AC-15** and **AC-17**.
10. Architecture: unit tests use a plain fake index and scorer, and an import check proves application has no third party retrieval import, verifies **AC-16**.

## Migration plan

**Strategy**: direct replacement of a rebuildable local derived index

**Phases**:

1. Ship query DTO schema `2`, store format `2`, and Chroma `chunk_id` locator metadata together.
2. Refuse format `1` query with an `ingest --rebuild` instruction.
3. Rebuild all derived vectors from unchanged canonical records and embedding pipeline inputs, then run local and live verification.

**Rollback**: Revert the feature and rebuild a format `1` store from the same canonical records. No source decision record or manifest data is transformed.

**Risks**: Rebuild repeats embedding spend, and a provider may return numerically different vectors for the same inputs. A user cannot query an old format `1` store after upgrading until rebuild completes. This direct cutover is chosen because the index is local derived data with no public clients, so a second live execution path or feature flag would add more risk than it removes.

## Build plan

The project uses Skateboard delivery. The first milestone adds a complete explicit filter path before adding hybrid ranking. The second milestone delivers the smallest useful multi source answer. Later milestones finish diagnostics, migration, and strict live proof.

1. Add `QueryFilters`, schema version `2` query DTOs, the closed filter vocabularies, `ActiveChunkDescriptor`, exact `IndexReader` and `LexicalScorer` contracts, repeatable CLI options, one transaction snapshot filtering, full FilterTrace, and zero provider empty filter abstention, satisfies **AC-1** through **AC-4**, **AC-10**, and **AC-16**.
2. Advance store format to `2`, pin Chroma cosine distance, add `chunk_id` locator metadata and exact accepted id constraints, retrieve every eligible vector, preserve SQLite schema `1`, and implement explicit rebuild refusal and recovery, satisfies **AC-6**, **AC-9**, and **AC-12**.
3. Add `rank_bm25`, the exact tokenizer and pinned stopword set, closed lexical and semantic precedence, local semantic sorting, reciprocal rank fusion, and the exact two pass diversity state transition. Deliver query 2 through the existing generation and citation path, satisfies **AC-5** through **AC-11**, **AC-13**, and **AC-16**.
4. Complete the five fixed debug sections, canonical row ordering, settings trace, typed `RetrievalFailure` with partial debug trace, CLI rendering, user documentation, and store migration guidance, satisfies **AC-9** through **AC-12** and **AC-17**.
5. Add deterministic unit and Chroma integration coverage, then run five consecutive live query 2 passes and five consecutive live query 4 abstentions against one rebuilt JobPilot store. Any unsupported answer is a blocker, satisfies **AC-13** through **AC-17**.

## Consequences

**Positive**:

1. Exact terms and semantic meaning can each recover evidence without either retriever setting the other one's recall ceiling.
2. Query 2 can cite several direct decisions while preserving strong extra evidence through the fill pass.
3. Every active chunk has a machine checkable path through filtering and retrieval.
4. A valid filter with no evidence has zero provider cost and an exact diagnosis.

**Negative and tradeoffs**:

1. Debug trace size grows linearly with active chunk count and is largest even when filters are unconstrained.
2. Every query rebuilds a small BM25 corpus and asks Chroma for every eligible vector before local top 24 selection. This is accepted at dozens to low hundreds of records and must be measured before changing.
3. Semantic retrieval requests every eligible vector in one Chroma call and has no pagination or batch ceiling in this feature. The strict exact id check turns a Chroma result limit into an operational failure rather than silently accepting a partial ranking. This is a known scale boundary beyond the current 15 record corpus; deterministic paging or batching needs a separate design before use on a corpus with thousands of eligible chunks.
4. Store format `2` requires an explicit rebuild and repeats embedding spend even though canonical records, chunk text, and embedding inputs do not change.
5. Persistent hidden constraints are deliberately unavailable. A user must repeat filters for each query.
6. The five run smoke gate costs ten live queries and does not establish a reliability rate.

**Neutral**:

1. Diversity was deliberately absent from Slice 1 and lands here with the rest of ranking. The two specs describe successive scopes, not conflicting rules.
2. Relevance floor remains `None`. Query 4 may abstain at retrieval or claim verification until Feature 11 calibrates it.
3. Reciprocal rank fusion constant `60`, limits `24` and `8`, and diversity cap `2` are recorded provisional values.
4. Query filters do not persist. Persistent hidden constraints would make later abstentions surprising and harder to trust.

## Follow-up

1. [ ] Feature 11 must treat query 4 and query 5 as the two expected abstentions among the five defining queries.
2. [ ] Feature 11 may calibrate the relevance floor, reciprocal rank fusion constant, candidate limits, and diversity cap from recorded settings and real outcomes.
3. [ ] Revisit full FilterTrace display only when a larger real corpus proves linear debug output is impractical. Keep the structured trace complete unless evidence supports another contract.
4. [ ] Structured query types for rejected alternatives, lineage, and supersession traversal remain deferred until the evaluation harness shows a need.

## Rationale

Reasoning and options: see [rationale.md](rationale.md).
