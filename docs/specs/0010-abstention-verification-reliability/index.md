# 0010. Abstention verification reliability

**Date**: 2026-08-12
**Status**: In Progress

## Summary

The query pipeline verifies atomic sub claims, and it emits only the claims that verification kept. It never restores a decomposed parent sentence, because a decomposition can omit the fabricated part and make the parent look safe. Coverage remains complete and binary. Grounded reasons may survive in the trace, but they cannot make a query answered when the required decision facet remains unanswered.

## Requirements

**User stories**:
- As a user of the query command, I want an honest abstention when the evidence does not support a claimed decision, so that I am not shown a cited answer that mixes a fabricated decision with a real borrowed clause.
- As an operator, I want the debug trace to show how each sentence was split and why each piece survived or was dropped, so that a bad split is visible rather than silent.

**Acceptance criteria** (the contract, each IDed and independently checkable):
- **AC-1**: A draft sentence that welds a fabricated decision to a verbatim borrowed clause is decomposed and verified by sub claim. The fabricated sub claim is dropped and can never return through parent sentence restoration, because a decomposed parent is never emitted. Deterministic tests cover both an explicit fabricated sub claim and a decomposition that omits the fabricated clause entirely.
- **AC-2**: Live gate against the real JobPilot corpus: query 4 abstains in every run of two separate `--runs 3` batches, 6 of 6 total. The trace must show that the fabricated decision sub claim was dropped and that the facet asking what was decided is uncovered. The drop is read from the entailment path, a row in `decomposed` whose `entailment` is `unsupported` and whose `kept` is false, not from the lexical `dropped_sub_claims` path; a checker reading the wrong field would call a passing run failed. The abstention proves the complete answer contract, while AC-1 proves the weld fix itself.
- **AC-3**: Live gate against the real JobPilot corpus: query 5 abstains in every run of the same two batches, 6 of 6 total. This is a smoke gate, not a measured abstention rate.
- **AC-4**: Every kept sub claim becomes its own answer sentence with the sub claim id. Parent order is preserved, then provider sub claim order. A decomposed parent is never emitted, even when every returned sub claim is grounded. Coverage then decides answered versus abstained. A facet is covered only when one kept sentence directly states its answer. Coverage cannot combine sentences, and a reason, context, consequence, premise, or anaphoric fragment cannot cover a decision facet unless that same sentence states the decision. One sentence may cover several facets only when it directly answers each one.
- **AC-5**: A sentence whose whole text is contained in an available cited chunk is never decomposed and never pays the decomposition call. A deterministic unit test proves the cost bound.
- **AC-6**: The debug trace shows accepted decomposition rows and each sub claim verdict. A genuine empty response appears only in `empty_decompositions`. A rejected nonempty response appears in `rejected_decompositions` with the sentence id, returned count, and one closed disposition: `over_cap`, `duplicate`, or `lexical_guard` (here meaning no sub claim was acceptable). A sub claim dropped by the lexical guard appears in `dropped_sub_claims` with its sub claim id, sentence id, and the disposition `lexical_guard`, which happens only when at least one sub claim in that response survives. A wholesale rejection records its `rejected_decompositions` row and no `dropped_sub_claims` rows, so one event is never counted twice. Rejected claim text is not exposed. All unsupported accepted rows remain distinct from both paths.
- **AC-7**: A provider failure during the decomposition call returns a failed query result with a provider failure trace, consistent with the existing entailment and coverage failures. A test proves the failure contract.
- **AC-8**: Before any containment or provider call, parent citation ids are deduplicated in parent order and split into `available_citations` (ids in accepted context) and `missing_citations` (the ordered remainder). Every containment, decomposition, entailment, and output citation uses only `available_citations`. With none available, the sentence is removed without a provider call. Missing ids are trace only and can never appear in answer citations. A `missing_chunk_refs` row is recorded for every sentence with a nonempty missing set, whether or not that sentence proceeds on its available citations.
- **AC-9**: The change does not newly fail the other live fixtures through a verification regression, checked as a smoke gate, not a rate comparison: three runs cannot separate a real regression from the fixture level variance the fresh baseline itself showed (query 1 went 1 of 3 on a provider hiccup with no code change involved). The bars are named so the gate needs no judgment call at read time. In the same two `--runs 3` batches used for AC-2 and AC-3, the incremental reingest assertion passes in both batches (it is a per batch assertion, not a per run one), the unverifiable claim assertion passes in at least 5 of the 6 runs, and the rationale summary assertion, restored by the per sub claim lexical guard of AC-11, passes in at least 5 of the 6 runs on re verification. The 5 of 6 bar is set by the live provider variance already documented for query 1, not by preference; a shortfall below it fails AC-9 rather than being argued about. Query 3 may abstain under strict coverage when the generated answer does not directly state every facet; that is the directness rule working as intended, and the generation quality gap is a follow up, not a coverage regression. Query 1's occasional provider failed state is a live hiccup, not a signal to compare against.
- **AC-10**: `schema_version` stays 2. The additive verification trace fields are `decomposed`, `empty_decompositions`, `rejected_decompositions`, `dropped_sub_claims`, and `missing_chunk_refs`. They default to empty tuples so an older constructor call remains valid. Named fields resolve, and JSON gains fields without removing or renaming any existing field. The runtime does not read persisted query results, so no data migration is needed.
- **AC-11**: The near subset check is only a lexical no new content vocabulary guardrail, applied per sub claim. It is not a proof that actors, negation, scope, order, or factual relations were preserved. For each sub claim, it compares a normalized token multiset against the parent token multiset. Tokens use Unicode NFKC, case folding, line ending normalization, whitespace splitting, and edge punctuation stripping; internal apostrophes and hyphens remain. A sub claim content token matches an unused parent content token when the two share a stem under these exact rules, where `shorter` and `longer` name the two tokens by length: `longer` equals `shorter`; or `longer` equals `shorter` plus `s`, `es`, `ed`, or `ing`; or `longer` equals `shorter` with its final `e` removed plus `ed` or `ing` (`use` and `using`); or `longer` equals `shorter` plus a repeat of `shorter`'s own final character plus `ed` or `ing` (`ship` and `shipped`); or `longer` equals `shorter` with its final `y` replaced by `i` plus `es` or `ed` (`rely` and `relies`). Every rule additionally requires `shorter` to be at least three characters, measured on the untransformed token. A function word token from the closed set in Feature design may be added without a parent match, at most two such tokens per sub claim, counted as instances whatever the words are, so a sub claim adding `is`, `not`, and `there` fails on the third. A function word matches only by exact normalized token equality, never by stem. Matching is per sub claim, not across the response. Deletion and reordering are allowed, which is safe because only verified sub claims are emitted. A sub claim with a genuinely new content word is dropped as an individual and never verified; the remaining accepted sub claims proceed to verification. The whole response checks run first, in this order: a genuine empty array, then more than 8 rows as `over_cap`, then a normalized duplicate row as `duplicate`, each without calling entailment. The per sub claim guard runs only on a response that survives all three. A response is rejected wholesale as `lexical_guard` only when no sub claim is acceptable.
- **AC-12**: The ordered canonical facet tuple is the single output of `extract_facets(original_question)` and is stored in `GenerationTrace.facets`, then passed unchanged to answer generation and coverage. Coverage uses the same fixed model constant as facet extraction and answer generation, at temperature 0. With no kept sentences, the application creates one uncovered row per facet with reason `no kept answer sentence` and makes no coverage call. Otherwise the provider returns exactly one row for every facet, in canonical facet order. Validation rejects unknown, missing, duplicate, or out of order facet ids; unknown, duplicate, or out of kept order sentence ids; a covered row with no sentence id; or an uncovered row with sentence ids. A schema failure gets the existing single repair attempt, then fails as `provider.coverage` at `claim_verification`. The live query 4 gate requires separate decision and reason facets. Its report classifies a failure from the existing trace: a missing separate decision facet is `facet_extraction`; separate facets with the decision facet wrongly covered is `coverage_directness`; separate facets with the decision facet uncovered but an answered result is `query_state`. No new trace field is added.

