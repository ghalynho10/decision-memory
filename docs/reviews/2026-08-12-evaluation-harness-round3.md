# Review, evaluation-harness, 2026-08-12 (round 3)

**Reviewed by**: Claude Opus 5 (author model not disclosed; per `docs/session-notes.md`, review subagents in this editor inherit the parent model, so treat the cross-model guarantee as unproven for this round too)
**Scope**: 14 files, branch vs `main` (merge-base `d262f51`)
**Verdict**: Approve with nits

## Summary

Third round on feature 11. Unlike round 2, code did change: I re-derived every claimed fix against the working tree rather than trusting the "Fix outcomes" section appended to round 2's file. **The round-2 Major is genuinely fixed** — `tests/test_evaluation_runner.py` is a real, provider-free test file that pins the corpus-isolation safety property (the source `rationale.md` bytes are compared before and after, and the probe write to the copy is left unstubbed so a path regression would be caught) plus all six failure branches. All seven round-2 Minors and all seven Nits are correctly and completely applied; I found no fix that was claimed but absent, and no fix that broke something else. Gates are green on my own run: `uv run pytest` 473 passed / 18 deselected, `ruff check` + `ruff format --check` clean, `mypy src` clean, and the integration-marked column-swap lock passes when explicitly selected.

What remains is four Minors, three of them **new findings this round** that earlier rounds missed rather than regressions: one crash path the lock fix left open (and its docstring actively misdescribes), and two oracle holes in the same false-positive family as the re-ingest bug round 2 caught — a fixture can pass on evidence that does not prove what the fixture claims to prove. None is a blocker, and none should hold the merge if the team accepts them as tracked follow-ups.

## Verification of the round-2 fix claims

| Claim | Verdict |
|---|---|
| Major: `run_reingest` isolation + branches now tested | **Confirmed.** 10 tests, no network, isolation asserted byte-for-byte |
| Re-ingest oracle false positive (`after` may be empty) | **Confirmed fixed**, with a distinct named failure and a dedicated test |
| Multi-run detail reports the last run, not the failing one | **Confirmed fixed** (`first_failing_detail`, `evaluation.py:318`); the test asserts both that the failing reason is present and the passing one is absent |
| Ingest failure misattributed to a missing API key | **Confirmed fixed**; hint gated on `code == "provider.key"`, both paths tested |
| Store lock on `ingest()` / `run_query()`, `RetrievalFailure` handled | **Partially.** Locks and `RetrievalFailure` are correct; `LockError` from `run_query` is still unhandled — see Minor 1 |
| `RetrievalFailure` caught in application, not infrastructure | **Architecturally sound, reasoning verified.** `RetrievalFailure` is declared in `application/dto.py`, so catching it in `application/evaluation.py:309` crosses no layer boundary; `PartialQueryTrace`'s docstring (`dto.py:589`) does forbid synthesizing absent stages, so the deviation from round 2's literal suggestion is justified, not a shortcut. I grepped every `run_query` call site: `_run_query_fixture` is the only one, and `run_reingest` calls `adapt`/`ingest`/`_chunk_ids` only, so nothing leaks |
| Leaked default temp dirs | **Confirmed fixed** via `ExitStack`; `typer.Exit` is raised inside the `with`, so cleanup runs on every exit path |
| Adapter resolved-and-discarded → loud warning | **Confirmed fixed**, and correctly scoped: `resolve_runtime_settings` defaults `adapter` to `BUILTIN_ADAPTER_ID`, so the warning cannot fire spuriously |
| Column-swap test kept `integration`, documented | **Confirmed**, and the docstring reasoning matches the file (its two siblings are integration-marked for the same reason). I ran it: it passes. This satisfies round 2's stated alternative remedy, though the underlying "CI never runs the one new regression lock" fact is unchanged |
| All 7 nits | **Confirmed**, each one. The two remaining `assert`s in `evaluation.py:302,344` are now pure mypy narrowing backed by `EvaluationFixture.__post_init__` raising a real `ValueError`, so `python -O` no longer opens a hole |

