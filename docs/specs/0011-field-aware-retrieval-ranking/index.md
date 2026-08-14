# 0011. Field aware retrieval ranking

**Date**: 2026-08-14
**Status**: In Progress

## Summary

Ask this tool what was decided about something and the chunk holding the actual decision never reaches the model. Retrieval ranks a chunk by its words alone, so the terse `decision.chosen` field loses to long body prose that happens to discuss the decision, and the fusion step then discards any chunk only one of the two retrievers found. This spec makes a chunk's field kind visible to keyword search in plain words, stops fusion from throwing away single retriever evidence, and gives the keyword tokenizer basic word ending awareness. Nothing stored changes, so no index rebuild is needed.

## Requirements

**User stories**:

1. As a developer asking what was decided about an area, I want the record's decision field to be among the evidence the answer is built from, not just prose that describes it.
2. As a reviewer, I want a chunk that only one retriever ranked to still be able to reach the answer, so evidence is not discarded for the shape of the retrieval stack rather than for its relevance.
3. As a maintainer, I want the gate that checks a decision question to check where the answer came from, not only what it says, so this class of failure cannot pass unnoticed again.

**Acceptance criteria**:

1. **AC-1**: Each accepted chunk's lexical document is exactly `f"{label}\n\n{chunk_text}"` under the new identifier `lexical-document-v1`, recorded in the settings trace. There is no `Field:` prefix: that prefix is a generation rendering concern, and carrying it here would add the near inert token `field` to every document. A chunk whose value path has no label entry uses the chunk text alone, mirroring how generation omits its `Field:` line for an unmapped path. The record title is not included. This composition happens at query time only: stored chunk text is unchanged, `embedding_input` is unchanged, `PipelineConfig` is unchanged, and no store rebuild is required.
2. **AC-2**: The nine entry field label mapping moves to the application layer as one source of truth, read by both the lexical document and the generation `Field:` line. The `decision.chosen` label is reworded from `the decision this record chose` to `what this record decided`. The other eight wordings are unchanged. The mapping is retrieval affecting: an edit to any wording changes lexical ranking as well as generation framing, and the spec records this so a later edit is not treated as cosmetic.
3. **AC-3**: Fusion eligibility is removed. Every chunk carrying a lexical rank contributes `1 / (60 + lexical_rank)` and every chunk carrying a semantic rank contributes `1 / (60 + semantic_rank)`, at any rank. A chunk with `no_term_match` or `nonpositive_score` carries no lexical rank and still contributes nothing lexically. The reciprocal rank fusion constant stays `60`.
4. **AC-4**: The top 24 boundary is retired. The `outside_top_24` value is removed from both the lexical and the semantic disposition enums, so every positive lexical row and every semantic row is `ranked`. `CANDIDATE_LIMIT` is deleted, and `lexical_limit` and `semantic_limit` leave the settings trace. Rank is retained on every row and strictly subsumes what the flag conveyed.
5. **AC-5**: `QUERY_SCHEMA_VERSION` (`dto.py:184`) becomes `3` and is used at all three `query.py` call sites (`880`, `1398`, `1431`) in place of the hardcoded literal, with one test asserting `result.schema_version == QUERY_SCHEMA_VERSION`. No data migration runs: the runtime never reads a persisted query result.
6. **AC-6**: The tokenizer advances to `lexical-tokenizer-v2`. The algorithm is unchanged through step 4 (NFC, one `str.lower()`, the code point scan, exact stopword removal on the untransformed surface token) and then applies stemming as a new step 5, replacing `apply no stemming`. The `lexical-stopwords-v1` vocabulary and its pinned digest are unchanged.
7. **AC-7**: One named morphology rule family, in one shared application module, serves both the lexical tokenizer and the spec 0010 AC-11 verification guard. The family is the five existing rules from `verification.py` `_stem_match` with `MIN_STEM_LENGTH` at `3`. It exposes two entry points because the two callers need different shapes: the **base set matcher** for verification, and the canonicalizing stemmer pinned as `morphology-v1` in Feature design below for the BM25 corpus. A property test asserts the one direction that must hold, that **a base set match implies equal canonical stems**; the converse deliberately does not hold. Any edit to the family must be measured against the retrieval gate and the verification drop rate together. **Amended 2026-08-14, and both entry points moved.** This criterion previously said the verification matcher's behaviour does not change and stated the property over the pairwise form. Both were wrong. Spec 0010's OD-8 replaced the directional pairwise comparison with a base set intersection over the same five rules, so the verification entry point does change; and the property as written was **already false before that change**, with 30 counterexamples in this repository's own vocabulary (`setting` and `settings` both match pairwise, and canonicalize to `setting` and `set`; `need` and `needs` match pairwise, and canonicalize to `n` and `need`). The property test would have failed on first contact with real text. Two further clarifications the corrected form needs: base set **agreement** is not the property, since a canonical stem need not be in the base set (`falls` has base set `{falls, fall}` and canonical stem `fal`, because the doubled letter rule fires on a doubling that is part of the word); and canonical equality does not imply a base set match (`file` and `fill` both canonicalize to `fil` while their base sets never intersect). That converse failing is not a defect. It is exactly the over stripping verification must not inherit and retrieval can tolerate, which is the whole reason this family has two entry points rather than one. The reasoning and the measurement are in [spec 0010's rationale](../0010-abstention-verification-reliability/rationale.md), *The additive matcher*.
8. **AC-8**: For the JobPilot fixture `query-2-resume-generation`, the query spec 0008 AC-13 gates, a `decision.chosen` chunk of one of its required records reaches the accepted context. This half is owned by this spec and passes on its own stack. The self corpus fixture needs no change here: its manifest already carries `expected_value_paths: ["decision.chosen"]`, so this criterion exists to close the same blind spot on the JobPilot side, where it is open.
9. **AC-9**: `query-2-resume-generation`'s oracle gains `required_value_path_prefixes=("decision.chosen",)` and `covering_sentence_scope=True`, so the covering sentence must carry that citation. Every other hardcoded JobPilot fixture keeps whole answer semantics. Its existing `required_record_ids` of `DM-0004` and `DM-0019` is unchanged, and because the oracle matches a prefix against any one required record rather than all of them (`evaluation.py:704-712`), this adds nothing to the `DM-0004` citation intermittency spec 0008 Follow-up items 8 and 9 record. A failure here is attributed by stage from the existing trace, and a drop at entailment or coverage is a spec 0010 finding rather than a regression in this spec. `covering_sentence_scope` is already `True` for every manifest battery query (`battery_manifest.py:216`), so no fixture gate change is implied.
10. **AC-10**: Against the frozen self corpus fixture, DM-0008's `decision.chosen` chunk is in the accepted eight in 6 of 6 runs. This bar confirms determinism, not a rate: BM25 over a fixed store and a nearest neighbour lookup over fixed vectors do not vary, so 5 of 6 is a determinism defect to investigate rather than ranking variance to tolerate.
11. **AC-11**: Each of the three ranking steps records, for DM-0008's `decision.chosen` chunk and for the `body[2]` chunk that currently takes its slot, the lexical rank and disposition, the semantic rank, the fused score and fused rank, and the final disposition. Every one of these already exists on `LexicalRow` and `FusedCandidate`, so no new instrumentation is added. The figures land in a numbered experiment.
12. **AC-12**: If after all three steps the decision chunk still misses the accepted eight, the reciprocal rank fusion constant is calibrated at that point from that measurement, under spec 0008 Follow-up item 2. It is not changed by argument inside this spec.
13. **AC-13**: The fixture gate's end to end result is recorded with its stage attribution (`abstention_cause`, the `dropped_sentences` reason, `classify_query4_failure`), and never as a bare pass or fail. The status note states plainly that a remaining failure belongs to spec 0010's verification stack, whose answering bar AC-15 itself calls provisional.
14. **AC-14**: Ruff, strict mypy, the unit suite, and the application and domain layering check pass. Tests cover the lexical document composition and its unmapped path fallback, the label mapping as a single source read by both callers, the retired dispositions, the schema constant at all three sites, the `lexical-tokenizer-v2` vectors, and the AC-7 implication property.

