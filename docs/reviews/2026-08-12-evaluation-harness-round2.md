# Review, evaluation-harness, 2026-08-12 (round 2)

**Reviewed by**: Claude Opus 5 (author model not disclosed; per `docs/session-notes.md`, review subagents in this editor inherit the parent model, so treat the cross-model guarantee as unproven for this round)
**Scope**: 13 files, branch vs `main` (merge-base `d262f51`)
**Verdict**: Changes requested

## Summary

Second review round on feature 11 (the evaluation harness). **No code changed since round 1**: `git status` shows only `docs/session-notes.md` modified and the round-1 findings file untracked, and every line cited in `docs/reviews/2026-08-12-evaluation-harness.md` is still present verbatim. The session note records the decision as "Fix before merge is undecided," so this is a re-assessment, not a re-check of fixes. I independently verified the round-1 findings against the current tree — all six still stand — and re-derived the Major on stronger grounds than round 1 stated. I also found one new correctness hole the first round missed: the re-ingest oracle passes when the target record's chunks drop to zero, so the assertion can report a false proof. I upgraded the "ignores the configured adapter" item from nit to Minor, because the code resolves the adapter setting and then discards it rather than never looking.

The change itself remains good work. `application/evaluation.py` is a clean, framework-free engine with a narrow port and thorough unit coverage; the `active_chunks` column-swap fix is verifiably correct (I checked the SQL: `SELECT ... c.active_fingerprint, c.value_path ...` puts fingerprint at index 4 and value_path at index 5, so the new `value_path=row[5]` / `fingerprint=row[4]` mapping is right, and it now agrees with `_active_chunk_rows`); the docs are honest about which fixtures fail and why. Gate status: `uv run pytest` 456 passed / 18 deselected, `ruff check` clean, `mypy src` clean.

## Major

### 🟠 The re-ingest orchestration and its corpus-isolation guarantee are asserted by no test at any level, `src/decision_memory/infrastructure/evaluation_runner.py:167`

**Problem**: Carried unchanged from round 1, and the honest framing is sharper than round 1 gave it. AGENTS.md says "infrastructure integration tested," so "no unit test on infrastructure" is not by itself a convention violation — but that defence does not apply here, because the integration test does not test this either. `tests/test_evaluation_live.py` is the only file that constructs `EvaluationRunner` (confirmed by grep across `src/` and `tests/`), it is skipped unless both `OPENAI_API_KEY` and `DECISION_MEMORY_JOBPILOT_DIR` are set, and its only assertion touching the re-ingest fixture is `assert check.detail` — that the string is non-empty. So:

- The four failure branches (`no such corpus file`, `adapt of the copy failed`, `initial ingest of the copy failed`, `re ingest of the copy failed`, plus the two terminal failure returns) have zero assertions anywhere.
- The headline docstring claim, "the user's corpus is never mutated," is a data-safety property over a real repository path (`docs/specs/0006-adzuna-job-discovery/rationale.md`) and **nothing asserts it**. Not the unit suite, not the integration suite.
- CI runs the unit suite only (AGENTS.md), so a future edit to the `copytree`/`TemporaryDirectory` block that started appending `_REINGEST_PROBE` to the real file would be caught by no automated check at all.

**Why it matters**: This is branching error-handling plus a destructive-write safety property — the exact combination the review guide marks Major when untested. The blast radius is a user's real source repository, and the failure would be silent (the assertion would still report PASS, since the real record's chunks would genuinely have changed).

**Suggested fix**: At least one fast, provider-free test that pins the isolation property: build a throwaway corpus with a `docs/specs/NNNN-x/rationale.md`, monkeypatch `EvaluationRunner.adapt` and `EvaluationRunner.ingest` to scripted outcomes so nothing hits OpenAI, call `run_reingest`, and assert the source `rationale.md` bytes are unchanged. The `no such corpus file` branch needs no patching at all. Both are cheap; the happy path can stay live.

## Minor

### 🟡 The re-ingest assertion passes when the record's chunks go to zero, `src/decision_memory/infrastructure/evaluation_runner.py:210`

**Problem**: New in this round. The oracle is `if before and before != after: PASS`. It never requires `after` to be non-empty. If the second adapt drops the record instead of updating it — the appended probe breaks a parse precondition, the spec gets skipped, and the record is removed from the manifest — the flow still reports success: `adapt` returns exit 0 for a *skipped* spec (only failed records and adapter exceptions produce exit 1; see `adapt_corpus`), and `ingest_records` returns exit 0 for a *removed* record (`RecordAction.REMOVED` is not `FAILED`). Both exit-code guards pass, `after` is empty, `before != after` holds, and the harness prints `PASS ... chunks changed after the rationale.md edit (7 -> 0 chunk ids)`.

