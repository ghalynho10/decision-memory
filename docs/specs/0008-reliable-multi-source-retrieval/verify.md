# Verify reliable multi source retrieval

## Purpose

Prove exact filter behavior, deterministic hybrid ranking, strict failure boundaries, honest corpus abstention, and the multi record JobPilot answer. Five live passes per defining query are a smoke gate against known intermittent verification behavior. They are not a reliability rate.

## Setup

1. Install the locked environment with `uv sync`.
2. Set `DECISION_MEMORY_JOBPILOT_DIR` to the real JobPilot checkout.
3. Supply `OPENAI_API_KEY` only for live ingest and query runs.
4. Adapt JobPilot and rebuild one store in format `2`.
5. Reuse that same rebuilt store for all ten live query runs.

## Verification ladder

### 1. Local quality gates

Run:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
uv build
```

Expected: every command succeeds. The unit suite makes no provider call.

### 2. Filter contract

Prove:

1. Each of the four repeatable CLI options reaches `QueryFilters`.
2. Duplicate values deduplicate and sort.
3. OR applies within a field and AND across fields.
4. Status normalization is lowercase only. Other identifiers remain case sensitive. A missing record status fails a nonempty status filter.
5. Exact value paths and the five fixed `[*]` selectors match the whole intended path. Prove `[0]` and `[10]` match, while `[01]`, descendants, and partial paths do not.
6. Malformed values return exit `2`.
7. A valid filter with no accepted chunk returns exit `0`, retrieval abstention, and no embedding or generation attempt.
8. Every active chunk gets one FilterRow with all failed reasons in fixed order.

### 3. Lexical, semantic, and fusion contract

With a deterministic fake index and scorer, prove:

1. The tokenizer produces every normative example from the spec, applies NFC and `str.lower()`, handles apostrophes, ASCII digits, combining marks, underscores, and hyphens exactly, retains `no`, `not`, and `nor`, and produces the pinned 171 word digest.
2. Lexical ties sort by score descending then chunk id.
3. No token intersection takes precedence over score sign and yields `no_term_match`.
4. Token intersection with a zero or negative score yields `nonpositive_score` and does not enter fusion.
5. Positive lexical rows beyond 24 remain visible as `outside_top_24`.
6. Chroma returns every eligible id under the accepted id constraint. Application validates cosine distances, then sorts locally by distance and chunk id.
7. More than 24 equal semantic distances always choose the same top 24 chunk ids. Remaining rows retain real scores and ranks with `outside_top_24`.
8. The exact reciprocal rank formula uses constant `60`, ranks starting at `1`, and zero for missing contributions.
9. Fused ties sort by chunk id.
10. Either retriever contribution may be absent without selecting a second execution path.
11. An empty ranked union causes retrieval abstention with no generation call.

### 4. Diversity contract

Use a fused fixture with more than two strong chunks from one record and relevant chunks from at least two other records. Prove:

1. The breadth pass accepts at most two per record.
2. A breadth accept records `accepted`, `breadth`, the next one based final rank, and final `accepted`.
3. A row at the record cap records `record_cap` and is deferred.
4. Once eight are accepted, every unvisited row records `accepted_limit_reached`, no pass or final rank, and `outside_top_8`.
5. The fill pass revisits only record capped rows in fused order.
6. A strong third chunk may fill an unused place while retaining `breadth_disposition: record_cap` and adding `selection_pass: fill`.
7. An unfilled deferred row has no pass or final rank and ends `outside_top_8`.
8. Final rank equals context append order, and exactly eight or all available fused candidates are accepted, whichever is smaller.

### 5. Store and integrity boundaries

Prove:

1. Format `1` refuses query and instructs `ingest --rebuild`.
2. Rebuild produces format `2` with SQLite schema `1`.
3. Every Chroma vector has `chunk_id` locator metadata and the collection metric is immutable cosine.
4. Semantic search applies the exact accepted id constraint and asks for the accepted count.
5. Returned ids and distances are positionally aligned and contain exactly one row for every accepted id.
6. An extra, missing, duplicate, or outside id fails at retrieval with exit `1`.
7. A distance outside `[0, 2]`, nonfinite score, scorer cardinality mismatch, scorer exception, or missing chunk fails with exit `1`.
8. Every retrieval integrity failure carries the exact terminal stage and partial trace, produces no QueryResult, and becomes no abstention.

### 6. Trace and rendering

Prove:

1. QueryResult and QueryTrace report schema version `2`.
2. Debug sections appear in fixed order: Freshness, Filter, Lexical, Semantic, Fusion, Diversity, Settings, Facets, Draft, Verification, Providers, Citations, Result.
3. Filter, lexical, and semantic rows sort by chunk id. Filter trace includes every active chunk even with no filter.
4. Fused candidates sort by fused rank and diversity accepted ids sort by final rank.
5. Retrieval settings include tokenizer and stopword identifiers, the pinned stopword digest, BM25 variant and parameters, limits, RRF constant, diversity cap, cosine metric, and `None` relevance floor.
6. A forced lexical or semantic failure renders its completed partial trace only with `--debug`, exits `1`, and emits no QueryResult.
7. Normal cited answer output remains unchanged.
8. Debug documentation still warns that copied output contains sensitive decision text and paths.

### 7. Live query 2 smoke gate

Run the exact question five consecutive times against one rebuilt JobPilot store:

```text
What decisions affect resume generation?
```

Every run must:

1. Return `answered` and exit `0`.
2. Cite `DM-0004` for on demand generation from the saved profile and storage of the produced PDF.
3. Cite `DM-0019` for deliberately excluding projects from generated resumes (DM-0019 AC-9; corrected oracle — was `DM-0014`, a flat single file spec the adapter does not ingest).
4. Cite `DM-0019` for ATS quality guidance and deterministic guards against unsupported numbers and em dash output.
5. Contain no factual sentence whose citations do not support it.
6. Show the three records surviving fusion and diversity in trace.

Any unsupported cited answer blocks completion.

**Gate status (2026-08-11):** failing on the Feature 11 verification gap. 5 of 5 runs returned `answered`/exit 0 and cited `DM-0019`, but `DM-0004` was cited in only 3 of 5 runs before the AC-5 fusion boundary fix, and in 0 of 5 runs in the post fix re run. `DM-0004` chunks stayed in the diversity accepted context in both samples, so the miss is generation/verification coverage, the same class as the query 4 fabrication. The movement confirms the omission is sensitive to the retrieved context, not a retrieval defect. Carried into Feature 11 as the query 2 DM-0004 coverage item. This gate is not declared passed.

### 8. Live query 4 smoke gate

Run the exact question five consecutive times against the same store:

```text
What was decided about separating server side and browser side database clients, and why?
```

Every run must:

1. Return exact `not enough evidence here` and exit `0`.
2. Return no sentence or citation.
3. Record either retrieval or claim verification as the terminal abstention stage.
4. Preserve the complete retrieval and verification trace reached by that run.

The evidence is outside the adapted corpus. A cited answer is a failure, not a partial pass.

**Gate status (2026-08-11):** failing — 5 of 5 runs returned a cited answer instead of abstaining (DM-0007 and DM-0008 in every run of the post fix re run; DM-0012 also appeared in some pre fix runs). This is the known, documented blocker (rationale "Query 4 verification finding", "Verification unit gap", "Relevance floor decision"; index.md Follow-up 6, 7, 8). Carried to Feature 11; this gate ran and failed and is not declared passed.

## Evidence to record

1. The quality gate command results.
2. Store format and SQLite schema versions after rebuild.
3. Deterministic unit and Chroma integration results for every stage.
4. For each of the ten live runs, state, exit code, cited record ids, terminal stage, and whether every sentence was supported.
5. A plain statement that five of five is a smoke result, not a reliability estimate.
6. A plain statement that Feature 11 now has two expected abstentions, query 4 and query 5.
