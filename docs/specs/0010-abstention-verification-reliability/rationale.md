# Rationale: abstention verification reliability

## Context

> ⚠️ Premise note: AC-2 originally treated query 4 abstention as proof that the fused claim no longer passed verification. Live traces proved these are separate properties. The revised decision tests removal of the fabricated claim and completeness of the remaining answer separately.

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

## Post build diagnostic evidence (2026-08-12)

Three live query 4 runs returned the same important shape. Draft sentence S1 split cleanly into three or four atomic sub claims. S1.1 stated that the decision was made to keep the server side and browser side database clients together. Entailment returned unsupported for S1.1, and the sub claim was dropped. The fabricated decision never reached the answer.

Query 4 still answered. Coverage marked F1, the facet asking what was decided, covered by surviving grounded reason fragments. F2 was covered by a fully grounded sentence. The result therefore exposed a coverage error, not a decomposition or entailment error.

Other runs abstained because the near subset check rejected harmless model normalization, including `refetch` against `refetches` and added grammar tokens. That check is a real bug, but fixing it first would allow more clean decompositions through and make the coverage error appear more often. Coverage is therefore settled first. The tolerance fix follows as a lexical guardrail, not a factual preservation proof.

The independent spec cross check then found a more serious output flaw. The first draft restored the parent sentence whenever every returned sub claim was kept. A decomposition could omit the fabricated clause, return only grounded material, and make that rule restore the unverified parent with the fabrication intact. The check guarded against added vocabulary but not omitted content. Parent restoration is therefore removed completely. Omission may lose useful prose, but it cannot reintroduce an unverified claim.

## Live gate evidence and AC-9 reconciliation (2026-08-12)

Two more live `evaluate --runs 3` batches against the real JobPilot corpus ran after the build, in addition to the fresh baseline above.

Passes: query 4 abstains 6 of 6, query 5 abstains 6 of 6, the unverifiable claim assertion passes 5 of 6 and 6 of 6, and the incremental reingest assertion passes both batches. Query 1 stays the known live hiccup.

Failures: query 3 abstains 0 of 6, and the rationale summary assertion abstains 0 of 6. These two form the AC-9 conflict this update reconciles.

The unverifiable claim reading above, 5 of 6 in one batch, is why AC-9 now names its bars instead of saying the assertions still pass. A cross check found that the shipped `verify.md` had already accepted a 5 of 6 as passing with no stated rule, which is exactly the undocumented judgment call a smoke gate should not need. AC-2 and AC-3 prove a named number and a smoke gate are not in tension, so AC-9 sets both live provider assertions at 5 of 6 and the incremental reingest assertion at both batches, since it is a per batch assertion rather than a per run one.

### Query 3 root cause

The strict directness coverage leaves a facet uncovered. Query 3 asks which decisions are provisional and which are not ratified. The generated answer sentence S1 splits into S1.1, which states that the decision is still provisional and covers the provisional facet, and S1.2, which states that the decision needs to be made for scope feature 1 and does not state not ratified. Coverage cannot combine fragments, and the directness rule refuses to cover the not ratified facet from partial material. The answer does not directly enumerate the decisions, so the harness honestly abstains.

This is the directness rule working as intended. AC-9 assumed strict coverage would not affect the other fixtures, but query 3 exposes a generation quality gap, not a coverage regression. Decision: revise AC-9 so query 3 is not required to pass, keep the strict oracle so the gap stays visible, and enroll a generation quality follow up (the generation directness follow up in the index).

### Rationale summary root cause

The rationale summary sentence requires decomposition, and the whole response lexical guard rejected both decompositions. The rejected sub claims, pulled once by instrumenting the guard, fall into three groups:

- short stem inflections blocked by the four character floor: `add` from `adding`, `use` from `using`
- added function words outside the six token allowance: `is`, `not`, `there`, `no`
- genuinely new content: S1.6 adds `goal` as a mild rephrase, and S2.8 fabricates that `agent_runs` was built for job search and not company research

`goal` is the one unmatched token recorded verbatim at the time. The instrumented pull that produced the S2.8 reading was not preserved, so its exact unmatched tokens cannot be quoted from this record; re instrument the guard and take a fresh reading if that evidence is ever load bearing again. The finding it supports, that the guard caught a real fabrication and must keep doing so, does not depend on the exact tokens.

