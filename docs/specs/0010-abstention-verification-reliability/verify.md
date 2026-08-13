# Verify: Abstention verification reliability · spec 0010 · updated 2026-08-12

> **The checklist below is out of date as of 2026-08-12 and must not be run.** `/architect` revised AC-4, AC-6, AC-10, AC-11, and AC-12 after experiments 0001 and 0002. The output unit changed from the sub claim fragment to the whole sentence, so almost every local check here describes a mechanism the spec no longer specifies. Build plan task 10 rewrites this file against the revised contract. **The Live findings sections below are kept deliberately**: they are the measured evidence that drove the revision, and they stay as history.

_Steps derived from spec 0010 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones. The code landed in `/develop abstention verification reliability`. The live gate ran on the finished per sub claim build and does not pass: AC-2, AC-3, and both AC-9 provider assertion bars fail, for one reason recorded under Live findings._

## Local checks

The first implementation passed its earlier checks. The cross check changed the contract, so every local gate below must run again against the corrected behavior.

- [ ] Explicit fabrication and decomposition omission both emit verified fragments only, never the parent -> AC-1, AC-4
- [ ] Fragment ids and ordering are parent order, then provider sub claim order -> AC-4
- [ ] Whole containment, decomposition, entailment, and output use only available citations; missing ids remain trace only, and every sentence with a nonempty missing set records a `missing_chunk_refs` row whether or not it proceeds -> AC-8
- [ ] Containment narrows to matching available ids; entailment keeps all available ids in parent order -> AC-4, AC-8
- [ ] Genuine empty, rejected over cap, rejected duplicate, rejected whole lexical guard, individually dropped sub claims, and all unsupported accepted rows remain distinct in trace -> AC-6, AC-10, AC-11
- [ ] The per sub claim lexical matcher follows AC-11 exactly: the five stem rules (plain suffix, dropped `e`, repeated final character, `y` to `i`), the three character floor measured on the untransformed token, at most two added function word tokens per sub claim counted as instances, exact token equality for function words, and the closed function word set -> AC-11
- [ ] A violating sub claim is dropped while clean sub claims proceed; a response with no acceptable sub claim is rejected wholesale and writes no `dropped_sub_claims` rows; the whole response checks (empty, over cap, duplicate) run before the per sub claim guard; adversarial deletion and reordering tests document that it makes no semantic guarantee -> AC-6, AC-11
- [ ] A fully contained sentence skips decomposition, and no available evidence skips every provider -> AC-5, AC-8
- [ ] Decomposition and coverage schema failure gets one repair, then the correct provider failure at `claim_verification` -> AC-7, AC-12
- [ ] The canonical facet tuple is reused unchanged; coverage rows are complete and ordered; invalid facet or sentence references fail -> AC-12
- [ ] Query 4 diagnostic fixtures distinguish a merged facet (`facet_extraction`), separate facets with a wrongly covered decision (`coverage_directness`), and an uncovered decision with an answered result (`query_state`) using existing trace fields -> AC-2, AC-12
- [ ] No kept sentences creates deterministic uncovered rows without a coverage call -> AC-12
- [ ] Directness cases forbid reason as decision, cross sentence composition, unrelated text, and anaphoric fragments -> AC-4, AC-12
- [ ] Abstained public output has no sentences or citations, while trace keeps verification detail -> AC-4, AC-12
- [ ] `schema_version` stays 2 and all five additive fields resolve -> AC-10
- [ ] `uv run pytest tests/test_sub_claim_verification.py` passes -> focused suite
- [ ] `uv run pytest` passes -> unit quality gate
- [ ] `uv run pytest -m integration` passes -> integration quality gate
- [ ] Ruff, format, strict mypy, and build pass -> quality gate

## Live acceptance (run twice, two separate `--runs 3` batches)

Run against the real JobPilot corpus with live providers:

```bash
uv run --env-file .env decision-memory evaluate /Users/ghaly/Documents/Work/Personal/job_pilot --runs 3
```