**Why it matters**: The assertion's whole claim is "the edited rationale.md reached the index." A record that vanished from the index proves the opposite, and the harness would report it as one of the feature's two Done-when gates being met. The printed detail even contains the evidence (`-> 0 chunk ids`) while the status says PASS, which is worse than a plain failure.

**Suggested fix**: Require `after` to be non-empty for the PASS branch, and add an explicit failure return for "the record disappeared from the index after the edit" so the diagnostic names what actually happened.

### 🟡 Multi-run failure detail describes the last run, not the failing run, `src/decision_memory/application/evaluation.py:257`

**Problem**: Carried, unaddressed. `last_detail` is reassigned every iteration of the `runs` loop, so under `--runs N` a fixture that fails on run 2 but passes on run 3 prints `FAIL query-x (2/3 runs): 2/3 runs passed; answered with required citations`. The appended clause describes a pass, on a row marked FAIL, and the actual failure reason is discarded. The existing test (`tests/test_evaluation.py:436`) only asserts `"2/3 runs passed" in detail`, so it does not catch this.

**Why it matters**: `--runs N` exists to characterise stochastic fixtures — exactly the case where the report is now self-contradictory. The scope doc shows this mode is the primary way the team measured query 4's coin-flip behaviour, so the wrong detail lands on the most-used diagnostic path.

**Suggested fix**: Track the first non-passing run's detail separately and append that when `status` is false.

### 🟡 Every ingest failure is reported as a missing API key, and a test cements the wrong message, `src/decision_memory/cli.py:1149`

**Problem**: Carried, unaddressed. `evaluate` prints `"ingest failed; the harness needs OPENAI_API_KEY to build the index"` for any non-zero `ingest_result.exit_code`. I traced `ingest_records`: it returns exit 1 for `manifest.invalid`, `pipeline.incompatible`, `supersession.invalid`, `store.parity`, and any per-record `FAILED` — five distinct causes, all misattributed to a missing key. `ingest_result.failure` carries the real code and detail and is never read. Additionally, `tests/test_cli_evaluate.py:119` asserts this exact string, so the misleading message is now locked in by a test; fixing the message requires updating that assertion.

**Why it matters**: The harness's stated contract is legible failure. Sending a user to check their API key when the real cause was store parity is the opposite.

**Suggested fix**: Print `ingest_result.failure.detail` (or the failure code) when present, and only name `OPENAI_API_KEY` when the code is `provider.key`. Update the CLI test to assert the key message only on the key path.

### 🟡 The harness pipeline skips the store lock on both ingest and query, and drops `RetrievalFailure` handling, `src/decision_memory/infrastructure/evaluation_runner.py:80`

**Problem**: Carried from round 1, and it is broader than round 1 described — it affects the ingest side too, not just the query side. The live `ingest` command wraps its run in `store_lock(store_dir, exclusive=True)` (`cli.py:694`) and the live `query` command wraps its run in `store_lock(store_dir, exclusive=False)` and catches `RetrievalFailure` and `LockError` (`cli.py:775,799,806`). `EvaluationRunner.ingest` and `EvaluationRunner.run_query` take neither lock and catch neither exception. A `RetrievalFailure` on any fixture therefore escapes as an unhandled traceback that aborts the whole battery instead of producing a FAIL row.

**Why it matters**: Two costs. The harness claims to prove "the exact live pipeline" but runs a pipeline missing the concurrency protocol, so it cannot catch a lock-related regression. And a retrieval-integrity failure — a reportable, per-fixture outcome — becomes a crash that discards the results of every fixture already run, including the paid live queries.

**Suggested fix**: Wrap the runner's ingest and query in the same locks the CLI commands use, and catch `RetrievalFailure` inside `run_query` so it becomes a failed fixture row rather than an escaped exception.

### 🟡 Default temp records and store directories are never cleaned up, `src/decision_memory/cli.py:1136`

**Problem**: Carried, unaddressed. Both default paths come from `tempfile.mkdtemp`, which never removes anything, while `run_reingest` in the same change correctly uses `TemporaryDirectory`. Each default run leaves a full adapted records tree plus a SQLite + Chroma store behind.

**Why it matters**: Unbounded disk growth from a command the scope notes show being run in repeated `--runs 3` batches, and it is inconsistent with the cleanup discipline used a few hundred lines away in the same feature.

**Suggested fix**: Use `TemporaryDirectory` for the paths the user did not supply (still printing them in the report), or clean up on exit when they were defaulted.

### 🟡 `evaluate` resolves the configured adapter and then discards it, `src/decision_memory/cli.py:1117`