## Decision

**Chosen option**: Option 1, fix the ranking mechanics in place so a decision chunk competes fairly, with no question inference

Make a chunk's field kind visible to lexical retrieval in plain words, let every ranked chunk contribute to fusion whatever its rank, and add word ending awareness to the tokenizer. Retrieval stays blind to what kind of question it was asked.

No community implementation skill shaped this decision. Every dependency was settled by specs 0001 and 0008, and no new tool is selected.

## Feature design

### What changes, by stage

```text
filter        unchanged
lexical       document gains the plain words field label (AC-1)
              tokenizer gains stemming, lexical-tokenizer-v2 (AC-6, AC-7)
              outside_top_24 disposition retired (AC-4)
semantic      unchanged in behaviour
              outside_top_24 disposition retired (AC-4)
fusion        eligibility gate removed, every ranked chunk contributes (AC-3)
diversity     unchanged, record cap 2 and accepted limit 8 both stay
generation    unchanged, except the reworded decision.chosen label (AC-2)
```

### Interface surface

No change. `decision-memory query` keeps every command, flag, exit code, and answer rendering it has today. The only user visible differences are inside `--debug`: the settings block drops two fields and gains one, both disposition vocabularies lose `outside_top_24`, and the Fusion section lists every accepted chunk instead of the top 29.

