# Experiment 0001: query decision-memory on its own specs

**Date**: 2026-08-12
**Status**: Complete
**Follow-up**: Experiment 0002 (fix the spec 0008 status line, re-run queries 6 and 7)

## Why

Feature 16 had been tuned against five fixture queries on the JobPilot corpus for six days without converging. Fixture percentages could not settle it, because judging a JobPilot abstention means recalling what JobPilot decided.

This project's own `docs/specs/` is a corpus where the author wrote every record the same week, so the author is the oracle for every answer and every abstention. The goal was qualitative: read real answers and grade them, rather than count pass rates.

## Setup

Corpus: this repository's own `docs/specs/`.

```bash
cd /Users/ghaly/Documents/Work/Personal/decision-memory
uv run decision-memory adapt . --output ~/Desktop/dm-test/records
uv run --env-file .env decision-memory ingest ~/Desktop/dm-test/records --store ~/Desktop/dm-test/index
uv run --env-file .env decision-memory query "QUESTION" --store ~/Desktop/dm-test/index
```

Ingest cost: 264 chunks, 64,656 embedding tokens, about $0.0013.

### Corpus composition (a finding in itself)

`adapt` discovered 6 specs and skipped 2:

```
skipped docs/specs/0008-reliable-multi-source-retrieval:
  status 'Accepted (AC-13/14/15 fail — verification gap carried to Feature 11)'
  is not a known status
skipped docs/specs/0009-proven-correctness-evaluation-harness: no index.md
```

Specs 0001 and 0002 are flat `.md` files, which the directory adapter does not discover (feature 12).

**The live corpus was 6 records of a possible 10**: DM-0003, DM-0004, DM-0005, DM-0006, DM-0007, DM-0010. Spec 0008, which decides hybrid retrieval, was absent. This turned out to matter.

## Results

Seven queries. Verdicts are the author's, as oracle.

| # | Question | Verdict |
|---|---|---|
| 1 | Why does the adapter warn instead of inventing missing fields? | Correct content, broken output |
| 2 | How does the CLI load a third party adapter, and what was the alternative? | **Good** |
| 3 | What database was chosen for storing user accounts and sessions? | **Correct abstention** |
| 4 | What does the doctor command do? | Correct, padded |
| 5 | What is entailment? | Wrong shape, should have abstained |
| 6 | What was decided about hybrid lexical and semantic retrieval? | **Wrong, and believable** |
| 7 | Why did we choose hybrid lexical and semantic retrieval? | **Correct abstention** |

### Query 2, the good case

```
The CLI loads a third party adapter by using the `select_adapter` function. [C1,C2]
The `select_adapter` function delegates third party selectors to `load_adapter`. [C1,C2]
The `load_adapter` function returns a validated `SourceAdapter` instance. [C1]
The alternative was to consider Python package entry point discovery. [C1]
It was not implemented as explicit selectors were not deemed a usability problem. [C1]
```

Correct, cited to DM-0005 Feature design and Follow-up, and it captured the rejected alternative with its reason. This is the tool working as designed.

### Query 1, fragment output

```
The adapter warns because a malformed grammar subject must exist in the original case corpus. [C1]
It passes only when it is absent from discovery. [C1]
It passes only when it is explicitly skipped. [C1]
...
```

"It" has no referent. The parent sentence bound it; the fragment does not.

### Query 5, padding

Source text, from spec 0010 Consequences:

> The lexical guardrail cannot prove preserved actors, negation, scope, order, or relations. Entailment remains responsible for factual support.

Output, 2 sentences expanded to 6 lines:

```
Entailment is responsible for providing factual support. [C1]
Lexical guardrails cannot prove preserved actors. [C1]
Lexical guardrails cannot prove negation. [C1]
Lexical guardrails cannot prove scope. [C1]
Lexical guardrails cannot prove order. [C1]
Lexical guardrails cannot prove relations. [C1]
```