**Problem**: Upgraded from a round-1 nit, because the code does more than omit the feature — it computes the answer and throws it away. `resolve_runtime_settings` returns a `RuntimeSettings` carrying `adapter` (CLI > `.decision-memory.yml` > built-in) and `output`. `evaluate` uses `settings.corpus_root` and ignores both other fields; `EvaluationRunner.adapt` hardcodes `JsmasteryAdapter()`. So a project whose `.decision-memory.yml` sets a third-party adapter gets its `corpus_root` honoured but its corpus adapted by the wrong adapter, silently, with no warning line.

**Why it matters**: Half-honouring the config file is more confusing than ignoring it. The likely outcome is a corpus that adapts to zero or wrong records and a battery of FAILs that look like retrieval bugs. The user guide says the battery is "calibrated to the built in adapter," but nothing in the tool says so at runtime.

**Suggested fix**: Either wire `settings.adapter` through the runner, or refuse/warn loudly when the resolved adapter is not `jsmastery-specs` (`BUILTIN_ADAPTER_ID`) so the mismatch is visible at the point of failure.

### 🟡 The column-swap regression lock sits outside the CI gate, `tests/test_store_format.py:174`

**Problem**: Carried, unaddressed. `test_active_chunks_keeps_value_path_and_fingerprint_separate` is `@pytest.mark.integration`, so it does not run in `uv run pytest` or in CI on push. It is a good test — it uses `fake_embed`, so it needs no network and would run fine in the fast suite — but the marker excludes it anyway. A regression of exactly the bug this branch fixed would pass CI.

**Why it matters**: The bug it guards silently corrupted `--value-path` filtering and citation value paths on real stores. It is the one genuinely new regression lock in this change, and it is the one not being run.

**Suggested fix**: The test appears to have no live dependency (`fake_embed`, real `SqliteChromaIndexWriter`). Check whether the `integration` marker is actually required here; if it is only there to match the file's convention, move this one test into the fast suite. Otherwise state the deliberate choice in the test docstring.

## Nits

- ⚪ `src/decision_memory/application/evaluation.py:215`, `run_evaluation` does not guard `runs >= 1`; only the CLI does (`cli.py:1131`). A library caller passing `runs=0` gets a vacuous all-pass outcome (`passed == runs` is `0 == 0`), which is the worst possible default for a correctness harness.
- ⚪ `src/decision_memory/infrastructure/evaluation_runner.py:193,206`, `getattr(ingest_outcome, "exit_code", 1)` is dead-defensive — `IngestResult` always has `exit_code`. Direct access would fail loudly instead of masking a shape change behind "initial ingest of the copy failed".
- ⚪ `src/decision_memory/application/evaluation.py:255,283`, `assert` used for type narrowing. Locked by `test_battery_has_eight_fixtures_in_fixed_order`, but asserts vanish under `python -O`; construction-time validation on the frozen dataclasses would be sturdier.
- ⚪ `src/decision_memory/cli.py:1128`, no upper bound on `--runs`. A typo like `--runs 500` fires ~3,500 paid live queries with no confirmation.
- ⚪ `src/decision_memory/cli.py:1143`, nothing prints until the entire battery finishes, so a live `--runs 3` run (21 queries plus a re-ingest) shows a blank terminal for minutes and looks hung. Printing the `records:`/`store:` header before the run, or streaming each fixture line as it completes, would fix it.
- ⚪ `src/decision_memory/application/evaluation.py:230`, `port.proposed_record_ids()` is called unconditionally even when no fixture sets `cite_all_proposed`. Harmless for the live runner, but it forces every port implementation to support it.
- ⚪ `src/decision_memory/application/evaluation.py:121`, `EvaluationOutcome` is `frozen=True` but holds a mutable `list`; `tuple` would make the immutability real, matching the tuple use elsewhere in the module.

## Strengths

- `application/evaluation.py` is the best-shaped file in the change: no Typer, Pydantic, OpenAI, or Chroma imports, fixtures as frozen dataclasses, a three-method port, and oracle logic that is fully unit tested through a scripted `FakePort`. `tests/test_evaluation.py` covers answered/abstained/re-ingest/rate/exit-code contract without a single infrastructure mock, exactly as AGENTS.md requires of application code.
- The `active_chunks` column-swap fix is correct and I verified it independently against the SQL rather than taking the diff at face value: the `SELECT` orders `active_fingerprint` before `value_path`, so the new mapping is right and now agrees with `parity_problems`' separate row mapping — which is presumably why the bug survived so long, since only one of the two readers was wrong.
- The re-ingest assertion's *design* is sound even though its oracle needs tightening: `chunk_id` incorporates the fingerprint, `rationale.md` is a contributing file, the second ingest deliberately resumes the same generation, and `_derive_id` reads the record id from the directory name — which is what makes copying a single spec dir into an isolated workspace work at all.
- `tests/test_cli_evaluate.py` deliberately scripts the engine seam rather than pinning today's stochastic live results, and says so in its module docstring. That is the right call and an easy one to get wrong.
- The docs refuse to flatter the result: `verify.md` leaves failing gates unticked, and the scope correction retracts the earlier "query 4 fabricates" claim as an unlucky sample after measuring 12 runs. That is unusually honest reporting.

