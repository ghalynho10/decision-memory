# 0011 rationale: field aware retrieval ranking

## Context

Experiment 0007 recorded a decision question failing at entailment, and traced the cause one stage further back than the failure: on a question asking what was decided, no `decision.chosen` chunk reached generation at all, across 8 accepted chunks in 6 runs. Generation asserted a decision from a `body[2]` chunk labelled `other prose from this record`, and sub claim entailment correctly refused it. That is not a verification defect, and no criterion in spec 0010 reaches it.

Spec 0008 decided how to rank: keyword search and semantic search over the same filtered chunks, reciprocal rank fusion over the two rankings, then two pass record diversity. Every one of those choices still holds. What spec 0008 never faced is whether the kind of field a chunk holds should affect its ranking for a question of that kind. The question did not exist when 0008 was written, because nothing had yet measured a decision question drawing its answer from prose about the decision rather than from the decision.

Three forces shape what can be done about it. The first is that this pipeline's value is that every stage is deterministic and fully traceable; every measurement since experiment 0003 has depended on it, and a provider call ahead of retrieval would put a new failure mode in front of the one stage that has none. The second is cost asymmetry: the lexical corpus is rebuilt in memory on every query, so changing what it contains is free, while anything hashed into `pipeline_signature` locks every existing store out until it is rebuilt. The third is that this failure was already gated and passed. Spec 0008's AC-13 runs a decision question against JobPilot and asserts what the answer says, which cannot distinguish a `decision.chosen` citation from a body chunk describing the same decision, so the class of failure was invisible exactly where it was first supposed to be caught.

Not deciding leaves the self corpus gate failing for a reason that the feature currently owning it cannot fix, and leaves the calibration work behind it measuring a starved pipeline for the second time.

## Options considered

### Option 1: Fix the ranking mechanics in place, with no question inference

Make the field kind visible to keyword search in plain words, stop fusion discarding evidence only one retriever ranked, and give the tokenizer word ending awareness. Retrieval stays blind to what kind of question it was asked; a field label either matches the question's words or it does not.

**Pros**:
- No provider call and no new failure mode ahead of the deterministic stage.
- Nothing hashed into `pipeline_signature` changes, so no store is locked out and no embedding spend repeats.
- A miss surfaces as `no_term_match` on that chunk in the existing lexical trace, which is inspectable.
- Fixes two general defects that harm every query, not only decision questions.

**Cons**:
- Depends on label wording earning an exact match, which is brittle against question forms nobody anticipated.
- Couples one mapping to two surfaces with different objectives, retrieval and generation framing.
- Retires closed enum values and settings fields that a verified spec pins.

### Option 2: Reserve a diversity slot for the decision chunk

Once a record is represented in the accepted context, include its `decision.chosen` chunk too, either as an extra slot or by displacing that record's lowest ranked accepted chunk.

**Pros**:
- Deterministic, targeted, and guarantees the answer chunk arrives rather than hoping ranking surfaces it.
- Touches one stage and changes no ranking, so the blast radius is the smallest of the four.

**Cons**:
- Leaves both real defects in place, and by guaranteeing the outcome it makes them unmeasurable afterwards.
- Privileges one field by rule, which is the structured behaviour this pipeline avoids, wearing a diversity stage costume.
- Says nothing about any other field, so the next field that cannot be surfaced needs its own slot rule.

### Option 3: A deterministic field intent rule

A fixed local rule with no model: a question containing decide, decided, decision, chose, or chosen marks decision intent, which boosts `decision.chosen` at fusion or reserves it a slot.

**Pros**:
- No model call, fully traceable, and cheap.
- Directly targets the observed failure with an explicit, readable rule.

**Cons**:
- A hand tuned word list is wrong on every question form it did not anticipate, and its silence is invisible: nothing in the trace says the rule did not fire.
- A third calibration surface beside the fusion constant and the additive tolerance, in a project that already has two too many.
- Ends retrieval's blindness to question kind, which is the property being protected, even though it breaks no letter of spec 0008 AC-11.

### Option 4: Model classified query types

A provider call routes the question to a query type (decision, reason, alternatives, lineage) that filters or weights by value path. This is spec 0008 Follow-up item 4 arriving in full.

**Pros**:
- Most capable, and generalizes to question kinds no rule anticipates.
- Would also unlock the lineage and supersession traversal that item 4 describes.

**Cons**:
- Puts a provider call and a new failure mode ahead of the only deterministic, reproducible stage in the pipeline.
- Every measurement since experiment 0003 depends on that reproducibility.
- Item 4 is about new query modes rather than ranking, so this solves the observed problem by building something much larger that was deferred for unrelated reasons.

