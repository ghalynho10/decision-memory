# Verify: Abstention verification reliability · spec 0010 · updated 2026-08-12

_Steps derived from spec 0010 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones. The code landed in `/develop abstention verification reliability`; the live gates are the remaining acceptance work._

## Local checks

The first implementation passed its earlier checks. The cross check changed the contract, so every local gate below must run again against the corrected behavior.

- [ ] Explicit fabrication and decomposition omission both emit verified fragments only, never the parent -> AC-1, AC-4
- [ ] Fragment ids and ordering are parent order, then provider sub claim order -> AC-4
- [ ] Whole containment, decomposition, entailment, and output use only available citations; missing ids remain trace only -> AC-8
- [ ] Containment narrows to matching available ids; entailment keeps all available ids in parent order -> AC-4, AC-8
- [ ] Genuine empty, rejected over cap, rejected duplicate, rejected lexical guard, and all unsupported accepted rows remain distinct in trace -> AC-6, AC-11
- [ ] The lexical multiset matcher follows the exact normalization and suffix rules; adversarial deletion and reordering tests document that it makes no semantic guarantee -> AC-11
- [ ] A fully contained sentence skips decomposition, and no available evidence skips every provider -> AC-5, AC-8
- [ ] Decomposition and coverage schema failure gets one repair, then the correct provider failure at `claim_verification` -> AC-7, AC-12
- [ ] The canonical facet tuple is reused unchanged; coverage rows are complete and ordered; invalid facet or sentence references fail -> AC-12
- [ ] Query 4 diagnostic fixtures distinguish a merged facet (`facet_extraction`), separate facets with a wrongly covered decision (`coverage_directness`), and an uncovered decision with an answered result (`query_state`) using existing trace fields -> AC-2, AC-12
- [ ] No kept sentences creates deterministic uncovered rows without a coverage call -> AC-12
- [ ] Directness cases forbid reason as decision, cross sentence composition, unrelated text, and anaphoric fragments -> AC-4, AC-12
- [ ] Abstained public output has no sentences or citations, while trace keeps verification detail -> AC-4, AC-12
- [ ] `schema_version` stays 2 and all four additive fields resolve -> AC-10
- [ ] `uv run pytest tests/test_sub_claim_verification.py` passes -> focused suite
- [ ] `uv run pytest` passes -> unit quality gate
- [ ] `uv run pytest -m integration` passes -> integration quality gate
- [ ] Ruff, format, strict mypy, and build pass -> quality gate

## Live acceptance (run twice, two separate `--runs 3` batches)

Run against the real JobPilot corpus with live providers:

```bash
uv run --env-file .env decision-memory evaluate /Users/ghaly/Documents/Work/Personal/job_pilot --runs 3
```

- [x] Batch 1: query 4 abstains 3 of 3 -> AC-2, AC-12 (2026-08-12)
- [x] Batch 1: query 5 abstains 3 of 3 -> AC-3 (2026-08-12)
- [x] Batch 2: query 4 abstains 3 of 3 -> AC-2, AC-12 (2026-08-12)
- [x] Batch 2: query 5 abstains 3 of 3 -> AC-3 (2026-08-12)
- [ ] The other fixtures do not newly fail in the same two batches: query 3, assertion rationale summary, assertion unverifiable claim, and assertion incremental reingest -> AC-9 (FAILS: query 3 and the rationale summary assertion abstain 0 of 6, see Live findings)

**Live findings (2026-08-12, milestone 5, two `--runs 3` batches):**

Query 4 abstains 6 of 6 and query 5 abstains 6 of 6, so AC-2 and AC-3 pass: the fused fabrication no longer survives, and the decision facet stays uncovered. AC-9 does not pass: query 3 and the rationale summary assertion abstain in all six runs each, and their traces show two distinct spec level causes, not a fixture level hiccup.

- Query 3 abstains because strict directness coverage leaves a facet uncovered. The decomposition splits S1 into S1.1 ("still provisional", covers the provisional facet) and S1.2 ("the decision needs to be made for scope feature 1"), and the fixed directness rule refuses to cover the "not ratified" facet from a fragment that does not state it. Coverage cannot combine fragments, so the generated answer does not directly state every facet.
- The rationale summary assertion abstains because the AC-11 lexical multiset matcher rejects the decomposition of the long answer sentences (`rejected_decomposition ... disposition=lexical_guard`, counts 6 and 8), so no kept sentences remain and the deterministic uncovered rows apply.

Both are the spec's own strict mechanisms (strict coverage, exact lexical guard) working as written; the AC-9 expectation that the other fixtures would keep passing does not hold under them. Resolving this is an acceptance criteria decision for `/architect`, not a code patch here: weakening either guard would undo the query 4 and query 5 fix.

**Caveat:** AC-1 proves the weld fix deterministically. Query 4's live trace confirms the fabricated decision is dropped. Its 6 of 6 abstention gate tests the separate complete answer contract, including the uncovered decision facet. It is a smoke gate, not a measured rate. AC-9 is also a smoke check, since three runs cannot separate a real regression from fixture variance such as query 1 at 1 of 3.

## Acceptance-criteria coverage

- AC-1 covered by explicit fabrication and omission attack tests
- AC-2 covered by both live query 4 batches, including facet extraction, dropped fabrication, and uncovered decision facet
- AC-3 covered by live batch 1 and batch 2 query 5
- AC-4 covered by fragment only output, stable identity, citation precision, directness, and abstention surface tests
- AC-5 covered by `test_verbatim_sentence_skips_decomposition_call`
- AC-6 covered by accepted, genuine empty, rejected, all unsupported, and debug render tests
- AC-7 covered by `test_decomposition_provider_failure_fails_the_query` and the validator tests
- AC-8 covered by the accepted context boundary and output citation tests
- AC-9 covered by the two live batches
- AC-10 covered by `test_schema_version_stays_two_and_trace_fields_resolve`
- AC-11 covered by exact matcher, cap, duplicate, lexical rejection, and adversarial semantic limitation tests
- AC-12 covered by canonical facet reuse, empty kept set, prompt, complete row validation, directness fixtures, diagnostic classification, and live query 4 checks

## Baseline (2026-08-12, before this feature)

Query 4 answered 3 of 3, query 5 answered 3 of 3, query 2 passed 3 of 3 with `DM-0004` cited, query 1 went 1 of 3 on a provider failed state. Compare against the acceptance runs above.

## Diagnostic after the first implementation

Three answering query 4 runs split S1 cleanly. The fabricated decision sub claim was unsupported and dropped every time. Coverage still marked the decision facet covered from grounded reason fragments. Other runs abstained only because the near subset check rejected harmless inflection or grammar changes. This is why coverage is fixed before the near subset tolerance.

## Cross check correction

The first implementation restored a decomposed parent when every returned sub claim was kept. A provider could omit the fabricated clause, return only grounded claims, and make that rule restore the fabrication. The corrected contract never emits a decomposed parent. The omission attack is now a required deterministic regression test.
