# Experiment 0006: isolating why coverage covers nothing

**Date**: 2026-08-13
**Status**: Complete
**Follows**: [Experiment 0005](0005-gate-oracle-first-measurement.md)
**Result**: The hypothesis under test was wrong. The AC-16 exclusion is not the blocker and is working as designed. The real blocker is that coverage rejects a direct, correct answer, and it is not something task 13 can move.

## Hypothesis

Experiment 0005 measured 11 sentences reaching coverage across 6 gate runs with none covering the decision facet, including one that reads as a direct answer. The AC-16 directness exclusion (`a statement about what the evidence does or does not establish is a limitation, not a decision`) landed in `08e6506`, the commit immediately before that measurement in `ebc8abf`.

Two facts sat together with nothing separating them. Before the exclusion, coverage covered the decision facet, wrongly, with a caveat (experiment 0004). After it, coverage covered nothing at all. The hypothesis was an over correction: that the exclusion was rejecting compound sentences which state a decision **and** note a limitation, which is the shape of a well hedged decision statement and exactly what the whole sentence contract exists to preserve.

The concern was worth testing before task 13, because calibration's success is partly judged by the answering bar. A coverage stage broken for an unrelated reason would make calibration read as a failure when it was not, which is the contaminated instrument mistake experiments 0003 and 0004 were written to correct.

## Method

One store, built from the frozen fixture at `docs/experiments/data/self-corpus-fixture/`, used for both arms so the comparison holds evidence constant.

- **Arm A**: 6 runs of the gate's decision query with `COVERAGE_SYSTEM_PROMPT` as shipped.
- **Arm B**: 6 runs of the same query on the same store with only the AC-16 exclusion clause removed. The edit was temporary and reverted with `git checkout` immediately after; the working tree was verified clean.

Sentence survival was counted per run, because a difference in coverage means nothing if the arms did not put comparable numbers of sentences in front of the coverage call.

## Result

| Arm | Sentences reaching coverage | Runs covering the facet |
|---|---|---|
| A, exclusion present | 11 | **0 of 6** |
| B, exclusion removed | 9 | **1 of 6** |

Per run, as `emitted/draft`:

```text
with:    r1=3/4  r2=1/4  r3=1/4  r4=3/4  r5=1/3  r6=2/4
without: r1=1/4  r2=2/3  r3=2/4* r4=1/3  r5=2/4  r6=1/4     (* covered)
```

Arm A put **more** sentences in front of coverage and covered nothing. Arm B put fewer in front and covered once. At this scale, 1 of 9 against 0 of 11 is a single event, not a rate.

## Finding 1: the exclusion is not the blocker, and removing it reproduces the defect it was written for

The one covering run in arm B covered with this sentence:

```text
F1 covered=True [S4]
S4: The JobPilot corpus cannot establish that hybrid retrieval is better at
    scale, and it does not claim general retrieval superiority.
```

That is the caveat sentence, and covering a decision facet with it is exactly the OD-5 defect experiment 0004 recorded. **Removing the exclusion brought the original bug straight back.** The exclusion is doing its job.

The hypothesis is therefore rejected, and rejected in both directions: the exclusion is neither the cause of the null result nor a candidate for narrowing on this evidence.

## Finding 2: coverage rejects a direct answer, and this is the real blocker

Arm A run 1 emitted three sentences. One of them:

```text
S1: The hybrid retrieval system uses a combination of lexical BM25 and semantic
    Chroma retrieval, followed by reciprocal rank fusion to combine their
    contributions.

F1 covered=False []
uncovered F1: What was decided about hybrid lexical and semantic retrieval?
```

The sentence is correct, well cited, and answers the question a reader would say the facet asks. Coverage rejected it.

The mismatch is in the framing. The facet asks what was **decided**. The sentence says what the system **uses**. Under AC-12's directness rule, a statement of fact about the system is not literally a statement of a decision, so a strict reading refuses it. The corpus stores decisions, generation writes descriptions of systems, and coverage demands the decision framing and never receives it.

This is not the caveat problem, not the marker problem, and not the additive tolerance. It is a fourth, separate cause, and it sits in AC-12 rather than in AC-11 or AC-16.

## What this changes

**Task 13 is unconfounded and can proceed.** The reason for running this test first was to rule out a contaminated instrument, and it did.

**Task 13 will not make the gate's answering half pass.** Calibration raises how many sentences survive verification. Survival is not the binding constraint: arm A had 11 sentences reach coverage and none covered. Experiment 0005 finding 3 predicted exactly this, and this experiment confirms it with the exclusion controlled for.

So the AC-15 answering bar is blocked behind a decision nobody has taken yet, and the drop rate work is independent of it. Both are real; neither substitutes for the other.

## Threats to validity

- Six runs per arm, one query, one corpus. A single coverage event separates the arms, and one event cannot distinguish a small real effect from noise. The finding this experiment rests on is finding 2, which does not depend on the arm comparison at all.
- Arm B ran second, so any drift in provider behaviour over the session is confounded with the arm. The arms were minutes apart, which bounds but does not remove this.
- Sentence survival differed between arms (11 against 9) despite identical inputs, which is a reminder that decomposition is stochastic and that per run counts here are small.
- One reading was checked and discarded: an uncovered coverage row appeared to carry a reason arguing *for* coverage. Reading the trace at the line rather than through a grep showed that reason belonged to a sub claim entailment row in the following section, not to the coverage row. Recorded because the check is the point, not the result.

## Next

The coverage directness gap is an open decision, recorded as OD-7 in spec 0010. It needs a choice about whether a facet asking what was decided may be covered by a sentence stating what the system does, and if so how that is expressed without reopening the caveat hole that AC-16 just closed.
