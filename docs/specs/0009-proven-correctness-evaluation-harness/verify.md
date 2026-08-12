# Verify: Proven correctness (evaluation harness) · spec 0009 · updated 2026-08-12

_Steps derived from the feature 11 scope row and specs 0001, 0007, and 0008. The five defining queries and two assertions were already fully specified; this feature built the harness that runs them. `/check verify` runs these; `/test` locks the durable ones._

## Commands

Run against the real JobPilot corpus with live providers:

```bash
uv run --env-file .env decision-memory evaluate /Users/ghaly/Documents/Work/Personal/job_pilot
```

- [ ] `evaluate` runs all eight fixtures in fixed order and prints PASS or FAIL per fixture, plus `result: N passed, M failed` and `final: passed|failed` -> harness report contract
- [ ] `evaluate` exit code is `1` when any fixture fails and `0` only when all pass -> exit contract
- [ ] `evaluate --runs 3` shows the per fixture pass rate (`x/3 runs passed`), not just pass or fail -> spec 0008 Follow-up 9
- [ ] `evaluate` needs `OPENAI_API_KEY` and fails loudly if it is missing -> fail loudly rule
- [ ] `evaluate /nonexistent` exits `3` -> missing corpus

## Fixture expectations (each maps to a Done-when or spec item)

- [ ] `query-1-private-beta-gate` PASS: answered, cites `DM-0012`, and at least one citation carries a `decision.alternatives[*]` value path -> query 1 oracle (spec 0007 AC-11, spec 0008 Follow-up 5)
- [ ] `query-2-resume-generation` PASS: answered, cites both `DM-0004` and `DM-0019` -> query 2 oracle (spec 0008)
- [ ] `query-3-provisional` PASS: answered, cites every proposed record (derived from the records, currently `DM-0015`) -> Done-when query 3
- [ ] `query-4-db-clients` reports legibly: must abstain (its evidence is outside the adapted corpus); currently FAIL, answering with `DM-0007`/`DM-0008` -> Done-when query 4, carried from feature 10
- [ ] `query-5-uploaded-files` reports legibly: must abstain in v1 (supersession not mapped); currently FAIL, answering with `DM-0002` -> Done-when query 5, carried from feature 10
- [ ] `assertion-rationale-summary` PASS: answered, cites `DM-0006` with a `rationale_summary` value path (the answer cannot come from the why list) -> assertion A (mvp.md)
- [ ] `assertion-unverifiable-claim` PASS: abstains on a question whose correct answer would be a fabricated specific fact -> spec 0001 fixture
- [ ] `assertion-incremental-reingest` PASS: editing a copy of `DM-0006`'s `rationale.md`, re adapting, and re ingesting changes the record's active chunk ids -> assertion B (mvp.md multi-file fingerprint rule)

## Regression lock (found and fixed by the harness)

- [ ] `--value-path 'context.problem'` on a real store filters to real value paths instead of returning `not enough evidence` -> the `active_chunks` value_path/fingerprint column swap fix (unit locked in `test_store_format.py::test_active_chunks_keeps_value_path_and_fingerprint_separate`)

## Acceptance-criteria coverage

- query 1 -> `query-1-private-beta-gate` · query 2 -> `query-2-resume-generation` · query 3 -> `query-3-provisional` · query 4 -> `query-4-db-clients` · query 5 -> `query-5-uploaded-files` · rationale summary assertion -> `assertion-rationale-summary` · unverifiable claim fixture -> `assertion-unverifiable-claim` · incremental re-ingest assertion -> `assertion-incremental-reingest`

## Known state (2026-08-12)

`query-4` and `query-5` are expected FAILs, the two Feature-11 carry-ins from feature 10's live gates; the harness measures and reports them, it does not patch them. Everything else passes live after the `active_chunks` value_path fix.
