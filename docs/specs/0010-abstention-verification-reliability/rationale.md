# Rationale: abstention verification reliability

## Context

The query pipeline verifies answers at the sentence level, but the attack surface is finer than a sentence. Spec 0008's "Verification unit gap" documented the failure: a generated sentence can weld an invented decision to a clause copied verbatim from a real cited chunk. The deterministic containment tier can find the borrowed clause, and the model entailment tier sees supporting text inside the sentence and returns supported. Spec 0008 recorded that three entailment prompt strictness variants all returned supported five of five for the query 4 fabrication, so this is not a prompt tuning problem; the fix must change the verification unit.

The relevance floor is not the fix. Spec 0008's "Relevance floor decision" recorded that the floor only makes query 4 abstain because its evidence is distant, and a future fabrication with close evidence would pass the floor and still verify as supported. It also risks trading a false answer for a false abstention.

Feature 11 built the evaluation harness that measures the symptom. It does not patch it. The symptom has two directions. Fabrication: query 4 and query 5 answer instead of abstaining. Coverage: query 2's `DM-0004` citation is intermittent, because evidence sits in the accepted context that generation never cites and verification never demands.

A fresh baseline on 2026-08-12 (three runs of the live harness against the real JobPilot corpus) shaped the scope. Query 4 and query 5 both answered three of three, so fabrication is the dominant, near reliable failure today. Query 2 passed three of three with `DM-0004` cited in this sample, and its omission measured 6 of 12 in an earlier batch, so coverage is real but intermittent, a rate with very little data. Query 1 went one of three on a provider failed state, a live hiccup unrelated to this feature.

## Fresh baseline evidence (2026-08-12)

Run on 2026-08-12, live providers, real JobPilot corpus, three runs each, using the feature 11 harness:

- query 1 private beta gate: 1 of 3, one run returned a provider failed state with no citations
- query 2 resume generation: 3 of 3, cites `DM-0004` and `DM-0019`
- query 3 provisional: 3 of 3
- query 4 db clients: 0 of 3, answered with `DM-0007` and `DM-0008`
- query 5 uploaded files: 0 of 3, answered with `DM-0002` and `DM-0003`
- assertion rationale summary: 3 of 3
- assertion unverifiable claim: 3 of 3
- assertion incremental reingest: pass, record chunks changed after the rationale edit

This is the dated evidence behind the fabrication only scope. A future reader can compare against it.

## Options considered

### Option 1: Sub claim decomposition with per sub claim verification

A sentence that is not verbatim in its cited chunks is split into atomic sub claims by a structured model call. Each sub claim inherits the parent's cited chunk ids and is verified alone: deterministic containment first, then model entailment for the rest. Grounded sub claims become answer sentences and feed the existing coverage check.

Pros:
- Directly removes the borrowed clause's hiding place: the invented decision is verified alone, without the verbatim support inside the sentence.
- Reuses the existing containment and entailment tiers, so the change is an added stage, not a replacement.
- Keeps grounded content: the borrowed clause survives as a sub claim, and coverage decides the outcome.

Cons:
- Adds a provider call per non verbatim sentence (latency and cost).
- Decomposition quality is a new dependency; a poor split can misclassify content.

### Option 2: Deterministic span coverage grounding floor

Require the sentence's content to be reconstructable from the cited chunks as contiguous spans, and reject it otherwise.

Pros:
- Deterministic, free, no provider call, no new failure mode.
- Directly attacks the recombination of known vocabulary: invented decisions reuse the same words as the evidence but not the same spans.

Cons:
- Also rejects legitimate paraphrases, which are not contiguous spans of a chunk, so it trades the fabrication for over abstention and can regress query 2's legitimately paraphrased `DM-0004` sentence.
- The whole sentence check was the pass only shortcut for a reason; making a deterministic test reject is a new policy that needs calibration the project does not have.

### Option 3: Atomic claim generation schema rewrite

