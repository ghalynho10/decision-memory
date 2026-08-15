# Experiment 0016: the tie break was real and never fired

**Date**: 2026-08-14
**Status**: Complete
**Follows**: [Experiment 0015](0015-the-store-is-deterministic-its-names-are-not.md)
**Result**: The unstable tie break is gone from ranking, and **the measurement that was supposed to show it mattering showed nothing**. Two builds of the JobPilot corpus accepted the same eight chunks, in the same order, on all three tested questions, **both before and after the fix**. The mechanism experiment 0015 traced is real and is now closed, but it was not changing answers on this corpus, so it does not explain experiment 0014's batch D. Spec 0012 is correct as a property of the code and is not supported by this measurement, and those are two different claims.

## Why this run happened

Experiment 0015 found that `chunk_id` moves on every build while content stays byte identical, and that `query.py` breaks ties on `chunk_id` in all three ranking paths. That is a path from a store rebuild to a different evidence set entirely inside shipped code, which is the shape experiment 0014's batch D showed when it answered `query-5-uploaded-files` 3 of 3 with a fluent, well cited, wrong answer.

Spec 0012 replaced the tie break with `(record_id, fingerprint, value_path, ordinal)`. Its build plan put the measurement before the change, for the reason this project has used eight times: an instrument that has never run against the current code cannot tell a fixed defect from an instrument that could never see it. That ordering is what produced this result.

The build plan's task 1 said the pre fix run was **"expected to show the two builds accepting different chunks."** It did not. This experiment records that.

## Method

`docs/experiments/data/store-build-determinism.sh` gained a fourth comparison level, `compare-retrieval.py`. The levels above it compare what two stores hold; this one compares what retrieval selects from them, which is the half that reaches the answer and the only level that exercises the embedding vectors.

For each question it runs the shipped `query` command against build a and build b, reads the accepted chunk ids off the debug trace, and translates them through the shipped `SqliteChromaIndexReader` into the stable key before comparing anything. **The keying is not a detail.** Accepted chunks come back as chunk ids, which share nothing across builds by construction, so comparing them as ids reports total disagreement whether or not anything real moved. That is the trap experiment 0015 recorded against itself.

Order is compared as well as membership, because the accepted list is in final rank order and that order builds the generation context.

Question set: `query-1`, `query-4`, `query-5`, imported from the shipped battery rather than written into the script, so they cannot drift from the fixtures. One expected to answer and two expected to abstain, since the accepted set is built before either outcome is decided.

Runtime: about 25 seconds per build, plus one real query per question per build.

## Result

Identical before and after the change:

```text
--- retrieval: accepted chunks per build ---
query-1: a=8 b=8 same set: True | same order: True
query-4: a=8 b=8 same set: True | same order: True
query-5: a=8 b=8 same set: True | same order: True
verdict: same accepted set 3/3, same accepted order 3/3
```

The store level comparison reproduced experiment 0015 a third time on a fresh pair of builds: 378 chunks each, identical text, identical fingerprints, and 378 of 378 chunk ids different.

### Why it did not fire

Reciprocal rank fusion separates the candidates into two score bands, and the accept boundary sits inside the upper one.

A chunk ranked by both retrievers scores `1/(60+l) + 1/(60+s)`, at least `2/84`, which is `1/42`. A chunk ranked by one retriever scores `1/(60+r)`, at most `1/61`. Since `1/42 > 1/61`, **every both ranked chunk outscores every single ranked chunk**, with no overlap at all. Enumerated exhaustively in exact rational arithmetic over every reachable `(lexical_rank, semantic_rank)` shape with `RRF_CONSTANT = 60` and `CANDIDATE_LIMIT = 24`:

```text
collision groups mixing a both ranked chunk with a single ranked chunk:  0
collision groups where all members are single retriever chunks:         24
collision groups where all members are both ranked chunks:             276
  of those, groups that are not simply (a, b) against (b, a):            1
    1/36  shared by (3, 24), (12, 12), and (24, 3)
```

The 24 single retriever collisions are the abundant class, and they sit entirely in the lower band. The diversity walk accepts eight, and on this corpus those eight are drawn from the upper band, where a collision needs two chunks with swapped ranks. So the ties are real, structurally guaranteed, and below the cut.