## Rationale

Option 1 is chosen because the diagnosis is mechanical, and each of its three parts corrects a mechanism rather than compensating for one. The failure has three independent causes, all verified in the code and in the frozen transcripts rather than inferred from the experiment writeup.

The keyword and semantic sides do not read the same document. `embedding_input` prepends the record title and the dotted value path to every embedding input, while the lexical stage tokenizes chunk text alone. So the semantic side knows a chunk is `decision.chosen` and BM25 does not, which is why DM-0008's decision chunk sits at semantic rank 10 and lexical rank 36. Fixing this is free, because the BM25 corpus is built from the passed tokens on every call and nothing is stored.

Fusion then discards it. Only ranks 1 to 24 enter the ranked set, and a missing contribution adds zero, so a chunk topping one retriever scores at most `1/61 = 0.0164` while a chunk ranked 24th in both scores `2/84 = 0.0238`. Any chunk in both lists at any rank beats any chunk first in one list alone. This is a general defect that harms every query, and it is worth correcting on its own merits.

Diversity then spends all eight slots before reaching the chunk. This third cause is deliberately not fixed. Reserving a slot would guarantee the outcome while leaving the two real defects in place, and would make them unmeasurable afterwards, which is the opposite of what a project that has already re measured a starved pipeline twice should do.

Two forces from Context settle the remaining shape. Because a provider call ahead of retrieval would compromise the reproducibility every measurement rests on, options 3 and 4 are rejected on that property rather than on capability. Because anything in `pipeline_signature` locks existing stores out, the embedding prefix stays as it is, even though moving it onto the same plain words mapping is genuinely the cleaner invariant; that is deferred to the next signature bump that happens for an independent reason, so the deferral is bound to a condition rather than left to be forgotten.

### Sub decisions inside the chosen option

**Field label only, no record title.** The title was expected to help and does not. The adapter takes `decision.chosen` from the `Chosen option` bold field alone, so DM-0008's decision chunk text already contains `retrieval`; spec 0008's title `Reliable multi source retrieval` contributes no new query term, only a term frequency bump offset by length normalization. Against that near wash it costs IDF dilution corpus wide and blurs within record discrimination, which is the wrong direction for a failure where the decision chunk lost to a `body[2]` chunk of the same record. The mechanism that actually works is the label's rarity: adding `decided` to only the six decision chunks makes it a high IDF term. Ship the narrower change and decide the title against the measurement.

**Every positive chunk contributes, and the constant stays at 60.** These fix different things and only one is a defect. The eligibility gate is a discontinuity, where rank 24 and rank 25 differ by a step function and a missing contribution is an unrecoverable zero. The constant sets how much weight agreement between retrievers carries, which is reciprocal rank fusion's premise rather than a bug: a chunk ranked first by one retriever beats a chunk ranked `r` by both only when `r > k + 2`, and `r = k + 2` is an exact tie rather than a win, since `2/(2k + 2)` equals `1/(k + 1)`. So at `k = 60` it takes rank 63 and at `k = 10` it takes rank 13. The behaviour is real and nothing has measured whether it is wrong. Spec 0008 Follow-up item 2 already owns that calibration, from recorded settings and real outcomes, so changing it here would be calibrating by argument, which spec 0010 task 13 exists to prevent. It gets the AC-12 numbered trigger instead. Keeping 60 rests on nothing having measured an alternative, not on any appeal to literature.

**Retire the top 24 boundary rather than keep it as a report.** Rank strictly subsumes a threshold flag, so keeping `outside_top_24` preserves no information. To be precise about the harm, since the loose version invites a correct rebuttal: the flag would not lie under the report only option, because it remains a true statement about rank. What breaks is the inference every existing reader draws from it, that the chunk did not contribute.

**Hand written suffix rules over Porter, and stemming does not land this query.** The five rule family already in `verification.py` reaches the decide, decides, decided, deciding group and ordinary plurals. It does not reach `chose` to `chosen`, which needs an `n` suffix, nor `retrieve` to `retrieval`, which needs `al`. Porter reaches `retrieval` and `retrieve` by stripping `al` and the final `e`; it reaches neither `chose` and `chosen`, which is irregular, nor `decided` and `decision`. So the real trade is one extra derivational pair against a third party dependency inside a layer that currently imports nothing and verifies its vocabulary digest at import. The hand rules win on reproducibility and layering. What matters for the gate query is that neither stemmer bridges `decided` to `decision`, so the label wording is the only path and stemming must not be presented as the fix.