### Data model

No persistent schema changes. The in memory query DTOs change as follows:

```text
LexicalRow.disposition     closed values become ranked, no_term_match,
                           nonpositive_score; outside_top_24 removed
SemanticRow.disposition    the enum collapses to ranked; outside_top_24 removed
RetrievalSettings          loses lexical_limit and semantic_limit
                           gains lexical_document_version
                           tokenizer_version reads lexical-tokenizer-v2
QueryResult.schema_version 2 becomes 3, from QUERY_SCHEMA_VERSION
```

`FusedCandidate`, `FilterRow`, `DiversityTrace`, and `ActiveChunkDescriptor` are unchanged in shape. The fused candidate collection grows from the union of two capped lists to every accepted chunk, because the semantic stage already ranks all of them.

### Module placement

| What | From | To | Why |
|---|---|---|---|
| `FIELD_LABELS`, `CHUNK_VALUE_PATHS`, `field_label()` | `infrastructure/openai_generation.py` | `application/fields.py` (new) | Application retrieval now reads it, and application may not import infrastructure |
| The morphology rule family | `application/verification.py` `_stem_match` | `application/morphology.py` (new) | Two application callers, one named rule set; also moved by spec 0010 task 18 |
| `lexical_document()` | new | beside `embedding_input` in `application/chunking.py` | Both compose a retrieval input from a chunk and its value path |

### The canonicalizing stemmer, `morphology-v1`

Pinned as an exact algorithm rather than by its relationship to the base set matcher, because several non equivalent stemmers satisfy that relationship while producing different token streams and different rankings. Applied once per token, after stopword removal, as step 5 of `lexical-tokenizer-v2`.

**Two different floors appear below and they are not the same value.** The **entry floor** is `MIN_STEM_LENGTH` (3), measured once on the untransformed input token, and it is the same floor the base set matcher applies to a derived `shorter`. The **round floor** is 2 characters, measured on each intermediate result inside a round, and it is what stops a strip or a tail rule from producing a degenerate stem. They serve different steps and must not be harmonized to one number: raising the round floor to 3 breaks `use` against `using`, and lowering the entry floor to 2 would change what the base set matcher accepts in spec 0010.

