# Review, feature/11-evaluation-harness, 2026-08-12

**Reviewed by**: DeepSeek V4 Flash (fresh-model review; author model not disclosed)
**Scope**: 12 files, branch (merge-base `d262f51`..HEAD)
**Verdict**: Changes requested

## Summary

This change ships the evaluation harness (feature 11, Slice 3): a pure application engine (`application/evaluation.py`) holding the five defining queries plus three extra fixtures as data, a live `EvaluationPort` (`infrastructure/evaluation_runner.py`) that adapts/ingests/runs real queries and the incremental re-ingest assertion on an isolated copy, an `evaluate` CLI command with a fixed exit contract (0/1/2/3), and a one-line `active_chunks` column-swap fix in `index_reader.py` with a regression lock. The engine is clean, well-typed, thoroughly unit tested, and the column-swap fix is verifiably correct (it now matches `parity_problems`' independent row mapping). The docs (verify.md, scope correction, user-guide) are honest and detailed. The headline issue is that the re-ingest assertion's orchestration — its branching failure paths and the "never mutates the user's corpus" safety property — has no hermetic test and only runs in the env-gated integration suite, so the riskiest logic in the change is outside the CI unit gate. Several minors follow on reporting and robustness in the `--runs N` diagnostic mode.

## Major

### 🟠 Re-ingest orchestration and its safety property are untested outside the env-gated suite, `src/decision_memory/infrastructure/evaluation_runner.py:167`
**Problem**: `run_reingest` is the most complex logic in the change — temp-copy orchestration, two adapts, two ingests, a before/after chunk comparison, and four early-return failure branches ("no such corpus file", "adapt of the copy failed", "chunks did not change", "no active chunks"). Only the live integration test (`test_evaluation_live.py`, skipped unless `OPENAI_API_KEY` and `DECISION_MEMORY_JOBPILOT_DIR` are both set) exercises it, and only the happy path; the failure branches and the isolation guarantee have zero assertions anywhere. The docstring's headline claim — "the user's corpus is never mutated" — is a data-safety property over a real repository (`docs/specs/0006-*/rationale.md`) with no regression test that the real file is byte-identical after a run. Because the unit suite (CI's gate) never constructs `EvaluationRunner`, a future edit to the copy logic could silently start mutating the real corpus and nothing would catch it.
**Why it matters**: This is branching error-handling logic plus a repository-data-safety guarantee, exactly the class the review guide's bar says warrants a Major when untested. The project already unit-tests similar tempfile/shutil orchestration hermetic (conformance `WorkspaceFixture`), so the pattern exists to follow. The live test does not run in CI (AGENTS.md: CI runs the unit suite only).
**Suggested fix**: Add fast, hermetic tests for the runner: (a) the "no such corpus file" branch (needs no providers — `runner.run_reingest("DM-0006", "docs/specs/nope/rationale.md")` should return the legible failure), (b) the isolation property by monkeypatching `EvaluationRunner.adapt`/`ingest` to scripted outcomes and asserting the real `rationale.md` is untouched and the before/after branch logic fires, and (c) `proposed_record_ids` parsing (proposed vs ratified records) which is currently only covered indirectly. Happy-path live coverage can stay in the integration suite.

## Minor

### 🟡 Multi-run failure detail reports the last run, not the failing run, `src/decision_memory/application/evaluation.py:257`
**Problem**: In `_run_query_fixture`, `last_detail` is overwritten every iteration, so when `runs > 1` the appended detail is always the final run's. If the last run passes but an earlier run failed, the FAIL row reads e.g. `FAIL query-2 (2/3 runs): 2/3 runs passed; answered with required citations` — the appended text describes a pass on a failed fixture, and the actual failing run's reason is lost.
**Why it matters**: `--runs N` exists precisely to surface flaky behavior; the report contradicts itself precisely when it is most informative. The first failing run's detail is what the user needs.
**Suggested fix**: Capture and retain the detail of the first non-passing run (e.g. keep `first_fail_detail`), and append that instead of the last run's detail.

### 🟡 Ingest failure is always reported as a missing API key, `src/decision_memory/cli.py:1149`
**Problem**: `evaluate_command` prints "ingest failed; the harness needs OPENAI_API_KEY to build the index" for any non-zero ingest result. `ingest_records` can fail for manifest, supersession, or store-parity reasons (all exit 1), which this message misattributes to a missing key.
**Why it matters**: Misleading diagnostics on the failure path; the harness's whole purpose is legible failure reporting.
**Suggested fix**: Print the ingest failure detail (`ingest_result.failure` / state) when present, and only mention the key when the failure code is `provider.key`.

### 🟡 Query path omits the store lock and `RetrievalFailure` handling the live `query` command has, `src/decision_memory/infrastructure/evaluation_runner.py:90`
**Problem**: The live `query` command wraps `query_index` in `store_lock(store_dir, exclusive=False)` and catches `RetrievalFailure`/`LockError` (cli.py:775, 799). `EvaluationRunner.run_query` does neither, so (a) a retrieval-integrity failure escapes as an unhandled exception that aborts the whole battery with a traceback instead of a legible FAIL row, breaking the harness's per-fixture report contract, and (b) if a user points `--store` at a store another process is ingesting, the harness reads/writes without the lock protocol.
**Why it matters**: Low likelihood with the fresh temp store default, but it is a deviation from the exact live pipeline the harness claims to prove, and it converts a reportable failure into a crash.
**Suggested fix**: Wrap the per-fixture query in the shared lock and catch `RetrievalFailure` inside the port (returning a failed fixture), matching the live command's wiring.

### 🟡 The column-swap regression lock is integration-marked and outside the CI unit gate, `tests/test_store_format.py:174`
**Problem**: `test_active_chunks_keeps_value_path_and_fingerprint_separate` is `@pytest.mark.integration`, so it does not run in the default unit suite or CI on push (both integration-excluded). The swap it locks silently corrupted `--value-path` filtering and citation value paths on real stores; no fast-suite test touches the real store's column mapping at all.
**Why it matters**: Consistent with the file's existing convention (real-store tests are integration-marked), but it means the fix that this branch makes is only guarded outside the automated gate. A regression of exactly this bug would pass CI.
**Suggested fix**: Either accept the integration-only lock deliberately and note it, or add a fast regression that asserts `value_path`/`fingerprint` separation over the real SQLite layout without the Chroma writer (the columns live in the chunk table, so a SQLite-only read can lock the mapping in the unit suite).

### 🟡 Temp `--records`/`--store` directories are never cleaned, `src/decision_memory/cli.py:1136`
**Problem**: `tempfile.mkdtemp` dirs are left behind on every default run (the full Chroma + SQLite index can be sizable), while `run_reingest` correctly uses `TemporaryDirectory`. The scope notes show repeated `--runs 3` batches, so `/tmp` accumulates `decision-memory-evaluate-*-*` stores.
**Why it matters**: Unbounded disk growth from a diagnostic command, inconsistent with the cleanup discipline used elsewhere in the same change.
**Suggested fix**: Use `TemporaryDirectory` for the default paths (still print the paths in the report), or clean up on exit when the user did not supply the dirs.

## Nits

- ⚪ `src/decision_memory/application/evaluation.py:215`, `run_evaluation` does not validate `runs >= 1` itself — only the CLI does (cli.py:1131); a library caller passing `runs=0` gets a vacuous 0/0 pass. Add the guard to the engine.
- ⚪ `src/decision_memory/infrastructure/evaluation_runner.py:193`, `getattr(ingest_outcome, "exit_code", 1)` is dead-defensive — `IngestResult` always has `exit_code`; direct attribute access would fail loudly instead of silently masking the real cause behind "initial ingest of the copy failed".
- ⚪ `src/decision_memory/cli.py:1104`, `evaluate` always uses the built-in `JsmasteryAdapter` and ignores the configured `.decision-memory.yml` adapter. Documented as "calibrated to the built-in adapter," but a user with a custom adapter configured gets a harness that adapts the wrong format; an explicit warning would avoid confusion.
- ⚪ `src/decision_memory/application/evaluation.py:249,281`, `assert` is used for narrowing in the engine — fine for internal fixture invariants (and locked by `test_battery_has_eight_fixtures_in_fixed_order`), but asserts are stripped under `python -O`; construction-time validation on the frozen dataclasses would be more robust.
- ⚪ `src/decision_memory/cli.py:1103`, no upper bound on `--runs`; a typo like `--runs 500` triggers ~3,500 paid live queries. A sanity cap (or a confirmation) would be kind.

## Strengths

- The engine (`application/evaluation.py`) is a textbook application-layer module: zero infrastructure imports, a narrow `EvaluationPort` protocol, fixtures as frozen dataclasses, and oracle comparison logic that is fully unit tested (answered/abstained/re-ingest/rate/exit contract) with a clean scripted `FakePort` — the tests deliberately refuse to pin stochastic live outcomes, which is the correct call given the fixtures are measurably stochastic.
- The `active_chunks` column-swap fix is verifiably correct: the corrected `row[4]`/`row[5]` mapping now agrees with `parity_problems`' independent `_active_chunk_rows` mapping, and the regression lock documents the bug it prevents.
- The incremental re-ingest assertion is soundly designed: `chunk_id` incorporates the fingerprint, `rationale.md` is a contributing file, and the second ingest resumes the same generation, so a changed chunk id genuinely proves the multi-file fingerprint reached the index — and it runs on an isolated copy, never the user's corpus.
- Docs are honest and unusually specific: verify.md's per-fixture expectations, the scope.md correction that query-4 abstention is a measured coin flip rather than a fabrication, and the user-guide's clear `--runs` semantics.

## Test coverage

Strong where it matters most: the engine's oracle branches, run-rate semantics, exit-code contract, and fixture battery are comprehensively unit tested (`test_evaluation.py`, 469 lines); the CLI's report grammar, fixed order, and exit mapping are locked with a scripted engine seam (`test_cli_evaluate.py`), including the missing-key and missing-corpus paths; the live integration test exercises the real battery end to end without pinning pass/fail. Gaps: the runner's re-ingest orchestration, its four failure branches, `proposed_record_ids`, and the corpus-isolation safety property are only covered by the env-gated integration test (Major above); the column-swap regression lock is outside the CI unit gate (Minor). The unit suite is green (456 passed, 18 integration deselected), and the changed files have no type/lint errors.
