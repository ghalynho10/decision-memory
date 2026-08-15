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

## Options considered for the three open decisions (2026-08-13)

Experiment 0003 measured the built revision and left three decisions owed. All three were settled on 2026-08-13. Two of them are about the measurement instrument rather than about the mechanism, which is why they were settled before any calibration ran: a tolerance calibrated against a contaminated corpus and a marker poisoned token stream would be calibrated against noise.

### OD-1: inline citation markers in the draft text

The answer model intermittently writes `[ch_...]` markers into `DraftSentence.text`, measured at 11 of 20 sentences. `sentence_tokens` reads a chunk id as a parent content token, and no sub claim can ever match a 64 character hash, so the completeness half fails and the parent is dropped. Experiment 0003 attributed 16 percent of drops to this, and noted the figure is a floor rather than a ceiling: the additive half runs first and claimed 8 of the 11 marker bearing sentences before completeness was reached, so the marker effect is partly masked by check order.

**Strip markers at the generation boundary (chosen).** `validate_draft` removes the marker before constructing the `DraftSentence`.

Pros:

- The marker is a serialization artifact and `chunk_ids` already carries the same data as a validated structured field, so the strip loses nothing.
- The fix lands where the artifact enters the system, so every later consumer of `text` inherits it instead of re deriving it. The token matcher, the containment shortcut, and the rendered answer are all fixed by one change.
- It repairs AC-5, which was silently dead: a sentence carrying a marker can never be a verbatim substring of the chunk it cites, so every marker bearing sentence was paying a decomposition call the cost bound said it should not. Roughly half of them were.
- The marker shape is `ch_` plus 64 lowercase hex, which is what `chunk_id` produces, so no English word can collide with it and the strip carries no false positive risk.

Cons:

- It is a pattern match on model output, not a guarantee about the model. A new way of writing an id would not be covered.
- Stripping before the one sentence check means the check reads a string the model did not emit; a sentence that parsed as one sentence only because a marker followed its period is now judged on the cleaned text. This is the correct reading, but it is a behaviour change in a validator, not only a cleanup.

**Teach the matcher to ignore chunk id shaped tokens (rejected).** Add a shape test to `sentence_tokens` and drop matching tokens.

Pros:

- Smaller, contained entirely to AC-11, and touches no validator.

Cons:

- Leaves AC-5 dead, because the containment shortcut compares raw text and the marker is still in it.
- Leaves raw chunk ids in the emitted answer, which is a separate output defect nobody had named.
- Hands the same problem to every later consumer of `text`, so each one has to learn that a chunk id is not a word. That is the shape of a bug that keeps coming back.

**On the prompt.** `ANSWER_SYSTEM_PROMPT` said to cite ids `exactly as shown in brackets in the evidence`, which is the wording that invites the marker into the prose. It cannot simply be deleted: the code comment beside it records that without the real bracketed ids named, a live model invents its own and every validation attempt fails. So it is reworded rather than removed, keeping the ids named while moving them explicitly into the `chunk_ids` field and forbidding them in the sentence text. The prompt is the soft half and the strip is the hard half; the strip is what makes the guarantee, since the model already complied inconsistently, and the prompt only lowers how often the strip fires. Doing only the prompt was not considered viable for exactly that reason.

### OD-2: what the self corpus gate reads

Task 11's expected answer was written verbatim into this spec's build plan, and this spec lives in the corpus the gate queries, so the first run answered out of that text. Experiment 0003 finding 4.

**Frozen fixture, committed script, this spec held out (chosen).**

Pros:

- Fixes contamination and reproducibility together. The second problem is the one the original framing missed: the live `docs/specs/` tree changes every time any spec is edited, so a gate run against it tests code and corpus content at the same time and can attribute a change to neither. This gate measures code behaviour, which makes it a test fixture, and a test fixture's input should be held constant.
- A committed script rather than a recorded command, because a manual copy step drifts and a scratch directory is wiped between sessions. The script follows the existing `docs/experiments/data/adr-sweep.sh` pattern, so it sits where the project already keeps reproducible measurement scripts.
- The output lives outside `docs/specs/`. Discovery reads `corpus_root/docs/specs` and iterates its direct children only, so a fixture whose own `docs/specs/` tree is nested under `docs/experiments/data/` is invisible to `adapt` at the repository root. Without that placement the snapshot would join the corpus it is held out of.
- The manifest's per record content hashes make drift a diff rather than a silent change of the measurement input.

Cons:

- The fixture goes stale by design, and re baselining is a deliberate step with no trigger. Recorded as a follow up rather than solved now.
- It duplicates spec content inside the repository, which is the second source problem this project warns about elsewhere. Mitigated by the placement (no tool reads it as a record) and by the manifest naming its source commit, not eliminated.

**Rebuild live each run, excluding this spec (rejected).** Same exclusion, built fresh from the working tree every time.

Pros:

- Simpler to describe, always current, nothing to re baseline.

Cons:

- Fixes contamination and leaves reproducibility broken. Editing any other spec between two runs changes the gate's evidence, so a run to run difference cannot be attributed to the code. That is the property the gate exists for.

**Scrub expected answers from this spec, leave the corpus whole (adopted as hygiene, rejected as the fix).**

Pros:

- Keeps the corpus honest to what the tool really reads.
- Removes the class rather than the instance: any spec can contaminate any gate this way, and holding one spec out of one gate does nothing about the next one.

Cons:

- Fragile on its own. Nothing checks for it, so it holds only while nobody writes an expected answer into a spec again.
- Insufficient on its own regardless: it does not touch the reproducibility half.

Taken together with the fixture rather than instead of it. The fixture is the mechanism and the scrub is the hygiene, and the expected answers move to the fixture manifest, which sits outside `docs/specs/` and is therefore never read by the adapter at all.

### Cross check on the settled decisions (2026-08-13, Sonnet 5)

A read only cross check of the settled decisions verified four mechanism claims against the code and found them sound: discovery is non recursive, so a fixture nested under `docs/experiments/data/` is structurally invisible rather than merely filtered; `chunk_id` is `ch_` plus a lowercase 64 character sha256, so no prose token can collide; AC-11's spec text matches `application/verification.py` exactly; and the recorded `DECOMPOSE_SYSTEM_PROMPT` is character for character the shipped string. Every acceptance criterion traces to a build task.

It found the fixture machinery underspecified in the same way AC-11 was twice found underspecified, and all of it was closed before the spec was confirmed. The manifest had no schema although task 10 writes it and task 11 reads it back; the content hash had no named source; the fixture path was never stated; the generator's language was an open fork; the isolation tests had no pytest marker, so under this project's unit only CI they would silently not have run; and the marker strip was prose rather than a pinned regular expression, leaving uppercase hex, comma spacing, and mixed bracket groups undefined. Each is now written into AC-13, AC-14, or the Feature design manifest block.

Three of the findings were judgment calls rather than omissions, and the reasoning is recorded because a later reader will otherwise re open them.

**Raw file bytes over the adapter's `fingerprint()` for the manifest hash.** `fingerprint()` already exists and hashes contributing file paths, bytes, and the adapter version together. It was rejected because this hash answers one question, did the fixture input change, and `fingerprint()` also moves on an `ADAPTER_VERSION` bump. That would report adapter churn as corpus drift, which is precisely the confusion the frozen fixture exists to prevent. Raw bytes also keep the generator reachable from plain bash, which resolved the script language fork at the same time.

**The fixture is chunk faithful, not record faithful.** `_extract_code_paths` resolves inline code spans against the corpus root, and every spec here cites `src/decision_memory/...` paths in backticks. A fixture root holding only `docs/specs/` resolves none of them, so its records carry smaller `evidence` sets and higher `mentions_unresolved` counts than a live adaptation of the same text. Mirroring the code tree into the fixture was rejected: it would drag `src/` and `tests/` into a frozen snapshot, which is a far larger duplicate than the spec copy already is and would go stale in a way that actually matters. The divergence is instead stated and verified once, by comparing a record's active chunk set between a live and a fixture adaptation. The gate reads chunk text and not evidence targets, so identical chunks confine the divergence to fields it never touches. This is the same family as the standing rule about spec 0003 mention counts: a corpus that documents its own reader changes what the reader sees, so the figure has to be measured rather than assumed.

**The duplicate collision is kept, not worked around.** Stripping before the duplicate text check means two sentences whose prose is identical and whose markers differ now collide, and the existing rule fails the whole response. Comparing pre strip identity instead was rejected: the marker was never content, so two sentences with the same prose are genuinely the same sentence, and letting them both through would emit duplicate prose citing different chunks. The rule is unchanged; AC-13 states the consequence and a test pins it, so the behaviour is chosen rather than discovered later in a trace.

### OD-3: `DECOMPOSE_SYSTEM_PROMPT` is out of sync

`/develop` added a completeness instruction to the prompt during the task 5 to 8 build, and this spec treats prompt text as a fixed constant, so the shipped wording had to be either recorded or reverted.

Recorded, not reverted. The instruction is load bearing rather than a drift: the validity test measures two directions, and a prompt asking only that the model add nothing leaves the completeness half firing on correct behaviour, because a model told only to avoid additions has no reason to preserve every clause. Reverting it would restore a hard gate that fails good decompositions. The exact shipped string is now written into Provider contracts.

One assumption in the original framing turned out wrong and is worth recording, because it changed the order of work. OD-3 was written as sequenced behind OD-1, on the reading that OD-1 `may change the same prompt`. It does not: OD-1 changes `ANSWER_SYSTEM_PROMPT` and OD-3 changes `DECOMPOSE_SYSTEM_PROMPT`. They are independent, and OD-3 is pure transcription.

## Options considered for the two open decisions and the schema ratification (2026-08-13)

Experiment 0004 ran the gate on the cleaned instrument and left two decisions owed plus one deviation to ratify. All three were settled the same day. Both open decisions came out of a single trace: the decision query answered, the sentence stating the decision had been dropped, and coverage covered the decision facet with a caveat instead. OD-4 is about the gate that could not see that; OD-5 is about the behaviour it failed to see.

### OD-4: the self corpus gate's oracle cannot detect a wrong answer