The lexical side says the same thing one level up. Running the shipped BM25 scorer over all 378 chunks for the six battery questions, offline and with no provider:

| Query | Positive scoring | Tied chunks | Tie groups | Tie straddling rank 24 |
|---|---|---|---|---|
| query-1 | 122 | 14 | 7 | no |
| query-2 | 118 | 6 | 3 | no |
| query-3 | 114 | 14 | 6 | no |
| query-4 | 135 | 2 | 1 | no |
| query-5 | 49 | 6 | 3 | no |
| rationale | 260 | 8 | 4 | no |

Ties are common, between 2 and 14 chunks per query. None straddles the top 24 boundary on any question.

### What is closed anyway

The property the fix delivers is proven by deterministic tests rather than by this run, and it is a real property. `tests/test_stable_ranking.py` re ranks an identical candidate set with every chunk id replaced and asserts the semantic order, the lexical order, the fused order, and the accepted eight all come back identical. Five of those tests were re run against the old `chunk_id` rule and **all five fail under it**, so they guard the regression rather than merely describing the new behaviour.

The lexical scorer was checked for the other route a build could have reached ranking: it feeds documents in `chunk_id` order, so any order sensitivity would have left retrieval build dependent even with a stable key. Measured at exactly zero score difference over a shuffled corpus, and pinned as a test.

## What this changes

- **Batch D is not explained by the tie break.** Experiment 0015 was careful to call its finding a mechanism rather than an attribution. This measurement is the attribution attempt, and it comes back negative. Whatever moved between experiment 0014's batches, on this corpus it was not the accepted context moving with the store.
- **The remaining candidate is provider variance**, which experiment 0014 named and could not separate. It is now the only named candidate still standing for the between batch spread, and nothing here measures it.
- **A guarantee replaced a coincidence.** The accepted set agreed across builds before the fix, but by the arithmetic of the score bands rather than by design, and that arithmetic is spec 0011's to change: its AC-3 and AC-4 remove fusion eligibility and retire the top 24 boundary, which makes 51 mixed band collision groups reachable that are impossible today. The fix that looks inert now is what keeps that change from being a correctness question.
- **Spec 0012's own build plan carried a wrong expectation**, and it is corrected here rather than quietly dropped. Predicting the result of a measurement in the task that orders it is how an instrument gets read to confirm rather than to find out.

## Threats to validity

- **Three questions, one corpus, one build pair.** A negative result over three questions does not show ties never reach the accept boundary. It shows they did not here.
- **The comparison cannot see a tie that both builds break the same way.** Two builds whose fresh chunk ids happen to order a tied pair identically would agree, and this reports agreement. With 378 ids moving on every build that is unlikely per pair, but the run does not count how many ties were exposed to the boundary at all, which is the measurement that would turn this negative into a bound.
- **The embedding half is exercised but not isolated.** Identical accepted sets mean the vectors did not move the ranking, which is stronger than experiment 0015 had, but no distance was compared directly, so a small vector difference absorbed by a large score gap would not show.
- **Post fix agreement is not evidence the fix works.** It is evidence nothing broke. The property itself is carried by the deterministic tests, and this run cannot distinguish a working tie break from an inert one, which is precisely the finding.

## Follow-up

- [ ] **Count how often a tie reaches the accept boundary**, which is what turns this negative into a bound rather than an observation. It needs no provider beyond the store: the fused scores are computable offline from a built store, so the number of collisions at positions 8 and 9 across the full battery is a cheap measurement nobody has taken.
- [ ] **Re run this after spec 0011 lands.** That spec makes the mixed band collision class reachable, so this is the measurement that should be expected to move, and it is the one place the tie break could start mattering on real data.
- [ ] **Provider variance is now the only named candidate for experiment 0014's between batch spread.** It needs its own instrument; nothing so far separates it from anything else.
- [ ] The capability re baseline that spec 0012 AC-9 defers is still owed, at the AC-24 denominator of four batches, and must not share runs with the spec 0010 task 21 prune.
