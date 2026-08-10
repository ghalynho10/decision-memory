# Review, feature/0007-core-cited-query, 2026-08-10

**Reviewed by**: DeepSeek V4 Pro (author on DeepSeek V4 Flash)
**Scope**: 57 files, branch feature/0007-core-cited-query vs main
**Verdict**: Blocked → Approved (blocker + major fixed in `17db8c4`; cosmetic minor also fixed 2026-08-10)

## Summary

This feature delivers a complete local cited RAG pipeline across `adapt` → `ingest` → `query`, with a versioned two-store index (SQLite + Chroma), semantic retrieval, structured generation with facet extraction/entailment/coverage, source citations, supersession disclosure, and full traces. The architecture is clean, the DTO contracts are well-specified, and the test suite is thorough with both deterministic fakes and real-store integration tests. However, one blocker must be addressed before merge: ingest silently destroys all data when the pipeline signature mismatches, contrary to the spec's explicit requirement that it refuse and point to `--rebuild`.

**Resolved after review (2026-08-10)**: the blocker (ingest refused to refuse on pipeline mismatch, AC-8) and the major (freshness compared `fingerprint` instead of `entry_digest`, AC-17) were fixed in commit `17db8c4` ("refuse pipeline mismatch on ingest and compare entry digests for freshness"). `/check verify` subsequently passed all local and live behaviors, including live JobPilot query 1 against the real corpus. The minor `IngestResult.store_path` is also fixed (2026-08-10): `_result` now threads `request.store_dir` through, so the CLI prints the real `output:` path instead of `/unset`, locked by a regression assertion in `tests/test_ingest.py`.

## Blockers

### 🔴 Ingest does not refuse pipeline mismatch without `--rebuild`, `src/decision_memory/infrastructure/index_store.py:79-97`

**Problem**: When `open_generation(force_rebuild=False)` encounters a mismatched pipeline signature, it silently creates a new empty generation instead of refusing. The `_run_ingest` flow then marks all records as "unchanged" (because `existing_states()` reads from the old generation), makes no embeddings, and `activate()` switches `ACTIVE` to the empty generation, orphaning all previous data.

**Why it matters**: Per spec 0007 AC-8: *"Normal ingest refuses mismatch and points to ingest --rebuild."* A user who upgrades their pipeline config (e.g., changes the embedding model) and runs a normal `ingest` will silently lose their entire index with no warning. Query would then see an empty index and abstain. The spec mandates an explicit refusal with a clear message directing the user to `ingest --rebuild`.

**Suggested fix**: Before creating a new generation in `open_generation` (or in `_run_ingest` before calling `open_generation`), check whether the active generation's pipeline signature matches the running one. If it does not match and `force_rebuild` is `False`, raise or return a failure with code `pipeline.incompatible` and a message like "pipeline signature changed; run ingest --rebuild to rebuild the index." There is already a test (`test_pipeline_mismatch_refuses`) that proves query refuses mismatch — a corresponding test for ingest must be added.

## Major

### 🟠 Freshness compares `entry.fingerprint` not `entry.entry_digest`, `src/decision_memory/application/query.py:740-755`

**Problem**: `_manifest_freshness` compares `ledger[entry.id]` (stored `desired_fingerprint`) against `entry.fingerprint` (the adapter-level source hash). The spec AC-17 says *"differing entry digest is record_changed."* The `entry_digest` is a broader hash that includes `{id, fingerprint, contributing_files, record_path, record_digest, field_sources}`, while `fingerprint` only covers source file contents plus adapter version.

**Why it matters**: If an adapter update changes how `field_sources` are mapped without changing source files, `entry.entry_digest` would differ but `fingerprint` would match. The global freshness state would still detect drift via the semantic manifest digest comparison (since `semantic_manifest_digest` includes the entries), but the per-record `StaleReason.RECORD_CHANGED` would not be attributed to the affected record. This makes the stale-reason breakdown incomplete.

**Suggested fix**: Compare `entry.entry_digest` instead of `entry.fingerprint` in the per-entry freshness check, or store and compare `desired_entry_digest` from `record_state` (which currently exists in the schema but is never populated by `write_record`).

## Minor

### 🟡 `IngestResult.store_path` is always `Path("/unset")`, `src/decision_memory/application/ingest.py:467`

**Problem**: The `_result` helper always passes `store_path=Path("/unset")` regardless of which store directory was actually used. The CLI uses this field for display.

**Why it matters**: The `IngestResult` DTO documents `store_path` as a meaningful field, but it never carries the real value. The CLI shows "/unset" after every ingest.

**Suggested fix**: Pass the actual `request.store_dir` through the result chain, or set it at the `_run_ingest` level before returning.

### 🟡 `_with_freshness` and `_with_stale_reason` are near-duplicates, `src/decision_memory/application/query.py:764-798`