**The label wording is load bearing and must be pinned with its reason.** `what this record decided` matches `decided` exactly. `what this record decides` would not: `decides` and `decided` are the same length, so neither is the other plus a family suffix. A later cosmetic edit would silently break the match, which is why AC-2 declares the mapping retrieval affecting.

**All nine chunks carry a label; only one wording changes.** These are separate decisions and are easy to conflate. Scope is all nine, because BM25 IDF self regulates: at 244 documents, `BM25Okapi` uses `ln((N - df + 0.5)/(df + 0.5) + 1)`, so a term in 6 documents scores `ln(37.7) = 3.63` against `ln(1.63) = 0.49` for a term in 150, about seven and a half times. Excluding the body label was rejected, and its stated benefit does not exist: BM25 has no negation, so a body label cannot mark a chunk as not a decision, and its value on the generation side is already measured weak, since experiment 0007 records generation asserting a decision from a `body[2]` chunk that carried that exact label. Rewording all nine was rejected as premature, because it reopens a mapping spec 0010 pinned as a constant and tunes eight labels against no measured failure.

**One rule family, two entry points.** This departs from the shape first discussed, one named rule set with one implementation, and the reason is a real difference between the callers. `_stem_match` is a pairwise matcher: it stems only when doing so yields the other token, which makes it deliberately conservative and stops it over stripping a word like `process` to `proces`. A BM25 corpus cannot work pairwise; it needs a canonical form per token, and a canonicalizer necessarily over strips. Forcing a single implementation would either loosen the AC-11 completeness guard, which spec 0010 protects as the safety critical direction, or leave lexical stemming useless. So the rule family, the suffix table, and `MIN_STEM_LENGTH` live in one module with two entry points, and AC-7 tests the one direction that must hold: a true pairwise match implies equal canonical stems. The converse deliberately does not hold, and the extra looseness is confined to the lexical side.

**Two halves for the JobPilot gate, with different owners.** A citation level criterion alone would couple this spec to spec 0010's verification stack, where experiment 0007 recorded the decision sentence dropped at entailment 6 of 6. Spec 0008's status note records exactly how that chain starts: its live gates failed and were carried to feature 11 as three items, which then carried to feature 16. Three hops is enough, so AC-8 is retrieval level and owned here, and AC-9 is stated but explicitly dependent.

**Which fixture, corrected during the cross check.** There is no JobPilot query that asks what was decided; the battery is the five hardcoded fixtures in `EVALUATION_FIXTURES` plus three assertions. The right target is `query-2-resume-generation`, whose question is `What decisions affect resume generation?` and which is exactly what spec 0008 AC-13 gates. Its shipped oracle asserts `required_record_ids` of `DM-0004` and `DM-0019` and carries no value path prefix at all, so it cannot tell a `decision.chosen` citation from a `body` chunk of the same record. That is the blind spot, stated more precisely than AC-13's own prose framing.

Two things fall out of reading the oracle rather than assuming it. Adding a prefix does not inherit the `DM-0004` intermittency spec 0008 Follow-up items 8 and 9 record, because the check matches a prefix against any one required record rather than all of them (`evaluation.py:704-712`), so `DM-0019` alone satisfies it. And the fixture gate needs no change: `battery_manifest.py:216` already sets `covering_sentence_scope=True` for every manifest query, so the self corpus side of this criterion has been shipped since spec 0010 and only the JobPilot side is open. Turning the flag on for `query-2-resume-generation` is a real change to that battery rather than a free reuse, since spec 0010 AC-15 deliberately left the hardcoded fixtures on whole answer semantics so nothing already built moved.

### Why this is not spec 0008 Follow-up item 4 coming due

Item 4 and Excluded item 2 both read `structured query types for alternatives, lineage, or supersession traversal`. Those are new query modes; the phrase field aware appears in neither. The session notes already carry a Ruled out entry recording that item 4 was considered for enrollment in the 2026-08-12 `/scope` replan and correctly stayed deferred because the live evidence pointed elsewhere. Experiment 0007's evidence is a ranking problem, so item 4 is still deferred for the same reason. The real reason for a new spec is narrower and is stated in Context: spec 0008 decided how to rank and never faced whether a chunk's field kind should affect ranking for a question of that kind.

Nothing in spec 0008 is being corrected, so the project's standing instruction about amending a shipped decision does not apply. Supersession was rejected for the same reason: filters, traces, store format 2, and the integrity boundaries all stay as built, and a supersession chain would report that as reversed. Spec 0008's AC-13 is likewise not amended. It is not wrong, it is incomplete, and its pass is cited in 0008's own status note, so rewriting the criterion would make that record unreadable, since a reader could no longer tell what was verified.