1. **Entry floor.** If the token is shorter than `MIN_STEM_LENGTH` (3), return it unchanged. This mirrors the base set matcher's floor, which is measured on the untransformed shorter token, so a token of exactly 3 characters is reduced.
2. Strip the first matching suffix, longest first: `ing`, `ed`, `es`, `s`. Strip only if at least 2 characters remain (**round floor**). At most one suffix is stripped per round.
3. If the result ends in a doubled letter (its last two characters are equal), drop one, but only if at least 2 characters remain (**round floor**).
4. Otherwise, if the result ends in `i`, replace that `i` with `y`.
5. Otherwise, if the result ends in `e`, drop it, but only if at least 2 characters remain (**round floor**).
6. Steps 3, 4, and 5 are mutually exclusive and apply at most one each per round.
7. **Repeat steps 2 to 6 until a round changes nothing**, then return the result.

**Amended 2026-08-14.** Step 7 replaced the original "there is no second pass". Running once was the source of the split that made spec 0010's AC-7 property false, because a plural of an `ing` noun loses only its `s` while the singular loses its whole `ing`: `settings` reached `setting` and stopped, while `setting` reached `set`. The same single round left `need` at `n`, since step 5 could fire on the two character result of step 2 with nothing to stop it, which is why steps 3 and 5 now carry the same 2 character floor step 2 already had.

**The round floor stays at 2 and must not be raised to 3.** Raising it looks safer and is not: at a floor of 3, `using` cannot strip `ing` to `us` and `use` cannot drop its `e` to `us`, so the `use` and `using` pair in the table below stops agreeing, and the property that justifies this whole arrangement breaks in 10 places rather than 0. The unsafe strip a higher floor was meant to prevent, `sing` collapsing to `s`, is already refused by the floor of 2, since one character would remain.

**Termination is bounded and must stay bounded by the rules, not by an iteration cap.** Every round either strips or rewrites in a way that strictly shortens the token, or it changes nothing and the loop halts. The round floor of 2 bounds the descent. So the loop runs at most as many rounds as the token has characters, and an implementer must not add an arbitrary cap: a cap would make this a different algorithm from the one pinned here.

Normative examples, which double as the test vectors and as the evidence for what the family does and does not reach:

```text
Input        Canonical stem   Rounds   Note
decide       decid            1
decides      decid            1        reaches the decide group
decided      decid            1
deciding     decid            1
decision     decision         1        does NOT reach decided, as intended
use          us               1
using        us               1        the e drop pair
ship         ship             1
shipped      ship             1        the doubling pair
rely         rely             1
relies       rely             1        the y to i pair
records      record           1        ordinary plural
chose        cho              2        was chos before the loop, corrected 2026-08-14
chosen       chosen           1        irregular, not reached by any stemmer here
retrieve     retriev          1
retrieval    retrieval        1        Porter would join these, this family does not
process      proc             3        was proces before the loop, corrected 2026-08-14
setting      set              2        the pair the single round split
settings     set              3        both reach set only because the loop repeats
need         ne               1        the pair the step 3 and 5 floors rescued
needs        ne               2
falls        fal              1        the experiment 0010 pair, joined here too
falling      fal              1
sing         sing             1        the floor of 2 refuses the strip, no collapse to s
singing      sing             2
```

### Value sourcing

```text
Produced value                  Source
Lexical document                field_label(value_path) plus the stored chunk text, composed
                                at query time under lexical-document-v1
Field label text                the nine entry application mapping (AC-2), one source of truth
Lexical tokens                  lexical-tokenizer-v2 over the lexical document
Canonical stem                  the shared morphology family's canonicalizing entry point
Verification stem match         the same family's base set entry point (spec 0010 AC-11)
Lexical rank                    positive BM25 scores sorted descending then chunk id, as today
Semantic rank                   unchanged, all eligible distances sorted locally
Fused score                     1/(60 + rank) summed over whichever ranks exist, no eligibility cut
Accepted context                unchanged two pass diversity over the fused order
Settings trace                  fixed query constants plus lexical-document-v1 and the v2 tokenizer id
AC-10 blocking figure           the DM-0008 decision.chosen chunk's final disposition, from the
                                existing Diversity trace, over 6 fixture runs
AC-11 step figures              LexicalRow.rank and .disposition, SemanticRow.rank,
                                FusedCandidate.fused_score, .fused_rank, .final_disposition
AC-13 stage attribution         abstention_cause, the dropped_sentences reason,
                                classify_query4_failure, all already in the trace
```

