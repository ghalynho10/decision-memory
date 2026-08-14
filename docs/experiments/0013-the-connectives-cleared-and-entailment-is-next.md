# Experiment 0013: the connectives cleared, and the blocker moved to entailment

**Date**: 2026-08-14
**Status**: Complete
**Follows**: [Experiment 0012](0012-the-other-three-abstentions.md)
**Result**: AC-21 removed the cause experiment 0012 named. **`where`, `while`, and `instead` appear zero times as a `failure_token` across the 12 traced runs**, and the completeness half is down from the sole cause on three fixtures to **1 of 7 rejections**, on `ensuring`, which is a genuine content word the check is right to demand. **Two of the three fixtures moved**: `query-1-private-beta-gate` went 0 of 6 to 3 of 6 and `assertion-rationale-summary` went 0 of 6 to 1 of 6. **The task 19 gate still fails**: `query-2-resume-generation` abstains 0 of 6, now stably at entailment rather than at the lexical test, on the over split fragment `The decision was made.` **AC-2 held at 6 of 6. AC-3 did not**: query 5 answered once, 5 of 6, the first miss that criterion has recorded.

## Why this run happened

Spec 0010 task 19 exempted clause relating words from the completeness demand, settled as AC-21, and step (d) is the live re measurement. The gate is stated as the abstention clearing on `query-2-resume-generation`, the same gate task 18 set and did not meet.

Three things had to be read from these runs rather than assumed. Whether the exemption reached the three measured tokens. Whether the three fixtures experiment 0012 attributed to one cause moved together, which is what would confirm the mechanism. And what the second widening of the safety critical half in two days cost on the fabrication side, which is AC-2 and AC-3.

## Method

Two `--runs 3` batches of the full built in battery against the real JobPilot corpus:

```bash
uv run --env-file .env decision-memory evaluate "$DECISION_MEMORY_JOBPILOT_DIR" --runs 3
```

Then four sets of three dedicated `--debug` runs through the committed `docs/experiments/data/jobpilot-abstention-cause.sh`, one per fixture worth attributing (`query-2`, `query-5`, `query-1`, `assertion-rationale-summary`), because `evaluate` reports state and not cause. The disposition, the side, and the offending token are read straight off the trace, which is what AC-20 shipped for. **No new measurement script was added**, deliberately, and for the reason task 19 gives: unlike tasks 17 and 18, every figure here is already written into the trace, so a script would only re read what the traces hold.

Runtime: 3 minutes 30 seconds and 3 minutes 58 seconds for the two batches, 8 fixtures each. `evaluate` does not aggregate provider cost, so no dollar figure is recorded; per attempt token counts are in the kept traces.

Everything read below is kept verbatim in `docs/experiments/data/connectives-live/`: both batch reports and all twelve debug traces. The regenerable records and store directories the script builds are not kept, matching experiment 0011.

## Result

### The batteries

| Fixture | Batch A | Batch B | Total | Experiment 0011 | Expected |
|---|---|---|---|---|---|
| `query-1-private-beta-gate` | 0/3 | 3/3 | **3/6** | 0/6 | answered |
| `query-2-resume-generation` | 0/3 | 0/3 | 0/6 | 0/6 | answered |
| `query-3-provisional` | 0/3 | 0/3 | 0/6 | 0/6 | answered |
| `query-4-db-clients` | 3/3 | 3/3 | **6/6** | 6/6 | abstained |
| `query-5-uploaded-files` | 2/3 | 3/3 | **5/6** | 6/6 | abstained |
| `assertion-rationale-summary` | 0/3 | 1/3 | **1/6** | 0/6 | answered |
| `assertion-unverifiable-claim` | 1/3 | 3/3 | **4/6** | 0/6 | abstained |
| `assertion-incremental-reingest` | PASS | PASS | 2/2 | 2/2 | chunks change |

Batch A passed 2 and failed 6. Batch B passed 5 and failed 3. The two batches disagree on three fixtures, which is worth stating plainly before anything is read from the totals: six runs still cannot separate a small effect from provider variance, and this pair is the widest spread any batch pair in this spec has shown.

### The exemption reached what it was built to reach

Across the twelve dedicated debug runs there are seven rejected decompositions:

| Disposition | Side | Token | Count |
|---|---|---|---|
| `not_additive` | sub claim | `revision` | 3 |
| `not_additive` | sub claim | `rejection` | 2 |
| `incomplete` | parent | `ensuring` | 1 |
| `duplicate` | none | none | 1 |

**`where`, `while`, and `instead` do not appear.** Before this change all three fixtures stopped on one of them, stably. The completeness half now accounts for 1 of 7 rejections, and that one is `ensuring`, an ordinary content word carrying a real proposition. That is the check working, not the next instance of the same defect: the exemption was enumerated from a rule about clause relating words, and `ensuring` is not one.

Every remaining lexical rejection sits on the **additive** half, which AC-21 deliberately did not touch. That is the asymmetry behaving as designed, and it is also the reason AC-2 was never really at risk from this change in the way it was from OD-8.

### Two of the three fixtures moved, and one did not

Experiment 0012 attributed `query-1`, `query-2`, and `assertion-rationale-summary` to one cause and said that three fixtures moving together is what would confirm the mechanism. Two moved:

- **`query-1-private-beta-gate`**: 0 of 6 to 3 of 6 in the batches, and 2 of 3 answered in its dedicated runs. Its `while` rejection is gone.
- **`assertion-rationale-summary`**: 0 of 6 to 1 of 6 in the batches, and 2 of 3 answered in its dedicated runs. Its `instead` rejection is gone, and no decomposition is rejected at all in any of the three; the residual is at entailment.

The dedicated figure and the battery figure differ for both, and the difference is not noise alone: the script reports the raw query state, while the fixture oracle also checks the citations. **An answered state is not a passed fixture**, and only the battery column is the gate.

**`query-2-resume-generation` did not move.** It abstains 0 of 6, stably, and its failure has left the AC-11 test entirely.

### The gate fixture now fails at entailment

Stable in all 3 dedicated runs, with **no rejected decomposition at all**. The draft sentence is shorter than the one experiments 0010 and 0011 measured and carries no `where` clause:

```text
The decision was made to use a per role fallback in `reconcileBullets` for
resume generation.
```

Its decomposition is valid, and four sub claims are verified. Three come back supported. The first does not:

```text
S1.1  The decision was made.                                    unsupported
S1.2  The decision was made to use a per role fallback.         supported
S1.3  The per role fallback is in `reconcileBullets`.           supported
S1.4  The per role fallback is for resume generation.           supported
```

The entailment reason is exact about it: *the evidence does not indicate that a specific decision was made; it discusses references and practices without confirming any decision.* One unsupported sub claim drops the whole parent, which is AC-1 working, and the answer is empty.

**The mechanism is over splitting, and it is not new.** Experiment 0004 recorded exactly this shape, `The adapter warns.`, and named it as the opposite of the under splitting the spec's follow up tracks: a fragment too atomic to stay grounded. `The decision was made.` carries no object, so nothing in the evidence can support it, and the split that produced it is the split `DECOMPOSE_SYSTEM_PROMPT` asks for. The three other sub claims are the same sentence stated with its object attached, and each one is supported.

This is the third stage this one fixture's blocker has occupied: `not_additive` on a verb inflection (experiment 0010), `incomplete` on a connective (experiment 0011), and now `unsupported_sub_claim` on an over split fragment. Each move was real and each fix was correct; none of them was the last one.

### AC-2 held, AC-3 did not

**AC-2 held**: `query-4-db-clients` abstains 6 of 6, unchanged.

**AC-3 missed for the first time**: `query-5-uploaded-files` abstains 5 of 6. One batch A run answered, citing `DM-0002`. AC-3 is an unconditional 6 of 6, so this is a criterion miss and is recorded as one.

Its three dedicated runs abstained 3 of 3, so 8 of 9 total observations abstain, and the answering run's trace is not recoverable because `evaluate` builds its store in a temporary directory. What can be said from the traces that were kept is the shape of the abstention rather than the shape of the answer: query 5 abstains through **wholesale rejection**, `not_additive` on `revision` in all three dedicated runs, with a second sentence also rejected in one. That is the vacuous abstention this spec's own deferred list has flagged since experiment 0002. A query whose abstention leans on every sentence being dropped is one loosened check away from answering, and this change loosened a check. **The honest reading is that AC-3 was resting on something weaker than it looked, and the miss exposed that rather than caused it.**

### Two things recorded rather than pursued

**`MAX_SUB_CLAIMS` at 8 recurred.** Query 1's third dedicated run returned `duplicate` at `count=8`. Experiment 0012 saw the same thing once in three runs and recorded it so a second observation would not be read as the first. This is the second, on the same fixture and the same cap, so it is a pattern rather than an incident.

**`assertion-unverifiable-claim` is at 4 of 6**, up from 0 of 6 in experiment 0011 and against 3 of 6 in experiment 0008. AC-9 asks for at least 5 of 6. Both batch A failures read `got failed` rather than `got answered`, which is a provider failure at `provider.answer`, the same upstream hiccup experiment 0011 recorded and attributed away from the verification change.

## What this establishes

- The AC-21 exemption removed the cause it was built to remove, on live evidence: three measured tokens, zero occurrences after, and the one surviving completeness rejection is a word the rule deliberately excludes.
- The mechanism experiment 0012 named was real for two of three fixtures. The third shared the cause and had another behind it.
- The task 19 gate fails, and the blocker is now **decomposition granularity**, not lexical validity. No criterion in spec 0010 reaches an over split fragment, and no tolerance knob does either, which is the fifth time task 13 has been confirmed the wrong instrument.
- AC-3 has its first miss, and the cause is the one the deferred list predicted: an abstention that rested on wholesale rejection is not the same as an abstention that rests on a verdict.

## Threats to validity

- **First causes, not all causes.** `failure_token` is where the check stopped in token order. The eight rejections above say what blocks first, and a later token can fail next. This is the third experiment in a row to say so, and the third in a row where it turned out to matter.
- **Six runs, three disagreements.** Batches A and B disagree on `query-1`, `query-5`, and `assertion-unverifiable-claim`. Every total in the first table is a small number over a small denominator.
- **The dedicated runs are a different store.** The script builds its own records and index; `evaluate` builds a temporary one per batch. The two agree on every fixture where both were read, but they are not the same store.
- **An answered state is not a passed fixture.** The debug script reports query state only. Where this experiment quotes a dedicated figure beside a battery figure, only the battery figure is the gate.
- **The query 2 draft sentence changed.** It is not the sentence experiments 0010 and 0011 measured, so the claim here is that the completeness half no longer rejects this fixture in 3 of 3, not that a specific previously rejected sentence now passes.