## Decision

**Chosen option**: Option 1: Sub claim decomposition with per sub claim verification, plus strict complete facet coverage.

The verification unit becomes the sub claim. The application first resolves the parent citation ids against accepted context. A sentence fully contained in one available cited chunk keeps the whole sentence path and only its available citations. Every other sentence with available evidence is decomposed by `gpt-4o-mini`. Each accepted sub claim is verified alone, containment first, then entailment. A containment grounded fragment cites only matching available chunks. An entailment grounded fragment cites the complete available citation set because the entailment call has no per chunk attribution. Only kept fragments are emitted. The parent sentence is never restored after decomposition.

Coverage remains binary and independent over the canonical facet tuple. A query is answered only when every facet is directly answered by one kept sentence. Coverage never composes an answer across sentences. Reasons alone cannot cover a decision facet. This is a targeted enforcement of spec 0007 AC-15. It does not solve query 2 citation completeness, because that missing record is not represented by a fixed facet and remains a follow up.

## Feature design

**Data model sketch**:

New entity, the sub claim, held only in the verification trace, no persistence:

- `sub_claim_id`: str, `f"{sentence_id}.{i+1}"`, 1 based over the decomposition response order. A duplicate under `normalize_for_containment` rejects the whole response. A lexically dropped sub claim keeps its position and id in `dropped_sub_claims`, so kept ids skip only where the drop signal accounts for them
- `sentence_id`: str, the parent DraftSentence
- `text`: str, the atomic claim
- `contained`: bool, whole sub claim verbatim in a cited chunk
- `entailment`: str, one of `skipped` (contained, no model call), `supported`, `unsupported`
- `reason`: str, the entailment reason, empty when skipped
- `kept`: bool, whether it survives
- `citations`: tuple of available chunk ids. A containment grounded sub claim narrows to the matching available chunks. An entailment grounded sub claim keeps all available citations because `entail_verdict` has no per chunk attribution