**Problem**: Both functions create a new `FreshnessTrace` by unpacking and repacking all fields. `_with_stale_reason` differs only in appending to `stale_reasons`. The duplication means any new field added to `FreshnessTrace` must be updated in both places.

**Why it matters**: Maintenance risk — if someone adds a field to `FreshnessTrace`, it's easy to miss one of these helpers.

**Suggested fix**: Have `_with_stale_reason` delegate to `_with_freshness` after constructing a trace with the appended reason tuple, or use a single helper with an optional `stale_reasons` override.

### 🟡 Bare `except Exception` could catch `KeyboardInterrupt` / `SystemExit`, multiple files

**Problem**: Several `except Exception` blocks in `query.py`, `ingest.py`, and `index_store.py` use `# noqa: BLE001` to justify catching all exceptions. While the design intent (return results, never raise) is correct per the spec, `except Exception` also catches `KeyboardInterrupt` and `SystemExit`, which could mask a user's intentional termination during a long-running provider call.

**Why it matters**: A user pressing Ctrl+C during an embedding call might see a "provider failure" result instead of a clean exit. The risk is low but real during slow API calls.

**Suggested fix**: Use `except BaseException as exc` and re-raise `KeyboardInterrupt` and `SystemExit`, or use `except (OSError, RuntimeError, ...)` with a narrower set, or accept the current behavior as intentional (the `# noqa: BLE001` comments suggest it is). No code change required if the team accepts the tradeoff; this is a note for awareness.

### 🟡 `IndexReader` opens a new SQLite connection per method call, `src/decision_memory/infrastructure/index_reader.py`

**Problem**: Each method on `SqliteChromaIndexReader` (e.g., `chunk()`, `manifest_metadata()`, `ledger_fingerprints()`) opens and closes its own SQLite connection. During a single `query_index` call, this means several connection creations.

**Why it matters**: For the expected local corpus size (single-digit records), this is negligible. If the corpus grows significantly, connection overhead could become measurable.

**Suggested fix**: Consider a connection pool or a single long-lived connection for the duration of a query in a future optimization pass. Not urgent for Slice 1.

## Nits

- ⚪ `src/decision_memory/application/dto.py:78`, `CandidateDisposition.BELOW_FLOOR` is defined but never emitted — the `relevance_floor` is `None` so `below_floor` is reserved for Feature 11 per spec. No code path produces this value today, which is correct per the spec but deserves a comment noting it's reserved.
- ⚪ `src/decision_memory/infrastructure/index_store.py:15`, the `from __future__ import annotations` import is present but not needed for `contextlib` usage — purely cosmetic.
- ⚪ `tests/fake_index.py:144`, `empty_eligible = False` attribute on `FakeIndex` — the name is slightly misleading; it means "the eligible tuples list will be empty" not "the index is empty". A comment would help.

## Strengths

- **Exceptional Clean Architecture discipline**: The application layer receives only narrow callables and protocols; no infrastructure imports leak inward. The `QueryDependencies` and `IngestDependencies` dataclasses make the composition root trivially testable with fakes.
- **Comprehensive test strategy**: The `FakeIndex` implements both reader and writer protocols, enabling deterministic end-to-end tests that lock the AC-11 structured propositions without touching OpenAI or Chroma. Integration tests separately validate the real store wiring with the same deterministic embedder.
- **The trace design is production-grade**: `QueryTrace` captures freshness, retrieval candidates with full precision scores, generation inputs, verification per-sentence, provider attempts with timings, and terminal stage — all as immutable tuples. This directly enables Feature 11's evaluation harness to test the application programmatically rather than parsing CLI prose.

## Test coverage

The test suite is thorough. Key areas covered:
- Happy-path roundtrip with deterministic fakes (`test_query_roundtrip.py`)
- Incremental ingestion, removals, tombstones, rebuild failure preservation (`test_ingest_incremental.py`)
- Freshness drift, `--allow-stale`, and stale citation markers (`test_freshness.py`)
- Lock protocol (shared/shared coexistence, exclusive blocking) (`test_lock.py`)
- Chunking grammar, field boundaries, prefix, oversize failure (`test_chunking.py`)
- Supersession link derivation, cycle detection, disclosure rendering (`test_supersession.py`)
- Chroma parity upsert, verify, valid distance bounds (`test_chroma_parity.py`)
- Real store roundtrip with `SqliteChromaIndexWriter`/`SqliteChromaIndexReader` (integration-marked)
- Provider planning (no key for dry-run / unchanged-only, key required before mutation)
- Empty index abstention, empty question rejection, corrupt store refusal

**Notable gap**: No test covers ingest refusing a pipeline mismatch without `--rebuild` (the blocker above). The query-side refusal is tested (`test_pipeline_mismatch_refuses`), but the ingest side is not.