The manifest asserted `expected_record` (`DM-0008`) and `expected_state` (`answered`). Both were satisfied by an answer whose covering sentence was `The JobPilot corpus cannot establish that hybrid retrieval is better at scale, and it does not claim general retrieval superiority.` Record plus state cannot see answer content, which is the one thing this gate exists to judge. A second defect arrived with it: the same query returned different states across two runs on identical input, so the gate passes and fails stochastically as well.

**Co located citation plus an abstention cause, run as a battery under `evaluate` (chosen).**

Pros:

- It reuses an oracle that already exists and has already been hardened for this exact failure shape. `QueryOracle.required_value_path_prefixes` carries the co location rule, and its docstring records that "a prefix matched only by an unrelated citation does not satisfy the oracle" was closed in review. Reimplementing that rule in a bespoke gate script is how two builds end up with two subtly different oracles, which is the gap the AC-14 manifest pin exists to close.
- `decision.chosen` is a tight target rather than a nominal one: 6 chunks out of 244 in the fixture store, against 168 body chunks, and the caveat sentence that caused the false pass was not one of them. The assertion would have caught the observed failure.
- The abstention half closes the older and more common hole. Experiments 0002, 0003, and 0004 each recorded a query meeting an `abstained` expectation only because every draft sentence had been dropped. Naming the cause is what separates the behaviour being gated from a pipeline collapse that happens to look the same from outside.
- `run_evaluation` already takes its fixtures as a parameter and already runs each query `--runs N` times with per fixture rate reporting, so the run count and the bar come from machinery that exists. A standalone script would have had to re grow the adapt, ingest, run, and report plumbing beside it.
- The expectations stay in the manifest, outside `docs/specs/`, and the code now reads them from there rather than relying on a person copying them into a script. AC-14's property holds by construction instead of by discipline.

Cons:

- `evaluate` grows a way to load a battery from a file. That is genuine CLI surface plus a loader that can be wrong on its own.
- It asserts which chunk the answer must cite, not what it must say. An answer citing `decision.chosen` and still stating the wrong thing would pass.
- Requiring `decision.chosen` can fail a good answer that states the decision while citing a rationale chunk. Deliberate: that failure is visible and worth looking at, where the current silent pass is not.

**A hand written phrase list on the answer text (deferred, not rejected).** Assert required substrings the answer must contain.

Pros:

- It checks the thing the gate is actually about, what the answer says, and it would also have caught the observed miss (the caveat contains neither `lexical` nor `semantic`).
- Purely additive to the manifest shape, so adding it later costs nothing that doing it now would save.

Cons:

- It is a hand written content assertion that has to be maintained alongside the fixture, and a phrase list is a weak proxy for meaning in either direction.
- The failure it uniquely catches, a correctly cited answer that states the wrong thing, has not been observed. This spec has already paid once for pinning detail ahead of the measurement that would have shaped it (AC-11, twice). Recorded as a follow up with a named trigger instead.

**Keep the oracle and label the gate indicative (rejected).** Stop calling it a gate and have a person read the two answers.

Pros:

- Honest about what state plus record can prove, and costs nothing to adopt.

Cons:

- It gives up the only cheap gate this feature has, and this is the gate that falsified the previous build. A gate that cannot fail is not a weaker gate, it is a different thing.

**On the bar.** Two batches rather than one is not a preference. `verify.md` records query 2 going 0 of 3 then 3 of 3 on identical code, a whole batch flip, and the rationale summary at 2 of 3 then 0 of 3. A single batch would have reported either totally broken or totally fine, and both readings would have been wrong. The two halves then get different treatment on purpose. All seven existing 6 of 6 style bars in this spec are abstention gates; the decision query is the first that requires an answer, and the two are not equally hard, because a stochastic pipeline fails toward abstention. So the answering half's 6 of 6 is provisional and gets confirmed or relaxed from the first post calibration measurement, in the same way AC-9's 5 of 6 was set from observed query 1 variance rather than chosen. The abstaining half stays 6 of 6 unconditionally, matching AC-2 and AC-3 exactly.

**On the loud loader.** A missing key defaulting to no constraint would reproduce OD-4 itself: a gate silently running under a weaker oracle than the one written down. So every key is present on every query, including the ones that do not apply, and an unrecognized key stops the run.

### OD-5: coverage accepted a caveat as covering a decision facet

The other half of the same trace, and a defect in behaviour rather than in the gate that observed it. AC-12 already says a reason, context, consequence, premise, or anaphoric fragment cannot cover a decision facet unless that same sentence states the decision. A sentence about what the corpus cannot establish is a limitation, and coverage covered the decision facet with it anyway. The rule was specified and unstated: `COVERAGE_SYSTEM_PROMPT` never mentioned this case.

**State the exclusion, count the miss, hold the guard behind a number (chosen).**

Pros:

- The cheapest thing that could work had never been tried. The instruction listed four fragment kinds and did not name the one that walked through, which is the same gap experiment 0004 found and fixed on the coverage schema an hour earlier: nothing had ever told the model the rule.
- The measurement is free. A caveat covering a decision facet fails the AC-15 `decision.chosen` requirement by construction, so the OD-4 oracle counts OD-5's misses out of runs that were happening anyway.
- A numbered trigger (2 or more misses in the 6 runs after the change) makes the next step a reading rather than an argument. An unnumbered one is the undocumented judgment call AC-9 was rewritten to remove.

Cons:

- It leaves a specified rule enforced only by a prompt for now, which is the arrangement that already failed once.
- Two of six is a floor for acting, not a measured rate, and it rests on a gate that currently answers rarely, so the sample it draws from is thin.

**Add the deterministic guard now (rejected for now, not on principle).** Drop meta sentences at the generation boundary in the AC-13 hard guard plus soft guidance shape.

Pros:

- It is the pattern that worked for AC-13, and it was kept there precisely because prompt compliance was inconsistent.
- A deterministic guard cannot regress the way an instruction can.

Cons:

- Its false positive class is real and unsized. A decision can legitimately be stated negatively ("we decided not to use entry point discovery"), and a caveat blocklist cannot tell that from "the corpus cannot establish". One observed miss does not size a lexical rule.
- Building it now means designing it from a single example. Waiting means designing it from whatever the 6 runs actually record, which is the same argument that put task 13's calibration behind task 11's measurement.

**Accept and only measure (rejected).** Change nothing, count the misses.

Pros:

- Keeps the sample clean of any confound from the instruction change.

Cons:

- Leaves a known, already specified rule stated in no place the model can read, when adding it is one sentence. Measuring a miss rate you have not tried to fix measures the wrong thing.

### OD-6: the coverage schema description, ratified as instance and pattern

Experiment 0004 added a `description` to the coverage schema's `sentence_ids` property after the coverage model returned a correct uncovered verdict in an invalid shape on 4 of 4 attempts, turning a correct abstention into a hard `provider.coverage` failure. `validate_coverage` was left unchanged as the hard gate. Measured either side: 4 of 4 attempts rejected before, 0 of 3 after. The repair attempt was not already absorbing it, since both attempts failed every time before the change.

Ratified, instance and pattern. Reverting was rejected on the evidence: the rule was missing from the prompt and the field list alike, and moving it into `COVERAGE_SYSTEM_PROMPT` instead would put a field level rule in a task level instruction, further from the field it constrains. Ratifying the instance alone was rejected because it settles nothing; no other schema in `openai_generation.py` uses `description`, so the next one would arrive as an unreviewed build time choice.

Two bounds keep a description from becoming a shadow spec. It may only restate a rule a named validator function already enforces, and it may never be the only place a rule is stated. Together they make a description deletable: removing every one of them must leave every test outcome unchanged.

The bound needs an owner or it is prose nobody checks, which is exactly how AC-11 ended up described rather than pinned across two build cycles. `/check review` is that owner: every schema property description must name the validator enforcing the same rule, and the review names that function. For the ratified instance it is `validate_coverage`, whose uncovered row check does the enforcing.

### Cross check on the round two decisions (2026-08-13, Sonnet 5)

A read only cross check of AC-15, AC-16, and AC-17 against the code confirmed the mechanism claims that matter: `Citation` carries both `record_id` and `value_path`, so the co location rule is computable from a `QueryResult`; `run_evaluation` and the runner are generic over corpus root and fixture list and assume no re ingest fixture, so a query only battery works today; regenerating the manifest with new fields leaves the copied files and their hashes untouched; `decision.chosen` is one unit per record in the chunker, so the fixture's chunk count claim holds; and AC-17's bound does not conflict with the live behaviour change, because a description is provider facing metadata that no validator reads.

It found seven things, and all seven are now written into the criteria. Three were defects rather than omissions, and the reasoning is recorded because each is the kind of thing that comes back.

**The oracle was whole answer scoped while the miss rule was sentence scoped.** `_satisfies` scans every citation in the answer, so record scope is the only narrowing it does. That catches the failure actually observed, where no emitted sentence cited `decision.chosen` at all, and it stops catching it the moment calibration lets a second sentence through: a caveat could cover the decision facet while some other sentence supplies the required citation. That is OD-4 reproduced one level down, in the criterion written to close OD-4. The narrowing is applied to the manifest battery only, because changing the semantics under the eight live JobPilot fixtures to keep one shape would trade a documented difference for an undocumented regression in gates this spec is not otherwise touching.

**The abstention cause was vacuously satisfiable.** A retrieval stage abstention carries an empty coverage tuple, and every row of an empty tuple satisfies any test, so a query that abstained before generation ever ran would have been reported as the deterministic no sentence case. This is the same shape the re ingest oracle already had to guard against, and the codebase carries a comment saying so. The cause is now read only from a claim verification abstention with a nonempty coverage tuple; any other stage is neither cause and fails with that stage named.

**The AC-16 trigger could be structurally unable to fire.** With the decision query abstaining in every run, the miss count is 0 by construction, and 0 reads as though the instruction worked. The first draft called this a thin sample, which is the weaker and wrong claim: a thin sample updates as runs accumulate, and a counter gated behind an event that never occurs does not. The count is now a fraction whose denominator is the runs in which the decision facet was covered at all, and a zero denominator reports as not exercised.

The remaining four were gaps rather than errors, closed the same way the earlier cross checks closed theirs, by pinning what was described. The `evaluate` flag is named and the corpus root is derived from the manifest's parent rather than paired by hand, since a battery run against the wrong corpus fails on record ids and looks like a broken pipeline. The loader validates that each expected record exists and each prefix matches a chunk, because an unsatisfiable oracle fails forever and cannot be told from a real failure. The deterministic reason string gets a named constant before a third reader arrives. And a covered row may name several sentences, so a miss requires that none of them cites the decision statement.