New entity, the rejected decomposition, held only in the verification trace:

- `sentence_id`: str, the parent sentence
- `returned_count`: int, the number of rows returned before rejection
- `disposition`: str, one of `over_cap`, `duplicate`, `lexical_guard` (here meaning no sub claim was acceptable)

New entity, the dropped sub claim, held only in the verification trace:

- `sub_claim_id`: str, the position based id of the dropped sub claim
- `sentence_id`: str, the parent sentence
- `disposition`: str, `lexical_guard`, the one closed disposition of an individually dropped sub claim
- no rejected claim text is recorded

`VerificationTrace` gains five additive fields:

- `decomposed`: tuple of sub claim rows, only for accepted sub claims, default `()`
- `empty_decompositions`: tuple of sentence ids whose provider response contained zero sub claims, default `()`
- `rejected_decompositions`: tuple of rejected whole responses, with no rejected claim text, default `()`
- `dropped_sub_claims`: tuple of individually dropped sub claim rows, with no rejected claim text, default `()`
- `missing_chunk_refs`: tuple of (sentence_id, missing chunk ids), the upstream signal when generation cited chunks that retrieval did not surface, default `()`

**State transitions** (verification pipeline):

resolve available and missing citations; with no available citation, remove the sentence and record the missing ids; otherwise run whole sentence containment against available chunk text only; if it passes, keep the parent with available citations; if it fails, decompose using the same available evidence; classify the response as genuine empty, over cap, duplicate, or otherwise lexical; drop each sub claim that fails the lexical guard as an individual, reject the whole response as `lexical_guard` only when no sub claim is acceptable, and record each drop in `dropped_sub_claims`; verify every accepted sub claim against available evidence; emit each kept fragment in provider order and never emit its parent; preserve parent draft order across fragments; if no sentence remains, create deterministic uncovered rows without a coverage call; otherwise run coverage against the unchanged canonical facet tuple and kept sentence tuple; any uncovered facet abstains; an abstained result exposes no public sentences or citations, while its trace retains the verification rows.

**API surface**:

No new command, no new flag, no new endpoint. The debug trace and JSON output gain the five additive verification fields above. Top level `QueryResult` is unchanged, `schema_version` stays 2.

| Surface | Change |
|---|---|
| `query --debug` | gains a Sub claims section listing accepted rows, genuine empty responses, rejected response dispositions, dropped sub claim rows, and missing chunk refs |
| JSON `QueryResult.trace.verification` | gains `decomposed`, `empty_decompositions`, `rejected_decompositions`, `dropped_sub_claims`, `missing_chunk_refs` |

**Provider contracts**:

Available evidence is assembled once per parent. Scan `DraftSentence.chunk_ids` in order, keep the first occurrence of each id, and look it up only in accepted context. Provider evidence uses available citation order. Each block is `CHUNK {chunk_id}:\n{text}`, joined with `\n\n---\n\n`. Containment, decomposition, and entailment all use this same lookup and order.

Decomposition receives the exact parent sentence plus the available evidence blocks. It uses `gpt-4o-mini`, temperature 0, and the existing single schema repair attempt. Its structured response is `{"sub_claims": [{"text": "nonempty string"}]}`. The provider prompt says at most 8, but the response schema leaves the array unbounded so the application can classify an over cap response instead of mislabeling it as provider failure. Text is trimmed and provider order is preserved. Empty text after trimming is malformed. Text repeated under `normalize_for_containment` rejects the complete response as `duplicate`. A malformed row fails as `provider.decompose`. A valid empty array removes the sentence and records a genuine empty. An over cap or duplicate response removes the sentence and records its closed rejection disposition.

The lexical guard runs per sub claim against the parent sentence, under the exact normalization, stem, bound, and ordering rules of AC-11, which is the single normative statement of the matcher. This section adds only the token set it refers to.

The function word set is closed and exhaustive, a spec constant rather than a grammatical category the builder extends. It is exactly `a`, `an`, `the`, `and`, `that`, `which`, `is`, `are`, `was`, `were`, `be`, `been`, `being`, `has`, `have`, `had`, `do`, `does`, `did`, `can`, `could`, `will`, `would`, `shall`, `should`, `may`, `might`, `must`, `to`, `of`, `for`, `with`, `by`, `as`, `at`, `on`, `in`, `from`, `about`, `so`, `but`, `or`, `if`, `because`, `when`, `then`, `there`, `it`, `this`, `these`, `those`, `their`, `not`, `no`, `never`, and `nor`. Any token outside this set is a content token and must find a parent match. Closing the set errs toward dropping a sub claim, which is the safe direction, and an unlisted word that shows up in practice is a spec edit, not a build time judgment.

A sub claim with a genuinely new content word is dropped as an individual and recorded in `dropped_sub_claims`; a response with no acceptable sub claim is rejected wholesale as `lexical_guard` and recorded in `rejected_decompositions` only, with no per sub claim rows. Dropped and rejected claim text is never recorded.

Coverage receives the original question, the canonical facets in facet order, and kept sentences in output order. Its fixed system instruction is: `For each facet, decide whether one provided answer sentence directly states its answer. Judge only what that sentence says. Do not combine sentences. A reason, context, consequence, premise, or anaphoric fragment does not state a decision. One sentence may support several facets only when it directly answers each one.` It uses `MODEL_FACETS_AND_ANSWER`, temperature 0, and the existing single schema repair attempt. Its response schema remains one row per facet with `facet_id`, `covered`, nonempty `reason`, and `sentence_ids`. Supporting ids are unique and follow kept sentence order.

**Value sourcing**:

| Action | Value produced or displayed | Source |
|---|---|---|
| canonical facets | ordered facet ids and text | the one validated `extract_facets(original_question)` result, stored in `GenerationTrace.facets` and passed unchanged to generation and coverage |
| available and missing citations | ordered chunk id tuples | first occurrence of each parent citation id, partitioned by membership in the accepted context lookup |
| provider evidence | ordered labeled chunk blocks | available citations and accepted context text, serialized by the fixed provider contract above |
| decompose sentence | ordered sub claim texts | validated `gpt-4o-mini` structured response, with the fixed model settings and schema above |
| lexical guard | accepted or dropped per sub claim, or whole response rejection | the AC-11 matcher (its exact stem rules, its two token function word bound, and the closed function word set in Provider contracts); empty, over cap, and duplicate stay whole response checks and run first |
| decomposition trace | accepted rows, dropped sub claim rows, genuine empty id, or rejection row | accepted provider response and verification rows; exact empty array; or closed application rejection disposition |
| per sub claim containment | contained bool, matching chunk ids | deterministic containment against each available cited chunk individually |
| per sub claim entailment | supported bool, reason | existing entailment call against the ordered available evidence blocks, only when containment failed |
| kept flag | kept bool | `contained or entailment == "supported"` |
| kept sub claim citations | ordered available chunk ids | matching available ids for containment; all available ids for entailment because entailment names no supporting chunk |
| answer sentence id and order | fragment id and stable output position | `sub_claim_id`; parent draft order, then provider sub claim order |
| public answer content | sentences and citations, or none | kept whole sentences and fragments only for an answered result; an abstained result exposes them only through trace |
| missing chunk ref signal | sentence id and ordered missing ids | the missing side of the citation partition, never an output citation source |
| facet coverage | one ordered row per canonical facet | deterministic uncovered rows when there are no kept sentences; otherwise the validated coverage response from the fixed contract above |

