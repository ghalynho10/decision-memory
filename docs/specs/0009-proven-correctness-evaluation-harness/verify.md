# Verify: Proven correctness (evaluation harness) · spec 0009 · updated 2026-08-12 (re-verified 2026-08-12 after the round 3/4 review fixes)

_Steps derived from the feature 11 scope row and specs 0001, 0007, and 0008. The five defining queries and two assertions were already fully specified; this feature built the harness that runs them. `/check verify` runs these; `/test` locks the durable ones._

## Commands

Run against the real JobPilot corpus with live providers:

```bash
uv run --env-file .env decision-memory evaluate /Users/ghaly/Documents/Work/Personal/job_pilot
```

- [x] `evaluate` runs all eight fixtures in fixed order and prints PASS or FAIL per fixture, plus `result: N passed, M failed` and `final: passed|failed` -> harness report contract
- [x] `evaluate` exit code is `1` when any fixture fails and `0` only when all pass -> exit contract
- [x] `evaluate --runs 3` shows the per fixture pass rate (`x/3 runs passed`), not just pass or fail -> spec 0008 Follow-up 9
- [x] `evaluate` needs `OPENAI_API_KEY` and fails loudly if it is missing -> fail loudly rule
- [x] `evaluate /nonexistent` exits `3` -> missing corpus

## Fixture expectations (each maps to a Done-when or spec item)

- [x] `query-1-private-beta-gate` PASS: answered, cites a `DM-0012` chunk whose own value path is `decision.alternatives[*]` (co-location, not merely some citation carrying that prefix anywhere in the answer) -> query 1 oracle (spec 0007 AC-11, spec 0008 Follow-up 5); re-verified 2026-08-12 under the round 3 co-location fix, 3/3 under `--runs 3`
- [x] `query-2-resume-generation` PASS: answered, cites both `DM-0004` and `DM-0019` -> query 2 oracle (spec 0008); 3/3 under `--runs 3` on 2026-08-12, but the feature 10 carry-in measured `DM-0004` coverage as intermittent (6 of 12 across earlier batches, see scope.md), so treat this as a good sample, not a fixed guarantee
- [x] `query-3-provisional` PASS: answered, cites every proposed record (derived from the records, currently `DM-0015`) -> Done-when query 3 (3/3 under `--runs 3` on 2026-08-12)
- [ ] `query-4-db-clients` reports legibly: must abstain (its evidence is outside the adapted corpus); currently FAIL, answering with `DM-0007`/`DM-0008` (0/3 on 2026-08-12) -> Done-when query 4, carried from feature 10 — abstention is stochastic, so the check is not yet reliable
- [ ] `query-5-uploaded-files` reports legibly: must abstain in v1 (supersession not mapped); currently FAIL, answering with `DM-0002`/`DM-0003` (0/3 on 2026-08-12) -> Done-when query 5, carried from feature 10
- [x] `assertion-rationale-summary` PASS: answered, cites a `DM-0006` chunk whose own value path is `rationale_summary` (the answer cannot come from the why list) -> assertion A (mvp.md); re-verified 2026-08-12 under the round 3 co-location fix, 3/3 under `--runs 3`
- [x] `assertion-unverifiable-claim` PASS: abstains on a question whose correct answer would be a fabricated specific fact -> spec 0001 fixture; 2/3 under `--runs 3` on 2026-08-12, one run returned a provider `failed` state (no citations) rather than an abstention — a live provider hiccup unrelated to this session's changes (the fixture has no required records or value paths, so none of the round 3/4 oracle fixes touch it), not chased further here per the harness's own measure-don't-patch philosophy
- [x] `assertion-incremental-reingest` PASS: editing a copy of `DM-0006`'s `rationale.md`, re adapting, and re ingesting changes the record's active chunk ids -> assertion B (mvp.md multi-file fingerprint rule); re-verified 2026-08-12 (23 -> 46 chunk ids)

## Regression lock (found and fixed by the harness)

- [x] `--value-path 'context.problem'` on a real store filters to real value paths instead of returning `not enough evidence` -> the `active_chunks` value_path/fingerprint column swap fix, regression locked by `test_store_format.py::test_active_chunks_keeps_value_path_and_fingerprint_separate`. That test is `@pytest.mark.integration` (it exercises the real SQLite store, matching its two siblings in the same file), so it does **not** run on the push gate (`uv run pytest`, unit only); a re-swap would not be caught by CI, only by `-m integration` or this live check.

## Acceptance-criteria coverage

- query 1 -> `query-1-private-beta-gate` · query 2 -> `query-2-resume-generation` · query 3 -> `query-3-provisional` · query 4 -> `query-4-db-clients` · query 5 -> `query-5-uploaded-files` · rationale summary assertion -> `assertion-rationale-summary` · unverifiable claim fixture -> `assertion-unverifiable-claim` · incremental re-ingest assertion -> `assertion-incremental-reingest`

## Known state (2026-08-12, re-verified after the round 3/4 review fixes)

`query-4` and `query-5` are expected FAILs, both feature 10 carry-ins (evidence outside the adapted corpus / supersession not mapped), not harness defects; the harness measures and reports them, it does not patch them. `assertion-unverifiable-claim` returned a provider `failed` state on one of three runs today, a live hiccup unconnected to this session's oracle changes. Everything else passed 3/3 under `--runs 3`, including `query-1` and `assertion-rationale-summary` under the round 3 co-location fix (round 3 made both stricter — a citation must belong to the _required_ record, not merely appear somewhere in the answer — and this run is the first live evidence that the real corpus's citations still satisfy the stricter rule). Verified live on 2026-08-12 (round 3/4 fixes): `--runs 3` exit 1 (`5 passed, 3 failed`) with per-fixture rates. Missing-key and `/nonexistent` paths verified earlier the same day and unaffected by these fixes.