A single sentence listing five items became five sentences repeating one stem. The query also should have abstained: this corpus contains no definition of entailment, and the answer was assembled from a tangential tradeoff note.

### Query 6, the serious one

```
Hybrid lexical and semantic retrieval was not included in the scope. [C1]
Lexical retrieval was excluded. [C1]
Semantic retrieval was included in the feature design scope boundaries. [C1]
Sources
C1 DM-0007 ... docs/specs/0007-core-cited-query/index.md Feature design
```

Ground truth, from `docs/scope/scope.md` feature 10, status `done`:

> Add structured metadata filtering and lexical retrieval alongside semantic retrieval... Hybrid retrieval always applies filters first, then runs BM25 and cosine retrieval, fuses ranks, and applies record diversity.

**The answer inverts a shipped decision.** Nothing is fabricated: spec 0007 really did scope lexical retrieval out, and the citation is accurate. Spec 0008 later reversed that scope decision, and spec 0008 was not in the corpus.

### Query 7, the control

The same topic phrased as a rationale question returned `not enough evidence here`, which is correct.

## Findings

**F1. Decomposition damages output in two distinct ways.** Orphaned references (query 1) and list explosion (query 5). Both follow from spec 0010 AC-4, which emits verified sub claims as the answer text. This is new evidence for the `/recover` rethink, and it is a stronger argument than any abstention rate: the fixture gates never measured readability, so six days of tuning never surfaced it.

**F2. A superseded decision can be reported as current.** Query 6 produced a fluent, accurately cited, plausible answer that contradicts a shipped decision. The failure is not fabrication. Every statement is true of spec 0007. The corpus simply lacked the document that superseded it, and nothing in the pipeline represents "this framing was later reversed."

**F3. Abstention is phrasing sensitive.** Queries 6 and 7 differ only in shape, ask about the same absent decision, and produce opposite outcomes. `Why did we choose X` found no rationale and abstained. `What was decided about X` found a decision statement about the topic and accepted it. **Nothing distinguishes a decision about a topic from the current decision about that topic.** The abstention machinery is not broadly broken; it has one specific blind spot.

**F4. The corpus gap signal does not reach query time.** `adapt` reported the skipped spec 0008 out loud. That warning never propagates to a query, so an answer drawn from a knowingly incomplete corpus carries no indication of it. A user who ingested weeks earlier has no way to know.

**F5. Citation provenance is excellent and is not implicated.** Every citation resolved to the correct record, chunk, source file, and section, including field level paths such as `consequences.negative[4]`. Even the wrong answer in query 6 cited its source correctly. Whatever is broken, it is not the provenance layer.

## What this changes

The feature 16 rethink stands, and F1 strengthens it with an argument the fixture gates cannot make.

F2, F3, and F4 describe a gap that is **not** covered by feature 16 or by any current scope row. It may matter more than feature 16: feature 16 makes answers ugly, while this makes an answer wrong and convincing. Candidate scope row, wording to be settled by `/architect`: surface known corpus gaps at query time, and distinguish a current decision from a superseded one.

## Threats to validity

- Seven queries, one run each. No repetition, so provider variance is unmeasured.
- One corpus, and an unusually clean one: these specs were written by a single author in one week under a consistent template.
- The query 6 failure required a malformed status line to trigger. That line came from this project's own process, so it is not exotic, but a healthy corpus would not have produced it.
- Verdicts are the author's judgment, not a mechanical oracle.

## Next

Experiment 0002. Set spec 0008's status to plain `Accepted`, preserving the AC-13/14/15 note elsewhere in the spec, then re-adapt, re-ingest, and re-run queries 6 and 7.

- If query 6 answers correctly from DM-0008, F2 is confirmed as a corpus completeness problem.
- If query 6 still answers from DM-0007 with spec 0008 present, the problem is retrieval preferring a stale document over a current one, which is a different and larger issue.
