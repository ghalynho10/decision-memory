# Experiment 0002: fix the corpus gap, and what it exposed

**Date**: 2026-08-12
**Status**: Complete
**Follows**: [Experiment 0001](0001-self-query-on-own-specs.md)
**Result**: Hypothesis partly confirmed, and a more important finding surfaced underneath it.

## Hypothesis

Experiment 0001 finding F2: query 6 ("What was decided about hybrid lexical and semantic retrieval?") returned a fluent, correctly cited answer that inverted a shipped decision, because spec 0008 was absent from the corpus and spec 0007 carried the superseded scope decision.

Two predicted outcomes were stated in advance:

1. With spec 0008 present, query 6 answers correctly from DM-0008. Corpus completeness confirmed as the cause.
2. With spec 0008 present, query 6 still answers from DM-0007. Retrieval prefers a stale document, a larger problem.

**Neither happened.** The actual outcome was a third case that was not predicted.

## Change

One line in `docs/specs/0008-reliable-multi-source-retrieval/index.md`:

```diff
-**Status**: Accepted (AC-13/14/15 fail — verification gap carried to Feature 11)
+**Status**: Accepted
```

No information was lost. The `**Status note (2026-08-11)**` line directly below already carries the AC-13/14/15 detail in full.

Re-adapt and re-ingest were both incremental and clean:

```
discovered 7 specs, skipped 1        (was: discovered 6, skipped 2)
  written DM-0008
plan: added 1, updated 0, unchanged 6, removed 0, failed 0
```

## Result

| Query | Before | After |
|---|---|---|
| 6. What was decided about hybrid lexical and semantic retrieval? | Wrong, inverted a shipped decision | `not enough evidence here` |
| 7. Why did we choose hybrid lexical and semantic retrieval? | `not enough evidence here` | `not enough evidence here` |

Safer, but still not correct. DM-0008 is now in the corpus and does decide this question.

## The trace

`--debug` on query 6 after the fix. Every stage up to the last one worked.

**Retrieval, correct.** DM-0008 chunks surfaced and were accepted into context.

**Facets, one facet.**

```
F1: What was decided about hybrid lexical and semantic retrieval?
```

**Draft, a genuinely good answer.**

```
S1: The hybrid retrieval system uses a combination of lexical BM25 and semantic
    Chroma retrieval, followed by reciprocal rank fusion to combine their scores,
    but it does not claim general retrieval superiority at scale due to the
    limitations of the JobPilot corpus.
```

That is correct, complete, appropriately hedged, and it answers the question.

**Verification, everything passed.**

```
S1.1 The hybrid retrieval system uses a combination of lexical BM25 and semantic Chroma retrieval.
     entailment=supported kept=True
S1.2 The hybrid retrieval system uses reciprocal rank fusion to combine their scores.
     entailment=supported kept=True
S1.3 The hybrid retrieval system does not claim general retrieval superiority at scale.
     entailment=supported kept=True
dropped_sub_claim S1.4 disposition=lexical_guard
```

**Coverage, rejected.**

```
F1 covered=False []
uncovered F1: What was decided about hybrid lexical and semantic retrieval?
state: abstained
abstention_stage: claim_verification
```

## Finding

**A correct, complete, fully verified answer was discarded at the last step.**

The mechanism is the interaction of two acceptance criteria in spec 0010:

- **AC-4** shatters the draft sentence and emits only the sub claim fragments.
- **AC-12** says a facet is covered only when *one* kept sentence directly states its answer, and coverage cannot combine sentences.

The decision here is inherently a three part statement: BM25 plus semantic, fused by reciprocal rank fusion, without a superiority claim. No single fragment states all of it. The parent sentence did. AC-4 destroyed the parent, AC-12 forbade reassembling it, so the facet came back uncovered and a correct answer abstained.

### This is the mirror of the JobPilot query 5 failure

| | JobPilot query 5 | This query |
|---|---|---|
| Fragments | vacuous, e.g. "The original approach was changed" | informative and specific |
| Entailment | supported | supported |
| Coverage | accepted them, wrongly | rejected them, wrongly |
| Outcome | answered when it should abstain | abstained when it should answer |

Same root cause, opposite symptom. Fragmenting the answer makes coverage unreliable **in both directions**: fragments that say too little can satisfy a facet, and fragments that each say part of the truth cannot.

### It also corrects a misdiagnosis in spec 0010

Spec 0010 `verify.md` records query 3's abstention as follows:

> This is the directness rule working as intended. AC-9 no longer requires query 3 to pass; the generation quality gap is enrolled as a follow up.

**That diagnosis is wrong, and this run demonstrates it.** Generation here was excellent. The draft was a good answer by any reading. Nothing about generation quality caused this abstention. The cause is structural, and the "generation directness follow up" enrolled against it would not have fixed it.

Any decision that takes more than one clause to state is currently unanswerable.

### Consequence for the rethink

The `/recover` proposal, judge the parent sentence rather than replace it, now fixes **both** failure directions with one change:

- Vacuous fragments can no longer cover a facet, because there are no fragments to judge. The parent is verified whole.
- Multi part answers stop abstaining, because the parent sentence states the whole decision directly.

That is a considerably stronger case for the rethink than either failure alone.

## Status of the earlier hypothesis

F2 from experiment 0001 is **partly confirmed**. The missing document did cause the wrong answer: with spec 0008 present, retrieval surfaces the right chunks and generation drafts the right answer. Prediction 2 is ruled out; retrieval does not prefer a stale document.

Prediction 1 could not be reached, because a different defect blocks the answer downstream of retrieval.

**F4 still stands and is untested.** Nothing surfaces a known corpus gap at query time. This experiment fixed the gap by hand after finding it by hand.

## Threats to validity

- One run per query. No repetition, so provider variance is unmeasured; abstention here is deterministic given the trace, but the draft wording is not.
- Only query 6 was traced with `--debug`. Query 7's abstention is plausibly the same mechanism but was not confirmed.
- One corpus, one author, one week of records.

## Next

1. `/architect` on spec 0010, with this trace as evidence. The scope question is whether decomposition judges the parent or replaces it, and the AC-4 plus AC-12 conflict should be named explicitly in the revision.
2. Correct the query 3 "generation quality gap" entry in spec 0010 `verify.md` and `rationale.md`; it is a structural conflict, not a generation problem.
3. F4 remains open as a scope candidate: surface known corpus gaps at query time.