The whole response rejection discarded the clean sub claims (S1.1 to S1.5, S2.1, S2.3) because of the few violators. The S2.8 fabrication proves the guard catches real fabrication, and the fix must keep that property. Decision: reject per sub claim, drop only the violating sub claim, keep the clean sub claims (each still individually verified), and broaden the matching rule: common inflections with a three character floor (a dropped final `e`, a doubled final consonant, a final `y` changed to `i`) plus a content neutral function word allowance. This is the tolerance the post build diagnostic deferred until strict coverage landed.

## The AC-4 and AC-12 conflict (2026-08-12, experiments 0001 and 0002)

The per sub claim build shipped and failed its live gate. Rather than tune it a third time, the tool was pointed at this repository's own `docs/specs/`, where the author wrote every record the same week and can therefore grade every answer. Full records: [experiment 0001](../../experiments/0001-self-query-on-own-specs.md) and [experiment 0002](../../experiments/0002-corpus-gap-fix-and-coverage-conflict.md).

Two failures showed up that six days of fixture tuning never surfaced, because the fixtures measure abstention rates and neither failure is one.

**Fragment output is unreadable.** Asked why the adapter warns instead of inventing fields, the tool returned `It passes only when it is absent from discovery.` The pronoun has no referent: its parent sentence bound it, and the fragment does not. A second query turned one sentence listing five items into five sentences repeating one stem. Nothing was fabricated and every citation resolved. The output was simply bad prose.

**A correct answer was discarded.** This is the load bearing finding. Asked what was decided about hybrid retrieval, with spec 0008 present in the corpus, the pipeline produced this draft:

```text
S1: The hybrid retrieval system uses a combination of lexical BM25 and semantic
    Chroma retrieval, followed by reciprocal rank fusion to combine their scores,
    but it does not claim general retrieval superiority at scale due to the
    limitations of the JobPilot corpus.
```

That is a correct, complete, appropriately hedged answer. It decomposed into four sub claims; three came back `entailment=supported`, and the fourth was dropped by the lexical guard. Coverage then returned `F1 covered=False` and the query abstained.

The mechanism is the interaction of two acceptance criteria. AC-4 shatters the parent and emits only fragments. AC-12 says a facet is covered only when one sentence directly states its answer, and coverage cannot combine sentences. This decision needs three clauses to state. The parent stated it; no fragment did. So a verified correct answer was thrown away at the final step.

**This is the mirror of the JobPilot query 5 failure.** There, vacuous fragments (`The original approach was changed`) were individually supported and wrongly covered their facets, so the query answered when it should have abstained. Here, informative fragments each carried part of the truth and covered nothing, so the query abstained when it should have answered. One cause, opposite symptoms: **fragmenting the answer makes coverage unreliable in both directions.** No setting of the lexical guard can fix that, which is why both settings moved every gate the wrong way.

**It also falsifies a diagnosis this spec recorded.** `verify.md` explains query 3's abstention as the directness rule working as intended, and enrolls a generation quality follow up. Generation in the trace above was excellent. The abstention had nothing to do with generation quality, and the enrolled follow up would not have fixed it.

### What the cross check actually ruled out

The independent cross check rejected parent restoration, and this revision restores parents, so the two need reconciling. The check rejected **unconditional** restoration: restore the parent whenever every returned sub claim is kept. That is unsafe, because a decomposition can omit the fabricated clause, return only grounded material, and make the parent look verified.

It never evaluated restoration gated on **completeness**. The guard as built checks that sub claims do not *add* content to the parent. The missing check is the mirror: that they do not *omit* it. With both halves required, the omission attack fails at the completeness check and never reaches entailment. The cross check's finding stands; it simply does not reach the option chosen here.

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

Rejected in favor of Option 1: the model call handles fusions with no syntactic seam, which a fixed splitting rule cannot see. The lexical contract blocks unmatched vocabulary and the cap blocks runaway output, while containment and entailment still decide factual support. The under splitting risk that remains, a decomposition returning the whole sentence as one sub claim, is recorded in Consequences as a known, traced, unresolved risk rather than treated as fully closed.

### Option 6 (scoped out): query 2 citation completeness

A citation completeness fix for query 2: either a stricter generation contract citing every accepted chunk that directly answers a facet, or a citation completeness verification stage.

This is a real design question and remains outside this feature. Query 2 omits a record that directly answers its broad question, but the fixed facet set does not name every decision the corpus contains. Making coverage demand unseen records requires a citation completeness contract, not the direct facet coverage correction query 4 exposed. Recorded as a follow up.