### Key invariants

1. No stored value changes. `PipelineConfig`, `embedding_input`, chunk text, chunk ids, and fingerprints are untouched, so `pipeline_signature` does not move and no existing store is locked out.
2. The two retrievers read different documents on purpose. The semantic side embeds the dotted `value_path` because the embedding model breaks it into subwords; the lexical side reads plain words because `lexical-tokenizer-v1` splits on the dot and yields tokens no question matches. This asymmetry is deliberate and is not to be harmonized without paying for a rebuild.
3. Retrieval never branches on what kind of question it was asked. No model rewrites the question, no rule inspects it, and no value path is boosted, filtered, or reserved a slot. A field label either matches the question's words or it does not, and a miss shows as `no_term_match` on that chunk in the existing lexical trace.
4. Rank is the only ordering fact. No stage carries a threshold flag whose meaning duplicates a rank already on the row.
5. The morphology family has one definition. Two entry points may exist for the two shapes the callers need, and the implication property (a base set match implies equal canonical stems) is tested; two independent rule sets may not. The two entry points have deliberately different lossiness, which is why only the implication holds and not its converse.
6. Diversity is untouched. Record cap 2 and accepted limit 8 stay, and no chunk is granted a slot for the field it holds.

### Security model

Unchanged. A local single user CLI with no authentication layer. Lexical retrieval remains local and sends nothing new outside the machine. Debug output still contains every active chunk and now also every fused candidate rather than the top 29, so the Fusion section grows to corpus size alongside the Filter, Lexical, and Semantic sections that already are.

### Critical test scenarios

1. Lexical document composition: a mapped path yields label, blank line, chunk text; an unmapped path yields the chunk text alone, verifies **AC-1**.
2. Single source label: the lexical stage and the generation evidence block read the same mapping, and `decision.chosen` reads `what this record decided`, verifies **AC-2**.
3. Single retriever chunk reaches the context: a chunk ranked by one retriever only, at a rank past 24, contributes to fusion and can be accepted, verifies **AC-3** and **AC-4**.
4. Schema constant: `result.schema_version` equals `QUERY_SCHEMA_VERSION` and equals 3, verifies **AC-5**.
5. Tokenizer vectors: every normative example in the `morphology-v1` table, plus the unchanged stopword digest, verifies **AC-6**.
6. Morphology implication: a base set match implies equal canonical stems, asserted over the normative table and the measured pairs, with the two known non properties covered as explicit negative cases (`falls` whose canonical stem `fal` is not in its base set, and `file` against `fill` whose equal canonical stems do not imply a base set match), verifies **AC-7**.
7. Fixture blocking bar: DM-0008's `decision.chosen` chunk is in the accepted eight in 6 of 6 runs, verifies **AC-10**.
8. JobPilot battery: `query-2-resume-generation` requires a `decision.chosen` citation from one of its required records on the covering sentence, and the other four queries and three assertions keep whole answer semantics with no value path prefix added, verifies **AC-8** and **AC-9**.
9. Layering: the application and domain layers import no `rank_bm25`, `chromadb`, `openai`, `typer`, or `pydantic`, verifies **AC-14**.

## Migration plan

**Strategy**: no migration needed

**Phases**: one deployment. Nothing hashed into `pipeline_signature` changes, so an existing store keeps working and `ingest --rebuild` is not required. This is the deliberate contrast with spec 0008, whose store format 2 did force a rebuild.

**Rollback**: revert the commits. No stored data was transformed, so an older build reads the same store unchanged. The only visible difference is the trace vocabulary and the schema version integer, neither of which is persisted.

**Risks**: the reworded `decision.chosen` label reaches generation as well as retrieval, so a regression would show in generation framing rather than in ranking. The three step measurement sequence is what separates the two.

