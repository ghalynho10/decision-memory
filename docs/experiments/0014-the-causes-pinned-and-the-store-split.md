# Experiment 0014: the causes are pinned, and the batches split

**Date**: 2026-08-14
**Status**: Complete
**Follows**: [Experiment 0013](0013-the-connectives-cleared-and-entailment-is-next.md)
**Result**: The first measurement at the AC-24 denominator, twelve runs over four batches. **AC-2 fell to 9 of 12 and AC-3 to 3 of 12**, both on the cause AC-23 pinned, which is the finding the spec said it would be rather than a regression. The failures are not spread evenly: **batch D alone accounts for every AC-2 miss and answers query 5 in 3 of 3**, a clean split on the store boundary. The deviation writer worked on its first live use: **60 of 84 query runs deviated and wrote a trace, the other 24 wrote nothing**, and that arithmetic matches the four reports exactly. **Query 4's abstention rests on a verdict in 9 of 12 runs**, which no experiment had ever established, and on wholesale rejection in the other 3. Task 21's target is confirmed at this denominator: **all 8 of query 2's abstaining runs die on the fragment `The decision was made.`**, with its object bearing siblings supported every time.

## Why this run happened

Spec 0010 task 20 has two halves and both landed before these runs. The instrument: `evaluate --traces DIR` keeps the full traced result of any run whose outcome differs from its fixture's expectation, through one optional `record_deviation` method on `EvaluationPort`. The oracle: `expected_abstention` moved onto the built in JobPilot battery, and query 4 and query 5 both pin `uncovered_facet`.

Three things had to be read from these runs rather than assumed. Whether the writer keeps what a surprising run needs, since experiment 0013's single answering run of query 5 was unattributable forever. What query 4's abstention actually rests on, which four experiments treated as green without ever looking. And what twelve runs say that six could not, since AC-24 chose four batches over more runs per batch specifically to keep the store effect and the provider effect apart.

## Method

Four `--runs 3` batches of the full built in battery against the real JobPilot corpus, four separate invocations:

```bash
uv run --env-file .env decision-memory evaluate "$DECISION_MEMORY_JOBPILOT_DIR" --runs 3 \
  --traces docs/experiments/data/cause-pinned-live/batch-<X>-traces
```

One invocation adapts once and ingests once, then runs every fixture three times, so the store is held constant inside a batch and varied between batches. That is the whole reason the count is four batches rather than twelve runs of one.

Runtime: 191, 214, 170, and 179 seconds, 12 minutes 34 seconds for 88 fixture runs (84 query runs plus 4 re ingest assertions). `evaluate` does not aggregate provider cost, so no dollar figure is recorded, matching experiment 0013.

Everything read below is kept verbatim in `docs/experiments/data/cause-pinned-live/`: the four batch reports, the timings, and the four per invocation trace directories as `batch-<X>-traces.tar.gz` (`tar xzf` to read them). They are archived rather than loose because a full trace carries a retrieval row per corpus chunk, so the 60 files are 22 MB raw and 4 MB packed; nothing is dropped from them. No new measurement script was added, for the reason task 19 gave and task 20 repeats: every figure here is written into a trace the run already keeps, so a script would only re read what the traces hold. The regenerable records and store directories are not kept.

## Result

### The batteries, in the AC-24 aggregate shape

| Fixture | A | B | C | D | Total | Within batch spread | Between batch spread | Expected |
|---|---|---|---|---|---|---|---|---|
| `query-1-private-beta-gate` | 0/3 | 2/3 | 0/3 | 1/3 | **3/12** | 2 | 3 | answered |
| `query-2-resume-generation` | 0/3 | 0/3 | 0/3 | 0/3 | **0/12** | 0 | 1 | answered |
| `query-3-provisional` | 0/3 | 0/3 | 0/3 | 0/3 | **0/12** | 0 | 1 | answered |
| `query-4-db-clients` | 3/3 | 3/3 | 3/3 | 0/3 | **9/12** | 0 | 2 | abstained, `uncovered_facet` |
| `query-5-uploaded-files` | 1/3 | 2/3 | 0/3 | 0/3 | **3/12** | 2 | 3 | abstained, `uncovered_facet` |
| `assertion-rationale-summary` | 1/3 | 1/3 | 2/3 | 0/3 | **4/12** | 3 | 3 | answered |
| `assertion-unverifiable-claim` | 2/3 | 0/3 | 2/3 | 1/3 | **5/12** | 3 | 3 | abstained |
| `assertion-incremental-reingest` | PASS | PASS | PASS | PASS | **4/4** | 0 | 1 | chunks change |

Within batch spread counts the batches whose result is neither 0 of 3 nor 3 of 3, which is the provider side. Between batch spread counts the distinct per batch results, which is the store side.

**Two fixtures have spreads pointing different ways, and they point opposite ways.** `query-4-db-clients` has a within batch spread of 0 and a between batch spread of 2: every batch is unanimous inside itself and one batch disagrees with the other three, which is as clean a store effect as this harness can produce. `assertion-rationale-summary` has a within batch spread of 3 and a between batch spread of 3: every batch is mixed inside itself, which is provider variance with no store signal separable from it. Reading either fixture's total as one number would hide which of the two it is, which is exactly what AC-24 refused to let a larger run count do.

