# Session notes

In session residue that has not earned a place in scope, a spec, or AGENTS.md yet. `/checkpoint` owns the sections below; other skills own anything else.

## Open threads

- mypy is the installed strict type checker (tooling milestone); `AGENTS.md` records "mypy or pyright", so pyright stays a permitted alternative if a later session wants to swap.
- Date handling gap: `/develop` added a Pydantic field validator to coerce an unquoted YAML date scalar (for example `date: 2026-08-07`) to its ISO string, because PyYAML parses it as a date object. Spec 0002 still does not mention this; a candidate for a follow up line in the spec.
- The application layer imports infrastructure directly (`write_record_file` at `application/adapter.py:23`, same pattern at `validation_service.py:17`). This breaks the dependency rule in `AGENTS.md`, was flagged in every review round, and has been deliberately deferred three times. It is not enrolled in scope or any spec, so it currently lives only in `docs/reviews/`.
- The minors and nits from all three review rounds have never been read. They are in `docs/reviews/2026-08-08-feature-jsmastery-specs-adapter.md`, the `-recheck.md`, and the `-final.md` beside them.
- The `evidence.mentions_unresolved` warning and its AC-6 count never appear in CLI output: the adapt report prints violations only for failed records, and `validate` rebuilds its own context with the count defaulting to zero. The calibration is only visible through the adapter's parse API and the unit tests. A candidate for a later decision on surfacing the warning in the adapt report.
- **Next task, unowned**: `_INLINE_CODE_RE` at `infrastructure/jsmastery_adapter.py:86` pairs backticks naively, so the double backtick escape idiom shifts pairing by one and long stretches of prose get scanned as code. Found by review round 3 (`-final.md`), confirmed pre existing at `abe5f86`, not caused by the AC-6 work. Nobody owns it: no scope row, no spec. Three cautions before starting. Validate by calling `JsmasteryAdapter().parse()` on the real corpus, never a script that imitates the pipeline (see Ruled out). Fixing it will move the counts recorded in spec 0003 `rationale.md` again. And some of the 118 tests may be pinning current behaviour, so a red test needs reading rather than assuming a regression.
- Three commits are unpushed (`33c7d9b`, `c67e8b9`, `c585ba7`); origin sits at `abe5f86`, and PR #1 is open against it, so the PR does not yet contain the AC-6 work. Review round 3 approved with nits, so the branch is pushable when wanted.
- Commit `abe5f86` is labelled `fix(adapter):` but contains only docs. It is already pushed with PR #1 open, so correcting the subject line needs a force push. Left undecided: leave it, or amend with `--force-with-lease`.
- Scope shows feature 4 as `done` while its `Build it` box is unticked. Reconcile with `/sync`.
- After the branch lands, run `/sync`, then `/architect core cited query` for feature 5.

## Ruled out

- Plain single command Typer app (one `@app.command` plus `no_args_is_help`) does not dispatch in Typer 0.27.1: it auto invokes the command and rejects the command name. The CLI uses a callback (`invoke_without_command`) plus commands instead.
- Measuring adapter behaviour with a hand written script that re implements the extraction pipeline. This produced wrong figures that were committed to spec 0003 `rationale.md` and survived a full cross check before review round 3 caught them. Two divergences caused it: the replica concatenated both contributing files into one string while the shipped `_evidence_and_unresolved` extracts per file and sums (which matters because backtick pairing is naive, so the join changes pairing across the seam), and it ignored `spec` kind evidence so it under reported the resolved targets. Call the shipped API.

## Standing instructions

- Commit messages in this project leave out the `Co-Authored-By: Claude` trailer. Asked for directly, so do not add it back on later commits.
- When a shipped decision turns out to need correcting, amend the existing spec rather than writing a new numbered spec or a supersession, unless the decision itself genuinely changed. This project's own adapter reads these specs, so an extra spec or a supersession chain puts a shape in the corpus that later gets reported as decision history when no second decision was ever made. Record the correction and its evidence in that spec's `rationale.md`.
- Re run `/check review` after a batch of `/debug` fixes on this feature. Across this work two of four fixes introduced new regressions (a deleted record never restored, an unbalanced fence swallowing whole sections) and a later round caught wrong measurements in a spec; none of it was caught by the passing test suite, only by a fresh model review.
- Any mention count recorded against spec 0003 is a reading taken at a moment, not a constant. That spec describes the adapter, so editing it changes the adapter's own input: adding quoted examples while documenting the AC-6 rule moved the pre fix count from 3,611 to 4,748 with no code change. Re measure after any edit rather than trusting a figure already written down.