## Build plan

Skateboard, and the three ranking changes land cumulatively with a measurement after each, most specific hypothesis first. No step is measured in isolation from a change already shipped, because the three interact: the label's effect on the fused result depends on the eligibility cut being gone, and stemming's effect depends on the label existing to stem. A full both query gate run costs about 12.5 cents at the rates experiment 0007 recorded, so three of them is about 37 cents.

1. Move the field label mapping and value path tuple to the application layer as one source of truth, reword `decision.chosen`, and leave the other eight, satisfies **AC-2**.
2. Add `lexical_document()` and its `lexical-document-v1` identifier, feed it to the lexical stage, and record the identifier in the settings trace. Then record the step 1 stage level figures, satisfies **AC-1**, **AC-11**.
3. Remove fusion eligibility, retire the top 24 boundary and its two settings fields, and advance the schema to 3 through `QUERY_SCHEMA_VERSION` at all three sites. The complete call site inventory for the retired names, so the build does not rediscover it: `query.py:96,445,446,937,938,1227,1228`, `dto.py:88,95,509,510`, the two renderer lines `cli.py:964-965`, and the tests at `test_retrieval_stages.py:296,387,391,458` and `test_evaluation.py:91,92`. Then record the step 2 stage level figures, satisfies **AC-3**, **AC-4**, **AC-5**, **AC-11**.
4. Move the morphology family to `application/morphology.py` with its two entry points and the implication property, implement `morphology-v1` to the pinned algorithm (including the repeat until stable loop and the floors on steps 3 and 5) and its corrected normative examples, then advance the tokenizer to `lexical-tokenizer-v2`. **Coordinate with spec 0010 task 18**, which moves the same module and owns the base set entry point; whichever lands first does the move. Then record the step 3 stage level figures, satisfies **AC-6**, **AC-7**, **AC-11**.
5. Add `required_value_path_prefixes=("decision.chosen",)` and `covering_sentence_scope=True` to the `query-2-resume-generation` oracle in `EVALUATION_FIXTURES`, leaving its `required_record_ids` and every other fixture untouched, satisfies **AC-8**, **AC-9**.
6. Run the blocking bar over the frozen fixture, record the end to end result with its stage attribution, and write the numbered experiment. Apply the AC-12 trigger only if the chunk still misses, satisfies **AC-10**, **AC-12**, **AC-13**.
7. Complete the deterministic tests, ruff, strict mypy, and the layering check, satisfies **AC-14**.

## Consequences

**Positive**:

1. A terse decision field can compete with long prose about the same decision, because the label carries the field kind in words a question can match and its rarity across the corpus is what BM25 rewards.
2. Evidence is no longer discarded for the shape of the retrieval stack. Today a chunk ranked first by one retriever loses to a chunk ranked 24th by both, at every corpus size.
3. The structural bias toward chunks both retrievers found largely dissolves, since semantic presence becomes universal. The one remaining asymmetry, lexical presence, is zero exactly when no query term appears in the chunk, which is a meaningful distinction rather than an arbitrary rank threshold.
4. Pressure to lower the reciprocal rank fusion constant drops, so that knob stays with its owner in spec 0008 Follow-up item 2 rather than being calibrated by argument here.
5. The gate that first missed this failure can now see it. A criterion asserting what an answer says cannot verify where it came from, and the JobPilot battery gains the provenance half the fixture gate already has.
6. `QUERY_SCHEMA_VERSION` stops being dead, which closes spec 0008 Follow-up item 13.

**Negative and tradeoffs**:

1. The field label mapping now serves two surfaces with different objectives. A wording chosen to earn a lexical match could weaken generation framing, and the reverse. The mapping is declared retrieval affecting for exactly this reason, and one wording is being changed on measured evidence while eight are left alone.
2. Label tokens lengthen every document slightly, and BM25 length normalization penalizes longer documents. It is negligible for a body chunk targeting 400 tokens, and second order but real for a decision chunk of roughly twelve tokens, where a two token label is about a 17 percent length increase. The high IDF exact match outweighs it.
3. Fusion becomes unbounded. Every query now builds, scores, sorts, and renders one `FusedCandidate` per accepted chunk rather than for the union of two capped lists, so the work and the debug section are both linear in corpus size, joining the three sections that already were. Diversity still stops at eight, so no behaviour changes. This lands on the same scale boundary spec 0008 negative consequence 3 already records for the semantic stage, and it is accepted for the same reason: the corpus is dozens to low hundreds of records, and the bound must be measured before it is changed rather than guessed at now.
4. The mechanism is corpus dependent and can weaken silently. It rests on the label words staying rare, and a corpus whose prose already uses `decided` and `decision` heavily, which is plausible for a corpus of decision records and certain for this project's own specs, shrinks the IDF advantage exactly where it is needed. A weakening shows as a lower lexical rank in the existing trace rather than as an error, so it is visible but only to someone looking.
5. Retiring `outside_top_24` deletes closed enum values and settings fields that spec 0008 AC-5, AC-6, and AC-10 pin, so a contract that passed verification is visibly narrowed, and it removes one of the four knobs spec 0008 Follow-up item 2 lists for calibration.
6. A new tokenizer identifier re pins a verified contract and changes lexical behaviour for every query, not only for decision questions.
7. The morphology family becoming shared means a change made for retrieval also moves the spec 0010 additive and completeness checks, whose split experiment 0007 measured at 7 of 7 `content_token`.

**Neutral**:

1. The two retrievers still read different documents. That is now a stated invariant rather than an omission.
2. Stemming is not what lands the gate query. The family reaches the decide group and ordinary plurals; it does not reach `decided` from `decision`, and neither would Porter. It is in scope for general recall, and the spec should not be read as claiming otherwise.
3. The reason query's evidence changes too, since `why[i]` also gains a label. Its sentences are dropped inside verification, which this spec does not touch, so any movement there is observed rather than expected.
4. Diversity is untouched, and no chunk is granted a slot for the field it holds. Guaranteeing the answer chunk a seat was considered and rejected because it would leave both real defects in place and make them unmeasurable afterwards.

## Follow-up

1. [ ] Decide whether the record title belongs in the lexical document, after the AC-11 figures exist. It was left out deliberately: the title contributes no new query term on the gate query, only a term frequency bump offset by length normalization, and copying record wide vocabulary into every chunk of a record dilutes IDF and blurs within record discrimination, which is the wrong direction when the decision chunk lost to a `body[2]` chunk of the same record.
2. [ ] Move the embedding prefix onto the same plain words mapping when the next pipeline signature bump happens for an independent reason. It is genuinely the cleaner invariant and only the forced rebuild makes it a bad trade today, so this is deferred to when the rebuild is already paid for, not abandoned.
3. [ ] Reconcile spec 0008 Follow-up item 2 in the same edit: deleting `lexical_limit` and `semantic_limit` removes one of its four named knobs, and the reciprocal rank fusion constant gains the AC-12 numbered trigger as its calibration condition.
4. [ ] Close spec 0008 Follow-up item 13 with the AC-5 work rather than leaving it open against a schema version that has since moved.
5. [ ] Promote the generalizable lesson to root `AGENTS.md` through `/sync`: a gate that asserts what an answer says cannot verify where the answer came from. Spec 0008 AC-13, spec 0010 AC-15, and this spec's AC-8 and AC-9 are three instances, and spec 0010's Follow-up already carries a similar promotion item.
6. [ ] Re measure the spec 0010 task 13 additive tolerance target after this work lands, as spec 0010's own amendment and the session notes both require. Experiment 0007's 7 of 7 `content_token` split was taken while no `decision.chosen` chunk reached generation, and both the evidence and the morphology rules move here.
7. [ ] Reword a further field label only against a measured failure, at the same evidence standard as the `decision.chosen` change. Tuning the other eight against no observed miss was considered and rejected as premature.

## Rationale

Reasoning and options: see [rationale.md](rationale.md).
