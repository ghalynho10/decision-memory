# Experiment 0011: the base set matcher works, and the next token is `where`

**Date**: 2026-08-14
**Status**: Complete
**Follows**: [Experiment 0010](0010-falls-against-falling.md)
**Result**: The AC-11 amendment did what it was built to do. The `falls` against `falling` drop is **gone**, and query 2's failure moved one token further along and onto the other half of the test: it is now `incomplete`, `failure_side=parent`, `failure_token=where`, stable 3 of 3. **The task 18 gate still fails**: `query-2-resume-generation` abstains 0 of 6 across two live batches. The new cause is that **`where` is not in the AC-11 closed function word set**, so a subordinating relative adverb is judged as content, and a decomposition that splits a `where` clause into standalone sub claims necessarily drops it. No tolerance and no matcher rule reaches that; it is a membership question about a closed set, and this spec says in the code itself that adding a word to that set is a spec edit rather than a build time judgement. **AC-2 held**: query 4 and query 5 pass 3 of 3 in both batches, which is the criterion the widening put at risk.

## Why this run happened

Spec 0010 task 18 replaced the directional stem comparison with the base set intersection settled as OD-8, and step (d) is the live re measurement. The gate is stated as the abstention clearing on `query-2-resume-generation`, not the absence of drops, because `incomplete` is the safety critical direction and a genuine omission must still fail it.

Two things had to be read from these runs rather than assumed. Whether the amendment reached the drop it was built for, and whether widening a guard that both halves share cost anything on the fabrication side.

## Method

Two `--runs 3` batches of the full built in battery against the real JobPilot corpus:

```bash
uv run --env-file .env decision-memory evaluate "$DECISION_MEMORY_JOBPILOT_DIR" --runs 3
```

Then three dedicated `--debug` runs of query 2 through the committed `docs/experiments/data/jobpilot-abstention-cause.sh`, because `evaluate` reports state and not cause, and the trace is where the disposition and the token live. Three more of the unverifiable claim assertion, for the reason in *A failure that is not this change* below.

The offending token is read straight off the trace. That is the whole point of task 18 step (a): experiments 0009 and 0010 each cost a dedicated script and a live provider call to learn one token, and this one cost neither.

Runtime: 3 minutes 20 seconds and 3 minutes 8 seconds for the two batches, 8 fixtures each. `evaluate` does not aggregate provider cost, so no dollar figure is recorded here; the per attempt token counts are in the kept traces.

Everything read below is kept verbatim in `docs/experiments/data/base-set-live/`: both batch reports, the three query 2 debug traces, the three unverifiable claim traces, and the pair comparison output from task 18 step (b). Experiments 0005 and 0006 kept no traces and a later question about them could not be answered.

## Result

Both batches, identical:

| Fixture | Batch A | Batch B | Total | Expected |
|---|---|---|---|---|
| `query-1-private-beta-gate` | 0/3 | 0/3 | 0/6 | answered |
| `query-2-resume-generation` | 0/3 | 0/3 | 0/6 | answered |
| `query-3-provisional` | 0/3 | 0/3 | 0/6 | answered |
| `query-4-db-clients` | 3/3 | 3/3 | **6/6** | abstained |
| `query-5-uploaded-files` | 3/3 | 3/3 | **6/6** | abstained |
| `assertion-rationale-summary` | 0/3 | 0/3 | 0/6 | answered |
| `assertion-unverifiable-claim` | 0/3 | 0/3 | 0/6 | abstained |
| `assertion-incremental-reingest` | PASS | PASS | 2/2 | chunks change |

Three passed, five failed, in both batches.

### The amendment worked, and the failure moved

The same draft sentence has now been measured three times. Its rejection has moved twice:

| Measured | Disposition | Side | Token |
|---|---|---|---|
| Experiment 0010 | `not_additive` | sub claim | `falls` |
| This run | `incomplete` | parent | `where` |

Experiment 0010's token is no longer reachable: `falls` and `falling` now meet at `fall`, which is exactly what the base set was built to do. The check stopped being at war with its own job on that pair, and then stopped one token later for an unrelated reason.

The parent sentence, unchanged from experiment 0010:

```text
The decision was made to use a fallback behavior for resume generation, where a
role whose bullets are affected by a dropped number never ends up empty, and only
the offending bullet is dropped first, with the role falling back to the user's
own written text if necessary.
```

The decomposition returned 4 sub claims, and the completeness half stopped on the parent's `where`. Stable in all 3 dedicated runs and in both batches.

### Why `where` fails

`where` is not a member of the AC-11 closed function word set. `when`, `then`, `there`, `which`, and `that` are; `where` is not. So it is a content token, and the completeness half requires every distinct parent content token to appear in some sub claim.