Worth stating plainly, because it is the cost of this shape: the directness rule now lives in three places, AC-12, `validate_coverage`, and the schema description. Only one of them enforces anything, which is the right arrangement, and it is still three things that have to move together. **Corrected 2026-08-13, while settling OD-7.** That count was wrong in both directions and is kept here with its correction rather than rewritten, because it was the stated reason for pinning the description text. `validate_coverage` enforces only shape: facet id validity and order, sentence id validity and emitted order, duplicates, and the consistency between `covered` and `sentence_ids`. It has no directness check at all, and the ratified `sentence_ids` description restates one of those shape rules. Directness lives in two places, AC-12 and `COVERAGE_SYSTEM_PROMPT`, and is enforced nowhere. The argument for pinning the text survives the correction and gets slightly stronger: two unenforced statements of one rule drift, and nothing fails when they do. So the description text is still pinned here as a spec constant rather than left to the build, and the AC-16 caveat exclusion still gets no description of its own: no validator enforces it, so under the first bound it belongs in the instruction and nowhere else.

## Options considered for OD-7, coverage directness (2026-08-13)

Experiment 0006 set out to test whether AC-16's exclusion had over corrected, and rejected that hypothesis in both directions: removing the exclusion produced one coverage in 6 runs and that one covered with the caveat sentence, the OD-5 defect AC-16 was written to close. What it found instead is a fourth cause, alongside `not_additive`, inline markers, and over splitting. Against the frozen fixture, 11 sentences reached coverage across 6 runs and none covered the single decision facet, including one that reads as a direct, correct, well cited answer:

```text
S1: The hybrid retrieval system uses a combination of lexical BM25 and semantic
    Chroma retrieval, followed by reciprocal rank fusion to combine their
    contributions.

uncovered F1: What was decided about hybrid lexical and semantic retrieval?
```

The facet asks what was **decided**; the sentence says what the system **uses**. Coverage was applying AC-12 correctly and AC-12 never covered this case, since its exclusion list stopped at a reason, context, consequence, premise, or anaphoric fragment. So the decision splits in two: what the rule should say, and which stage should change.

The rule question was settled first, and the answer is no: a sentence stating what the system does does not state a decision. Relaxing that is the one direction the evidence already argues against, since a caveat is also a statement about the system and experiment 0006 measured what happens when this stage is loosened.

### Answer generation, with the evidence blocks labeled by field (chosen)

Pros:

- It uses a signal the pipeline already carries and drops. Every accepted chunk is an `ActiveChunkDescriptor` with `record_id`, `record_title`, and `value_path`; `query.py` forwards only `chunk.text`. The embedding side has rendered the title and value path above the same chunk text since spec 0007, through `embedding_input`. The asymmetry between those two paths is the concrete shape of OD-7, and closing it invents nothing.
- It leaves coverage alone, so the AC-16 caveat exclusion stays exactly as measured. The stage behaving correctly is not touched, and the stage feeding it badly is.
- It is aligned with what the fix is for. The goal is generation writing decision language rather than system description, and a label reading `the decision this record chose` is decision language. The alternative rendering, `decision.chosen`, reaches the same place only by inference.
- The answer improves for a reader, not only for the gate. A person asking what was decided currently gets a description and has to infer that a decision was made at all.

Cons:

- It changes model input, so every measurement taken over the previous phrasing is a reading of a different distribution. That includes task 13's 68 percent calibration target, which is why task 17 runs first and task 13 now begins by re reading.
- Decision framing may run longer and more clausal, which could raise `not_additive` rather than lower it. Plausible mechanism, not a measurement.
- It adds a mapping that has to track `chunking.py` as the record schema grows.

### `COVERAGE_SYSTEM_PROMPT` (rejected)

Pros: smallest possible change, one sentence, in the stage where the refusal happens.

Cons: experiment 0006 already measured this direction. Removing the AC-16 exclusion produced exactly one coverage in 6 runs, and it covered with the caveat sentence, reproducing OD-5. A caveat and a description are both statements about the system, so no wording reliably separates them, and the false positive class is the one AC-16 exists to prevent. Tightening instead is worse: under AC-4 whole sentence output, a real decision statement routinely carries a descriptive clause (`The project adopted hybrid retrieval, which combines BM25 with Chroma`), so an explicit description exclusion would reject the sentences this fix exists to accept. Adding it would also put directness in a third place while it is enforced in none.

### Facet extraction (rejected)

Pros: the facet becomes a question a generated sentence can answer, and no prompt downstream changes.

Cons: it changes the question the user asked. The gate's decision query means what it says, and rewriting `what was decided` into `what does the system use` makes the gate pass by lowering the bar rather than by fixing anything. It also puts the drift somewhere a reader of the answer cannot see it.

### Giving coverage the citations (rejected, and the sharpest of the four)

Pros: precise. A sentence citing a `decision.chosen` chunk is exactly the sentence a decision facet wants, and the signal is already computed.

Cons: it destroys the gate. The AC-15 co located citation check is the oracle's only defence against a caveat covering the decision facet, and telling coverage that citing `decision.chosen` is what makes a sentence state the decision hands coverage the oracle's own criterion. Any covered run would then satisfy the oracle by construction, and the gate would stop discriminating exactly where it was just strengthened to discriminate. It also merges grounding into directness, which the code keeps apart: coverage receives the question, the facets, and `S1: text`, and nothing about citations.

### The label rendering: plain words, not the dotted value path

This sub decision is where the chosen option could still have failed. `sentence_tokens` splits on whitespace and strips only edge punctuation, so `decision.chosen` survives as one token with its internal dot. An echoed label in a draft sentence therefore enters `parent_tokens` as one content token a decomposition has no reason to carry, and the response fails the completeness half. AC-13 calls the chunk id case unconditional, which is right for a 64 hex hash; a dotted path is a shade more reproducible than a hash and far less than a word, so call it near certain. Either way it is the AC-13 failure in a new class.

A strip cannot close it the way AC-13 does. AC-13's regexes work because `ch_` plus 64 hex cannot occur naturally; a dotted value path is lexically indistinguishable from ordinary prose (`adapter.py`, `U.S.`), the value path grammar is an open pattern rather than a closed list, and a hardcoded alternation would have to track the canonical schema forever. It is a second strip class strictly harder than the first.

Plain words make the failure class not exist rather than catching it: every token of `the decision this record chose` is ordinary vocabulary a decomposition reproduces, and the stem rules already cover `chose` against `chosen`. The residual risk is stated rather than hidden, and the first draft of this section understated it. Prose labels read as content, so they may bleed into sentences more readily than a dotted token would, and a bleed is **not** merely cosmetic: a leaked label's words are content tokens (`decision`, `record`, and `chose` all sit outside the closed function word set), so a decomposition that treats the leaked phrase as scaffolding and omits it fails completeness and drops the whole parent, which is the same outcome by the same mechanism. What plain words buy is probability, not immunity. A hash is a token a decomposition essentially never reproduces; ordinary words are ones it usually does, especially under a prompt already telling it to cover every clause. So the risk drops sharply, the failure mode is unchanged, and the Follow-up item counts both the bleed rate and how many of those sentences ended as `incomplete`, from the kept traces.

A second risk runs the other way and was missed until the cross check. Telling generation to state a decision pushes it toward assertive phrasing, and a hedged source chunk can be overclaimed into an unhedged decision statement that comes back `unsupported` and drops its parent. That is the mirror image of the `not_additive` worry, equally speculative, and it gets the same treatment: experiment 0007 records the entailment verdicts of sub claims from decision framed sentences, which the trace already carries at no extra cost.

The mapping is nine entries, not more. A chunk's `value_path` is set in one place from nine `add()` calls. `title` and `supersedes` appear only in the missing field source check and never become chunks; `decision.alternatives[i].title` and `.rejection_reason` are source paths whose chunk carries `decision.alternatives[i]`. Pinning thirteen would ship four entries no chunk can carry.

### `record_title` withheld

Considered and rejected on trust, not cost. The title is adapter extracted corpus content, at the same trust level as the chunk text, and the evidence block is already fenced to the model as untrusted with an explicit instruction to ignore instructions inside it. Giving a corpus derived string authority inside that fence adds injection surface for no gain. `value_path` is different in kind: a closed vocabulary this project's own chunker produces.

### Proving it: coverage conditional, not the gate verdict

`EvaluationOutcome` carries checks, passed, failed, and an exit code. The answering half fails both when coverage refuses a good sentence and when no sentence survives verification, so a failing gate cannot attribute the result, and experiment 0006 broke that same confound by counting sentences reaching coverage separately. Experiment 0007 therefore measures per run, at sentence level as well as run level, and keeps the AC-15 co location check in the same batches so the caveat control is measured at the same time. A proof reporting only the positive half would repeat the instrument mistake experiments 0003 and 0004 were written to correct.

The numerator is a semantic judgement no validator can produce, so it is labelled the human half, its rule is written before the runs, and every judged sentence is quoted verbatim, as experiment 0006 did with S1 and S4. That is what makes finding 2 of experiment 0006 still checkable, and it lets a later reader re judge the same sentences and disagree.

`classify_query4_failure` is not extended. It returns `None` for a trace with separate facets, the decision facet uncovered, and an abstained result, which is the correct reading for query 4, an abstention gate, and is exactly OD-7's shape on a query where answering is expected. Overloading it would need a mode flag to keep its query 4 semantics, and AC-15's abstention cause already separates `no_emitted_sentences` from `uncovered_facet`, so the classifier would restate what the oracle reports and still could not judge whether a sentence states the decision.

### The `not_additive` split, instrumented in the same task

Not a separate decision so much as a constraint the trace imposes. `sub_claim_is_additive_free` returns `False` on the first unmatched content token, while `MAX_ADDED_FUNCTION_WORDS` bounds only function word additions, so the tolerance knob reaches one of the two causes and not the other. The 68 percent has never been split, which means task 13's headroom is unmeasured and may be well below its stated target.