**Key invariants**:
- The accepted context lookup is the only source of provider evidence and output chunk citations. Missing ids remain trace only.
- A decomposed parent sentence is never emitted. Only its individually verified fragments may enter coverage or public output.
- The lexical guard proves only that no unmatched content vocabulary was introduced under its per sub claim token rules. It does not prove factual equivalence, relation preservation, completeness, or good decomposition. A dropped sub claim never verifies or emits.
- A sub claim that fails the lexical guard is dropped as an individual. The response is rejected wholesale only when no sub claim is acceptable, or when it is empty, over cap, or duplicate.
- Decomposition runs only after whole sentence containment fails against available evidence. No available evidence removes the sentence without a provider call.
- Grounded is `contained or entailment == "supported"`, the existing binary verdict. There is no separate acceptance threshold.
- Grounding decides whether a sentence is supported. Coverage separately decides whether that one sentence directly answers a required facet.
- Coverage uses the canonical facet tuple unchanged. Exactly one valid row per facet is required in the same order. A covered row names one or more unique known kept sentence ids. An uncovered row names none.
- Coverage cannot combine sentences. One sentence may appear in several rows only when it directly answers every named facet.
- Query 4 diagnosis reads `GenerationTrace.facets`, coverage rows, uncovered facets, and result state in that order. A merged decision and reason facet is assigned to facet extraction before coverage is judged. Separate facets make coverage directness independently diagnosable.
- Provider schema failure receives one repair attempt. Final decomposition or coverage failure fails the query at `claim_verification`; it never becomes abstention.
- `schema_version` stays 2. The runtime reads no persisted query result, and all five trace additions are output only.

**Security model**:

No new surface. Decomposition sends the candidate sentence and available cited chunk text to the existing provider, the same class of data entailment already sends. Rejected claim text is not added to the trace or normal output.

**Configuration required**:

None. Decomposition and entailment stay fixed to `gpt-4o-mini`. Coverage uses `MODEL_FACETS_AND_ANSWER`. All calls use temperature 0. There is no acceptance threshold to configure. The cap, lexical matcher, prompt text, schemas, and dispositions are spec constants, not settings.

