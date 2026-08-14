# Experiment 0008: the first live JobPilot run since the spec 0010 build, and the fixture set inverts

**Date**: 2026-08-14
**Status**: Complete
**Follows**: [Experiment 0007](0007-field-labels-and-the-additive-split.md)
**Result**: **AC-2 is met, 6 of 6.** Query 4, the fabrication gate feature 16 was created to close and which feature 11 measured as a coin flip, now abstains in every run of two separate batches. AC-3 is at **5 of 6**, one miss with the known `DM-0002` shape. The run also exposes something no fixture measurement could: **the fixture set has inverted.** At feature 11 the passing fixtures were queries 1, 2 and 3 plus the assertions, and only queries 4 and 5 failed. Now queries 4 and 5 essentially pass and queries 1, 2, 3 and the rationale summary assertion fail, all with the same disposition: `expected answered, got abstained`. The spec 0010 work traded fabrication for over abstention, and this is the first measurement of that trade on the corpus it matters for.

## Why this run happened

Task 14 was the last unchecked box on feature 16 and had never run. Every experiment from 0004 to 0007 measured the frozen self corpus fixture, and the last live JobPilot data was feature 11's verification on 2026-08-12, which predates every spec 0010 change: whole sentence output, sub claim decomposition, the marker strip, the coverage tightening, and the AC-18 field labels. So the stated goal of feature 16, AC-2 and AC-3, had not been measured against the build meant to achieve it.

The run was prompted by a question about whether to stop the project, which is worth recording: the cheapest available information was whether the goal was already met, and nobody had looked.

## Method

Two sequential batches of the built in JobPilot battery, each with a fresh records directory and a fresh store, so they are genuinely separate batches in the AC-2 and AC-3 sense.

```bash
uv run --env-file .env decision-memory evaluate "$DECISION_MEMORY_JOBPILOT_DIR" --runs 3
```

Corpus: the live JobPilot tree, 20 specs. Batch 1 ran 03:28:47 to 03:32:01, batch 2 ran 03:32:01 to 03:36:48. Both exited 1. No code changed between them.

## Result

| Fixture | Batch 1 | Batch 2 | Total | Expected |
|---|---|---|---|---|
| `query-4-db-clients` | 3/3 | 3/3 | **6/6** | abstained |
| `query-5-uploaded-files` | 2/3 | 3/3 | 5/6 | abstained |
| `assertion-incremental-reingest` | PASS | PASS | 2/2 | chunks change |
| `query-1-private-beta-gate` | 3/3 | 0/3 | 3/6 | answered |
| `assertion-unverifiable-claim` | 0/3 | 3/3 | 3/6 | abstained |
| `query-2-resume-generation` | 0/3 | 0/3 | 0/6 | answered |
| `query-3-provisional` | 0/3 | 0/3 | 0/6 | answered |
| `assertion-rationale-summary` | 0/3 | 0/3 | 0/6 | answered |

Batch 1: 3 passed, 5 failed. Batch 2: 4 passed, 4 failed.

## Finding 1: AC-2 is met, 6 of 6

`query-4-db-clients` abstained in all six runs across both batches. This is the criterion feature 16 exists for. Feature 11 recorded it as "a measured coin flip" and spec 0008 carried it forward as a known blocker through feature 10 and feature 11. It is now stable across two batches with no code change between them.

This is the first acceptance criterion in the feature 16 chain to be met on live evidence rather than deferred.

## Finding 2: AC-3 is at 5 of 6, and the miss has the recorded shape

`query-5-uploaded-files` answered once in batch 1, citing `DM-0002`. That is the exact failure spec 0008 Follow-up item 1 and the feature 11 status note both describe. The AC-3 bar is 6 of 6 unconditionally, so the criterion is not met, but the single miss is the known case rather than a new one.

Batch 2 passed it 3 of 3, so the behaviour is not stable in either direction on six runs.

## Finding 3: the fixture set has inverted

Every failing fixture below the abstention gates fails the same way: `expected answered, got abstained`. Queries 1, 2, 3 and the rationale summary assertion all decline questions they are supposed to answer.