It cannot be recovered afterwards: `RejectedDecomposition` records a sentence id, a returned count, and a disposition, and records no claim text by deliberate rule. So the split has to be instrumented before the runs that measure it. It lands in task 17 rather than task 13 because the instrument is purely observational, changing no disposition, no retry, and no drop, so there is nothing to contaminate; because a second set of runs would put the two figures in two provider sessions, reintroducing the session drift experiment 0006 records in its own threats to validity; and because the answer may reshape task 13, which is better known early than at the point the plan already treats calibration as the critical path. A closed category rather than text keeps the no claim text rule intact, and a defaulted trailing field follows the AC-10 precedent.

### The chunk id notation, held deliberately

`ANSWER_SYSTEM_PROMPT` says ids are copied exactly as shown in brackets while generation renders them in parentheses. The mismatch is real, and task 17 rewrites that very block, so the hold is written into the task as an instruction: an implementer would otherwise harmonize it as an obvious tidy up and the decision would vanish with no record.

Deferring is safe because `validate_draft` hard rejects any cited id outside `known_chunk_ids`, so the invented id failure the bracket wording guards against surfaces as `provider.answer` rather than passing silently, and no such failure appears in experiments 0004, 0005, or 0006. The wording is inaccurate about the rendering, not load bearing in practice, because a hard validator sits underneath it.

Deferring is right because experiment 0007 needs one changed input. Both fixes are worse than neutral right now. Rendering brackets would put the literal `_MARKER_GROUP_RE` shape in front of a model that already echoes markers without ever having seen them modelled. Rewording the prompt would edit the input actually driving model behaviour, and AC-13 pinned the bracket wording on a live observation that dropping it makes a model invent its own ids. Stated narrowly: a higher echo rate would not perturb `not_additive` itself, since the strip runs before the other `validate_draft` checks, but it would move the duplicate collision rate task 9 recorded and the whitespace repaired prose the human half judges.

One correction that came out of settling this, recorded because the reasoning it corrects was used in this decision: the 11 of 20 marker figure from experiment 0003 is the baseline from **before** any prohibition existed. `git log -S` places the sentence forbidding a chunk id in the sentence text in the task 9 marker strip commit, after experiment 0003 measured. It shows the echo happens, not that a prohibition fails to stop it, and the post prohibition rate has never been measured because the strip removes markers before anything records the text. Any future argument about whether a prompt prohibition suffices has to start from that absence of evidence.

### The reader's rule for the human half (written 2026-08-13, before task 17 ran anything)

AC-19 requires this rule to exist before the runs, and to be written by whoever runs task 17. It was written by the `/develop` session that built task 17, authorized by the engineer, and committed before the first batch was started; the commit order is the check on that claim, not this sentence.

**What is being judged.** One question, applied to one emitted sentence at a time: *does this sentence state the decision the record chose?* Nothing else. Not whether the sentence is true, well cited, well written, or relevant.

**What the reader may look at.** The sentence text verbatim, the query, and that query's facets. **Nothing else**: not the coverage rows, not the abstention cause, not the citations, not the drop reasons, not the record the sentence came from. The whole point of the human half is to be an independent reading of the same sentences the coverage model judged, and a reader who has already seen coverage's verdict is reading that verdict back. So the verdicts are written down first and the machine half is joined to them afterwards, per run.

**The three verdicts.**

- **`states_decision`**. The sentence asserts that a choice was made and names what was chosen, both in that one sentence. Phrasings that qualify: *X was chosen*, *the project adopted X*, *the decision was X*, *X was selected over Y*. A decision stated negatively qualifies (*entry point discovery was deliberately not used*), because a decision can legitimately be stated as a refusal. Extra clauses do not disqualify it: a decision sentence routinely carries a reason, a caveat, or a description of how the chosen thing works (*The project adopted hybrid retrieval, which combines BM25 with Chroma*), and under the AC-4 whole sentence contract that compound shape is the normal one. What matters is that the choice and its content are both present.
- **`does_not`**. The sentence does one of: describe how the system works or what it consists of (*The hybrid retrieval system combines lexical BM25 with semantic search*), give a reason, state a consequence, state a limitation of the evidence, or refer to a decision without saying what it was (*a decision was made about retrieval*). The description case is the central one and the one OD-7 is about: it says what exists, never that anything was chosen.
- **`ambiguous`**. The rule does not clearly place it. Two cases are named in advance rather than discovered: (1) a choice is named but no chooser and no choosing verb appears, so the sentence reads equally as description (*Hybrid retrieval is used for the query pipeline*); (2) the sentence clearly states a decision, but a different one from the one the facet asks about. Anything else the rule does not place is also `ambiguous`.

**Why a third verdict at all.** A forced call is the undocumented judgement AC-9 was rewritten to remove. An `ambiguous` count is also a reading of how well this rule was written: a large one means the rule, not the pipeline, is what needs another pass.

**What makes it checkable.** Every judged sentence is quoted verbatim in experiment 0007's per run records, so a later reader can apply this rule to the same sentences and disagree. That is the closest a semantic measure gets to reproducible, and it is the standard experiment 0006 set when it quoted S1 and S4.

### The AC-16 caveat miss count, recorded (2026-08-13, from the task 17 runs)

AC-16 requires the count to live here, as a fraction with its denominator, whenever the gate runs after the instruction change.

**Numerator 0, denominator 0. Not exercised, so the trigger fires nothing and the instruction stands.** The decision facet's coverage row came back uncovered in all 6 runs, so no run had a covered decision row for a caveat to have wrongly covered. The AC-12 escalation count, coverage covering a decision facet with a sentence that only describes what the system does, is 0 over 0 for the same reason and is equally unexercised.

The denominator is zero for a different reason than the one experiment 0005 recorded, and the difference matters more than the repeated zero. There, coverage ran in every run and refused 11 sentences, the caveat among them. Here **coverage judged nothing at all**: every draft sentence was dropped before it, so the deterministic no sentence path applied in all 12 runs. A reader comparing the two zeros should not read them as the same observation twice.

This is the second consecutive measurement where AC-16's trigger cannot fire. That is not evidence the guard is unnecessary; it is evidence the pipeline has never put the guard in a position to be needed. The count stays unreadable until the answering half starts landing, which experiment 0007 finding 3 shows is blocked on retrieval rather than on anything AC-16 or AC-18 touches.

## The additive matcher (2026-08-14, OD-8)

The question put to `/architect` was whether the AC-11 verification guard should adopt `morphology-v1`, the
canonicalizing stemmer spec 0011 pins for lexical retrieval, instead of the pairwise matcher. The answer is no, and a
third option was taken instead.

### What was measured, and over what

Every figure below was measured over **3,690 distinct content tokens**: all lowercase word tokens appearing three or
more times across `docs/**/*.md` in this repository, with the AC-11 function word set removed. That is 6,806,205
unordered pairs. The corpus is this project's own prose, chosen because it is the closest available proxy for the token
stream the matcher actually sees (draft sentences are generated from chunks of decision records written in the same
register), and because it needs no provider call. It is not the JobPilot corpus, and that is the main limit on these
numbers: see *Limits* below.

Three matchers were compared. `_stem_match` as shipped. `morphology-v1` exactly as pinned in spec 0011's
*The canonicalizing stemmer* section, two tokens matching when their canonical stems are equal. And the base set
intersection now written into AC-11, which inverts the same five rules to the set of `shorter` values each token could
have been derived from, and matches when the sets intersect.

| | fixes the defect class | loses a pair the shipped matcher accepts | new false matches |
|---|---|---|---|
| `_stem_match` as shipped | 0 | (baseline) | (baseline) |
| `morphology-v1` | 650 pairs | **30** | **28** |
| base set intersection | 622 pairs | **0** | **0** |

The base set losing nothing is not a measurement result, it is true by construction: if `longer` equals `shorter` plus
a suffix under one of the five rules, then `shorter` is in both base sets, so every pair the directional form accepted
the intersection also accepts. The measurement confirms the implementation matches the construction.

### Why `morphology-v1` was rejected

Two mechanisms, both traced against the pinned algorithm:

```text
lost, because at most one suffix is stripped and there is no second pass
  settings -> strip s   -> "setting"        (no further step applies)
  setting  -> strip ing -> sett -> doubled  -> "set"          unequal
  and these two DO match under the shipped pairwise rules

lost, because the character floor is measured on the input and never on the output
  needs -> strip s  -> "need"
  need  -> strip ed -> ne -> drop final e   -> "n"            unequal

invented, because the tail rules converge two different words
  file -> ends in e, drop it       -> "fil"
  fill -> doubled ll, drop one     -> "fil"                   false match
  site -> "sit"  ;  sits -> strip s -> "sit"                  false match
```

The 28 false matches are what actually decide it. The additive half exists to stop a substitution, and it is the guard
standing behind **AC-2**, the fabrication gate, which [experiment 0008](../../experiments/0008-first-live-jobpilot-run-since-the-build.md)
records passing 6 of 6 across two live batches. AC-2 is the only criterion in this chain currently green on live
evidence. Twenty eight false matches means twenty eight substitutions the guard would begin to accept, and buying the
answering win by spending the fabrication win is the worst outcome available. The base set adds zero, so the guard's
strength is provably unchanged rather than argued to be acceptable.

### Why the base set, and why this is a correction

[Experiment 0010](../../experiments/0010-falls-against-falling.md) left the fix open, noting that the obvious direction,
reducing both tokens to a common stem, is precisely the over stripping the pairwise design deliberately avoided, and
that the false match risk behind that choice had never been measured. It has now been measured, and the framing it
assumed turns out to be a false choice: reducing to a common stem is not the only way to reach a common base. Inverting
the existing rules reaches one without ever producing a lossy stem, which is why it fixes 622 pairs while adding no
false match. The over stripping trade is avoided, not accepted.

That is also why this amends AC-11 in place. AC-11 already read "two tokens match when they share a stem", and
`_stem_match`'s own docstring read "true when two content tokens share a stem". Sharing a stem is symmetric. The five
enumerated rules implemented something directional, so `falls` and `falling` never reached `fall` and never matched.
The base set makes the implementation do what the criterion already claimed. Under this project's standing rule, a new
spec number or a supersession would put a decision shape in the corpus this tool reads for a decision nobody made.

### The rejected third option

A hand enumerated inflection bridge, adding just the participle to finite pairs the defect needs (`-s` against `-ing`,
`-s` against `-ed`, `-ed` against `-ing`) on top of the existing matcher. Rejected: enumerating surface pairs is the
same defect one layer up, and the next inflection gap would need another enumeration. The base set derives the same
pairs from rules already agreed rather than listing them.