## Coverage options considered after live verification

### Accept the grounded reasons as a partial answer

Keep the surviving reason fragments, change query 4's oracle, and treat the answer as useful even though it does not state what was decided.

Pros:

- Preserves useful grounded text.
- Adds no provider or schema work.

Cons:

- `QueryResult` has only answered, abstained, and failed states. It cannot say that one required facet is missing.
- Calling the result answered would weaken spec 0007 AC-15 and make partial output look complete.
- Honest partial answers need a new state and rendering contract, which is a separate product decision.

### Enforce direct complete facet coverage

Keep the binary result contract. A facet is covered only when a kept sentence directly states its answer. Use the same fixed model as facet extraction and answer generation for coverage, give it explicit decision versus reason rules, and validate all supporting sentence ids against the kept sentences.

Pros:

- Preserves the meaning of answered without adding a new result state.
- Fixes query 4 at the stage the live trace identified.
- Changes one existing provider call and its validation, with no storage or public schema migration.

Cons:

- The larger model costs more for every nonempty query.
- Semantic coverage remains model judged, so the live gate is still necessary.

### Add typed facets and deterministic coverage rules

Classify facets as decision, reason, alternative, status, or consequence, then require a compatible sentence type before coverage can pass.

Pros:

- Makes answer roles explicit in the trace.
- Could support richer partial answer rendering later.

Cons:

- Adds another model classification contract and expands the DTO surface.
- Open ended questions do not fit a small closed type list without false precision.
- It is a broader redesign than this measured failure requires.

## Output options considered after the cross check

### Restore a parent after every returned sub claim passes

Keep the original prose when all returned claims are grounded. A stronger form would also require deterministic reconstruction of all material parent content.

Pros:

- Preserves fluent answer prose.
- Avoids exposing model fragments when the sentence was fully supported.

Cons:

- Passing every returned claim says nothing about content the decomposition omitted.
- A safe reconstruction rule would need to prove material span completeness, multiplicity, order, negation, and relation preservation. That is more complex than the verification stage and still fragile.
- The simple all kept rule can restore the exact fabrication verification removed.

### Emit verified fragments only

Once a sentence is decomposed, discard the parent as an output candidate. Emit each kept sub claim with its own id and available citations.

Pros:

- Verification cannot be undone by output formatting.
- Omission becomes lossy rather than unsafe.
- The rule is deterministic and easy to audit.

Cons:

- Answer prose is less fluent and may repeat context.
- A poor decomposition can drop useful grounded detail.

## Options considered for the AC-9 reconciliation

### Whole response lexical rejection (previous)

Keep the guard as a whole response verdict: any sub claim with an unmatched content token rejects the entire decomposition, and the sentence contributes no kept sub claims.

Pros:
- Simple and conservative; a single verdict per response.
- The rejected response is visible in one trace disposition.

Cons:
- One bad sub claim discards every clean sub claim in the same response.
- Live decompositions of long sentences reliably contain a rephrased or occasionally fabricated sub claim, so sentences with useful content abstain entirely, which is what produced the rationale summary abstention.

### Per sub claim lexical rejection (chosen)

Drop a violating sub claim as an individual and record it in the trace; let the clean sub claims proceed to verification. Reject the whole response only when no sub claim is acceptable.

Pros:
- The guard removes exactly what violated it and nothing else.
- The safety property holds because each surviving sub claim is still individually verified; nothing fabricated can emit.
- A partially rejected response is an explicit intermediate state, and the trace shows which sub claims were dropped.

Cons:
- Adds a fifth additive trace field for the dropped sub claims.
- A fabricated sub claim that shares a response with useful content still drops that fabricated sub claim, which is correct, but the useful content survives rather than the whole sentence abstaining.

### AC-9 keeps requiring query 3 to pass (rejected)

Keep the original wording so the feature is not done until query 3 passes under strict coverage.

Pros:
- Keeps the strongest gate.

Cons:
- Query 3 abstains because the generated answer does not directly state the not ratified facet, which the directness rule correctly refuses to cover. Forcing a pass would require relaxing directness, which would undo the query 4 fix, or improving generation, which is a separate follow up, not this change.

### Cross check on the revision (2026-08-12, Sonnet 5)

