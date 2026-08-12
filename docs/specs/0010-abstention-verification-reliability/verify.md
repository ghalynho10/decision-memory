# Verify: Abstention verification reliability · spec 0010 · updated 2026-08-12

_Steps derived from spec 0010 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones. The code landed in `/develop abstention verification reliability`; the live gates are the remaining acceptance work._

## Local checks (deterministic, already implemented and passing)

- [x] `uv run pytest tests/test_sub_claim_verification.py` → the whole deterministic suite -> AC-1, AC-4, AC-5, AC-6, AC-7, AC-8, AC-10, AC-11
- [x] A synthetic fused clause splits into a verbatim sub claim (kept, narrowed) and an invented sub claim (dropped), and coverage decides -> AC-1, AC-4
- [x] Two sub claims verbatim in different chunks each cite only its own chunk; when every sub claim is kept the original sentence is re emitted unchanged -> AC-4
- [x] An entailment grounded sub claim keeps the parent's full cited set -> AC-4
- [x] A fully verbatim sentence never pays a decomposition call -> AC-5
- [x] The trace shows the split, each sub claim text and verdict, and distinguishes an empty decomposition from sub claims that were all unsupported -> AC-6
- [x] A decomposition introducing content absent from the parent, or over the cap of 8, is discarded as an empty decomposition -> AC-6, AC-11
- [x] A provider failure during decomposition fails the query with `provider.decompose`; a malformed decomposition payload is rejected at the provider boundary -> AC-7
- [x] A sentence citing no accepted chunk is dropped and counted; partial missing verifies against the present subset -> AC-8
- [x] `schema_version` stays 2 and the additive trace fields resolve -> AC-10
- [x] `uv run pytest` unit suite green -> quality gate
- [x] `uv run pytest -m integration` green -> quality gate (live tests updated for the new decompose dependency)
- [x] Ruff, format, strict mypy, and build clean -> quality gate

## Live acceptance (run twice, two separate `--runs 3` batches)

Run against the real JobPilot corpus with live providers:

```bash
uv run --env-file .env decision-memory evaluate /Users/ghaly/Documents/Work/Personal/job_pilot --runs 3
```

- [ ] Batch 1: query 4 abstains 3 of 3 -> AC-2
- [ ] Batch 1: query 5 abstains 3 of 3 -> AC-3
- [ ] Batch 2: query 4 abstains 3 of 3 -> AC-2
- [ ] Batch 2: query 5 abstains 3 of 3 -> AC-3
- [ ] The other fixtures do not newly fail in the same two batches: query 3, assertion rationale summary, assertion unverifiable claim, and assertion incremental reingest -> AC-9

**Caveat:** 6 of 6 is strong evidence the weld no longer passes, not a measured abstention rate. A true rate needs more runs. Likewise, AC-9 is a smoke check over two `--runs 3` batches, not a rate comparison; three runs cannot separate a real regression from the fixture level variance the baseline itself shows (query 1 at 1 of 3).

## Acceptance-criteria coverage

- AC-1 covered by the fused clause test (`test_fused_clause_is_split_and_invented_decision_dropped`)
- AC-2 covered by live batch 1 and batch 2 query 4
- AC-3 covered by live batch 1 and batch 2 query 5
- AC-4 covered by the narrowing, breadth, and all kept re emit tests
- AC-5 covered by `test_verbatim_sentence_skips_decomposition_call`
- AC-6 covered by the trace, empty vs all unsupported, under split, and debug render tests
- AC-7 covered by `test_decomposition_provider_failure_fails_the_query` and the validator tests
- AC-8 covered by the full and partial missing ref tests
- AC-9 covered by the two live batches
- AC-10 covered by `test_schema_version_stays_two_and_trace_fields_resolve`
- AC-11 covered by the invented content and over cap discard tests

## Baseline (2026-08-12, before this feature)

Query 4 answered 3 of 3, query 5 answered 3 of 3, query 2 passed 3 of 3 with `DM-0004` cited, query 1 went 1 of 3 on a provider failed state. Compare against the acceptance runs above.
