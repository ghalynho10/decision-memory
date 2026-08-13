# Experiment 0003: the whole sentence build and its failing gate

**Date**: 2026-08-12
**Status**: Complete
**Follows**: [Experiment 0002](0002-corpus-gap-fix-and-coverage-conflict.md)
**Result**: The gate still fails. Both reported causes are real. A measured rate over 12 queries puts them in order and shows the system currently answers 1 query in 12.

> **Correction, same day.** An earlier version of this file claimed the inline citation marker cause did not exist, on the strength of one live run. A 12 query measurement disproved that: markers appear in the draft text intermittently, in 11 of 20 sentences. The correction and the measurement are recorded below, and the original reasoning is kept because the way it went wrong is the finding worth keeping.

## What was built

`/develop` implemented spec 0010 tasks 5 to 8 on `feature/abstention-verification` (`abba958`, `8a60bca`): decomposition is now a check on a draft sentence rather than a rewrite of it. The two half validity test, whole sentence output, `dropped_sentences` in place of `dropped_sub_claims`, and the rewritten test suite. 529 unit tests pass; ruff, format, strict mypy, and the build are green.

One change the spec did not name: `DECOMPOSE_SYSTEM_PROMPT` now asks the model for completeness as well. Without it the new hard gate fires on correct behaviour. Spec 0010 treats prompt text as a fixed constant, so this belongs in the spec rather than only in the code.

`/develop` ran the cheap gate (task 11) early, ahead of the calibration task, which was the right call and better than the order the spec records.

## The gate result

| Query | Required | Actual |
|---|---|---|
| What was decided about hybrid lexical and semantic retrieval? | answer from DM-0008, whole sentence | **abstains** |
| Why did we choose hybrid lexical and semantic retrieval? | abstain | abstains, but vacuously |

Every draft sentence was dropped, so the second query passes for the wrong reason. That is the same failure class experiment 0002 recorded: a gate satisfied by an artifact rather than by the behaviour it claims to measure.

## Finding 1: measured drop rates over 12 queries

12 queries against this repository's own corpus, 20 draft sentences, one run each. Transcripts and the script are in the scratchpad; the counts are read from the trace dispositions.

| Cause | Count | Share of drops |
|---|---|---|
| `not_additive` | 14 | 74% |
| `incomplete` | 3 | 16% |
| `duplicate` | 1 | 5% |
| `unsupported_sub_claim` | 0 | 0% |

**19 of 20 draft sentences were dropped. 1 query of 12 answered.** The feature as built is not usable, and the additive half of AC-11 is the reason in three cases out of four. That is task 9's calibration target, and the size of the gap says it is not a small adjustment.

## Finding 2: the inline citation markers are real, and intermittent

`/develop` reported that the generator writes inline `[ch_...]` markers into the draft sentence text, that `sentence_tokens` reads a chunk id as a parent content token, that no sub claim can match it, and that a sentence carrying one therefore fails completeness. This is correct.

Counting bracket groups per rendered draft line separates the two sources, because the debug renderer at `cli.py:970` appends its own group with `",".join(...)` while the model writes `", "`:

| | Sentences | Dispositions |
|---|---|---|
| marker in text | 11 of 20 | `not_additive` 8, `incomplete` 2, `duplicate` 1 |
| no marker | 9 of 20 | `not_additive` 6, `incomplete` 1, emitted 1 |

Two refinements on the report. Markers do not cause `incomplete` unconditionally: the additive half runs first and claimed 8 of the 11 marker bearing sentences before completeness was reached, so the marker effect is partly masked by check order. And `incomplete` fires without a marker too (one case), so markers are not its only cause.

**A wrong correction, recorded because the mistake is instructive.** An earlier version of this file claimed this cause did not exist. The reasoning: the renderer appends brackets, so a trace showing them proves nothing; and in one live run a sentence with a chunk id visible in its rendered line still received entailment verdicts, which under the revised contract can only happen after completeness passes. That inference is valid. The premise was not: that particular run had a clean text, and marker injection turns out to be intermittent at roughly one sentence in two. One clean sample was generalized into a claim about the mechanism.

