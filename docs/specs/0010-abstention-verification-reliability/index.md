# 0010. Abstention verification reliability

**Date**: 2026-08-12
**Status**: In Progress

## Summary

The query pipeline verifies whole sentences, but the failure is finer than a sentence: a generated sentence can weld an invented decision to a clause copied verbatim from real evidence, and both verification tiers accept it. This spec changes the verification unit to the sub claim. A sentence that is not verbatim in its cited chunks is split into atomic sub claims, and each sub claim is verified alone, so the borrowed clause can no longer hide the invented part. The change makes query 4 and query 5 abstain honestly, and it records the coverage gap for query 2 as a follow up instead of folding it into this feature.

## Requirements

**User stories**:
- As a user of the query command, I want an honest abstention when the evidence does not support a claimed decision, so that I am not shown a cited answer that mixes a fabricated decision with a real borrowed clause.
- As an operator, I want the debug trace to show how each sentence was split and why each piece survived or was dropped, so that a bad split is visible rather than silent.

**Acceptance criteria** (the contract, each IDed and independently checkable):
- **AC-1**: A draft sentence that welds a fabricated decision to a verbatim borrowed clause is rejected. A deterministic unit test with a synthetic fused clause proves the fabricated sub claim is dropped and never appears in the answer.
- **AC-2**: Live gate against the real JobPilot corpus: query 4 abstains in every run of the acceptance sample, taken as two separate `--runs 3` batches, 6 of 6 total. This is strong evidence the weld no longer passes, not a measured abstention rate.
- **AC-3**: Live gate against the real JobPilot corpus: query 5 abstains in every run of the same two batches, 6 of 6 total. Same caveat as AC-2.
- **AC-4**: Grounded sub claims survive and become answer sentences, fabricated sub claims are dropped, and the existing coverage check then decides answered versus abstained. A deterministic unit test proves both halves.
- **AC-5**: A sentence whose whole text is verbatim in a cited chunk is never decomposed and never pays the decomposition call. A deterministic unit test proves the cost bound.
- **AC-6**: The debug trace shows the decomposition itself, the sub claim texts, plus each sub claim's verdict, and it distinguishes an empty decomposition from sub claims that were all unsupported. A deterministic unit test proves the distinction is visible.
- **AC-7**: A provider failure during the decomposition call returns a failed query result with a provider failure trace, consistent with the existing entailment and coverage failures. A test proves the failure contract.
- **AC-8**: A sub claim whose parent cited no chunk present in the accepted context is never supported, it is verified against empty evidence and dropped, and the trace records the missing chunk references so the signal is countable. A deterministic unit test proves both the drop and the trace.
- **AC-9**: The change does not newly fail the other live fixtures, checked as a smoke gate, not a rate comparison: three runs cannot separate a real regression from the fixture level variance the fresh baseline itself showed (query 1 went 1 of 3 on a provider hiccup with no code change involved). Query 3, the rationale summary assertion, the unverifiable claim assertion, and the incremental reingest assertion still pass in the same two `--runs 3` batches used for AC-2 and AC-3. Query 1's occasional provider failed state is a live hiccup, not a signal to compare against.
- **AC-10**: `schema_version` stays 2. The trace addition is additive and named fields still resolve. A test proves the result schema is unchanged.
- **AC-11**: A decomposition response that introduces content not present in the parent sentence, or that returns more than 8 sub claims (a sanity bound to catch a runaway response, not a value tuned against data), is discarded and treated as an empty decomposition, never verified as written. A deterministic unit test proves the discard and that it lands in the same trace path as AC-6's empty decomposition signal.

## Decision

**Chosen option**: Option 1: Sub claim decomposition with per sub claim verification.

The verification unit becomes the sub claim. A sentence whose whole normalized text is a substring of one of its cited chunks keeps today's path untouched. Any other sentence is decomposed by a structured model call on `gpt-4o-mini` into atomic sub claims. The decomposition call is contract bound: each returned sub claim must be a near-subset of the parent sentence's own tokens (no new facts), capped at 8 sub claims; a response that violates either rule is discarded and treated as an empty decomposition (AC-11). Each surviving sub claim starts from the parent sentence's cited chunk ids (the model is never allowed to assign or redirect citations) and is verified alone, deterministic containment first, then entailment for the rest, where grounded means `contained or entailment == "supported"`, the existing binary verdict with no separate threshold. A kept sub claim's citations are narrowed only where the pipeline has per-chunk precision: a sub claim grounded by containment is checked against each cited chunk individually (not only as an `any` across the set, as whole sentence containment does today) and narrows to the specific chunk(s) whose text contains it. A sub claim grounded by entailment keeps the parent sentence's full cited set, because `entail_verdict` (spec 0007, AC-15) verifies against the joined evidence of all cited chunks and returns one supported/reason pair with no per-chunk attribution; asking it to name a supporting chunk would be a change to an existing, already relied on contract, not something this spec makes silently. This asymmetry is a stated limitation, not invented precision. When every sub claim of a decomposed sentence is kept, the original sentence text and citations are re-emitted unchanged instead of the fragments, so a fully grounded sentence keeps its original prose. The relevance floor stays out of scope and the coverage direction for query 2 is a follow up, not this feature.