## Minor

### 🟡 A `LockError` during a query still crashes the battery, and `run_query`'s docstring says the opposite, `src/decision_memory/infrastructure/evaluation_runner.py:141`

**Problem**: The docstring now states that "`RetrievalFailure` **and `LockError`** propagate uncaught ... the application evaluation engine ... is where those become a legible failed fixture." Only half of that is true. `_run_query_fixture` (`application/evaluation.py:309`) catches `RetrievalFailure` and nothing else, and it *cannot* catch `LockError`: that class lives in `infrastructure/index_lock.py`, so importing it into the application layer would break the dependency rule the fix was written to respect. Nothing else catches it either — `evaluate_command` has no `try/except LockError`, unlike `query_command` (`cli.py:807`) and `ingest_command` (`cli.py:697`), which both handle it. So `store_lock(..., exclusive=False)` at `evaluation_runner.py:168` raising produces an unhandled traceback that discards every fixture already run, which is exactly the outcome round 2 flagged. Note the asymmetry: `ingest()` on the same class *does* translate `LockError` into a failed `IngestResult`, so the two sides of the same fix landed inconsistently.

**Why it matters**: Low probability but a real crash path — it needs `--store` pointed at a store another process is writing, which is a plausible thing to try. The larger cost is the docstring: it asserts a safety property the code does not have, so the next reader will not look for the gap.