**Critical test scenarios**:
- Fabrication removal: a fused sentence returns both grounded and fabricated sub claims; only the grounded fragment is emitted, verifies **AC-1**, **AC-4**
- Omission attack: decomposition returns only the grounded clause and omits the fabricated clause; the parent is never restored, verifies **AC-1**, **AC-4**
- Fragment identity: two kept fragments emit `S1.1` then `S1.2`; a later parent emits after both, verifies **AC-4**
- Accepted context boundary: missing citations are removed before whole containment; a partially available entailment fragment cites only available ids; a sentence that proceeds on its available ids still records its `missing_chunk_refs` row; no output citation names a missing id, verifies **AC-8**
- Citation precision: containment keeps only matching available ids, while entailment keeps all available ids in parent order, verifies **AC-4**, **AC-8**
- Decomposition outcomes: accepted, actual empty, over cap, normalized duplicate, whole lexical guard rejection, and per sub claim drops remain distinct in trace; the whole response checks fire in their stated order, and a wholesale rejection writes no `dropped_sub_claims` rows, verifies **AC-6**, **AC-10**, **AC-11**
- Lexical limits: `refetch` and `refetches` match, `use` and `using` match under the dropped `e` rule, `add` and `adding` match under the plain suffix rule, `ship` and `shipped` match under the repeated final character rule, `rely` and `relies` match under the `y` to `i` rule, a two character token never matches, two added function word tokens pass while a third fails, an unlisted function like word is treated as content and fails, and a new content token fails; a sub claim with a new content word is dropped while the clean sub claims proceed, and a response with no acceptable sub claim is rejected wholesale; dropped `not`, reversed actors, reordered relations, and omitted content demonstrate that the guardrail makes no semantic guarantee and only verified fragments can emit, verifies **AC-1**, **AC-11**
- Cost bound: a fully contained sentence skips decomposition, while a sentence with no available evidence skips all providers, verifies **AC-5**, **AC-8**
- Provider failure: malformed decomposition or coverage gets one repair, then fails with the correct provider code at `claim_verification`, verifies **AC-7**, **AC-12**
- Empty kept set: every canonical facet receives a deterministic uncovered row and coverage is not called, verifies **AC-12**
- Coverage row integrity: unknown, missing, duplicate, or out of order facet ids and invalid sentence ids fail validation, verifies **AC-12**
- Directness table: a stated decision covers a decision facet; a reason, premise, consequence, unrelated sentence, cross sentence combination, or anaphoric fragment does not; one compound sentence may cover several facets only when it states each answer, verifies **AC-4**, **AC-12**
- Diagnostic split: a merged query 4 facet reports `facet_extraction`; separate facets with a wrongly covered decision report `coverage_directness`; an uncovered decision with an answered result reports `query_state`, verifies **AC-2**, **AC-12**
- Abstention surface: kept fragments remain in trace but public sentences and citations are empty, verifies **AC-4**, **AC-12**
- Live gate: query 4 extracts separate decision and reason facets, drops the fabricated decision, leaves the decision facet uncovered, and abstains in both `--runs 3` batches; query 5 also abstains, the unverifiable claim and incremental reingest assertions do not newly fail, and query 3 may abstain as the recorded generation gap, verifies **AC-2**, **AC-3**, **AC-9**, **AC-12**

## Build plan

Ordered by the Skateboard approach: first close the output restoration path and accepted context boundary, then make coverage strict, then relax the lexical guardrail, then rerun every gate.

1. Remove parent restoration from `query.py`. Resolve available citations before whole containment, emit only verified fragments after decomposition, keep output citations inside accepted context, and make abstained public output empty while preserving trace rows, satisfies **AC-1**, **AC-4**, **AC-5**, **AC-8**
2. Complete the decomposition contract and trace. Add exact provider serialization, duplicate rejection, the three rejection dispositions, and `rejected_decompositions` rendering without rejected text, satisfies **AC-6**, **AC-7**, **AC-10**, **AC-11**
3. Tighten coverage in place. Reuse the one canonical facet tuple, switch to `MODEL_FACETS_AND_ANSWER`, add the fixed directness instruction, handle no kept sentences deterministically, validate complete ordered facet rows plus sentence references, and classify query 4 gate failures from existing trace as facet extraction, coverage directness, or query state, satisfies **AC-2**, **AC-4**, **AC-12**
4. Replace the whole response lexical guard with the per sub claim guard from AC-11: drop violating sub claims individually, reject the response only when none is acceptable, add the `dropped_sub_claims` trace signal, and apply the broadened matching rule exactly as AC-11 states it (the five stem rules, the three character floor on the untransformed token, the two token function word bound, and the closed function word set from Provider contracts). Keep its claim lexical only, satisfies **AC-6**, **AC-10**, **AC-11**
5. Replace and extend deterministic tests for omission restoration, fragment identity, accepted context citations, decomposition dispositions, per sub claim lexical drops, lexical limits, coverage directness, facet completeness, provider failures, abstention output, and schema stability, satisfies **AC-1**, **AC-4** to **AC-8**, **AC-10** to **AC-12**
6. Update `verify.md`, then run `/check verify` and `/test`, satisfies **AC-1** to **AC-12**
7. Run `evaluate --runs 3` twice against the real JobPilot corpus. Confirm query 4 has separate decision and reason facets, drops the fabricated decision, leaves the decision facet uncovered, and abstains 6 of 6. Confirm query 5 abstains 6 of 6. Confirm the rationale summary assertion, the unverifiable claim assertion, and the incremental reingest assertion do not newly fail; query 3 may abstain as the generation quality gap recorded in the follow up, satisfies **AC-2**, **AC-3**, **AC-9**, **AC-12**