- [ ] Batch 1: query 4 abstains 3 of 3 -> AC-2, AC-12 (2 of 3 on the 2026-08-12 re run)
- [ ] Batch 1: query 5 abstains 3 of 3 -> AC-3 (0 of 3 on the 2026-08-12 re run)
- [ ] Batch 2: query 4 abstains 3 of 3 -> AC-2, AC-12 (3 of 3 on the 2026-08-12 re run)
- [ ] Batch 2: query 5 abstains 3 of 3 -> AC-3 (0 of 3 on the 2026-08-12 re run)
- [ ] Both batches: query 4's fabricated decision sub claim is a row in `decomposed` with `entailment` unsupported and `kept` false, and the decision facet is uncovered -> AC-2 (the drop path is the entailment path, not `dropped_sub_claims`)
- [x] Batch 1 and batch 2: the incremental reingest assertion passes both batches -> AC-9 (2026-08-12 re run)
- [ ] Batch 1 and batch 2: the unverifiable claim assertion passes in at least 5 of the 6 runs -> AC-9 (3 of 6 on the 2026-08-12 re run)
- [ ] After the per sub claim lexical fix lands, the rationale summary assertion passes live in at least 5 of the 6 runs (restored by the broadened tolerance) -> AC-9 (2 of 6 on the 2026-08-12 re run)
- [ ] Query 3 abstention is the recorded generation quality gap, not an AC-9 failure; re run the live gate after the generation directness follow up -> AC-9 (deferred, see follow up)

**Live findings (2026-08-12, milestone 5, the whole response guard):**

Query 4 abstained 6 of 6 and query 5 abstained 6 of 6 on the build that rejected a decomposition response as a whole. The unverifiable claim and incremental reingest assertions passed in both batches. Query 3 abstained 0 of 6 and the rationale summary assertion abstained 0 of 6, with two distinct spec level causes, not a fixture level hiccup. The AC-9 expectation that the other fixtures would keep passing under the strict mechanisms did not hold, so AC-9 was revised by `/architect`.

- Query 3 abstains because strict directness coverage leaves a facet uncovered. The decomposition splits S1 into S1.1 ("still provisional", covers the provisional facet) and S1.2 ("the decision needs to be made for scope feature 1"), and the fixed directness rule refuses to cover the "not ratified" facet from a fragment that does not state it. Coverage cannot combine fragments, so the generated answer does not directly state every facet. This is the directness rule working as intended. AC-9 no longer requires query 3 to pass; the generation quality gap is enrolled as a follow up and the live gate reruns after it.
- The rationale summary assertion abstains because the whole response AC-11 lexical matcher rejected the decomposition of the long answer sentences (`rejected_decomposition ... disposition=lexical_guard`, counts 6 and 8) and discarded the clean sub claims along with the violators. AC-11 is revised to per sub claim rejection with the broadened tolerance; the rationale summary is re verified live after `/develop` implements that fix.

**Live findings (2026-08-12, build plan task 7, the per sub claim guard, two `--runs 3` batches):**

The per sub claim guard is built exactly as the revised AC-11 states it, and the unit suite, ruff, format, strict mypy, and the build all pass. The live gate does not: the two re run batches fail AC-2, AC-3, and both provider assertion bars of AC-9.

| fixture | batch 1 | batch 2 | total | bar | verdict |
|---|---|---|---|---|---|
| query 4 abstains | 2 of 3 | 3 of 3 | 5 of 6 | 6 of 6 | FAIL, AC-2 |
| query 5 abstains | 0 of 3 | 0 of 3 | 0 of 6 | 6 of 6 | FAIL, AC-3 |
| unverifiable claim | 1 of 3 | 2 of 3 | 3 of 6 | at least 5 of 6 | FAIL, AC-9 |
| rationale summary | 2 of 3 | 0 of 3 | 2 of 6 | at least 5 of 6 | FAIL, AC-9 |
| incremental reingest | pass | pass | both batches | both batches | PASS, AC-9 |
| query 3 | 0 of 3 | 0 of 3 | 0 of 6 | recorded gap | not an AC-9 bar |
| query 1 | 2 of 3 | 0 of 3 (failed state) | live hiccup | not a bar | not a signal |
| query 2 | 0 of 3 | 3 of 3 | 3 of 6 | feature 10 carry in | out of scope here |

The direction is the finding, not the numbers. Loosening the guard from a whole response verdict to a per sub claim one moved every abstention gate the wrong way: query 5 went from 6 of 6 abstaining to 0 of 6, the unverifiable claim from 5 of 6 and 6 of 6 down to 3 of 6, and query 4 from 6 of 6 to 5 of 6. The rationale summary, the one assertion the change was meant to restore, only reached 2 of 6, short of its own 5 of 6 bar.

The query 5 trace says why. Its answer sentence decomposes into eight sub claims; the guard drops S1.5, S1.6, and S1.7, and the remaining five all come back `entailment=supported` and kept:

```text
S1.1 The original approach was changed.                                    supported
S1.2 The critique found a gap in the safety reasoning.                     supported
S1.3 The critique suggested a more robust alternative for handling upload keys. supported
S1.4 The suggested alternative was adopted.                                supported
S1.8 The change avoided potential collisions.                              supported
dropped_sub_claim S1.5 (S1) disposition=lexical_guard
dropped_sub_claim S1.6 (S1) disposition=lexical_guard
dropped_sub_claim S1.7 (S1) disposition=lexical_guard
```

Coverage then covers the facets from those five and the query answers. Under the whole response guard the same three violators rejected the entire response, no sentence survived, the deterministic uncovered rows applied, and the query abstained. So query 5's 6 of 6 abstention was an artifact of the wholesale rejection, not a verdict that the evidence fails to support the answer. The same mechanism explains the unverifiable claim assertion. Query 4's one answering run is diagnosed by the AC-12 classifier as `coverage_directness`, which is the classifier working: separate facets, the decision facet wrongly covered.

This falsifies the load bearing assumption behind the revision, that per sub claim rejection keeps the safety property because each surviving sub claim is still individually verified. Individual verification does hold, and it is not enough: entailment says supported for vacuous or partial fragments such as "The original approach was changed", and strict coverage still accepts them. It also matches the 2026-08-12 `/debug` finding, that loosening the guard makes these queries answer more, not less.

This is an acceptance criteria decision for `/architect`, not a code patch here. Chasing the gate from the build would mean re tightening the guard, which re breaks the rationale summary, or weakening coverage, which re breaks query 4. Neither is a build time call. The per sub claim guard is committed as specified so the evidence is reproducible.

**Caveat:** AC-1 proves the weld fix deterministically. Query 4's live trace confirms the fabricated decision is dropped. Its 6 of 6 abstention gate tests the separate complete answer contract, including the uncovered decision facet. It is a smoke gate, not a measured rate. AC-9 is also a smoke check, since three runs cannot separate a real regression from fixture variance such as query 1 at 1 of 3.

## Acceptance-criteria coverage

- AC-1 covered by explicit fabrication and omission attack tests
- AC-2 covered by both live query 4 batches, including facet extraction, dropped fabrication, and uncovered decision facet (FAILS on the per sub claim guard, 5 of 6)
- AC-3 covered by live batch 1 and batch 2 query 5 (FAILS on the per sub claim guard, 0 of 6)
- AC-4 covered by fragment only output, stable identity, citation precision, directness, and abstention surface tests
- AC-5 covered by `test_verbatim_sentence_skips_decomposition_call`
- AC-6 covered by accepted, genuine empty, rejected, all unsupported, and debug render tests
- AC-7 covered by `test_decomposition_provider_failure_fails_the_query` and the validator tests
- AC-8 covered by the accepted context boundary and output citation tests
- AC-9 covered by the two live batches against its named bars; incremental reingest passes both batches, while the unverifiable claim (3 of 6) and rationale summary (2 of 6) assertions FAIL their 5 of 6 bar on the per sub claim guard; query 3 is the recorded generation quality gap
- AC-10 covered by `test_schema_version_stays_two_and_trace_fields_resolve`
- AC-11 covered by the five stem rule cases, the character floor, the function word bound and closed set, cap, duplicate, whole response check ordering, per sub claim drop versus wholesale rejection, and adversarial semantic limitation tests
- AC-12 covered by canonical facet reuse, empty kept set, prompt, complete row validation, directness fixtures, diagnostic classification, and live query 4 checks

## Baseline (2026-08-12, before this feature)

Query 4 answered 3 of 3, query 5 answered 3 of 3, query 2 passed 3 of 3 with `DM-0004` cited, query 1 went 1 of 3 on a provider failed state. Compare against the acceptance runs above.

## Diagnostic after the first implementation

Three answering query 4 runs split S1 cleanly. The fabricated decision sub claim was unsupported and dropped every time. Coverage still marked the decision facet covered from grounded reason fragments. Other runs abstained only because the near subset check rejected harmless inflection or grammar changes. This is why coverage is fixed before the near subset tolerance.

## Cross check correction

The first implementation restored a decomposed parent when every returned sub claim was kept. A provider could omit the fabricated clause, return only grounded claims, and make that rule restore the fabrication. The corrected contract never emits a decomposed parent. The omission attack is now a required deterministic regression test.
