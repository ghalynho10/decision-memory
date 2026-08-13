# Experiment 0005: the strengthened gate oracle, first measurement

**Date**: 2026-08-13
**Status**: Complete
**Follows**: [Experiment 0004](0004-clean-pipeline-re-measurement.md)
**Result**: The gate fails 0 of 6 on both halves, which spec 0010 predicted, and it now says why. The abstaining query abstains from `no_emitted_sentences` where its manifest pins `uncovered_facet`, so the vacuous abstention that passed every earlier gate is now a named failure. The AC-16 caveat miss count is **0 misses over 0 covered runs**, and the zero denominator is a result rather than a gap: the decision facet was never covered at all, in 6 runs where coverage was called every time and a caveat sentence reached it every time.

## What changed under the measurement

Spec 0010 tasks 16 and 15 shipped before this run, in that order, and both changed what the gate can see rather than what the pipeline does:

- **The directness exclusion is stated to the coverage model** (AC-16). `COVERAGE_SYSTEM_PROMPT` now says that a statement about what the evidence does or does not establish is a limitation, never a decision, and never covers a decision facet. `validate_coverage` and the schema shape are unchanged.
- **The gate's oracle is state, a co located citation, and an abstention cause** (AC-15). The manifest carries `expected_value_paths` and `expected_abstention` on every query, the loader refuses a manifest key it does not recognize, and `evaluate --battery PATH` runs the battery the manifest declares with the corpus root taken from that file's parent directory.

The corpus is the same frozen fixture as experiment 0004, regenerated only to add the two manifest keys: the copied files and their 22 hashes are byte identical, so nothing under the measurement moved. All 6 fixture tests pass, including the faithfulness check on `DM-0008`.

Instrument:

```bash
uv run --env-file .env decision-memory evaluate \
  --battery docs/experiments/data/self-corpus-fixture/manifest.json \
  --runs 3 --records <dir>/records-a --store <dir>/store-a   # batch A
# batch B identical, into records-b and store-b
```

## Finding 1: both halves fail 0 of 6, and the failures are now legible

| Query | Manifest expectation | Batch A | Batch B | Detail the gate reported |
|---|---|---|---|---|
| decision | `answered`, cite `decision.chosen` of `DM-0008` from the covering sentence | 0/3 | 0/3 | expected answered, got abstained |
| reason | `abstained` from `uncovered_facet` | 0/3 | 0/3 | abstained from `no_emitted_sentences`, expected `uncovered_facet` |

Both batches are identical, which is itself worth noting: experiment 0004 saw the decision query flip states between runs, and it did not flip once in these 6.

The second row is the point of the whole criterion. **Under the old state only oracle that row reads PASS, 6 of 6.** The query abstains, which is what the manifest asked for, and every earlier gate stopped there. It abstains because all three of its draft sentences were dropped before coverage ran, so the pipeline proved nothing about abstention; the gate now names that and fails. Experiments 0002, 0003, and 0004 each recorded this by hand while reading traces, and no gate could see it.

The first row fails as the spec said it would, and its bar was provisional for exactly this reason: a stochastic pipeline fails toward abstention, and the answering half cannot land before task 13's calibration.

## Finding 2: the AC-16 caveat miss count is 0 over 0, and the zero denominator is the finding

The trigger AC-16 defines is a number: build the deterministic guard if a caveat covers the decision facet in 2 or more of the 6 gate runs taken after the instruction change, otherwise the instruction stands and the count is recorded here with its denominator.

**Numerator 0, denominator 0.** The decision facet's coverage row came back `covered=False` in all 6 runs, so no run had a covered decision row for a caveat to have wrongly covered.

The denominator is zero for a reason worth separating from the obvious one. It is **not** that nothing reached coverage:

| Run | Draft sentences | Emitted to coverage | Coverage calls | Decision facet |
|---|---|---|---|---|
| 1 | 4 | 3 | 1 | uncovered |
| 2 | 3 | 2 | 1 | uncovered |
| 3 | 3 | 2 | 1 | uncovered |
| 4 | 3 | 2 | 1 | uncovered |
| 5 | 3 | 1 | 1 | uncovered |
| 6 | 3 | 1 | 1 | uncovered |

Coverage ran in every run, on 11 emitted sentences across the 6. The caveat sentence experiment 0004 caught being accepted as a decision survived verification in all 6 runs, and in runs 5 and 6 it was the **only** sentence reaching coverage, which is the exact configuration of the recorded miss:

```text
S3  The JobPilot corpus cannot establish that hybrid retrieval is better at
    scale, and it does not claim general retrieval superiority.
```

Coverage refused to cover the decision facet with it every time. So the reading is that the caveat miss cannot occur in the pipeline's current state, on this query, with the exclusion instruction in place. The trigger cannot fire on 0 of 0, the instruction stands, and the deterministic guard is not built.

**Two scope limits on that number, so a later reader does not take it for more than it is.**

- It is one query's behaviour. AC-16 defines the trigger over the gate runs, so this is the right scope for the trigger itself; it is **not** a general caveat coverage miss rate. Re measure it across the 12 query sweep once calibration lets sentences through in quantity.
- It comes from 6 dedicated runs of the gate's decision query against the batch B store, not from the 12 runs inside the two `evaluate` batches. The report gives a per fixture pass rate, not per run coverage rows, and the fraction needs the rows. Same store, same frozen corpus, same question, one run apart.

## Finding 3: the answering half is harder than the drop rate suggests

Run 1 emitted three sentences, one of which reads as a direct answer to the question the facet asks:

```text
S1  The hybrid retrieval system uses a combination of lexical BM25 and
    semantic Chroma retrieval, followed by reciprocal rank fusion to
    combine rankings ...
```

The decision facet still came back uncovered. Across the 6 runs, 11 sentences reached coverage and none of them covered the single facet the question produced.

That matters for task 13. The calibration target is the additive tolerance, and loosening it raises how many sentences survive to coverage; these runs already had survivors and still did not answer. So the provisional 6 of 6 answering bar in AC-15 is exposed to two independent things: whether sentences survive verification, and whether coverage's directness rule accepts one of them as stating the decision. Only the first is what task 13 calibrates.

The drops behind it are the familiar ones and confirm task 13's target rather than moving it: 8 dropped sentences across the 6 runs, all `decomposition_invalid`, 7 `not_additive` and 1 `incomplete`.

## What this changes

1. **Nothing about the build.** The gate failing honestly is the gate working; only a gate that passes wrongly is a defect. Both failures were predicted in AC-15 and both landed exactly as written.
2. **The AC-16 guard is not built, on a number rather than a judgment call.** 0 of 0, recorded with its denominator, re measured after calibration.
3. **The AC-15 answering bar stays provisional**, and finding 3 says why it should: confirming or relaxing it needs a post calibration measurement that separates sentence survival from coverage directness.
4. **The `expected_abstention` field is worth applying to the JobPilot abstention gates**, which spec 0010's follow up already tracks. Query 5 and the unverifiable claim assertion pass on `expected_state` alone today, and this run is the first direct evidence that a state only abstention gate can be passing on nothing.

## Threats to validity

- Two batches of one query pair, plus 6 runs of one query, on a 6 record corpus. The 0 of 6 figures are unanimous, which is stronger than a rate, but the sample is one question on one small corpus.
- The AC-16 denominator is measured on the query most likely to produce a caveat, since that is where the miss was recorded. That biases toward finding a miss, which makes a zero more meaningful, and it says nothing about the other 11 queries in the sweep.
- Coverage is still barely sampled: 6 calls here, all on the same question.
- The exclusion instruction and the co location oracle shipped together in the same session, so the coverage refusals cannot be attributed to the instruction alone. Experiment 0004 recorded a caveat covering the facet before the change and this run records it not covering after, one observation either side.