A read only cross check of the revised spec found one defect that would have shipped, plus five underspecified rules. All were fixed before the spec was confirmed. Recorded because the first finding is the third time on this feature that a passing local reading hid a failing real one.

**The additive check's scope was unstated, and the natural reading broke the query the revision exists to fix.** The draft said every sub claim content token must match an *unused* parent token, without saying whether the pool is consumed across the response or reset per sub claim. Checked against the real experiment 0002 decomposition: the parent names `hybrid` once, `system` once, and `retrieval` three times, while the three sub claims each restate the subject, using `hybrid` three times, `system` three times, and `retrieval` five. A response wide pool rejects that as `not_additive`, so the revision would have abstained on its own motivating example through a brand new mechanism.

The fix makes the two halves deliberately asymmetric. The additive half is per sub claim against a fresh parent pool, because a decomposition restating a shared subject adds nothing and is the normal shape of a correct split. The completeness half is response wide and presence based, because omission is the attack and a dropped clause removes its content words from the response entirely. Multiset completeness was rejected: it would reject ordinary splits without catching anything the presence reading misses.

The other five, all now pinned in AC-11 or Provider contracts: exact equality was subject to the three character floor, so a verbatim `db` could not match itself (`_stem_match` already exempted equality and its docstring called the clarification owed, so the code was right and the spec was wrong); completeness was multiset versus set ambiguous; a token eligible against several parent tokens had no tie break, which is exactly the "two conforming builds disagree" failure AC-11 was pinned to prevent, now fixed as greedy first unused in parent order; the malformed row check had no stated position and now runs before empty, over cap, and duplicate, so two empty strings cannot pair as a duplicate; and the under splitting follow up tracked only the degenerate single sub claim case, not a multi way split that still co locates a fabricated clause with its camouflage.

**One finding changed a bar rather than a rule.** AC-9 credited the rationale summary's 5 of 6 recovery to the per sub claim guard, which this revision removes, so the criterion contradicted AC-11 in the same document. The evidence is against simply restating the bar: one rejected sub claim substituted the synonym `goal`, and no stem rule can match a synonym. The bar is therefore re measured rather than asserted, and a single decomposition retry was added for the stochastic paraphrase case, mirroring the schema repair the other provider calls already make.

## Options considered for the AC-4 and AC-12 conflict

### Judge the parent, emit the parent (chosen)

Decomposition becomes a check, not a rewrite. A response must be valid (adds nothing, omits nothing) and every sub claim must be supported; then the parent sentence is emitted verbatim. Otherwise the parent is dropped whole. Coverage judges whole sentences.

Pros:
- Fixes both failure directions with one change. Vacuous fragments cannot cover a facet because no fragment is emitted; multi part decisions are answerable because the parent states them.
- Restores readable prose without a second generation pass, so no new fabrication surface appears.
- Ends the guard granularity question permanently. Removing a sub claim breaks completeness by construction, so per sub claim dropping stops being a coherent option.
- The completeness half closes the omission attack that the cross check raised against unconditional restoration.
- Makes the additive tolerance safe to loosen, because sub claims never reach output.

Cons:
- One unsupported or unverifiable sub claim costs the whole sentence, including grounded clauses that sat beside it.
- The lexical tolerance now drives the abstention rate, since an unverifiable sub claim and an unsupported one have the same effect. Experiment 0002's `S1.4` shows this is not hypothetical, and it means the revision does not automatically pass that query.
- Content token completeness cannot see a dropped negation or a reversed relation. Entailment alone catches those.

### Let coverage combine fragments from the same parent (rejected)

Keep fragment output, and relax AC-12 so coverage may combine sentences that came from one parent.

Pros:
- Smaller change; touches coverage only.
- Fixes the multi part abstention directly.

Cons:
- Does not fix readability at all, which experiment 0001 showed is the failure a reader meets first.
- Makes the vacuous fragment problem worse, not better: combination gives coverage more ways to assemble a facet answer out of material that individually states nothing.
- Re-opens the question the directness rule was written to settle, so it trades a known failure for the one that came before it.

### Regenerate prose from the verified fragments (rejected)

Add a second generation pass that rewrites the kept fragments into flowing text.

Pros:
- Produces the best looking output of any option.
- Keeps per fragment verification exactly as built.

Cons:
- The regenerated text is unverified by construction. Every claim would have to be re-verified, or the pipeline would emit model output that no check ever saw, which is the exact failure this whole feature exists to prevent.
- Adds a provider call and a new failure mode to every non verbatim answer.