### A correction made during this design, recorded rather than dropped

The first direction taken on the retrieval side was to fix `morphology-v1` by applying its rules until stable **and**
raising its output floor from two characters to three, on the reasoning that the floor is what makes a second pass
safe, since `singing` would otherwise strip twice to `s`. The floor half was wrong, and the measurement is what caught
it:

| candidate | property violations | implication violations | normative drift |
|---|---|---|---|
| `morphology-v1` as pinned | 277 | 30 | 0 |
| rules until stable, floor 2 | **0** | **0** | 1 |
| rules until stable, floor 3 | 10 | 7 | 3 |

The existing two character floor already refuses the unsafe strip, because taking `ing` off `sing` would leave one
character. Raising it to three bought nothing and broke `use` against `using`, which is one of the algorithm's own
normative examples: at a floor of three, `using` cannot strip to `us` and `use` cannot drop its `e` to `us`, so the
pair that motivated that rule stops agreeing. Applying the rules until stable, with the floor left at two, is the whole
fix, and it holds the property exactly at 0 violations. The one normative drift is `chose`, which reaches `cho` rather
than `chos`; it is tracked as a Follow-up against spec 0011's table.

### What this says about spec 0011 AC-7

AC-7 requires a property test asserting that a true pairwise match implies equal canonical stems. **That property is
false as specified**, before any change made here, and the test would have failed on first contact with real text.
There are 30 counterexamples in this repository's vocabulary, and they are the same 30 pairs the table above records
`morphology-v1` losing: the data was already in hand, it had simply not been connected to the property.

Base set agreement is also false, in both directions, and for two independent reasons:

```text
the canonical stem need not be in the base set
  falls    base set {falls, fall}   canonical stem "fal"
  because step 3 drops a doubled letter unconditionally, and fall's ll is
  part of the word rather than an inflection

canonical equality need not imply a base set match
  file / fill   canonical stems both "fil"
                base sets {file} and {fill} never intersect
```

The direction that holds is the implication: **a base set match implies equal canonical stems**, verified on every
fixed pair (`falls` and `falling` to `fal`, `setting` and `settings` to `set`, `need` and `needs` to `ne`). The
converse deliberately does not hold, the same shape AC-7 originally intended with the base set substituted for the
pairwise form. The converse failing on `file` and `fill` is not a defect: it is exactly the over stripping verification
must not inherit and retrieval can tolerate, which is the entire reason the family has two entry points. So AC-7's one
family constraint survives and is worth keeping, with the property restated as the implication.

### The completeness half widens too, and it was checked rather than assumed

Both halves of the AC-11 validity test match through `tokens_match`, so this amendment reaches
`response_is_complete` as well as `sub_claim_is_additive_free`. That direction matters more than the additive one,
because completeness is the half that catches the AC-1 omission attack, where a decomposition quietly drops the
fabricated clause and returns only the grounded one. A broader matcher passes completeness more often, which is a
loosening of a safety guard inside a change whose whole argument is that it loosens nothing unsafely.

Checked against the shipped fixture and the base set matcher. The attack still fails, and it fails on `accepted`,
the omitted clause's own verb, which finds no match anywhere in the response:

```text
parent    The board approved the merger on Tuesday, and the board accepted
          a bribe to rush it.
response  The board approved the merger on Tuesday.
verdict   incomplete, first unmatched parent token "accepted"
```

Then checked against cases built specifically to exploit the widening, where the omitted clause shares an inflected
verb with the clause that survives, which is exactly the pair the base set now joins and the directional form did not:

```text
parent    The system drops the record and the system is dropping the audit log.
response  The system drops the record.
verdict   incomplete, first unmatched parent token "audit"

parent    The gate blocks the answer and the gate blocked the fabrication.
response  The gate blocks the answer.
verdict   incomplete, first unmatched parent token "fabrication"
```

The shared verb is matched now where it was not before, and the clause is caught anyway, on its own distinctive
noun. That is the general shape: a clause carries content words the rest of the sentence does not, and those are
what completeness fails on.

**The residual risk is named rather than closed.** An omitted clause every one of whose content words is an
inflection of a word surviving elsewhere in the response would pass completeness now where it previously failed.
No such case has been observed in any experiment or constructed here, and the class is narrow, but it is a real
consequence of the amendment and it is recorded as one rather than argued away. Task 18 re runs both AC-1 attack
tests against the new matcher for this reason: a task that loosens a guard carries the safety test, not only the
capability test.

### Why the verdict is a dataclass and not a four value tuple

Carrying `failure_token` for both halves needs a return slot neither half check has left.
`sub_claim_is_additive_free` spent its one signature change on the AC-19 category, and `response_is_complete`
returns a bool. The obvious minimal move is to widen `classify_decomposition_detail` from
`(disposition, additive_failure)` to a four value tuple, and it was rejected.

Three of those four values are closed vocabularies, and all four are strings. A positional tuple of same typed
values whose meaning is carried only by slot order is a defect this project has already shipped: commit
`004dc3c`, "read value_path and fingerprint from the right chunk columns", was two adjacent strings read in the
wrong order. Mypy could not see it, because a `str` in the wrong slot type checks perfectly, and the evaluation
harness is what caught it. Adding two more slots to the same shape is the same bug with more room.

So `classify_decomposition_detail` returns a frozen `DecompositionVerdict` with the closed sets pinned per field,
and `failure_token` as its one free string, which stays a token rather than claim text.

