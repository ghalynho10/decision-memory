# Experiment 0007: field labels reach generation, and the blocker moves one stage

**Date**: 2026-08-13
**Status**: Complete
**Follows**: [Experiment 0006](0006-coverage-directness-isolation.md)
**Result**: AC-18 worked on the stage it targeted and the gate still fails 0 of 6. Generation now states decisions: **24 of 24 draft sentences** are framed as a decision, against the descriptions experiment 0006 recorded. Coverage never got to judge one, because every sentence was dropped before it. The decision query now fails at **entailment**, not coverage, and the reason it fails is one stage earlier still: **no `decision.chosen` chunk is ever retrieved**, so the model asserts a decision from a `body[2]` chunk and entailment correctly refuses it. The first ever `not_additive` split is **7 of 7 `content_token`, 0 `function_word_overrun`**, which means the task 13 tolerance knob reaches none of these drops.

## Method

Two `--runs 3` batches over the frozen self corpus fixture, both against one store, so the evidence is held constant the way experiment 0006 held it. The instrument is committed: `docs/experiments/data/coverage-directness.sh` drives the shipped CLI, keeps every `--debug` transcript verbatim in `data/coverage-directness/transcripts/`, and `coverage-directness-extract.py` emits one record per run to `data/coverage-directness/runs.jsonl` in the shape spec 0010 Feature design pins. The queries and their expectations come from the fixture manifest, never from a spec.

```bash
decision-memory adapt docs/experiments/data/self-corpus-fixture --output <dir>/records
decision-memory ingest <dir>/records --store <dir>/index
docs/experiments/data/coverage-directness.sh <dir>/index
```

All 6 fixture tests pass, including the AC-14 faithfulness check, so the fixture is a faithful stand in before any result is read.

**What changed under the measurement** (spec 0010 task 17):

- **AC-18**: each generation evidence block gains a `Field:` line in plain words above the chunk text, from the pinned nine entry mapping; the evidence travels as `(chunk_id, value_path, text)` triples; `ANSWER_SYSTEM_PROMPT` gains the decision framing instruction and forbids copying the `Field:` line.
- **AC-19**: `sub_claim_is_additive_free` reports why it stopped and `RejectedDecomposition` carries the defaulted `additive_failure` category. Observational: the disposition, the retry set, and every drop path are unchanged.

## Finding 1: generation now states decisions, 24 of 24

Every draft sentence in all 12 runs is framed as a decision. This is the human half of AC-19, judged against the rule written into the spec's `rationale.md` before these runs ran, and **it is a secondary reading, labelled as such**: the primary denominator is structurally zero, because no sentence reached coverage in any run (see finding 2), so `reader_verdicts` is empty on all 12 records and these are the **draft** sentences instead.

**24 of 24 `states_decision`, 0 `does_not`, 0 `ambiguous`.**

The decision query wrote one sentence, byte identical in all 6 runs:

```text
S1: The decision was to use a hybrid retrieval system that combines lexical
    BM25 and semantic Chroma retrieval, followed by reciprocal rank fusion to
    integrate the results.
```

The reason query wrote three per run, in the same shape:

```text
S1: Hybrid retrieval was chosen because it allows for deterministic
    multi-source behavior, complete diagnostics, and honest abstention, even
    though it does not claim general retrieval superiority at scale.
S2: Lexical retrieval was chosen because it allows for local scoring with
    BM25 in memory, using SQLite as the authoritative data source, and it
    avoids relying on third-party libraries in application code.
S3: Semantic retrieval was chosen to provide a path for Chroma to return up
    to 24 candidates, with the application accepting eight, and to allow for
    semantic rank explanation and claim verification.
```

Set beside what experiment 0006 recorded reaching coverage from the same corpus, the contrast is the whole point of AC-18:

```text
0006 arm A: The hybrid retrieval system uses a combination of lexical BM25
            and semantic search...      (refused by coverage, correctly)
0007:       The decision was to use a hybrid retrieval system that combines...
```

The mechanism AC-18 named is real. Generation was answering a decision question from prose that never said it was a decision, and telling it which part of the record each chunk is changed the phrasing on the first try, in 24 of 24 sentences.

**Every judged sentence is quoted above** so a later reader can apply the same rule and disagree. The verdicts were written after the machine half, from the quoted text alone, without reading the coverage rows.

## Finding 2: the blocker moved from coverage to entailment, and the gate still fails 0 of 6