### Accept the fragments and lower the coverage bar (rejected)

Keep everything and let a facet be covered by the union of fragments without a directness requirement.

Pros:
- No mechanism change.

Cons:
- This is the pre spec 0010 behaviour that let query 4 answer with a fabricated decision. It undoes the feature.

## Rationale

Sub claim decomposition is the chosen option because it removes the hiding place the spec 0008 evidence identified. Three entailment prompt variants failed on the whole sentence, which rules out prompt tuning and points at the unit. Verifying each sub claim alone means the invented decision no longer carries its verbatim support inside the sentence it is verified against. The deterministic span floor was rejected because it would reject legitimate paraphrases and can regress query 2; the generation rewrite was rejected because it is the largest surface change for the same goal; the stronger model was rejected because the documented failure is structural, not model capability; deterministic clause splitting (Option 5) was rejected because it only catches fusion at a syntactic seam, and the model call generalizes to fusions that have none.

Fabrication only was the scope decision, on the fresh baseline. Query 4 and query 5 are the reliably failing gates, and coverage is intermittent with a single sample showing it passing. The project has repeatedly paid for changing one thing and seeing what moved, and the harness measures fixtures, not stages, so landing both directions at once would make the attribution impossible.

The post build trace narrows that earlier statement. Query 2 citation completeness remains a separate direction, but query 4 complete facet coverage is part of the same acceptance path. The fabricated decision is gone, yet the binary result is still wrong because the remaining reasons do not answer what was decided. This spec cannot call that result acceptable without either weakening spec 0007 AC-15 or adding an explicit partial result state.

Strict complete facet coverage is chosen. Coverage uses the same fixed model as facet extraction and answer generation because the task is direct semantic answer matching, not the narrower entailment task. The prompt judges only what each emitted sentence states. It explicitly says that a reason, context, consequence, or premise does not answer what was decided unless the sentence states the decision. Deterministic validation then enforces referential integrity for the sentence ids. A covered row has at least one known emitted sentence, and an uncovered row has none.

The facet tuple comes from one extraction call over the original question and remains fixed through answer generation and coverage. This makes the completeness boundary explicit, but it does not prove that extraction found every required facet. Query 4 therefore asserts separate decision and reason facets in the live gate. Using the same model family for extraction, generation, and coverage can produce correlated errors, so the six run gate remains a smoke result rather than a proof. Typed facets or an independent evaluator are the next design step if the directness error remains unstable.

Facet extraction and coverage failures need different fixes, so the live report classifies them from fields already present in the trace. It first checks whether query 4 produced separate decision and reason facets. A merged facet is an extraction failure, and coverage directness is not judged for that run. With separate facets, a covered decision facet supported only by reasons is a coverage directness failure. If the decision facet is uncovered but the result is answered, the failure belongs to query state assembly. This adds no runtime field and prevents one red AC-2 result from pointing at the wrong stage.

Typed facets were rejected for now. They would make partial answer roles explicit, but they introduce a broader schema and another model classification before the product has chosen a partial result surface. If strict coverage still fails after the stronger prompt and model choice, typed facets are the next design step rather than more prompt tuning.

The application resolves the parent's citation ids against accepted context before every verification path. This boundary matters more than whether a citation was present in the draft. Missing ids can be counted in trace but can never supply evidence or escape into output. Containment already checks a sub claim against each available chunk individually, so a containment grounded fragment narrows to the matching chunks. Entailment has no per chunk precision and therefore keeps all available parent citations. Extending entailment to name a supporting chunk remains a follow up.

The decomposition call is another place the model can distort content. The lexical guardrail blocks unmatched vocabulary under a small, explicit normalization rule, but it cannot prove semantic preservation. Reusing old tokens can reverse actors, drop negation, change scope, or reorder a relation. Deletion is allowed because decomposition exists to split and shorten the parent, and parent restoration is forbidden, so omission is no longer an output injection path. Every accepted fragment still needs containment or entailment before it can emit. A rejected nonempty response has its own trace disposition rather than pretending the model returned nothing.