## Consequences

**Positive**:
- The fused clause fabrication can no longer hide inside a sentence; query 4 and query 5 can abstain honestly.
- The verification unit now matches the attack surface, atomic claims instead of whole sentences.
- Cost is bounded: only non verbatim sentences pay the decomposition call.
- The trace shows the split itself, so a bad split is visible, and the empty, dropped, and missing signals point at upstream problems.
- The lexical guard drops only the violating sub claim, so one imperfect sub claim no longer discards the whole decomposition; each kept sub claim is still individually verified, and the drops stay visible in the trace.
- The answered state again means every fixed facet has a direct answer. Grounded partial material cannot silently stand in for a missing decision.
- A decomposition omission can lose useful text, but it can never restore unverified parent content.
- Missing citations can never escape the accepted context boundary into output.

**Negative / tradeoffs**:
- One more provider call per non verbatim sentence adds latency and cost to those queries; a sentence that decomposes into K sub claims that all fail containment can add up to K further entailment calls on top.
- The decomposition model can split poorly, which can keep a fabricated fragment that separately passes verification or drop grounded content; the trace makes both visible but does not fix them.
- Under splitting is a known, unresolved risk: if the decomposition returns the whole sentence as a single sub claim, that sub claim's entailment check degrades to today's failing whole sentence check for that sentence. This feature makes the sub claim count visible in the trace so an under split is observable, it does not guarantee against it.
- Every decomposed answer is emitted as fragments. This costs readability, but it is the safe trade because parent restoration can undo successful verification.
- The lexical guardrail cannot prove preserved actors, negation, scope, order, or relations. Entailment remains responsible for factual support.
- A per sub claim drop can still lose a mildly rephrased sub claim when the tolerance does not cover its rewrite, and a genuinely fabricated sub claim is dropped, which can also discard useful content that sat in the same response as the fabrication.
- The 6 of 6 acceptance gate is strong evidence, not a measured abstention rate; a true rate needs more runs.
- Coverage uses the larger fixed generation model, so every nonempty query costs more than the earlier coverage call.
- Strict complete coverage can abstain even when some grounded fragments are useful. A future partial answer surface would need to say which facets remain unanswered instead of calling the result complete.

**Neutral**:
- `schema_version` stays 2; the five trace fields are additive and query results are not read back from persistence.
- No store change, no rebuild, no new configuration.
- Query 2 citation completeness remains out of scope. Fixed facet coverage cannot demand an omitted record that no facet names.

## Follow-up

- [ ] Generation directness, query 3: the generated answer for a facet should directly state the answer in one sentence. Query 3 abstains because the answer does not directly enumerate which decisions are provisional. Tighten the answer generation contract, or add a stage that directly states each facet, then re run the live gate. Kept separate from the coverage change so directness is not weakened.
- [ ] Coverage direction, query 2 `DM-0004` consistency: design a citation completeness fix (a stricter generation contract that cites every accepted chunk directly answering a facet, or a citation completeness verification stage). Deliberately deferred so this feature changes one thing and stays measurable.
- [ ] If partial answers become a product requirement, design an explicit partial result state and render every uncovered facet. Do not weaken the meaning of `answered` to carry partial output silently.
- [ ] If the missing chunk ref signal fires with any frequency, investigate upstream: generation cited chunks that retrieval did not surface, a bug before verification.
- [ ] Relevance floor calibration remains deferred from spec 0008 follow-up item 2; it is not the fix for either direction.
- [ ] Once the fix lands, consider measuring a true abstention rate over more runs, since the 6 of 6 gate is evidence, not a rate.
- [ ] If the live acceptance runs (or later usage) show the decomposition call returning a sentence as a single undivided sub claim with any frequency, the under splitting risk in Consequences is live, not theoretical; revisit with a deterministic minimum split heuristic or a hybrid deterministic clause splitter (Option 5 in rationale.md, deterministic clause splitting, was rejected for the general case, not necessarily as a narrow fallback here).
- [ ] An entailment grounded sub claim keeps all available parent citations rather than a narrowed set, since `entail_verdict` has no per chunk attribution. If over citation appears in practice, consider extending its schema to name supporting chunks.

## Rationale

Reasoning and options: see [rationale.md](rationale.md).