## Test coverage

The engine is well covered and the CLI boundary is well covered. `tests/test_evaluation.py` (469 lines) locks the fixture battery, both oracle directions, the proposed-record derivation, run-rate semantics, and the exit contract; `tests/test_cli_evaluate.py` locks report grammar, fixed order, exit codes 0/1/2/3, and the missing-key path. Suite is green: 456 passed, 18 deselected, ruff and mypy clean.

The gap is entirely in `infrastructure/evaluation_runner.py`, 233 lines with no assertion of its own behaviour anywhere in the repo. The Major covers the isolation property and the failure branches; also uncovered are `proposed_record_ids` (glob, parse, status filter — testable with plain files and no providers) and `_chunk_ids`. The one new regression lock in the change, `test_active_chunks_keeps_value_path_and_fingerprint_separate`, needs no network but is marked integration and so never runs in CI.

## Fix outcomes (2026-08-12, applied same day, not re-reviewed)

Every Major, Minor, and Nit in this round was addressed. Not re-run through `/check review`; the summary below is the implementer's account, not an independent verdict.

- **Major (isolation property untested)**: fixed. New `tests/test_evaluation_runner.py` (9 tests) monkeypatches `adapt`/`ingest`/`_chunk_ids` to pin every branch of `run_reingest`, including that the source `rationale.md` survives byte for byte.
- **Re-ingest oracle false positive**: fixed. `after` must now be non-empty for a PASS; a record dropping to zero chunks is a distinct named failure, locked by a dedicated test.
- **Multi-run detail reports the last run, not the failing one**: fixed. The engine now tracks the first non-passing run's detail separately; `test_runs_measures_rate_across_repeated_queries` strengthened to assert the failing detail is present and the passing one is not.
- **Ingest failures all blamed on a missing key**: fixed. `evaluate` now prints `ingest_result.failure`'s real stage/code/detail, with the API-key hint gated on `code == "provider.key"`. `test_evaluate_missing_api_key_fails_loudly` updated; `test_evaluate_other_ingest_failure_names_its_real_cause` added.
- **Missing store lock, dropped RetrievalFailure**: fixed, with one deviation from the suggested fix. `ingest()` and `run_query()` now hold the same locks the live CLI commands hold. `RetrievalFailure` is caught one layer up, in the application engine's `_run_query_fixture`, not inside the infrastructure `run_query()` as literally suggested — converting it to a `QueryResult` at the infrastructure layer would require synthesizing a full `QueryTrace` from a `PartialQueryTrace`, which the DTO's own docstring says must never be synthesized. Catching it at the port-call boundary in application code gets the same practical outcome (a legible FAIL row, battery continues) without that fabrication. Locked by `test_retrieval_failure_becomes_a_failed_fixture_not_a_crash` and `test_ingest_returns_a_legible_failure_on_a_lock_conflict`.
- **Leaked default temp dirs**: fixed. Defaulted `--records`/`--store` paths now live in `TemporaryDirectory`s scoped to the command via `ExitStack`, still printed for the user, cleaned up on exit either way.
- **Adapter resolved and discarded**: fixed via the warn branch, not the wire-through branch. `evaluate` now warns loudly when the configured adapter isn't the built-in one, rather than silently running the wrong adapter against a battery whose fixtures assume the built-in corpus's record ids.
- **Column-swap regression test marked integration**: kept as integration, not moved. Its two siblings in the same file are also integration-marked despite using `fake_embed`, because the file's convention is real store implies integration regardless of network use; moving only this one test would break that consistency. Documented the reasoning directly in the test's docstring instead.
- **All seven nits**: fixed — `runs >= 1` guard with a real `raise` (library callers, not just the CLI); dead `getattr(..., "exit_code", 1)` replaced with direct access (both call sites); `assert` type-narrowing backed by real `__post_init__` validation on `EvaluationFixture` (a `raise`, not an `assert`, so it survives `python -O`); `--runs` capped at 20; `records:`/`store:` now print before the battery runs, not after; `proposed_record_ids()` only called when a fixture actually sets `cite_all_proposed`; `EvaluationOutcome.checks` is now a tuple.

Suite after fixes: `uv run pytest` 473 passed / 18 deselected, `ruff check` clean, `mypy src` clean.