Deterministic clause splitting (Option 5) was considered as a way to avoid the decomposition call's own model dependence entirely. It was rejected because the documented weld happens to sit at a conjunction boundary, but a fusion with no syntactic seam, an appositive, or an interleaved paraphrase would pass through unsplit and land back on today's failing whole sentence check; the model call generalizes to meaning where a fixed splitting rule cannot. This leaves one acknowledged, unresolved risk: a decomposition that under splits, returning the whole sentence as a single sub claim, degrades that sentence's check back to the same structural failure this feature exists to close. The contract check cannot catch this, because a single sub claim equal to the sentence is a valid near-subset. This spec makes the risk visible, the sub claim count is present in the trace whenever a sentence decomposes, rather than claiming to close it; Follow-up records revisiting with a narrower deterministic split if live evidence shows it firing with any frequency.

Verified fragments only is chosen over parent restoration because it has the smallest trustworthy invariant. Formatting never gains authority to emit text that verification did not keep. A reconstruction rule is the runner up, but proving complete material reconstruction would recreate a semantic verifier inside a readability optimization. The readability loss is the correct cost.

The model is fixed to `gpt-4o-mini` because decomposition quality determines what gets verified; making it swappable would make the guarantee swappable, consistent with the no abstraction call that keeps infrastructure as the swap point. The provider failure contract fails the query rather than degrading, because degrading would silently fall back to the exact behavior this feature exists to fix; a malformed or unparseable response is treated the same way, a provider failure with no retry, rather than a third undefined path.

The acceptance bar, 6 of 6 across two `--runs 3` batches, now tests the complete answer contract. AC-1 and the query 4 trace test that the fabricated decision is removed. AC-2 separately requires the decision facet to remain uncovered and the query to abstain. Six runs are still a smoke gate, not a measured rate.

The live gate reconciliation keeps the coverage oracle strict. Query 3 abstains because the answer does not directly enumerate which decisions are provisional, and the directness rule refuses to cover the not ratified facet from partial material; relaxing directness would undo the query 4 fix, so the gap is recorded as a generation quality follow up instead. The lexical guard moves to per sub claim granularity because a whole response verdict discards clean sub claims when one sub claim violates the rule, and the live pull proved that happens reliably on long sentences. Each surviving sub claim is still individually verified, so the guard keeps its safety property while the tolerance (a three character stem floor, the common inflections, and the content neutral function word allowance) stops harmless normalization from discarding grounded content. The S2.8 fabrication stays rejected.

Two independent cross checks then pushed the matcher from a described rule to a pinned one, and that is the shape it keeps. A deterministic guard with no model call cannot be specified as a grammatical category plus examples, because two conforming builds would then accept different sub claims. So the stem rules are written as five exact string transformations, the three character floor is measured on the untransformed token, the function word allowance is two tokens per sub claim counted as instances rather than as distinct words, a function word matches only by exact token equality, and the function word set is closed and written out in full. Closing the set is deliberately the strict direction: an unlisted word makes the guard drop a sub claim, which loses content but never admits a fabrication, and adding a word later is a spec edit with a visible reason rather than a silent build time choice.

## References

**Project sources**:
- `AGENTS.md`, the Clean Architecture and verification conventions
- spec 0007, the core cited query, its AC-15 verification contract and the partial verification rule (drop failed claims, re check the remainder)
- spec 0008, the reliable multi source retrieval, rationale "Verification unit gap", "Query 4 verification finding", and "Relevance floor decision", follow up items 7 and 8
- spec 0009, the proven correctness evaluation harness, its verify.md known state and the fixture expectations
- `docs/scope/scope.md`, feature 16 done when and the feature 10 status corrections
- the fresh baseline runs, 2026-08-12, recorded above
- the post build `/debug` traces, 2026-08-12, recorded above
- the AC-9 live gate runs and the instrumented rejected sub claim pull, 2026-08-12, recorded above
- `docs/experiments/0003-whole-sentence-gate-and-a-misdiagnosis.md`, the measured drop rates on the built revision: 19 of 20 draft sentences dropped and 1 query of 12 answered, with `not_additive` at 74 percent of drops, inline citation markers at 16 percent, and `unsupported_sub_claim` at zero. Read it before the next design pass; it reorders the work
- `src/decision_memory/application/verification.py`, `application/query.py`, `application/dto.py`, `infrastructure/openai_generation.py`, the code this feature changes

**Practices & standards**:
- pass only shortcut for deterministic checks: a deterministic test never rejects, it only sends on
- no evidence, no support: a claim verified against empty evidence can never be supported
- one change at a time for measurable attribution