## Feature design

**Data model sketch**:

New entity, the sub claim, held only in the verification trace, no persistence:

- `sub_claim_id`: str, `f"{sentence_id}.{i+1}"`, 1 based over the decomposition response's returned order, assigned after dropping any normalized duplicate sub claim texts
- `sentence_id`: str, the parent DraftSentence
- `text`: str, the atomic claim
- `contained`: bool, whole sub claim verbatim in a cited chunk
- `entailment`: str, one of `skipped` (contained, no model call), `supported`, `unsupported`
- `reason`: str, the entailment reason, empty when skipped
- `kept`: bool, whether it survives
- `citations`: tuple of chunk ids. A containment grounded sub claim narrows to the specific chunk(s) whose text contains it. An entailment grounded sub claim keeps the parent sentence's full cited set, since `entail_verdict` has no per-chunk attribution to narrow from

`VerificationTrace` gains three additive fields:

- `decomposed`: tuple of sub claim rows, only for sentences that were decomposed
- `empty_decompositions`: tuple of sentence ids whose decomposition returned zero sub claims, kept distinct from all unsupported
- `missing_chunk_refs`: tuple of (sentence_id, missing chunk ids), the upstream signal when generation cited chunks that retrieval did not surface

**State transitions** (verification pipeline):

sentence with whole containment passing is kept, never decomposed; sentence with whole containment failing goes to decomposition; the decomposition response is validated against the contract (each sub claim a near-subset of the parent sentence's own tokens, no new facts, at most 8 sub claims) before anything else runs, a violation is discarded and treated as an empty decomposition; each surviving sub claim gets containment then entailment; grounded sub claims are kept; a containment grounded sub claim's citations narrow to the specific chunk(s) that contained it, an entailment grounded sub claim keeps the parent's full cited set; the rest are dropped; if every sub claim of a sentence is kept, the original sentence text and citations are re-emitted unchanged instead of the fragments; the coverage check runs over the kept units and decides answered or abstained.

**API surface**:

No new command, no new flag, no new endpoint. The debug trace and the JSON output gain the three additive trace fields above. Top level `QueryResult` is unchanged, `schema_version` stays 2.

| Surface | Change |
|---|---|
| `query --debug` | gains a Sub claims section listing each decomposed sentence, its sub claim texts, verdicts, and the two signals |
| JSON `QueryResult.trace.verification` | gains `decomposed`, `empty_decompositions`, `missing_chunk_refs` |

**Value sourcing**:

| Action | Value produced or displayed | Source |
|---|---|---|
| decompose sentence | sub claim texts | returned by the decomposition call on `gpt-4o-mini`, fixed model, capped at 8 sub claims |
| contract check | pass or discard | deterministic near-subset token check of each returned sub claim against the parent sentence's own text; a violation or an over-cap response is discarded and folds into the empty decomposition signal |
| per sub claim containment | contained bool, matching chunk ids | deterministic containment checked against each of the parent sentence's cited chunks individually, the same normalizer whole sentence containment already uses; unlike the whole sentence `any(...)` check, each matching chunk id is kept |
| per sub claim entailment | supported bool, reason | entail verdict call, only when containment failed; the existing binary verdict against the joined evidence of all cited chunks, no per-chunk attribution, no separate threshold |
| kept flag | kept bool | `contained or entailment == "supported"` |
| kept sub claim citations | narrowed or full chunk ids | for containment: the specific matching chunk id(s); for entailment: the parent sentence's full cited set, since entailment names no supporting chunk |
| answer sentences | kept sub claims, or the original sentence | kept sub claims become AnswerSentence fragments with their narrowed citations; when every sub claim of a sentence is kept, the original sentence text and citations are re-emitted unchanged instead |
| empty decomposition signal | sentence ids | decomposition call returned an empty list, or a response the contract check discarded |
| missing chunk ref signal | sentence id, missing ids | parent sentence chunk ids minus the ids present in the accepted context; when only some of a sentence's chunk ids are missing, its sub claims are verified against the present subset, and the empty evidence rule applies only once that subset is itself empty |

**Key invariants**:
- Sub claims always start from the parent sentence's chunk ids; the model is never allowed to assign or redirect citations. Post verification, the engine narrows a containment grounded sub claim's citations to the specific matching chunk(s), deterministically, from what containment already established. An entailment grounded sub claim keeps the parent's full cited set; `entail_verdict` verifies against the joined evidence of all cited chunks and returns no per-chunk attribution, so there is nothing to narrow from without changing that call's contract, which this spec does not do.
- A decomposition response that introduces content absent from the parent sentence, or that returns more than 8 sub claims, is discarded and treated as an empty decomposition, never verified as written.
- Decomposition runs only for sentences that failed whole containment.
- A sub claim verified against empty evidence is never supported; when only part of a sentence's chunk ids are missing, its sub claims are verified against the present subset first, and the empty evidence rule applies only once that subset is empty.
- Grounded is `contained or entailment == "supported"`, the existing binary verdict; there is no separate acceptance threshold.
- When every sub claim of a decomposed sentence is kept, the original sentence text and citations are re-emitted unchanged instead of the fragments.
- A provider failure in the decomposition call fails the query, matching entailment and coverage. A malformed or unparseable decomposition response is treated the same way, a provider failure, with no retry.
- `schema_version` stays 2; the trace fields are additive.

**Security model**:

No new surface. The decomposition call sends the candidate sentence and the parent's cited chunk texts to the existing provider, the same data entailment already sends.

**Configuration required**:

None. The decomposition model is fixed to `gpt-4o-mini`, the same model entailment and coverage use. There is no acceptance threshold to configure: grounded reuses entailment's existing binary verdict. The sub claim cap (8, a sanity bound against a runaway response, not a value tuned against data) and the contract's near-subset rule are spec constants, not settings.

**Critical test scenarios**:
- Happy path: a synthetic sentence with a verbatim borrowed clause and an invented decision splits into two sub claims; the borrowed one is kept via containment and its citations narrow to the specific chunk that contains it, the invented one is dropped, coverage decides the outcome, verifies **AC-1**, **AC-4**
- Citation narrowing (containment): two sub claims of one sentence are each verbatim in a different one of the parent's cited chunks; each kept sub claim cites only its own matching chunk, never the union of the parent's cited set, verifies **AC-4**
- Citation breadth (entailment): a sub claim is grounded by entailment, not containment; it keeps the parent sentence's full cited set rather than a narrowed one, since entailment names no specific supporting chunk, verifies **AC-4**
- All kept re-emit: every sub claim of a decomposed sentence is grounded; the original sentence text and citations are re-emitted unchanged rather than the fragments, verifies **AC-4**
- Contract guardrail: the decomposition call returns a sub claim containing content absent from the parent sentence (or more than 8 sub claims); the response is discarded and the trace records it as an empty decomposition, verifies **AC-6**, **AC-11**
- Under split visibility: the decomposition call returns exactly one sub claim equal to the whole sentence; the trace records a single sub claim so the under split is visible rather than silent, verifies **AC-6**
- Cost bound: a fully verbatim sentence is kept without any decomposition call, verifies **AC-5**
- Failure case: the decomposition call raises, the query returns a failed result with a provider failure trace, verifies **AC-7**
- Edge case: decomposition returns zero sub claims, the sentence is removed and the trace records the empty decomposition distinctly from all unsupported, verifies **AC-6**
- Edge case: the parent cited no chunk in the accepted context, the sub claim is dropped and the trace records the missing refs, verifies **AC-8**
- Edge case: only part of the parent's chunk ids are missing from the accepted context, the sub claim is verified against the present subset rather than dropped outright, verifies **AC-8**
- Live gate: two `--runs 3` batches of `evaluate` against the real corpus, query 4 and query 5 abstain 6 of 6, verifies **AC-2**, **AC-3**, **AC-9**

## Build plan

Ordered by the Skateboard approach: the smallest usable whole that closes the weld first, then the transparency, then the regression locks, then the live acceptance.

1. Add the sub claim DTOs and the decomposition provider call, `decompose_sentence`, in `openai_generation.py`, fixed to `gpt-4o-mini` and capped at 8 sub claims, structured like the existing verdict calls, satisfies **AC-6**, **AC-7**, **AC-11**
2. Add the contract check: a deterministic near-subset token validation of each returned sub claim against the parent sentence's text, plus the cap check; a violation discards the response into the empty decomposition path, satisfies **AC-11**
3. Wire the sub claim verification stage into `query.py`: decompose non verbatim sentences, verify each sub claim (containment checked per chunk, then entailment for the rest), narrow a containment grounded sub claim's citations to its specific matching chunk(s) while an entailment grounded sub claim keeps the parent's full set, re-emit the original sentence when every sub claim of it is kept, feed the existing coverage check, record the empty decomposition and missing chunk ref signals (verifying against the present subset when only part of a sentence's chunk ids are missing), satisfies **AC-1**, **AC-4**, **AC-5**, **AC-6**, **AC-8**
4. Extend `VerificationTrace` in `dto.py` and the debug rendering in `cli.py` with the three additive fields, keeping `schema_version` 2, satisfies **AC-6**, **AC-10**
5. Add the deterministic unit tests: synthetic fused clause, citation narrowing, all kept re-emit, contract guardrail, under split visibility, grounded sub claims survive, verbatim sentences skip, empty decomposition, absent chunks (full and partial), malformed decomposition response, schema unchanged, satisfies **AC-1**, **AC-4**, **AC-5**, **AC-6**, **AC-7**, **AC-8**, **AC-10**, **AC-11**
6. Write `verify.md`, then run `/check verify` and `/test`, satisfies **AC-1** to **AC-11**
7. Live acceptance: run `evaluate --runs 3` twice against the real JobPilot corpus, confirm query 4 and query 5 abstain 6 of 6 and the other fixtures do not newly fail, satisfies **AC-2**, **AC-3**, **AC-9**

## Consequences

**Positive**:
- The fused clause fabrication can no longer hide inside a sentence; query 4 and query 5 can abstain honestly.
- The verification unit now matches the attack surface, atomic claims instead of whole sentences.
- Cost is bounded: only non verbatim sentences pay the decomposition call.
- The trace shows the split itself, so a bad split is visible, and the empty and missing signals point at upstream problems.

**Negative / tradeoffs**:
- One more provider call per non verbatim sentence adds latency and cost to those queries; a sentence that decomposes into K sub claims that all fail containment can add up to K further entailment calls on top.
- The decomposition model can split poorly, which can either keep a fabricated fragment that happens to be verbatim or drop grounded content; the trace makes both visible but does not fix them.
- Under splitting is a known, unresolved risk: if the decomposition returns the whole sentence as a single sub claim, that sub claim's entailment check degrades to today's failing whole sentence check for that sentence. This feature makes the sub claim count visible in the trace so an under split is observable, it does not guarantee against it.
- Answer sentences for a sentence with some but not all sub claims kept become fragments, so the answer text granularity changes for those queries; a sentence with every sub claim kept avoids this by re-emitting the original text.
- The 6 of 6 acceptance gate is strong evidence, not a measured abstention rate; a true rate needs more runs.

**Neutral**:
- `schema_version` stays 2; the trace addition is additive.
- No store change, no rebuild, no new configuration.
- The coverage direction for query 2 is explicitly out of scope and recorded as a follow up.

## Follow-up

- [ ] Coverage direction, query 2 `DM-0004` consistency: design a citation completeness fix (a stricter generation contract that cites every accepted chunk directly answering a facet, or a citation completeness verification stage). Deliberately deferred so this feature changes one thing and stays measurable.
- [ ] If the missing chunk ref signal fires with any frequency, investigate upstream: generation cited chunks that retrieval did not surface, a bug before verification.
- [ ] Relevance floor calibration remains deferred from spec 0008 follow-up item 2; it is not the fix for either direction.
- [ ] Once the fix lands, consider measuring a true abstention rate over more runs, since the 6 of 6 gate is evidence, not a rate.
- [ ] If the live acceptance runs (or later usage) show the decomposition call returning a sentence as a single undivided sub claim with any frequency, the under splitting risk in Consequences is live, not theoretical; revisit with a deterministic minimum split heuristic or a hybrid deterministic clause splitter (Option 5 in rationale.md, deterministic clause splitting, was rejected for the general case, not necessarily as a narrow fallback here).
- [ ] An entailment grounded sub claim keeps the parent sentence's full cited set rather than a narrowed one, since `entail_verdict` (spec 0007, AC-15) has no per-chunk attribution today. If over citation on entailment grounded sub claims shows up as a real problem in practice, revisit by extending `entail_verdict`'s structured schema to name a supporting chunk, a change to that existing contract, deliberately not made by this spec.

## Rationale

Reasoning and options: see [rationale.md](rationale.md).