At feature 11 the position was the mirror image. Its status note records the two failing fixtures as "feature 10 carry-ins" and names them: query 5 stable, query 4 a coin flip. Everything else passed.

So the spec 0010 build closed the fabrication failures and opened an answering failure. That trade was predicted by the drop rate: experiments 0003, 0004 and 0007 measured 19 of 20, 19 of 21 and 18 of 21 draft sentences dropped on the self corpus fixture. What was not known is that it reaches the JobPilot corpus this hard, because nothing had measured it there.

**This is a real regression and it is on the safe side.** The tool declines rather than inventing, which is what feature 16 was built to achieve. It is still a regression, and it is larger than the gate it was traded for: two fixtures moved from failing to passing, and four moved from passing to failing.

## Finding 4: `query-2-resume-generation` abstains, which bears on spec 0011

Spec 0011's AC-9 requires `query-2-resume-generation` to answer with a co located `decision.chosen` citation on the covering sentence. This run measures that fixture at 0 of 6, abstaining. A query that does not answer cannot carry a covering sentence, so AC-9 cannot pass in this state.

Spec 0011 already handles the attribution correctly: AC-9 says a drop at entailment or coverage is a spec 0010 finding rather than a regression in that spec, and AC-8 is the retrieval half that passes on its own stack. So this is not a defect in spec 0011. It does mean feature 19 would ship with AC-9 failing for a reason outside itself, and spec 0011 was written before this measurement existed.

## Limits on what this run can tell you

- **`evaluate` reports state, not cause.** Every `expected answered, got abstained` row here is unattributed. Whether those queries abstain from `no_emitted_sentences` (sentences dropped in verification) or `uncovered_facet` (coverage refused what survived) is exactly the distinction AC-15 introduced, and it needs one `query --debug` run to read. Nothing in this experiment separates them, and the two point at different fixes.
- **Batch 1's `assertion-unverifiable-claim` failed as `failed`, not as a wrong answer.** The row reads `expected abstained, got failed (citations: none)`, which is a pipeline failure state rather than the fixture answering when it should abstain. Batch 2 passed it 3 of 3. This looks like a transient provider failure of the kind AC-9 already describes for query 1, but it is one observation and is recorded as such rather than dismissed.
- **`query-1-private-beta-gate` went 3 of 3 then 0 of 3**, and batch 2's failures were abstentions rather than the provider failed state AC-9 calls a live hiccup. Three runs cannot separate a real regression from fixture level variance, which is the reason AC-9 made this a smoke gate rather than a rate comparison.
- **Six runs per fixture, two batches, one corpus.** Experiment 0006 already records that six runs cannot separate a small effect from noise. Finding 1's 6 of 6 and finding 3's four fixtures at 0 of 6 or 3 of 6 are not small effects. Finding 2's single miss is one event.
- **Cost was not captured.** The `evaluate` command does not report the provider cost that experiment 0007 recorded for the fixture gate, so only wall clock is available: 3 minutes 14 seconds and 4 minutes 47 seconds, 8 minutes 1 second total for 48 query runs plus two adapt and ingest cycles.

## What this changes

- **Feature 16's stated goal is half met on live evidence.** AC-2 passes 6 of 6 and AC-3 is at 5 of 6. Neither had been measured against the build meant to achieve them. Feature 16's scope row does not yet carry this and `/sync` owns reconciling it.
- **The over abstention outranks the retrieval work for the JobPilot corpus.** Feature 19 addresses a decision question on the self corpus fixture. Four JobPilot fixtures now decline questions they should answer, and that is the larger problem on the corpus this tool is aimed at.
- **The next cheapest decision is a single `query --debug` run on query 2.** It attributes the abstention to drops or to coverage, and that determines whether feature 19 helps the real problem or only the self corpus one. Until that is known, choosing between them is a guess.
- **Task 13 is further constrained than experiment 0007 recorded.** That experiment measured the additive split at 7 of 7 `content_token` on a pipeline where no `decision.chosen` chunk reached generation. This run shows the drop behaviour reaching the JobPilot corpus too, so whatever fixes the drops has to work on both, and the note in `docs/session-notes.md` about re measuring the split after retrieval changes applies to this corpus as well.