The method note from the earlier version survives, and now cuts both ways: read the field, not a rendered view of it, and do not settle a rate question with a single sample. Both errors were made here within an hour, in opposite directions.

## Finding 3 (secondary): list splitting against strict entailment is rare

An earlier single run showed a sentence dying because decomposition split an enumerated list into one claim per item and entailment rejected one item on a fine distinction:

```text
S2.6  The `load_adapter` function handles metadata failures.
      entailment=unsupported
      reason=The evidence does not mention that the `load_adapter` function
             specifically handles metadata failures; it only lists various
             types of failures that can occur, including metadata failures,
             without indicating that the function addresses them.
```

The mechanism is real: splitting a list multiplies the independent chances that some item draws a strict reading, and one such verdict removes the whole parent under the drop the whole sentence rule.

**It did not fire once in 12 queries.** `unsupported_sub_claim` accounts for 0 of 19 drops. It was previously written up here as the more serious of the two causes, on the strength of that single observation. The measurement does not support that; it is a real mechanism at a negligible observed rate, and it should not shape the next design pass. Worth re measuring once the additive half is calibrated, since almost nothing currently reaches entailment at all.

## Finding 4: the self corpus gate is contaminated, by this project's own spec

Spec 0010's build plan (task 11) names the gate's expected answer verbatim. That spec lives in `docs/specs/`, which is the corpus the gate queries. The first run answered out of that text.

The gate therefore measures what it claims to only with spec 0010 held out of the corpus. The fault is in how the spec was written, not in the build: writing an expected answer into a document the system under test reads makes the corpus a source for the answer.

This is the same shape as experiment 0001 finding F2 seen from the other side. There, a missing record made a wrong answer look right. Here, an added record makes a right answer meaningless.

## Also recorded

The repository's own `.decision-memory` store is unusable: `adapt` plus `ingest` left it partial, with two `digest.record_mismatch` records and missing vectors, failing parity at `fetched 239, expected 288`. A clean rebuild from scratch completed with zero failures, so this is stale ledger state rather than a code defect. Rebuilding costs re embedding. Worth watching: if a partial ingest can leave a store that fails parity and cannot self repair, that is a durability question for the ingest path, separate from feature 16.

`verify.md` is untouched. Spec 0010 assigns its rewrite to task 10, and the pending decisions above would invalidate steps written now.

## What this changes

The order of work is now measured rather than argued.

1. **Task 9 is the priority and is bigger than "calibration" suggests.** The additive half rejects 74 percent of drops. Until it is fixed almost nothing reaches entailment, which also means every other rate here is measured on a starved pipeline.
2. **The marker question needs a decision**, and it is small: either the matcher ignores tokens matching the chunk id shape, or the generation boundary strips markers from `text` since `chunk_ids` already carries them structurally. The second is cleaner, because the marker is redundant with a structured field and its presence in `text` also defeats the AC-5 containment shortcut.
3. **The gate must hold spec 0010 out of the corpus**, or stop naming its expected answer inside it.
4. **List splitting is not on the critical path.** Re measure after 1 and 2 land.

A design pass should settle 2 and 3, and can take 1 as a measurement task rather than a decision. Point 4 needs nothing yet.

## Threats to validity

- 12 queries, one run each, no repetition. Decomposition is stochastic and the same query produced different dispositions across runs, so these are rates on a small sample, not stable figures. The 74 percent additive share is large enough to act on; the 0 percent for `unsupported_sub_claim` is a weaker claim, since a rare event can miss a 12 query window.
- Every rate is measured on a starved pipeline. With 74 percent of sentences dying before entailment, the downstream causes are undersampled by construction and should be re measured once the additive half is calibrated.
- Marker detection counts bracket groups in the rendered line, which is a heuristic. It is corroborated by the separator difference (`", "` from the model, `","` from the renderer) and by the disposition correlation, but it was not read from the field directly.
- The queries were written by the same person who read the results, against a corpus of 7 records. They are not a neutral sample.
- The run used the scratchpad store built for experiment 0001, not the repository store, which was in the failed parity state described above.