| Query | Manifest expectation | Batch 1 | Batch 2 | What the gate reported |
|---|---|---|---|---|
| decision | `answered`, cite `decision.chosen` of `DM-0008` from the covering sentence | 0/3 | 0/3 | abstained, no sentence survived verification |
| reason | `abstained` from `uncovered_facet` | 0/3 | 0/3 | abstained from `no_emitted_sentences` |

Both rows are unchanged from experiment 0005 in verdict, and both changed underneath it in cause.

| | Experiment 0005 | Experiment 0006 arm A | Experiment 0007 |
|---|---|---|---|
| decision query draft sentences | 3 to 4 per run | 3 to 4 per run | **1 per run** |
| sentences reaching coverage | 11 across 6 runs | 11 across 6 runs | **0 across 6 runs** |
| decision query drop cause | mixed | mixed | **`unsupported_sub_claim`, 6 of 6** |
| decision facet covered | 0 of 6 | 0 of 6 | 0 of 6, never judged |

Generation now writes one focused sentence for the one facet instead of three or four, and that one sentence is dropped every time. Coverage was called in every run of experiment 0005; here it judged nothing, because the deterministic no sentence path applied in all 12 runs.

Sub claim entailment verdicts across the decision query's 6 runs: **18 supported, 6 unsupported**, exactly one unsupported per run, and it is the same sub claim every time, the one that states the decision:

```text
S1.1  The decision was to use a hybrid retrieval system.
      entailment=unsupported
      reason=The evidence describes a retrieval system with various stages
             and methods but does not explicitly state that a hybrid
             retrieval system was chosen.
```

The other three sub claims of the same sentence (the BM25 and Chroma combination, the fusion step, the integration) come back supported in every run. So the sentence is grounded in everything except its decision clause, and the decision clause is what takes it down.

This is the second risk AC-19 named in advance, and it materialised: an instruction to state a decision pushes generation toward assertive phrasing that can overclaim against a hedged source chunk. What AC-19 did not anticipate is why the source chunk was hedged.

## Finding 3: no `decision.chosen` chunk is retrieved at all, on a question asking what was decided

The sentence cites one chunk, `ch_db2197c3...`, and that chunk is **`body[2]` of `DM-0008`**, whose field label is `other prose from this record`. Entailment is right: that chunk does not state the decision.

The eight accepted chunks, by value path, identical in every run:

| Record | Value path |
|---|---|
| DM-0008 | `body[2]` |
| DM-0008 | `context.problem` |
| DM-0007 | `body[2]` |
| DM-0007 | `body[2]` |
| DM-0006 | `body[3]` |
| DM-0006 | `rationale_summary` |
| DM-0008 | `body[1]` |
| DM-0008 | `body[13]` |

**Not one `decision.chosen` chunk is in the accepted context**, and the store holds six of them, one per record. `DM-0008`'s, the one the manifest names as the expected answer, is in the store and ranks:

```text
ch_488bebf3...  lexical  score=2.230641  rank=36  disposition=outside_top_24
                semantic rank=10         similarity=0.422761
                fused    rank=21  breadth=record_cap  final=outside_top_8
```

It is ranked 36th lexically, so it contributes no lexical rank at all; 10th semantically; 21st after fusion; and it is cut twice more, by the record cap and by the top 8. The chunk holding the answer never reaches generation.

That reframes what AC-18 could ever have achieved. The premise was that generation is the one stage that never received the `value_path`, which was true. The binding constraint is one stage earlier: **the retrieval stack does not prefer a decision chunk for a question that asks what was decided**, and no amount of labeling at generation can fix evidence that is not there. AC-18's own value sourcing table is what makes this legible: the label named the chunk `other prose from this record` and the model asserted a decision from it anyway.

The AC-15 unsatisfiable oracle check passes here, correctly and unhelpfully: it verifies that `DM-0008` carries a `decision.chosen` chunk, which it does. It has no way to check that retrieval will ever surface it.

## Finding 4: the `not_additive` split is 7 of 7 `content_token`, and task 13's headroom is zero on this evidence

The reason query dropped all 18 of its sentences as `decomposition_invalid`, and the split AC-19 instrumented is now readable for the first time:

| Disposition | Count | `additive_failure` |
|---|---|---|
| `incomplete` | 11 | empty by construction |
| `not_additive` | 7 | **`content_token` 7, `function_word_overrun` 0** |

Per run, the pattern is nearly fixed: S1 and S2 fail `incomplete`, S3 fails `not_additive`, in five of six runs; batch2-run1 has S1 fail `not_additive` instead.