### Two tokenizers, opposite behaviour on the same string

Worth recording because it is easy to conflate later. Under `lexical-tokenizer-v1` the dot is not a letter, digit, combining mark, or apostrophe, so `decision.chosen` breaks into `decision` and `chosen`, neither of which equals `decided`. Under spec 0010's AC-11 verification tokenizer, `sentence_tokens` splits on whitespace and strips only edge punctuation, so the same dotted string stays one token. This is why mirroring `embedding_input` into the lexical document would not have fixed the gate query, and why the AC-18 mapping had to avoid the dotted token in the first place.

## Evidence

All figures below are read from `docs/experiments/data/coverage-directness/transcripts/batch1-run1-decision.txt`, the frozen verbatim transcript from experiment 0007, and from the code lines named. Experiment 0007 records the ranks as identical across all 6 runs.

**Corpus and stage sizes.** 244 active chunks, all accepted by the filter (no filters supplied). 29 fused candidates, the union of the two capped lists. 8 accepted into the context.

**The question and its facet.** `F1: What was decided about hybrid lexical and semantic retrieval?` Tokens after `lexical-tokenizer-v1`: `decided`, `hybrid`, `lexical`, `semantic`, `retrieval`.

**The three DM-0008 chunks that matter.**

| Chunk | Value path | Lexical | Semantic | Fused | Final |
|---|---|---|---|---|---|
| `ch_db2197c3` | `body[2]` | score 10.616366, rank 1 | rank 1, distance 0.478219 | rank 1, score 0.032787 | accepted, final rank 1 |
| `ch_488bebf3` | `decision.chosen` | score 2.230641, rank 36, `outside_top_24` | rank 10, distance 0.577239 | rank 21, score 0.014286 | `outside_top_8` |
| `ch_b96718e3` | `decision.alternatives[2]` | score 0.000000, `no_term_match` | rank 5, distance 0.528237 | rank 20, score 0.015385 | `outside_top_8` |

Both decision bearing chunks are semantically strong and lexically dead, and both die at the same place. The winner is a body chunk scoring 4.8 times higher lexically.

**The fusion cliff, read off the transcript.** Fused ranks 1 to 19 all carry two contributions, scoring 0.032787 down to 0.025000. Fused rank 20 is the first single contribution row at 0.015385, on a semantic rank of 5. The gap between rank 19 and rank 20 is the arithmetic bound, not a coincidence: the worst possible dual score is `2/84 = 0.0238` and the best possible single score is `1/61 = 0.0164`.

**Why the decision chunk is lexically invisible.** Its stored text is the terse `Chosen option` line, `Option 1, fix the existing query path with filtered parallel retrieval and reciprocal rank fusion`, plus the following sentence. Against the five query tokens it shares exactly one, `retrieval`. The chunk is impoverished precisely because it is terse and refers back to a named option, while the field name that would identify it as the decision never enters the lexical document at all.

**Why cause 2 alone is not enough.** If every positive scoring chunk contributed its true rank, the decision chunk would score `1/96 + 1/70 = 0.0247` against fused rank 19's `2/80 = 0.0250`. It still loses. Cause 1 is what has to land, and this is why the build plan measures cumulatively rather than in isolation.

**Code lines verified during this design.**

| Claim | Location |
|---|---|
| Lexical document is chunk text alone | `application/query.py:908` |
| Embedding input carries title and dotted value path | `application/chunking.py:94-102` |
| Only ranks 1 to 24 enter the fused set | `application/query.py:937-943` |
| BM25 corpus is rebuilt from passed tokens each call | `infrastructure/bm25.py:25-28` |
| Chroma is asked for every accepted chunk | `infrastructure/index_reader.py:179` |
| Tokenizer applies no stemming | `application/lexical.py:226-260` |
| The five rule morphology family and its floor | `application/verification.py:119,143-155` |
| `decision.chosen` comes from the `Chosen option` bold field | `infrastructure/jsmastery_adapter.py:278-279` |
| Field labels live in infrastructure, read only by generation | `infrastructure/openai_generation.py:118-128,150-165` |
| `prefix_version` is hashed into the pipeline signature | `application/pipeline.py:46,66` |
| `QUERY_SCHEMA_VERSION` is defined and unused | `application/dto.py:184` |
| Three hardcoded `schema_version=2` call sites | `application/query.py:880,1398,1431` |