The refinement that matters more than the choice of shape: **`classify_decomposition` is derived from
`classify_decomposition_detail`, returning `verdict.disposition`, and is never a parallel implementation.** The
existing code already documents itself this way ("this is the thin half of `classify_decomposition_detail`: one
implementation, so the disposition and the AC-19 category can never disagree"), and the amendment must not lose
it. Two functions computing one verdict independently is exactly the second traversal AC-19 rejected, and
experiment 0010's instrument is the standing evidence that a replica walk really does diverge: its cross check
caught a disagreement on its first run.

`DecompositionVerdict` and `RejectedDecomposition` stay separate. The first is the internal result of one
classification; the second is the trace record built from it, and its two new fields are defaulted under the
AC-10 precedent so an older constructor call stays valid.

### Why the comparison script lands before the matcher

The 622, 0, and 0 figures are the safety argument for this amendment, and AC-2's guard strength rests on them.
Merging the matcher on a scratch measurement would ship a guard loosening change on a number nobody can
re derive. This spec has run that sequence twice already for weaker reasons: tasks 9 and 10 before task 11, to
clean the instrument before measuring with it, and task 16 before task 15, because a count taken before the
instruction change measures nothing.

That order has one wrinkle worth settling explicitly rather than leaving to the build. The figures are a
**comparison**, so re verifying them needs both matchers callable. A script landing strictly before the matcher
exists would have to carry its own copy of one side, which is the replica problem experiment 0010's instrument
had to cross check against. The resolution is that **`_stem_match` is not deleted**. The base set becomes what
the AC-11 guard uses, and the pairwise form stays in the shared module as the relation the base set is the
closure of, called by the instrument and its tests. The script then imports two shipped entry points, no replica
exists anywhere, and the claim stays re verifiable after the merge rather than only at it.

### Limits

- **One corpus.** 3,690 tokens of this project's own prose. A different corpus could hold a pair these five rules join
  wrongly, and the zero false match figure is evidence rather than proof. The live batches in task 18 are what confirm
  AC-2 still holds.
- **Pair counts are not drop counts.** 622 fixed pairs is a property of the matcher, not a prediction of how many
  sentences stop being dropped. The gate is the abstention clearing on `query-2-resume-generation`.
- **The expected reach is all 18 drops, not 7.** Both halves of the AC-11 test match through `tokens_match`, so this
  amendment reaches the 11 `incomplete` drops as well as the 7 `not_additive` ones experiment 0007 recorded. Reading the
  effect against the `not_additive` share alone would use the wrong denominator.

## The completeness exemption (2026-08-14, OD-9)

[Experiment 0012](../../experiments/0012-the-other-three-abstentions.md) attributed the three failing fixtures experiment
0011 left untraced. Two of them stop the same way query 2 does, and the third does not belong to this decision at all.

| Fixture | Disposition | Side | Token | Stable |
|---|---|---|---|---|
| `query-2-resume-generation` (from [experiment 0011](../../experiments/0011-where-the-matcher-stopped-next.md)) | `incomplete` | parent | `where` | 3 of 3 |
| `query-1-private-beta-gate` | `incomplete` | parent | `while` | 2 of 3 |
| `assertion-rationale-summary` | `incomplete` | parent | `instead` | 3 of 3 |
| `query-3-provisional` | none, no decomposition rejected | | | 3 of 3 |

### Three categories, one function

`where` is a relative adverb, `while` is a subordinating conjunction, and `instead` is a conjunctive adverb sitting inside
the complex preposition `instead of`. They share no part of speech. What they share is a job: each one relates one clause
to another, and `DECOMPOSE_SYSTEM_PROMPT` asks for exactly the transformation that dissolves the relation. Splitting a
sentence into standalone atomic sub claims is what removes the need for the word, so no sub claim carries it, and the
completeness half then demands a match for a token the decomposition was right to drop.

This is the third form of one defect. Experiment 0010 found it in morphology, where making a participle finite is what
decomposition requires. Experiment 0011 found it in set membership for one word. Experiment 0012 finds that the membership
question is not about one word and not about one category.

The current set already carries most of this family: `and`, `but`, `or`, `nor`, `if`, `because`, `as`, `that`, `which`,
`when`, `then`, and `so` are all in it. The gaps are arbitrary rather than principled. `which` is exempt and `whose` is
not. `when` is exempt and `while` is not. `of` is exempt, which is why `instead of` looks half exempt already. Nobody
chose those boundaries; the set was written as a list of common short words and the family was never named.

### Why a rule and not three more words

Adding `where`, `while`, and `instead` is the growth by failure pattern experiment 0011's own follow-up warned against.
The next failing token is `whose` or `although` or `however`, and learning each one has a measured price: experiments
0009, 0010, 0011, and 0012 each cost a live batch to learn a single token, and rejected claim text is never recorded, so
the value is not recoverable after the fact. Four experiments to learn four words is the argument for a rule.

### The three candidate rules

**Clause connectives, enumerated now (chosen).** A word is exempt from the completeness demand when its job is relating
one clause to another, so that a decomposition into standalone clauses leaves it nothing to do. The set is enumerated
exhaustively today from four closed grammatical categories: coordinating conjunctions, subordinating conjunctions,
conjunctive adverbs, and relative or interrogative pro-forms, plus the correlative markers. The rule is decidable without
the next failure, by construction rather than by observation: take the sentence, split it into standalone one clause
statements, and ask whether the word has anything left to do. It covers all three measured tokens and closes the `whose`
gap that `which` already being exempt leaves open.

**The whole closed word class (rejected).** Exempt every word belonging to a class you cannot add a member to by coining
one: determiners, pronouns, auxiliaries, prepositions, conjunctions, particles, quantifiers, degree words. It is the most
mechanical test available and it subsumes the current set cleanly. It was rejected because it exempts for a reason that
does not apply. A quantifier is not dissolved by decomposition: `all records are indexed` splits into sub claims that keep
`all`, and the same holds for `every`, `more`, `than`, `without`, and `during`. Those words survive a split intact, so
their absence from a sub claim is a real omission and the completeness half should keep demanding them. Exempting them
would give up reach the omission guard did not have to give up, and quantifiers are truth conditional in the way negation
is, which is a class this spec already carries as accepted risk rather than one to widen further.

**The three measured tokens (rejected).** Smallest possible change and precisely what was measured. Rejected as the growth
by failure pattern above: it buys one live batch of progress and owes another decision to the next token.

**A completeness side tolerance (rejected, added to this record after a cross check found it missing).** The symmetric
design: give the completeness half a budget of unmatched parent content tokens per response, the way
`MAX_ADDED_FUNCTION_WORDS` gives the additive half a budget of unmatched function word instances. It needs no enumeration
to write or maintain, no second vocabulary for a reader to track, and no per word judgement like the `provided` exclusion,
so it is genuinely simpler on every axis this record has been weighing. It was missed on the first pass and it deserves
its rejection in writing rather than by omission.

It is rejected because it is untargeted in exactly the direction that matters. A budget tolerates the omission of **any**
N parent content tokens, which includes the nouns of a fabricated clause. That is the AC-1 omission attack: the attack
works by dropping a clause, and a check that permits dropping up to N content words permits it directly. The connective
exemption cannot be used that way, because it names words rather than a count, and every noun, lexical verb, and adjective
stays demanded however many of them the response omits. The two options are not the same trade at different sizes; one
gives up a bounded and named class, the other gives up an unbounded and unnamed one.

It also has no principled setting. `MAX_ADDED_FUNCTION_WORDS` is 2 and task 13 has been queued to calibrate it since
2026-08-12 without ever reaching it, because the drop causes kept turning out to be things a tolerance does not reach. A
second uncalibrated knob on the safety critical half would repeat that with worse consequences. And it would answer the
question experiment 0012 asked with a number rather than a rule, which is what the follow-up asking for a membership rule
was written to avoid.

### Ambiguous words, and the two exclusions

Many closed class words have a second use, and the completeness half reads a bare token, so it cannot tell which use is
present. Two exclusion rules decide those cases, and both are part of the membership rule rather than taste applied to it.

**A word whose primary use is a content word stays a content token**, even where grammar lists a connective use for it.
That keeps `provided`, `given`, `granted`, `considering`, and `seeing` out. `provided the record exists` is a real
subordinator in English, and `the adapter provided the record` is far more likely in this corpus, so exempting it would
trade a rare relating use for a common content one.

**A word whose second use is truth conditional stays a content token.** This is the same test that rejected the whole
closed word class, and the first draft of this enumeration failed to apply it to its own members, which a cross check
caught. It keeps out `once`, `still`, `further`, `finally`, `specifically`, `similarly`, `after`, `before`, `since`,
`till`, `until`, `than`, `except`, `besides`, `both`, `either`, and `neither`. The clearest case is `once`: `the check runs once` decomposes into `the
check runs`, and nothing else in that clause carries the frequency, so `once` is doing a quantifier's work, and
quantifiers surviving a split intact is precisely why the closed class option was rejected. `still` marks continuation,
`further`, `specifically`, and `similarly` mark degree and manner, `finally` marks time, `than` carries a comparison,
`except` and `besides` carry an exclusion, and `after`, `before`, `since`, `till`, and `until` are also prepositions,
which is the `without` and `during` shape by another name.

Seventeen words removed by that second rule out of a first draft of sixty five is a high error rate for a rule its author
had already written down, and it took **two** passes to reach: a cross check found fourteen, and the engineer's review
then found the three the cross check and the author had both missed, `both`, `either`, and `neither`. That second miss is
the more instructive one. All three had been filed under a category name, correlative markers, and the category label did
the thinking that the rule was supposed to do; nobody re asked what `both` costs when the split drops it. It is recorded
rather than smoothed over, because the lesson is not that the rule was wrong but that a category row is a place a member
can hide from the rule, which is precisely the failure mode this whole decision exists to replace.

**The one member whose exclusion has a real cost is `both`**, and it is worth stating plainly rather than filing under a
rule. Its two uses point opposite ways. The correlative use is genuinely dissolved: `the pipeline uses both BM25 and
Chroma` splits into two sub claims that each name one retriever, and neither has anything left for `both` to do, so
excluding it means that sentence can be dropped as `incomplete` on `both`. The quantifier use genuinely carries content:
`both options were rejected` loses the count and the exhaustiveness. The exclusion takes the second reading, because the
stated safe direction for this set is to err toward dropping a sentence, and because a spurious drop is visible in the
trace while a permitted omission is not. It is expected to cost live drops, and `failure_token` is already pointed at it,
so this is the one member of either list that should be revisited on evidence rather than on the rule.

What survives ambiguity is the narrower class where the non relating use carries no truth conditions of its own: a dropped
clause `whereas the adapter shipped` still owes `adapter` and `shipped`, so the connective is not what catches it.

### Why the two halves get separate sets

Experiment 0012 established that every measured AC-11 failure is `failure_side=parent`. The additive half is implicated by
nothing measured, and it is the guard standing behind AC-2, the only criterion in this chain green on live evidence at 6
of 6.

A single shared set would convert each connective from budgeted to free on the additive side. Today a sub claim may add up
to `MAX_ADDED_FUNCTION_WORDS` unmatched function word instances and fails past that bound; a set member is not counted at
all when it finds a parent match, and when it does not it consumes budget rather than failing outright. Moving 48 words
into `FUNCTION_WORDS` widens that tolerance for no measured reason. That is the same trade OD-8 refused when it rejected
`morphology-v1` over 28 invented matches, and refusing it twice for the same reason is consistency rather than caution.

So the exemption is a skip list on the completeness traversal only. `tokens_match` is not touched, which matters more than
it looks: the matcher is the one function both halves share, and every previous amendment to it had to argue its way
through the safety critical half. This amendment does not reach the matcher at all, so that argument does not have to be
made again.

The asymmetry has one visible consequence, recorded rather than discovered later. A connective outside `FUNCTION_WORDS` is
still a content token to the additive half, so a sub claim that introduces `while` with no parent match still fails as
`not_additive` and reports `content_token` rather than `function_word_overrun`. That is the intended reading: a
decomposition adding a clause relation the parent never had is adding content. It is also unlikely, since decomposition
pulls clauses apart rather than joining them, and the `failure_token` field records it if it ever happens.

### What this does to the omission attack

The completeness half is the safety critical direction, and this widens it. The honest statement of the cost is that an
omitted clause every one of whose words is a connective or an existing function word would now pass where it previously
failed.

**The first draft of this section bounded that wrongly, and the correction is recorded rather than quietly swapped.** It
said such a clause carries no proposition, because a clause needs a lexical verb or a predicate and neither is exempt.
That is false, and its own example falsifies it. `FUNCTION_WORDS` already exempts the copulas (`is`, `are`, `was`, `were`,
`be`, `been`, `being`), the auxiliaries, the modals, and the negators (`not`, `no`, `never`, `nor`), so a copula plus a
negation is a complete predication built entirely from exempt words. `which it was not` is a negated identity, which is a
proposition, not an empty fragment. Using a newly added member, `although it was not` is the same shape one door further
in. A cross check caught this; it is corrected here rather than in place because a wrong safety argument that gets silently
replaced by a right one leaves no record that the wrong one was ever relied on.

The true bound is narrower and it is the one that matters for AC-1. The attack this half exists to stop hides a fabricated
decision inside an omitted clause, and a fabricated decision names an entity, an action, or a property. Every word that
names one is a noun, a lexical verb, or an adjective, and none of those is exempt under either rule. So the attack cannot
be built out of exempt words, which is a claim about the attack rather than a claim about propositions in general. What is
genuinely given up is the class of assertions expressible with copulas, auxiliaries, modals, negators, and connectives
alone, and that class already existed before this amendment; what this adds is more syntactic doors into it. The
constructed test in task 19 is a negated copula for exactly this reason, since a test built from filler would exercise a
weaker case than the amendment creates.

This is a stated bound, not a proof, so task 19 re runs both AC-1 attack tests against the widened exemption and adds a
constructed case in the new class, exactly as task 18 re ran them against the widened matcher rather than assuming they
survived it.

### Query 3 is not this decision

`query-3-provisional` rejects no decomposition and drops no sentence in any run. It abstains because facet extraction
promoted the contrast term in `provisional rather than ratified` to a second facet the answer must satisfy, and because
that facet inverted between runs on identical input (`Which decisions are ratified?` in runs 1 and 3, `Which decisions are
not ratified?` in run 2). Attributing it to the function word set would be wrong, and it is enrolled as a follow-up rather
than folded in here.

### Limits of the evidence behind OD-9

- **First causes, not all causes.** `failure_token` is where the check stopped in token order. Removing `where`, `while`,
  and `instead` from the picture does not establish that these three sentences pass, which is exactly what happened when
  `falls` gave way to `where`. The gate for task 19 is the abstention clearing, not the absence of drops.
- **Three sentences.** Each token comes from one draft sentence on one question. Three fixtures agreeing on a mechanism is
  stronger than experiment 0011's one, and it is still three sentences.
- **No corpus wide count.** Nothing measures how often a connective appears in a generated sentence across the corpus, so
  the size of the win is unmeasured and 48 words is a count of the set, not a prediction.
- **The set is enumerated from grammar, not from this corpus.** Most of its 48 members have never been observed failing
  here and some may never occur. That is the point of enumerating ahead of the failure, and it is also why the count is
  large relative to the evidence behind it.

## Granularity, cause, and denominator (2026-08-14, OD-10 to OD-12)

[Experiment 0013](../../experiments/0013-the-connectives-cleared-and-entailment-is-next.md) cleared the cause OD-9 named
and left three things behind. The gate fixture's blocker moved to a stage no criterion reached, a fabrication side
criterion missed for the first time, and the two batches behind every number in the experiment disagreed on three of
eight fixtures.

### OD-10: the fragment that cannot be grounded

The measured trace, stable in 3 of 3 dedicated runs, with no rejected decomposition at all:

```text
parent  The decision was made to use a per role fallback in `reconcileBullets`
        for resume generation.

S1.1  The decision was made.                                    unsupported
S1.2  The decision was made to use a per role fallback.         supported
S1.3  The per role fallback is in `reconcileBullets`.           supported
S1.4  The per role fallback is for resume generation.           supported
```

The entailment reason names it exactly: the evidence does not indicate that a specific decision was made, it discusses
references and practices without confirming any decision. `The decision was made.` carries no object, so nothing in any
evidence can support it, and the split that produced it is the split `DECOMPOSE_SYSTEM_PROMPT` asks for. One unsupported
sub claim drops the whole parent, which is AC-1 working exactly as written.

This is the same shape [experiment 0004](../../experiments/0004-clean-pipeline-re-measurement.md) recorded as
`The adapter warns.` and named as the opposite of the under splitting the Follow-up tracks. It has been on record since
before AC-11 took its current form, and nothing in the spec reached it: the four validity checks ask whether the split is
faithful, never whether a piece of it asserts anything checkable.

**Skip a sub claim a sibling already covers (chosen).** The relation is a strict content subset plus matching polarity and
modality plus order preservation, applied after the AC-11 verdict and before the first entailment call.

The argument that decides it is an asymmetry no other guard in this spec has. **A prune is permission to skip a check, so
a refused prune costs exactly today's behaviour.** Every guard the spec has argued about until now traded safety against
capability in both directions, so each condition had to be weighed. Here a false negative is free, which is why the
relation carries three conditions instead of the one the mechanism needs, and why each could be added against a specific
case rather than against a measured rate:

| Without it | The candidate | Is a strict subset of | And the sibling being supported says |
|---|---|---|---|
| polarity | `The decision was made.` | `The decision was not made to use X.` | nothing about the candidate |
| modality | `The decision was made.` | `The decision may be made to use X.` | nothing about the candidate |
| order | `Client side refetch was rejected.` | `The team rejected background polling and chose client side refetch.` | nothing about the candidate |

**The residual is rebinding and it is not closed.** The third row above was the engineer's first counterexample and order
preservation rejects it. The second one it does not:

```text
sibling    The team chose client side refetch and rejected background polling.
           content positions: team 1, chose 2, client 3, side 4, refetch 5,
                              rejected 6, background 7, polling 8

candidate  Client side refetch was rejected.
           matches positions 3, 4, 5, 6: strict, in order, no polarity marker
           on either side
```

It prunes, unchecked, and it asserts the opposite of the evidence. That case is the test, and the test asserts the prune
**happens**. A test asserting a refused prune pins nothing about the residual; it records that one sentence fails one
condition. Task 19's `although it was not` worked because it was a case that passes and therefore stands on the boundary,
and this is its equivalent.

What bounds the residual is a property rather than a marker set, and it is worth stating precisely because the honest
version is narrower than the reassuring one. Subsumption is strict, so a subsuming claim always matches more content
tokens than the candidate, and over a finite response that ordering cannot cycle, so **a maximal claim always exists and
always faces entailment**. The two pass rule then makes every pruned claim's recorded sibling one of those. So a pruned
claim's content tokens are all present in a claim that is actually verified, and a fabricated content word can never leave
the verification set by being pruned. It can only be **rebound**, which is a question about predicate argument structure,
and no lexical relation decides that. Three conditions narrow the class; none closes it.

**The two pass rule came out of the cross check and is a real correction, not a tightening.** The first draft pruned
against any subsuming sibling and asserted that a pruned claim's tokens are present in "the sibling that stays and is
verified". That holds only when the immediate target is itself unpruned. A chain (C under B, B under A) leaves C's
recorded sibling pruned, and the guarantee silently becomes an assumption that `tokens_match` composes transitively. It
does not generally: `base_sets_intersect` relates two tokens when their base sets meet, and set intersection is not
transitive, so A can meet B and B meet C with A and C disjoint. Nobody has built a live three token example and that is
beside the point, because the fix removes the need for one. Restricting pass two to maximal claims costs a single filter
over a list bounded by `MAX_SUB_CLAIMS`, keeps the motivating prune (the fuller restatement of the query 2 sentence is a
subset of nothing, so it is maximal), and turns a claim about the matcher into a property of the algorithm. **The
alternative considered was forbidding a pruned claim from acting as a subsumer**, which reaches the same place through an
iterative rule; it was rejected as the same guarantee expressed as a fixed point rather than as two passes, with an order
dependence to reason about that the maximal set does not have.

**A prompt only rule (rejected).** Add to `DECOMPOSE_SYSTEM_PROMPT` that every sub claim must keep the object of its verb
and must not restate another more weakly. Cheapest, no new safety argument, no code. Rejected as the soft half of a split
AC-13 already made the other way: the prompt lowers how often a thing happens and the deterministic half is what makes the
guarantee. It is worth adding later as the soft half beside AC-22, and it is not a substitute for it.

**Condition the drop rule instead (rejected).** Send every sub claim to entailment as today, and ignore an unsupported
verdict when a strict superset with matching polarity came back supported. It looks like strictly more evidence per
decision and it keeps the fragment's verdict in the trace. It was rejected on three counts, and the first is decisive:
**it carries the identical rebinding hole**, since it reads the same relation and only reads it later. It also pays the
entailment call the prune saves, and it turns AC-1's absolute rule (any unsupported sub claim drops the parent) into a
conditional one. Checking a claim and then ignoring its verdict is not more safety than not checking it.

**Measure the rate first and decide later (rejected).** Consistent with this spec's habit of refusing to pin detail ahead
of evidence, and wrong here: the fixture is stable at 3 of 3, the mechanism is named in the trace, and the same shape was
already on record from experiment 0004. There is no rate to learn that would change the decision.

**On recording the prune.** The observability that option 3 offered is the one thing it had that the chosen option lacked,
and it is recoverable without conditioning AC-1 or paying the call: a pruned claim keeps its `decomposed` row, its
position, and its text, with `entailment="pruned"` and `subsumed_by`. Contiguous ids (AC-6) are unaffected, because
nothing is removed from the response, only from the set of claims entailment is asked about. **The text is kept
deliberately**, and it is not a lapse of the no claim text rule: that rule governs `rejected_decompositions`, and
`decomposed` rows have carried full text for supported and unsupported claims since task 1. A pruned claim belongs to a
valid response, so nothing about it is rejected text.

**On where it lives.** The relation is a pure function in `verification.py`, called from `query.py`. Folding it into
`classify_decomposition_detail` was rejected: that function answers whether the response is a faithful division of the
parent, and pruning is not that question, so folding it in would make a disposition depend on a rule unrelated to validity
and add a fourth traversal to the one place AC-20 insisted on keeping to a single traversal and a single verdict.

### OD-11: the abstention that rests on nothing

AC-3 missed for the first time, 5 of 6, and the traces that were kept say why the criterion was fragile rather than why
that run answered. Query 5's three dedicated runs abstain through **wholesale rejection**, `not_additive` on `revision`
every time, with a second sentence also rejected in one. An abstention that leans on every sentence being dropped is one
loosened check away from answering, and the change measured in the same experiment loosened a check.

**The miss exposed the weakness rather than caused it**, and that reading is what rules out the obvious response.
Relaxing the bar to 5 of 6 in the AC-9 shape would lower a fabrication side guard on a single observation while leaving
the vacuity underneath untouched, so the criterion would be both weaker and still not mean what it says.

**Pin `uncovered_facet` on query 5 (chosen).** The cause to pin is a statement of correct behaviour, not an observation,
which is why measuring first does not apply: today's cause is already known to be `no_emitted_sentences` and measuring it
again cannot say what the gate ought to require. Pinning the observed cause instead was rejected outright, since OD-4
already named it the vacuous one, so it would ratify the exact thing the deferred item exists to remove and keep a
criterion green for the wrong reason.

**Pin query 4 at the same time (chosen, and this is the deliberate half).** AC-2 at 6 of 6 is the one criterion this chain
has treated as green on live evidence since experiment 0008, and nothing has ever established that its abstention rests on
a verdict rather than on everything being dropped before one was reached. Examining query 5 and not query 4 would be
choosing which answer to learn. If the pin turns AC-2 red, that is the same finding as query 5's and is recorded as one,
not as a regression this round introduced.

**The instrument goes first, because the oracle cannot recover what the harness discarded.** A defaulted `--records` or
`--store` resolves to a `TemporaryDirectory` registered on an `ExitStack` (`cli.py`, `_resolve_evaluate_paths`, lines 1129
to 1160) and is removed when `evaluate_command` returns, and `EvaluationCheck` keeps a fixture id, a status, a detail
string, and two counts, while the port already hands back a full traced result. So experiment 0013's single answering run of query
5 is unattributable forever, and no amount of re running recovers it. Only a run whose outcome differs from its
expectation writes a trace, so a clean batch costs nothing and the only file ever written is the one somebody will want.
Widening `EvaluationCheck` to carry the trace was rejected: the report is a summary, a trace is not summary shaped, and
every consumer of that dataclass would grow a field it never reads.

Three details of the writer are decisions rather than build choices, and the cross check found all three unsettled.
**The destination is a new `--traces DIR` and explicitly not a temporary one**, because a defaulted `--records` or
`--store` resolves onto the `ExitStack` and is deleted when the command returns, so the obvious place to write is the one
place that guarantees the evidence disappears again. **The directory is per invocation and timestamped**, because the four
AC-24 batches are four separate commands that each number their runs 1 to 3, so a name built from fixture id and run index
alone collides across batches and destroys the store versus provider attribution the denominator exists to enable. And
**the write leaves the application layer through the port**, as one optional `record_deviation` on `EvaluationPort`
defaulting to a no op. `_run_query_fixture` is pure application code and this project forbids file I/O there, so the two
alternatives were putting the write in the application layer or re deriving the pass or fail inside an infrastructure
implementation. The second is the two implementations of one verdict that AC-20 refused for `classify_decomposition`
after commit `004dc3c` shipped exactly that bug, and it would be a worse instance here, since the whole point of the file
is to record the runs the oracle disagreed about.

### OD-12: what a fraction of six can settle

Every gate in this spec is a fraction of 6, and experiment 0013's two batches passed 2 and 5 on identical code, the widest
spread any batch pair in this spec has shown.

**The reserve condition offered during the design conversation was superseded by what the check found.** It read: if
fixtures flip within a batch too, it is provider variance and eighteen runs is worth revisiting. That assumed the two
sources were alternatives. They are not, and they are separable, which is the case the condition did not specify.

The separation needed no new runs. One `evaluate` invocation adapts once, ingests once, then runs every fixture
`--runs N` times (`evaluation.py:494-535`), so the store is constant inside a batch and varies between them. Any batch
result that is neither 0 of 3 nor 3 of 3 is therefore a flip against a constant store:

| Fixture | Batch A | Batch B | What varies |
|---|---|---|---|
| `query-1-private-beta-gate` | 0/3 | 3/3 | the store, cleanly |
| `query-5-uploaded-files` | **2/3** | 3/3 | the provider, and this is the AC-3 miss itself |
| `assertion-rationale-summary` | 0/3 | **1/3** | the provider |
| `assertion-unverifiable-claim` | **1/3** | 3/3 | a `provider.answer` failure, not a verdict |

**Eighteen runs was rejected on this separation rather than on cost.** Averaging over both sources would fold a store
effect that moved one fixture by three runs of three into the same denominator as a provider effect that moved another by
one of three, and the larger of the two would disappear into the number. Twelve runs across four batches is enough for the
provider side, and the store side is a suspected correctness defect that belongs in Follow-up with an investigation rather
than in a denominator. A retrieval path whose results depend on which build ran would also be consistent with experiment
0007 finding no `decision.chosen` chunk retrieved at all, which is why the investigation starts at chunk identity and
ordering across two builds of the same corpus before it looks anywhere downstream.

**Forward looking rather than retroactive.** Re measuring every existing bar at twelve was rejected while the gate is still
unmet: AC-2 and AC-3 are touched by OD-11 and are re measured at twelve anyway, and what a full sweep adds is AC-9 and
AC-15, which nothing in this round changes, at the cost of the most live runs this spec would have paid for in one task.

**The reading rule is part of the criterion rather than advice.** Every rate is reported with its denominator and with
which of the two variances it is exposed to, and a capability figure below twelve is an observation that may not set or
move a criterion. Experiment 0013 followed that rule voluntarily in its threats to validity; writing it down is what makes
the next experiment owe it.

**The aggregate shape is pinned for the reason AC-14, AC-15, and AC-19 each pinned theirs.** Four batches are four
separate `evaluate` invocations and nothing joins them, so the experiment aggregates by hand, and a figure read later by
whoever confirms a bar cannot be left to whatever table that experiment's author felt like drawing. The two spread columns
are the load bearing part: a within batch spread counts the batches whose result is neither 0 of 3 nor 3 of 3, which is
the provider side, and a between batch spread counts the distinct per batch results, which is the store side. Experiment
0013 could be read this way only because someone noticed; the columns are what make the next reading automatic.

### On retiring task 13

The task specified its own retirement on 2026-08-13: if the content token share dominates the additive split, it changes
shape or retires, and that outcome is a finding rather than a failure. Experiment 0007 measured the split at **7 of 7
`content_token` and 0 `function_word_overrun`**, so the share is total rather than dominant. `sub_claim_is_additive_free`
returns on the first unmatched content token while `MAX_ADDED_FUNCTION_WORDS` bounds function word additions alone, so the
knob reaches one category and every measured drop is in the other: **no value of it would have changed any measured
result**, and the five occasions this plan re ordered around it were five instruments aimed at the wrong half.
Re pointing the number at whatever the next measurement finds was rejected as a placeholder rather than a task; a real
tunable surfacing later earns a new task with known content and a measurement behind it. Retiring the task does not remove
the constant: `MAX_ADDED_FUNCTION_WORDS` stays at 2 as the sanity bound it already is, and OD-8's refusal to convert
budgeted additions into free ones still rests on it.

### Threats to validity

- **The rebinding residual is bounded by an argument, not a measurement.** That a maximal claim exists and faces
  entailment follows from subsumption being strict over a finite response, and that every pruned claim points at one
  follows from the two pass rule. Both are proofs about the algorithm rather than observations about live traces, and a
  future change to either the strictness condition or the two passes takes the bound with it. Nothing connects those facts
  except this paragraph and the property test task 21(d) carries.
- **The transitivity question is avoided, not answered.** Whether `tokens_match` composes across a chain is still unknown,
  and the two pass rule means nothing depends on the answer. If a later change reintroduces chained pruning for any
  reason, the question comes back and it should be measured over the repository vocabulary the way OD-8's 622 and 30 were,
  not argued.
- **The prune has never been measured.** Its rate is unknown by construction, and the estimate that it fires on roughly
  one sub claim per over split sentence comes from a single fixture in a single experiment.
- **Two gates are being turned red on purpose.** If AC-2 fails its cause pin, the spec cannot immediately distinguish a
  gate that was always vacuous from one this round broke, and the only evidence separating them is the disposition mix in
  the new traces.
- **The store hypothesis rests on one fixture.** `query-1-private-beta-gate` splitting 0 of 3 then 3 of 3 is one clean
  batch boundary in one experiment. It is enough to refuse to average over it and not enough to call it a defect yet.
- **Four batches is still four sessions.** Twelve runs raises resolution on the provider side and does nothing about
  session level correlation between batches, which is the thing the store item exists to investigate.

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
- the settled decisions cross check, 2026-08-13, Sonnet 5, recorded above; its four verified mechanism claims were checked against `infrastructure/jsmastery_adapter.py` (discovery and code path resolution), `application/chunking.py` (chunk id shape), `application/verification.py` (the matcher), and `infrastructure/openai_generation.py` (the prompts)
- `docs/experiments/0003-whole-sentence-gate-and-a-misdiagnosis.md`, the measured drop rates on the built revision: 19 of 20 draft sentences dropped and 1 query of 12 answered, with `not_additive` at 74 percent of drops, inline citation markers at 16 percent, and `unsupported_sub_claim` at zero. Read it before the next design pass; it reorders the work
- `docs/experiments/0004-clean-pipeline-re-measurement.md`, the gate re measured on the cleaned instrument: 19 of 21 draft sentences dropped and 0 queries of 12 answered, `not_additive` at 68 percent of drops, `unsupported_sub_claim` newly at 16 percent through over splitting, the coverage schema failure and its before and after figures, and the gate's stochastic pass on a wrong answer. It raised OD-4, OD-5, and the ratification
- `docs/experiments/0006-coverage-directness-isolation.md`, the two arm isolation that rejected the AC-16 over correction hypothesis in both directions and raised OD-7: 11 sentences reached coverage across 6 runs with the exclusion in place and none covered the decision facet, while removing the exclusion covered once, with the caveat sentence. Its threats to validity section is the source of the session drift argument for taking two figures from one set of runs
- `src/decision_memory/application/chunking.py`, the nine `add()` calls that are the only source of a chunk's `value_path`, and `embedding_input`, which already renders the title and value path above the chunk text on the embedding side
- `src/decision_memory/application/dto.py`, `ActiveChunkDescriptor` (which carries `record_id`, `record_title`, and `value_path` that generation never receives), and `RejectedDecomposition` and `DroppedSentence`, whose no claim text rule bounds the AC-19 category
- `src/decision_memory/application/evaluation.py`, `QueryOracle` and `_satisfies`, the co location rule AC-15 reuses, `EvaluationOutcome`, which carries no per stage detail, `classify_query4_failure`, whose `None` is correct for query 4 and blind to OD-7's shape, and `run_evaluation`, which already takes its fixtures as a parameter
- `docs/experiments/0013-the-connectives-cleared-and-entailment-is-next.md`, the AC-21 live re measurement and the source of OD-10, OD-11, and OD-12: `where`, `while`, and `instead` at zero occurrences as a `failure_token` across 12 traced runs, the completeness half down to 1 of 7 rejections, `query-2-resume-generation` still 0 of 6 and now failing at entailment on `The decision was made.`, AC-2 holding at 6 of 6, AC-3's first miss at 5 of 6, and the batch table whose within batch and between batch spread is the whole basis of AC-24
- `src/decision_memory/application/evaluation.py`, `run_evaluation` and `_run_query_fixture` (lines 494 to 535), whose `for _ in range(runs)` inside one adapt and one ingest is what makes a batch a constant store, and `EvaluationCheck`, whose four scalar fields are where the trace is discarded
- `src/decision_memory/infrastructure/evaluation_runner.py`, the `TemporaryDirectory` at line 254 that makes a surprising run unrecoverable
- `src/decision_memory/application/verification.py`, `FUNCTION_WORDS` (the source of the thirteen `POLARITY_MARKERS` members), `classify_decomposition_detail`, and its four ordered checks, none of which reaches decomposition granularity
- `src/decision_memory/application/query.py` lines 696 to 760, the per sub claim verification loop and the unconditional `all_supported` drop, which is where the prune is applied and which is otherwise untouched
- `tests/test_sub_claim_verification.py`, the two shipped AC-1 attack fixtures (`_WELD_GROUNDED` and `_WELD_FABRICATED`), whose content token sets each carry a token the other lacks (`approved`, `merger`, `tuesday` against `accepted`, `bribe`, `rush`, sharing only `board`), so neither subsumes the other and the prune does not reach either attack
- `src/decision_memory/application/verification.py`, `application/query.py`, `application/dto.py`, `infrastructure/openai_generation.py`, the code this feature changes

**Practices & standards**:
- pass only shortcut for deterministic checks: a deterministic test never rejects, it only sends on
- no evidence, no support: a claim verified against empty evidence can never be supported
- one change at a time for measurable attribution