A decomposition cannot carry it. `where` is a subordinator: it joins a relative clause to its head, and turning that clause into a standalone atomic sub claim is precisely what removes the need for it. `DECOMPOSE_SYSTEM_PROMPT` asks for exactly that transformation. So this is the same shape as the defect the amendment just fixed, one layer up: the check punishes the behaviour it asks for, this time through set membership rather than through morphology.

**This is not a build time fix.** `FUNCTION_WORDS` carries its own instruction in the code:

> It is exhaustive by decision, not a grammatical category the builder extends: a word outside it is a content token that must find a parent match, so an unlisted word makes the test drop the parent sentence, which loses content but never admits a fabrication. Adding a word is a spec edit, not a build time judgment.

The failure direction is the safe one, which is why the set was closed this way in the first place. It loses content, it never admits a fabrication. So the gate stays failed rather than being cleared by an unratified edit.

### AC-2 held, which is the number that mattered

The base set widens both halves of the validity test, and the additive half is the guard standing behind AC-2, the fabrication gate and the only criterion in this chain green on live evidence. Spec 0010's own Consequences names AC-2 as the criterion to watch if anything regresses.

Query 4 and query 5 abstain 3 of 3 in both batches, 6 of 6 each. Nothing regressed. The pair comparison predicted this (0 invented false matches over 3,374 content tokens), and this is the live confirmation of that prediction rather than a restatement of it.

### A failure that is not this change

`assertion-unverifiable-claim` reads `expected abstained, got failed (citations: none)` in both batches, against 3 of 6 in [experiment 0008](0008-first-live-jobpilot-run-since-the-build.md). It would be easy to read that as a regression from this change, and it is not.

The three dedicated runs came back 2 abstained and 1 failed, so it is stochastic rather than newly broken. The failing run fails at `provider.answer` with a `GenerationError` after two attempts, and its trace shows an empty `Draft`, an empty `Verification`, and an empty `Sub claims` section. Decomposition never runs. The matcher cannot be reached by a query that never produces a draft sentence, so this failure sits entirely upstream of anything task 18 touched. Experiment 0008 recorded the identical row and called it a transient of the class AC-9 already describes for query 1; two batches at 0 of 6 make it more than a single observation, and it is carried below rather than explained away.

### The AC-20 instrument, checked in passing

Two dispositions were observed live and both carried what AC-20 says they should. The `incomplete` rows carry `failure_side=parent` with a token. A `duplicate` row observed on the unverifiable claim assertion carries `failure_side=` and `failure_token=` empty, which is the case that stops before any token is examined.

## What this changes

- **OD-8 is confirmed on live evidence.** The base set fixes the drop it targeted, and it costs nothing on the fabrication side. Both halves of that claim are now measured rather than argued.
- **The task 18 gate does not clear**, and the blocker is a closed set's membership rather than a rule or a tolerance.
- **Task 13 is confirmed the wrong instrument for the fourth time.** A tolerance knob does not reach a subordinating conjunction any more than it reached a verb inflection.

## Threats to validity

- **One sentence, one query.** Everything about `where` comes from one draft sentence on one fixture. The token is stable across 6 batch runs and 3 dedicated runs, but stability is not generality, and no count exists for how often a subordinator drops a sentence across the corpus.
- **First causes, not all causes.** `failure_token` is the token the check stopped at in token order. Removing `where` from the picture would not necessarily let this sentence through; a later token could fail next, exactly as `falls` gave way to `where`. This run says what is blocking now, not what is left.
- **The other four failing fixtures were not traced.** Query 1, query 3, and the rationale summary assertion abstain 0 of 6 and their causes were not read. They may or may not share this one.
- **Corpus drift.** The pair comparison figures in spec 0010's rationale were measured over 3,690 tokens; the committed instrument now reads 3,374 over the same rule, and the docs tree has changed since. The direction of every figure is unchanged; see the note in that script.

## Follow-up

- [ ] **`where` and the closed function word set (a decision, owed to `/architect`).** The measured fix is to admit subordinating relative adverbs, and the set is closed by decision, so this is a spec edit. It is also not obviously one word: `where` is the token measured, but `whose` appears in the same sentence and the same argument reaches it. The decision needs the rule, not the token, and it needs to say what stops the set growing by one word per failing sentence forever.
- [ ] **`assertion-unverifiable-claim` at 0 of 6.** A `provider.answer` `GenerationError` on a fixture that passed 3 of 6 in experiment 0008. Upstream of verification, so it belongs to generation, and two batches at zero is past the point where a transient explains it on its own.