Change the generation contract so the model emits atomic claims with per claim evidence instead of sentences.

Pros:
- Fixes the shape at the source, so verification works on claims that were never welded.

Cons:
- Changes the generation schema, the draft DTO, the trace, and every fixture oracle that reads sentences; the largest surface change of the options.
- The model still has to be constrained to emit truly atomic claims, and a schema alone does not guarantee it.

### Option 4: Stronger independent verifier model

Verify entailment with a stronger model than `gpt-4o-mini`, for example `gpt-4o`.

Pros:
- No pipeline restructure.

Cons:
- Costs more per query and stays model based, and the documented failure was the supporting text inside the sentence, which a stronger model was not shown to resist.
- Spec 0008 recorded three prompt variants failing on the sentence as a whole; the fix must change the unit, not the model.

### Option 5: Deterministic clause splitting

Split a sentence into sub claims with a deterministic rule, breaking on coordinating conjunctions and subordinators (`and`, `which`, `that`, relative clause markers), instead of a model call.

Pros:
- Free, no provider call, no new failure mode from a model deciding the split.
- Would catch the documented weld pattern, an invented decision joined to a borrowed clause by a conjunction.

Cons:
- Only catches fusion at a conjunction or subordinator boundary. The documented spec 0008 weld happens to be that shape, but a fusion inside a single clause, an appositive, or a paraphrase that interleaves invented and borrowed content with no syntactic seam would pass through unsplit, back to today's whole sentence check. The model call generalizes past syntax to meaning.
- Trades one calibration problem (entailment prompt strictness, already tried and failed per spec 0008) for another (which conjunctions and subordinators to split on, and which not to, is itself a rule that needs tuning against real sentences the project does not yet have).