`MAX_ADDED_FUNCTION_WORDS` bounds function word additions and nothing else, so **the tolerance knob reaches 0 of these 18 drops**. Task 13 was written to calibrate that knob against experiment 0004's 68 percent, and this is the measurement its 2026-08-13 amendment asked for before choosing a setting.

Two bounds on that reading, both stated in the spec's own terms and both conservative in the same direction:

- The `content_token` share is a **lower** bound on what the knob cannot reach. Some `function_word_overrun` cases are unreachable too, since a rescued sub claim can fail later on a content token, a later sub claim can fail in its place, and a response whose sub claims all pass the additive half can still fail `incomplete`.
- Here the `function_word_overrun` share, the **upper** bound on reachable headroom, is **zero**. There is nothing above it to be conservative about.

The 11 `incomplete` drops are outside the knob by construction: completeness is the safety critical direction and the tolerance does not apply to it.

Two things moved under this figure at once, which is worth naming rather than smoothing over. Experiment 0004 measured 68 percent `not_additive` on a different phrasing distribution, and task 17 was ordered before task 13 precisely because it changes how generation phrases sentences. It did: these are long, clausal, decision framed sentences, and the mix here (61 percent `incomplete`, 39 percent `not_additive`) is not comparable to 0004's as a rate. The split within `not_additive` is the figure this experiment adds, and it does not depend on the mix.

## Finding 5: the AC-16 caveat miss count is 0 over 0 again, for a different reason

Numerator 0, denominator 0. The decision facet was covered in 0 of 6 runs, so no run had a covered decision row for a caveat to have wrongly covered.

The denominator is zero for a different reason than in experiment 0005. There, coverage ran in every run and refused 11 sentences including the caveat. Here coverage never judged a sentence at all, because none survived. The trigger cannot fire on 0 of 0 in either case, the instruction stands, and the deterministic guard is not built. The AC-12 escalation count, coverage covering a decision facet with a description of how the system works, is also 0 over 0 and equally unexercised.

## Finding 6: the gate costs 12 cents and two minutes

The first recorded figure for a claim this spec has made several times.

| | Per run | 12 runs |
|---|---|---|
| Wall clock | 8.6 s (decision), 11.1 s (reason) | 118.1 s |
| Provider cost | $0.0092 (decision), $0.0116 (reason) | **$0.1250** |

Cost is computed from the token usage the provider reported per attempt, priced at $2.50 and $10.00 per million for `gpt-4o` and $0.15 and $0.60 per million for `gpt-4o-mini`. Those rates are recorded here so the same token counts can be re priced later. The figure excludes the one time adapt and ingest that built the store.

The gate is cheap. It is cheap enough that "run it twice before arguing" is the right default, which is what every experiment since 0003 has had to argue for from no data.

## Threats to validity

- **The extractor is a transcript reader, not the shipped oracle.** It mirrors `abstention_cause`, the AC-15 co location scope, and `_facet_is_reason` line for line and names each in its own docstring, but it reads printed text. A change to the debug renderer breaks it loudly; a change to the oracle's rules would not, and would leave it silently stale.
- **One query each, 6 runs.** Experiment 0006 already records that 6 runs cannot separate a small effect from noise. Finding 1's 24 of 24 and finding 3's 0 of 8 are not small effects; finding 4's 7 of 7 rests on 18 sentences from one query.
- **The store was rebuilt** for this experiment, so its embeddings are freshly generated rather than the ones experiments 0005 and 0006 queried. The corpus bytes are identical (the fixture manifest hashes are unchanged), and the retrieval ranks in finding 3 are stable across all 6 runs.
- **Two observational additions were made to take these measurements**: provider token usage on `ProviderAttempt`, without which the cost figure cannot exist, and the coverage row's reason in the debug render, which is the field `abstention_cause` reads. Neither changes a decision the pipeline makes. Both are recorded here as instruments rather than assumed ratified, and belong in the `/check review` pass over task 17.

## What this changes

- **Task 13 needs a different instrument, or it retires.** The tolerance knob reaches 0 of 18 drops in this measurement. The spec's own amendment says that outcome is a finding rather than a failure, and this is that finding.
- **A retrieval side decision is now owed.** The decision chunk of the record the manifest names is never retrieved for a decision question. That is not a verification defect and no criterion in spec 0010 reaches it, so it belongs to `/architect` rather than to this feature. It is the reason the AC-15 answering half cannot land, and it outranks calibration.
- **AC-18 is settled as working on its own stage and insufficient on its own.** The prompt half did what it was written to do, measurably. Keeping it is right; expecting it to close the gate is not.