**Suggested fix**: Wrap the `run_evaluation` call in `evaluate_command` with `except LockError` (mirroring `cli.py:807`'s message and exit 1) — the presentation layer is where the other two commands handle it, so this needs no new layer crossing. Then correct `run_query`'s docstring to say only `RetrievalFailure` is turned into a fixture row.

### 🟡 Query 3's oracle passes vacuously when no record is proposed, `src/decision_memory/application/evaluation.py:380`

**Problem**: `cite_all_proposed` computes `missing = proposed - cited_ids` and passes when `missing` is empty. If `proposed` is empty — the adapter changed, a status parse regressed, or `proposed_record_ids` skipped the records — the subtraction is empty and query 3 passes on *any* answered result, citing anything at all. This is the same false-positive class round 2 caught in the re-ingest oracle (`before`/`after` non-empty is now required there); the identical guard is missing here. `proposed_record_ids` (`evaluation_runner.py:193`) makes it easier to hit than it looks: it silently skips any file where `parsed.record is None`, so a parse regression shrinks the required set instead of failing.

**Why it matters**: Query 3 is one of the feature's named Done-when gates. A gate that reports PASS when its own oracle has been emptied out is worse than one that fails, and the verify checklist would carry the tick forward.

**Suggested fix**: Fail the fixture with a named reason when `cite_all_proposed` is set and the resolved proposed set is empty. Separately, make `proposed_record_ids` surface unparseable record files rather than dropping them.

### 🟡 Required records and required value paths are checked independently, so assertion A can pass on another record's evidence, `src/decision_memory/application/evaluation.py:387`

**Problem**: `_satisfies` checks `required_record_ids ⊆ cited_ids` and then, separately, that *some* citation's `value_path` starts with each required prefix. The two conditions never have to hold on the same citation. For `assertion-rationale-summary` the module docstring is explicit that the point is "an answered query that cites a **rationale_summary** chunk **of DM-0006**" — but a result that cites DM-0006's `why[0]` plus some other record's `rationale_summary` satisfies both clauses and reports PASS. Query 1 has the same shape (`DM-0012` + a `decision.alternatives[` citation that may belong to a different record).

**Why it matters**: Assertion A exists to prove one specific field survived parse → chunk → embed → retrieve → generate for one specific record. As written it proves the weaker claim that both things appeared somewhere in the same answer. Given the corpus has many records with a `rationale_summary`, the loophole is reachable, not theoretical.

**Suggested fix**: When `required_record_ids` is non-empty, require each prefix to be matched by a citation whose `record_id` is in that set; keep the current any-citation behaviour only when no records are required.

### 🟡 `evaluate --store` silently rebuilds whatever store you point it at, `src/decision_memory/cli.py:1183`

**Problem**: `runner.ingest(rebuild=True)` is unconditional, and `--store` accepts any path. Pointing it at an existing index (the obvious reading of "run the battery against my store") stages a fresh generation from the harness's own adaptation and switches to it, replacing the user's active generation. `--records` is the same story one step earlier: `adapt` writes `<id>.md` files and overwrites `manifest.json` in whatever directory it is given. Neither option warns, and the option help ("Index store path; defaults to a temporary directory") does not hint that the command is destructive. `ingest --rebuild` at least makes the user type the flag.

**Why it matters**: A command named `evaluate` reads as read-only. The damage is recoverable (re-ingest) but silent and unprompted, on a path the user chose precisely because they cared about it.

**Suggested fix**: Refuse a `--store` that already has an active generation unless an explicit `--rebuild`-style flag is passed, or at minimum warn loudly and say the store will be rebuilt. Same for a non-empty `--records`. Document in `docs/user-guide.md`, which currently mentions neither option.

## Nits

- ⚪ `src/decision_memory/cli.py:1175`, the defaulted `records:`/`store:` paths are printed and then deleted by the `ExitStack` before the user can look at them. Worth labelling them as temporary in the line itself, so a failing run does not send someone to a path that no longer exists.
- ⚪ `src/decision_memory/cli.py:1137`, `--runs` is validated *after* the corpus check, so `evaluate /nonexistent --runs 0` exits 3 rather than the usage code 2. Usage validation conventionally comes first.
- ⚪ `docs/user-guide.md:156`, the new section documents neither `--records`/`--store` nor the 20-run cap; a user who types `--runs 50` learns about the cap only from the error.
- ⚪ `src/decision_memory/infrastructure/evaluation_runner.py:203`, `assert parsed.record.id is not None` is the one narrowing `assert` left in a hot path that `__post_init__` does not back; under `python -O` a `None` id would enter a `frozenset[str]`.
- ⚪ `tests/test_evaluation_runner.py:107`, the isolation test proves the source file is untouched but never asserts the *copy* received the probe. Since `open("a")` creates a missing file, a wrong copy path would still pass. One `assert probe in copy.read_text()` would close it.
- ⚪ `docs/scope/scope.md:160`, the status line says "456 unit passing"; the suite is now 473.

## Strengths

- The round-2 Major was fixed properly rather than minimally. `tests/test_evaluation_runner.py` stubs exactly three seams (`adapt`, `ingest`, `_chunk_ids`) and deliberately leaves the `copytree` + probe-write machinery real, which is what makes the isolation assertion mean something. Four of the ten tests re-assert the source bytes on *failure* paths too, not just the happy path — that is the version of the test that survives refactoring.
- The `RetrievalFailure` catch-site deviation is the right call and, unusually, the stated reason holds up under checking: `PartialQueryTrace`'s docstring really does forbid the synthesis the literal fix would have required, and the chosen site crosses no layer boundary because the exception is an application DTO. Deviating from a review suggestion with a documented reason beats complying with it badly.
- Each fix carries its own regression lock, and two of them (`test_evaluate_other_ingest_failure_names_its_real_cause`, the "2/3 runs" detail test asserting the *passing* detail is **absent**) are written as negative assertions. That is the harder and more durable form.
- Comments explain *why* throughout the new code — the `--runs` cap, the first-failing-detail choice, the `runs >= 1` raise, the early `records:`/`store:` print, the integration marker on the column-swap test. Every one of them encodes a review finding so the next editor cannot silently undo it.
- The docs continue to refuse to flatter the result: `verify.md` leaves the carried-in gates unticked and the scope correction retracts an earlier over-claim after measuring 12 runs.

## Test coverage

Well covered overall, and materially better than round 2. `tests/test_evaluation.py` (535 lines) locks the fixture battery, both oracle directions, construction-time validation, the `runs=0` raise, the run-rate semantics including the failing-detail choice, the `RetrievalFailure` path, and the exit contract, all without an infrastructure mock. `tests/test_cli_evaluate.py` (263 lines) locks report grammar, fixed order, exit codes 0/1/2/3, the runs cap, the adapter warning, and both ingest-failure messages. `tests/test_evaluation_runner.py` (240 lines) closes the round-2 Major.

Remaining gaps, all in `infrastructure/evaluation_runner.py`: `proposed_record_ids` is still untested at any level despite being pure filesystem-plus-parse logic (glob, parse-failure skip, status filter) that decides query 3's oracle — this is the one I would ask for, and it pairs with Minor 2. `_chunk_ids` is stubbed away in every new test and exercised only by the env-gated live suite. `run_query` legitimately needs live providers. The one new regression lock in the change (`test_active_chunks_keeps_value_path_and_fingerprint_separate`) still does not run in CI; the deliberate choice is now documented, which is what round 2 offered as the alternative, but the fact remains that a repeat of the exact bug this branch fixed would pass the push gate.

## Fix outcomes (2026-08-12, applied same day, not re-reviewed)

All four Minors and all six Nits addressed. Not re-run through `/check review`; this is the implementer's account, not an independent verdict.

- **`LockError` from `run_query` crashed the battery; docstring overclaimed**: fixed. `evaluate_command` now wraps the `run_evaluation` call in `except LockError`, mirroring `query_command`'s existing handling (message, exit 1). `run_query`'s docstring corrected to say only `RetrievalFailure` becomes a fixture row; `LockError` propagates to the CLI, same as it always did for `query`/`ingest`. Locked by `test_evaluate_lock_conflict_during_the_battery_fails_loudly`.
- **Query 3 passes vacuously on an empty proposed set**: fixed. `_satisfies` now fails `cite_all_proposed` fixtures with a named reason when the proposed set is empty, before doing the subtraction that would otherwise be vacuously satisfied. `proposed_record_ids`'s unbacked `assert parsed.record.id is not None` also removed (folded into the existing filter condition, so a `None` id is skipped rather than risking a `python -O` hole); left unparseable/id-less records silently skipped rather than raised, since this method runs once before the whole battery and an exception there would crash every fixture, not just query 3 — the empty-set check in `_satisfies` is the actual defense regardless of why the set came back empty. Locked by `test_cite_all_proposed_fails_when_proposed_set_is_empty`.
- **`required_record_ids` and `required_value_path_prefixes` checked independently**: fixed. When `required_record_ids` is non-empty, a prefix must now be matched by a citation whose own `record_id` is in that set, not merely by some citation anywhere in the answer. Locked by `test_value_path_prefix_must_belong_to_a_required_record`.
- **`evaluate --store`/`--records` silently rebuild whatever they're pointed at**: fixed via a loud warning, not a refusal (the harness legitimately always rebuilds; refusing would break intentional repeated use of the same scratch path). `--store` warns via `read_active()` when the path already has an active generation; `--records` warns when the directory already has files. Documented in `docs/user-guide.md`. Locked by `test_evaluate_warns_when_records_dir_is_not_empty` and `test_evaluate_warns_when_store_has_an_active_generation`.
- **Nits**: defaulted `records:`/`store:` lines now say `(temporary, removed on exit)`; `--runs` bounds now validate before the corpus-existence check (`test_evaluate_runs_validated_before_the_missing_corpus_check` proves exit 2 wins over exit 3 when both apply); `docs/user-guide.md` now documents `--records`, `--store`, and the 20-run cap; the isolation test strengthened with `test_run_reingest_probe_reaches_the_isolation_copy`, which inspects the copy's `rationale.md` at each scripted adapt call and asserts the probe is absent on the first and present on the second. The `docs/scope/scope.md` stale test count is left for `/sync` to reconcile from repo evidence, per that file's ownership.

Suite after fixes: `uv run pytest` 481 passed / 18 deselected (up from 473), `ruff check` clean, `mypy src` clean.