Rejected in favor of Option 1: the model call handles fusions with no syntactic seam, which a fixed splitting rule cannot see. Contract bound decomposition (a near-subset check against the parent sentence's own tokens, capped at 8 sub claims) keeps the model call's downside, that it could itself fabricate, checked deterministically, so this spec gets the model's semantic reach without handing it a second unchecked place to invent content. The under splitting risk that remains, a decomposition returning the whole sentence as one sub claim, is recorded in Consequences as a known, traced, unresolved risk rather than treated as fully closed.

### Option 6 (scoped out): the coverage direction

A citation completeness fix for query 2: either a stricter generation contract citing every accepted chunk that directly answers a facet, or a citation completeness verification stage.

This is a real design question and was deliberately kept out of this feature. The two directions are not the same problem: fabrication is verification failing to reject a claim it can see, coverage is nothing demanding a claim that was never made. Changing one thing keeps the measurement clean, and coverage is intermittent with almost no data, so designing against it now would repeat the premature floor calibration mistake. Recorded as a follow up.

## Rationale

Sub claim decomposition is the chosen option because it removes the hiding place the spec 0008 evidence identified. Three entailment prompt variants failed on the whole sentence, which rules out prompt tuning and points at the unit. Verifying each sub claim alone means the invented decision no longer carries its verbatim support inside the sentence it is verified against. The deterministic span floor was rejected because it would reject legitimate paraphrases and can regress query 2; the generation rewrite was rejected because it is the largest surface change for the same goal; the stronger model was rejected because the documented failure is structural, not model capability; deterministic clause splitting (Option 5) was rejected because it only catches fusion at a syntactic seam, and the model call generalizes to fusions that have none.

Fabrication only was the scope decision, on the fresh baseline. Query 4 and query 5 are the reliably failing gates, and coverage is intermittent with a single sample showing it passing. The project has repeatedly paid for changing one thing and seeing what moved, and the harness measures fixtures, not stages, so landing both directions at once would make the attribution impossible.

The sub claim model starts from the parent's chunk ids because the decomposition must only narrow what is checked, never redirect it; the model itself is never allowed to assign or pick citations, which would hand it a new place to fabricate. What is checked can still be narrowed after the fact, but only where the pipeline actually has per-chunk precision to narrow from. Containment already checks the sub claim against each cited chunk individually, so a containment grounded sub claim narrows deterministically to the specific chunk(s) that matched, closing the over citation gap the cross check found for that case. Entailment does not have this precision: `entail_verdict` (spec 0007, AC-15) verifies against the joined evidence of every cited chunk at once and returns a single supported/reason pair, with no chunk level attribution, and it is the same call the existing whole sentence path already relies on. Making it name a supporting chunk would be a change to that existing contract, not a decision this spec makes as a side effect of a citation display gap; an entailment grounded sub claim therefore keeps the parent's full cited set, a stated, narrower fix than the cross check first proposed, and Follow-up records the remaining asymmetry rather than inventing a call it cannot make.

The decomposition call is itself a second place the model could invent content, since it is a model call the same as the entailment call that motivated this whole feature. The contract check, a deterministic near-subset comparison of each returned sub claim against the parent sentence's own tokens, closes that gap without adding a second model dependent judgment: a sub claim that contains material absent from the source sentence is discarded before it is ever verified, folding into the same empty decomposition signal AC-6 already defines. Grounded reuses entailment's existing binary verdict with no new threshold, because introducing a second acceptance bar this spec cannot calibrate would repeat the mistake spec 0008 already made once with the relevance floor.

Deterministic clause splitting (Option 5) was considered as a way to avoid the decomposition call's own model dependence entirely. It was rejected because the documented weld happens to sit at a conjunction boundary, but a fusion with no syntactic seam, an appositive, or an interleaved paraphrase would pass through unsplit and land back on today's failing whole sentence check; the model call generalizes to meaning where a fixed splitting rule cannot. This leaves one acknowledged, unresolved risk: a decomposition that under splits, returning the whole sentence as a single sub claim, degrades that sentence's check back to the same structural failure this feature exists to close. The contract check cannot catch this, because a single sub claim equal to the sentence is a valid near-subset. This spec makes the risk visible, the sub claim count is present in the trace whenever a sentence decomposes, rather than claiming to close it; Follow-up records revisiting with a narrower deterministic split if live evidence shows it firing with any frequency.

The model is fixed to `gpt-4o-mini` because decomposition quality determines what gets verified; making it swappable would make the guarantee swappable, consistent with the no abstraction call that keeps infrastructure as the swap point. The provider failure contract fails the query rather than degrading, because degrading would silently fall back to the exact behavior this feature exists to fix; a malformed or unparseable response is treated the same way, a provider failure with no retry, rather than a third undefined path.

The acceptance bar, 6 of 6 across two `--runs 3` batches, is stated plainly as strong evidence that the weld no longer passes, not a measured abstention rate. The project already learned not to trust a five run smoke gate, and this is a larger smoke gate, not a rate. A true rate needs more runs and belongs to the harness later.

## References

**Project sources**:
- `AGENTS.md`, the Clean Architecture and verification conventions
- spec 0007, the core cited query, its AC-15 verification contract and the partial verification rule (drop failed claims, re check the remainder)
- spec 0008, the reliable multi source retrieval, rationale "Verification unit gap", "Query 4 verification finding", and "Relevance floor decision", follow up items 7 and 8
- spec 0009, the proven correctness evaluation harness, its verify.md known state and the fixture expectations
- `docs/scope/scope.md`, feature 16 done when and the feature 10 status corrections
- the fresh baseline runs, 2026-08-12, recorded above
- `src/decision_memory/application/verification.py`, `application/query.py`, `application/dto.py`, `infrastructure/openai_generation.py`, the code this feature changes

**Practices & standards**:
- pass only shortcut for deterministic checks: a deterministic test never rejects, it only sends on
- no evidence, no support: a claim verified against empty evidence can never be supported
- one change at a time for measurable attribution