### The deviation writer, checked against the reports

84 query runs happened (7 query fixtures, 3 runs, 4 batches). The reports' passing runs sum to 24: batch A 7, batch B 8, batch C 7, batch D 2. The trace directories hold 60 files: 14, 13, 14, and 19. **24 plus 60 is 84, so every deviating run wrote exactly one file and no passing run wrote anything.** That is the AC-23 contract holding on its first live use, checked against a number the instrument does not produce.

Batch A's `query-4-db-clients` wrote nothing at all, and batch D's wrote three files. A clean fixture costs nothing, and the failure this exists for is the one that is kept.

### AC-2: query 4 abstains 12 of 12, and it rests on a verdict in 9 of them

This is the first time the question has been asked. AC-2 has been read as green since experiment 0008, and nothing in it ever distinguished an abstention resting on a verdict from one resting on every sentence being dropped.

| Runs | State | Cause | What is behind it |
|---|---|---|---|
| A1 to A3, B1 to B3, C1 to C3 | abstained | `uncovered_facet` | sentences reached coverage, the decision facet came back uncovered |
| D1, D2, D3 | abstained | `no_emitted_sentences` | one draft sentence, dropped `unsupported_sub_claim`, no sentence reached coverage |

**By state the fixture is 12 of 12, unchanged.** By cause it is **9 of 12**, so AC-2 fails its rewritten bar. Both halves of that are worth stating plainly. The abstention is a real verdict three quarters of the time, which is better than the deferred list's worst case and better than what the same pin found underneath AC-3. And it is vacuous in the other quarter, which means the criterion this chain has treated as its one green result was partly resting on the collapse it exists to rule out.

The three vacuous runs are all in batch D, and the trace names the mechanism precisely. The draft sentence is `The decision was to make one request, then a client side refetch.`, and its first sub claim, `The decision was to make one request.`, comes back `unsupported` in all three while `The decision was to make a client side refetch.` comes back supported. One unsupported sub claim drops the whole parent, which is AC-1 working as designed, and with the only sentence gone coverage has nothing to judge.

### AC-3: query 5 is 3 of 12, and it answers 4 times

| Runs | State | Cause | What is behind it |
|---|---|---|---|
| A1, B2, B3 | abstained | `uncovered_facet` | the pinned cause, 3 of 12 |
| A2, B1, C1, C2, C3 | abstained | `no_emitted_sentences` | every draft rejected `not_additive` on a sub claim token (`revision`, `valid`, `led` four times) |
| A3, D1, D2, D3 | answered | none | cites `DM-0002`, all sub claims supported |

AC-3's bar is 12 of 12 on state and cause, so **3 of 12** is a clear miss, and the state alone is **8 of 12**. Experiment 0013 recorded the first state miss at 5 of 6 and read it as a criterion resting on something weaker than it looked. Twelve runs say that reading was right and understated: five of the eight abstentions are the wholesale rejection the deferred list has flagged since experiment 0002, and the tokens behind them are ordinary content words (`led` in four runs).

The four answering runs are one behaviour, not four. Every one cites `DM-0002` `body[7]`, and the emitted sentence is fluent and plausible:

```text
The original approach was changed because the critique found a gap in the safety
reasoning and suggested a more robust alternative for handling upload keys, which
was adopted.
```

Coverage accepts it as a direct answer, and every sub claim comes back supported. Nothing here is a verification bug in the narrow sense: the pipeline is answering a question about uploaded files from a record that really does discuss upload keys. It is the fabrication direction this whole spec exists to close, and it is now recoverable rather than a rumour, because the run that produced it wrote its trace.

**Three of the four answering runs are batch D.** The fourth is A3.

### Batch D is a different index, and that is the loudest signal here

Batch D is the only batch where query 4 lost its cause, the only batch where query 5 answered three times out of three, and the only batch where `assertion-rationale-summary` scored zero. Its report is 1 passed and 7 failed, against 2 passed and 6 failed in each of A, B, and C.

The deferred item **Store level nondeterminism in `evaluate`** predicted exactly this shape from experiment 0013's single clean split, and this run reproduces it on a different fixture with a wider margin. The first step that item names is unchanged and is now better motivated: compare chunk identity and ordering across two builds of the same corpus before looking at anything downstream. Nothing in this experiment can do that, because the stores were temporary and are gone; the traces record what the pipeline did with a store, never how the store was built.

### Task 21's target is confirmed at twelve runs

`query-2-resume-generation` is 0 of 12 as a fixture, but the runs behind that number split two ways.

**Eight runs abstained, and every single one died on the same fragment.** A1, A2, A3, C1, C2, C3, D2, and D3 all drop their only sentence as `unsupported_sub_claim`, and in all 8 the unsupported claim is `The decision was made.` while every object bearing sibling is supported:

```text
S1.1  The decision was made.                                    unsupported
S1.2  The decision was made to use a per role fallback.         supported
S1.3  The per role fallback is in `reconcileBullets`.           supported
S1.4  The per role fallback is for resume generation.           supported
```

Experiment 0013 measured this 3 of 3 on one batch. It is now 8 of 8 abstaining runs across three separate stores, which is the evidence AC-22 was written on and it holds at the decision grade denominator. The fragment is a strict content subset of S1.2 with matching polarity and modality and in order, so it is exactly what the AC-22 prune skips.

**Four runs answered, and failed the fixture for an unrelated reason.** B1, B2, B3, and D1 each answer citing `DM-0019` and are marked FAIL for `missing required records DM-0004`. That is the deferred **coverage direction, query 2 citation completeness** item, not a verification failure, and it means the task 21 gate could clear the abstention and still leave this fixture red. **The gate should be read as the abstention clearing, which is how task 21 states it, and not as this fixture passing.**

One run shows the prune's own boundary. B2's S2 returned 8 sub claims including both `The decision was made.` (unsupported) and `The final PDF contains bullet or summary sentences.` (unsupported). The second is a content subset of a sibling that carries `no`, a negator, so the AC-22 polarity condition refuses that prune, which is the condition doing its job on a real sentence rather than a constructed one.

### The rest of the battery

- **`assertion-unverifiable-claim` failed 7 of 12 runs at `provider.answer`**, not at verification. Every kept trace for it is a `failed` state with that code. It is 5 of 12 against an AC-9 bar of 5 of 6, and the shortfall is upstream of anything this task touched, the same attribution experiments 0011 and 0013 made.
- **`assertion-rationale-summary` is 4 of 12**, and all 8 kept traces abstain from `uncovered_facet`. Sentences survive and coverage refuses them. No decomposition is rejected in any of the 8, so the AC-11 work is no longer what holds this fixture back.
- **`query-1-private-beta-gate` is 3 of 12**, with 6 kept abstentions from `uncovered_facet` and 3 from `no_emitted_sentences`.
- **`query-3-provisional` is 0 of 12**, with 9 kept abstentions from `uncovered_facet`, 1 from `no_emitted_sentences`, and 2 answering runs that missed a proposed record. Its instability is the deferred facet extraction item, untouched here.
- **`assertion-incremental-reingest` passes 4 of 4 batches**, unchanged.

### Lexical rejections, and the cap again

21 decompositions were rejected across the 60 kept traces. 18 are `not_additive` with `failure_side=sub_claim` and `additive_failure=content_token`; the tokens are `led` (4), `cannot` (3), `meant` (2), `means` (2), and one each of `every`, `cost`, `revision`, `valid`, `whose`, `rejection`, and `purpose`. **Not one is `incomplete`**, so the AC-21 exemption is still holding on the completeness half, and every remaining lexical rejection sits on the additive half exactly as that criterion's asymmetry intended.

`MAX_SUB_CLAIMS` at 8 recurred three more times, all `duplicate` at `returned_count=8`, all on `query-1-private-beta-gate` (A3, B3, D2). With experiments 0012 and 0013 that is four observations on one fixture and one cap. The Follow-up item already calls it a pattern needing a decision; this is more of the same evidence, not a new finding.

## What this establishes

- The AC-23 instrument works and costs nothing on a clean run. 60 deviating runs wrote a trace, 24 passing runs wrote none, and the count reconciles exactly with the four reports.
- **AC-2 is 9 of 12 and AC-3 is 3 of 12 on the pinned cause.** Both were predicted to go red on cause, and both did. Neither is a regression introduced by this round: no pipeline behaviour changed in task 20.
- Query 4's abstention rests on a verdict in 9 of 12 runs. That is the first evidence either way, and it is a better answer than the deferred list assumed.
- Query 5 answers 4 of 12 with a fluent, well cited, wrong answer, and the trace for every one of those runs is kept.
- **The store effect is real, large, and separable.** Batch D differs from the other three on three fixtures at once, and the two spread columns tell a store effect from a provider effect without any new runs.
- Task 21's target is confirmed at 8 of 8 abstaining runs on `query-2-resume-generation`, across three stores.

## Threats to validity

- **Twelve runs is the denominator a criterion may move on, not a large sample.** Every fraction above still carries a small denominator, and the fixtures with a within batch spread of 3 are the ones where a single extra run could move the total.
- **Only deviating runs have traces.** The nine passing query 4 runs are recorded as `uncovered_facet` because the oracle checked that and passed them, not because a kept trace was read. That is sound, since the oracle reads the same cause function, but it is not the same evidence as a file on disk.
- **Four stores, not one variable.** Between batch spread is attributed to the store because that is what a new invocation rebuilds, but an invocation also crosses a provider session boundary. Experiment 0006 recorded session drift as its own threat, and nothing here separates the two.
- **`assertion-unverifiable-claim` is measured through a provider failure.** Its 5 of 12 mixes a verification result with 7 runs that never reached verification.
- **First causes, not all causes.** `failure_token` records where a check stopped in token order, for the fourth experiment running.
