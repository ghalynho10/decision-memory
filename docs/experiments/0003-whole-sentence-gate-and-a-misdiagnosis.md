# Experiment 0003: the whole sentence build, its failing gate, and a misdiagnosis

**Date**: 2026-08-12
**Status**: Complete
**Follows**: [Experiment 0002](0002-corpus-gap-fix-and-coverage-conflict.md)
**Result**: The gate still fails. One of the two reported causes does not exist. A different cause, unreported, does.

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

## Finding 1: the reported marker cause does not exist

`/develop` reported two causes. The second was that the generator writes inline `[ch_...]` citation markers into the draft sentence text, that `sentence_tokens` reads a chunk id as a parent content token, that no sub claim can ever match it, and therefore that **any sentence carrying a marker fails completeness unconditionally**. It recommended an `/architect` pass on how the validity test should treat those markers.

That is wrong, and acting on it would have produced a fix for a problem the system does not have.

**The markers come from the debug renderer, not the text.** `cli.py:970`:

```python
markers = ",".join(sentence.chunk_ids)
typer.echo(f"  {sentence.sentence_id}: {sentence.text} [{markers}]")
```

The generation schema carries `chunk_ids` as a separate structured array, and `validate_draft` stores `text=text.strip()` beside it. The brackets visible in a `--debug` trace are formatting applied at print time.

**The direct evidence is a live run on the built code.** Querying `How does the CLI load a third party adapter?` produced:

```text
rejected_decomposition S1 count=4 disposition=not_additive
dropped_sentence S1 reason=decomposition_invalid
dropped_sentence S2 reason=unsupported_sub_claim
```

No `incomplete` disposition appears. S2 is the proof: it decomposed into seven sub claims and every one received an entailment verdict. Under the revised contract entailment runs only on a valid decomposition, so S2 passed both halves of AC-11, completeness included. Its text is:

> The `load_adapter` function is a public infrastructure function that validates a `SourceAdapter` instance and handles selector, import, attribute, metadata, or method presence failures.

Had a `[ch_b0a5850...]` marker been part of that text, completeness would have required some sub claim to carry that token. None do. The sentence would have failed `incomplete`. It did not.

The likely path to the wrong conclusion: read the renderer's appended brackets as text content, form the hypothesis, then test it by inserting a marker by hand. Inserting one does fail completeness, so the test confirms the hypothesis without ever checking the premise.

**Method note for later runs.** A claim about what a field contains has to be read from the field, not from a rendered view of it. The debug renderer is a presentation layer and it adds punctuation the data does not have.

## Finding 2: the real second cause is list splitting against strict entailment

S2 in the run above died as `unsupported_sub_claim`. The parent listed five failure kinds; decomposition split the list into five separate claims; entailment then rejected one of them:

```text
S2.6  The `load_adapter` function handles metadata failures.
      entailment=unsupported
      reason=The evidence does not mention that the `load_adapter` function
             specifically handles metadata failures; it only lists various
             types of failures that can occur, including metadata failures,
             without indicating that the function addresses them.
```

The parent sentence is correct and well cited. One over strict verdict on one item of an enumerated list removed the whole sentence.

This is the drop the whole sentence tradeoff that spec 0010 Consequences accepted, meeting a decomposition behaviour the spec did not anticipate: splitting an enumerated list multiplies the number of independent chances that some sub claim draws a strict reading. The more items the parent enumerates, the likelier the sentence dies. Nothing in the spec schedules work against this, and task 9 does not reach it, because task 9 calibrates the lexical tolerance and this is an entailment verdict.

## Finding 3: the self corpus gate is contaminated, by this project's own spec

Spec 0010's build plan (task 11) names the gate's expected answer verbatim. That spec lives in `docs/specs/`, which is the corpus the gate queries. The first run answered out of that text.

The gate therefore measures what it claims to only with spec 0010 held out of the corpus. The fault is in how the spec was written, not in the build: writing an expected answer into a document the system under test reads makes the corpus a source for the answer.

This is the same shape as experiment 0001 finding F2 seen from the other side. There, a missing record made a wrong answer look right. Here, an added record makes a right answer meaningless.

## Also recorded

The repository's own `.decision-memory` store is unusable: `adapt` plus `ingest` left it partial, with two `digest.record_mismatch` records and missing vectors, failing parity at `fetched 239, expected 288`. A clean rebuild from scratch completed with zero failures, so this is stale ledger state rather than a code defect. Rebuilding costs re embedding. Worth watching: if a partial ingest can leave a store that fails parity and cannot self repair, that is a durability question for the ingest path, separate from feature 16.

`verify.md` is untouched. Spec 0010 assigns its rewrite to task 10, and the pending decisions above would invalidate steps written now.

## What this changes

Task 9 stands and is still needed. Finding 1 removes an `/architect` question that was about to be asked. Finding 2 adds one that was not going to be asked, and it is the more serious of the two, because no calibration reaches it.

The next design pass should settle three things together:

1. Whether per sub claim entailment is too strict when decomposition splits an enumerated list, and if so whether the fix belongs in the decomposition contract (do not split a list into separate claims), in the entailment prompt, or in the survival rule (allow a bounded number of unsupported sub claims).
2. The additive tolerance calibration that task 9 already owns.
3. How the self corpus gate avoids reading its own expected answer, either by holding spec 0010 out of the corpus or by keeping expected answers out of the spec.

## Threats to validity

- Finding 1 rests on one live run, but the inference is structural rather than statistical: entailment ran on S2, entailment runs only after validity passes, so S2's decomposition satisfied completeness. A marker in the text makes that impossible.
- Finding 2 rests on one observed sentence. That list splitting multiplies strictness is a mechanism argument, not a measured rate; how often it fires is unknown and worth measuring in the same pass as task 9.
- The run used the scratchpad store built for experiment 0001, not the repository store, which was in the failed parity state described above.
