# Experiment 0009: why query 2 abstains, and the answer it threw away

**Date**: 2026-08-14
**Status**: Complete
**Follows**: [Experiment 0008](0008-first-live-jobpilot-run-since-the-build.md)
**Result**: The cause is **`no_emitted_sentences`**, deterministically, 3 of 3. Coverage never judged anything. Generation produced **one** correct, decision framed, cited sentence answering the question; its decomposition came back `not_additive` with `additive_failure=content_token`, the AC-11 retry failed the same way, and the sentence was dropped. The answer existed and the verifier discarded it. Two further facts: **no `decision.chosen` chunk reaches the accepted eight** for this query either, the same defect experiment 0007 found on the self corpus; and query 2 extracts **one facet**, so it produces one sentence and a single decomposition failure is total abstention.

## Why this run happened

Experiment 0008 measured four JobPilot fixtures failing as `expected answered, got abstained` and could not attribute any of them, because `evaluate` reports state and not cause. The distinction decides what to build next. `no_emitted_sentences` means sentences died in verification and feature 19 cannot reach the problem; `uncovered_facet` means sentences survived and coverage refused them, which better evidence might fix.

`query-2-resume-generation` was chosen because spec 0011's AC-9 targets it by name, so its behaviour is load bearing for feature 19 as well as for the abstention question.

## Method

`docs/experiments/data/jobpilot-abstention-cause.sh`, committed with this experiment. `evaluate` builds records and a store in a temporary directory and removes them on exit, so there is no persistent JobPilot store to query; the script builds one, then runs the query with `--debug` three times and saves the full trace per run.

Question: `What decisions affect resume generation?`, which is `QUERY_TWO` in `application/evaluation.py`. Corpus: the live JobPilot tree, 20 specs. No code changed between runs.

## Result

Identical in all three runs.

```text
Facets     F1: What decisions affect resume generation?
Draft      S1: The decision was made to use a fallback behavior for resume
               generation, where a role whose bullets are affected by a dropped
               number never ends up empty, and only the offending bullet is
               dropped first, with the role falling back to the user's own
               written text if necessary.
Verification
           S1 containment=False
           removed S1
           F1 covered=False [] reason=no emitted answer sentence
           uncovered F1: What decisions affect resume generation?
Sub claims
           rejected_decomposition S1 count=4 disposition=not_additive
                                     additive_failure=content_token
           dropped_sentence S1 reason=decomposition_invalid
Providers  decompose attempt=1 ... success
           decompose attempt=1 ... success
Result     state: abstained
           abstention_stage: claim_verification
```

## Finding 1: the cause is `no_emitted_sentences`, and it is deterministic

The coverage row carries the AC-12 deterministic reason `no emitted answer sentence`, which is only written when no sentence reached coverage at all. Under AC-15 that is the `no_emitted_sentences` cause, not `uncovered_facet`.

Three runs, one outcome, same disposition and same failure category each time. This is not a stochastic near miss.

**So the abstention is a verification drop, not a coverage refusal.** For this query, coverage directness, the AC-16 caveat exclusion, and OD-7 are all irrelevant: none of them ever ran.

## Finding 2: the answer existed and was discarded

S1 is a correct answer to the question. It names a decision, it is specific, it is drawn from `DM-0019` and carries its citation. A reader would call it a good answer.

It failed `containment`, so it went to decomposition, which is correct behaviour: it is not verbatim in any one chunk. The decomposition returned 4 sub claims, and the AC-11 additive half rejected them because at least one sub claim carried a content token the parent sentence does not have. The single AC-11 retry ran (two `decompose` provider attempts are in the trace) and failed the same way.

**This is the failure mode with the worst shape available**: not a fabrication caught, not a hedge refused, but a correct cited answer destroyed by the check that exists to protect it.

## Finding 3: `additive_failure=content_token`, so task 13 cannot reach it

The AC-19 instrument, shipped in task 17 days before this run, gives its verdict on the first live query it has been pointed at, and it agrees with experiment 0007's 7 of 7 on the self corpus fixture.

`sub_claim_is_additive_free` returns `False` on the first unmatched content token, while `MAX_ADDED_FUNCTION_WORDS` bounds only function word additions. A content token miss is outside the knob entirely. **Task 13 as specified would not move query 2.**

Recall the bound reading pinned in spec 0010: `content_token` is a lower bound on what the tolerance cannot reach. One observation here, on one sentence, but it is the same category the self corpus produced 7 of 7 times.

## Finding 4: no `decision.chosen` chunk reaches the accepted eight

The accepted context for this query, by value path:

```text
body[5]  body[3]  body[2]  body[1]  body[6]  body[2]
context.problem  decision.alternatives[1]
```

Six of eight slots are body chunks. Not one `decision.chosen` chunk arrives, on a question asking what decisions affect something. This is experiment 0007's finding 3 reproduced on the JobPilot corpus, and it is the defect spec 0011 was written to fix.

**This corrects a claim made while reading finding 1.** On the strength of the abstention cause alone it looked as though feature 19 could not help query 2. Finding 4 says otherwise, and there is a mechanism beyond better evidence: `decision.chosen` text is terse and canonical, so a sentence drawn closely from it is far likelier to pass the AC-5 containment shortcut and never be decomposed at all. That is a hypothesis and is recorded as one, not as a result.

## Finding 5: query 2 has no redundancy

Facet extraction returned **one** facet, which restates the question. One facet produced one draft sentence. One draft sentence means one decomposition, and a single decomposition failure is total abstention with nothing else to fall back on.

That explains why this fixture is 0 of 6 in experiment 0008 rather than intermittent, and it means the fixture measures the reliability of a single decomposition call rather than of the pipeline as a whole.

## The diagnostic gap this exposes

The trace names the failure **category** but not the offending **token**, because `RejectedDecomposition` records no claim text by design and `additive_failure` was deliberately specified as a closed category rather than text.

That was the right call for a category. It is not enough to fix the check: knowing that some content token failed does not say whether the decomposition genuinely paraphrased, or whether the matcher's morphology rules are too narrow for the token pair involved. Recording the single offending token, a token rather than claim text, would stay inside the no claim text rule by exactly the reasoning that admitted `additive_failure` in AC-19.

## Limits

- **One query.** Queries 1 and 3 and the rationale summary assertion also abstain in experiment 0008 and were not measured here. Their cause is still unattributed and must not be assumed to match.
- **Three runs, one outcome.** Enough to call this deterministic for practical purposes, not enough to bound a rare alternate path.
- **One sentence.** Finding 3's `content_token` verdict rests on a single decomposition of a single long sentence. It agrees with experiment 0007, which is a different corpus and 7 observations, but this experiment on its own is n=1.
- **The store was built fresh** by the script, so its embeddings are newly generated rather than the ones experiment 0008 queried. Retrieval is deterministic given a store, and the accepted set was identical across all three runs here.
- **Cost and wall clock were not captured** per run; the provider attempt rows in each trace carry prompt and completion tokens if a figure is needed later.

## What this changes

- **The open question from experiment 0008 is answered for query 2: drops, not coverage.** Feature 19 does not address the mechanism that kills this query's answer.
- **But feature 19 is not ruled out for query 2 either**, on finding 4, and the containment shortcut gives it a plausible indirect route. The two problems are less separable than the abstention cause alone suggested.
- **The AC-11 additive half is now the highest value target on live evidence.** It is destroying correct answers on the corpus this tool is aimed at, deterministically, and the calibration task already specced for it cannot reach the failure category.
- **Before that work starts, the offending token needs recording.** Fixing a check whose failures you can only see by category is guesswork, and this project has a standing rule against exactly that.
