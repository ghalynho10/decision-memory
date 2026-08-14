# Experiment 0012: the other three abstentions, attributed

**Date**: 2026-08-14
**Status**: Complete
**Follows**: [Experiment 0011](0011-where-the-matcher-stopped-next.md)
**Result**: Experiment 0011 left three failing fixtures untraced and warned they may or may not share query 2's cause. Two of them do, at the mechanism if not at the shape: `query-1-private-beta-gate` stops on `while` and `assertion-rationale-summary` stops on `instead`, both `incomplete`, both `failure_side=parent`, exactly as query 2 stops on `where`. `query-3-provisional` does not: it produces a fully verified, entailment supported sentence and abstains at coverage on a facet the question did not ask for. **Every measured AC-11 failure now sits on the completeness half. The additive half is implicated by none of them**, which means the owed decision does not have to move the guard standing behind AC-2.

## Why this run happened

Experiment 0011's third threat to validity: query 1, query 3, and the rationale summary assertion abstain 0 of 6 and their causes were not read. Its follow-up asks `/architect` whether subordinating relative adverbs belong in the AC-11 closed function word set, and says the decision needs the rule rather than the token.

A rule cannot be chosen from one token. `where` was the only member of its class ever observed failing, and a set edit ratified on a single observation is the growth by failure pattern the follow-up itself warns against. These three fixtures are the only other live evidence available, and they cost one script call each because task 18 put the token in the trace.

## Method

Three invocations of the committed `docs/experiments/data/jobpilot-abstention-cause.sh`, one per fixture, 3 runs each against the real JobPilot corpus, questions taken verbatim from `application/evaluation.py`:

```bash
S=docs/experiments/data/jobpilot-abstention-cause.sh
D=docs/experiments/data/abstention-attribution
$S "Why was the private beta access gate added, and what was the alternative?" 3 "$D/query-1"
$S "Which decisions are still provisional rather than ratified?" 3 "$D/query-3"
$S "Why does the Adzuna job discovery feature refetch data client side instead of using a background polling job?" 3 "$D/rationale-summary"
```

Each invocation adapts and ingests its own store, so the three runs are independent. The traces are kept in `docs/experiments/data/abstention-attribution/`, one directory per fixture, `meta.txt` plus three full `--debug` traces, matching what experiment 0011 kept. The regenerable `records/`, `index/`, `adapt.txt`, and `ingest.txt` are not kept.

No code changed between this run and experiment 0011. This is attribution of an already measured state, not a re measurement of it.

## Result

| Fixture | Disposition | Side | Token | Stable |
|---|---|---|---|---|
| `query-1-private-beta-gate` | `incomplete` | parent | `while` | 2 of 3 |
| `assertion-rationale-summary` | `incomplete` | parent | `instead` | 3 of 3 |
| `query-3-provisional` | none, no decomposition rejected | | | 3 of 3 |

Query 2's row from experiment 0011, for comparison: `incomplete`, parent, `where`, 3 of 3.

Query 1's third run instead returned `duplicate` at `count=8`, which is `MAX_SUB_CLAIMS`. It is recorded below and not pursued here.

### Query 1 stops on `while`

The dropped sentence, run 2 and run 3 identical:

```text
The private beta access gate was added to ensure that only approved users can
access certain features, while unapproved users are redirected to a private beta
screen, preventing unauthorized access to paid routes.
```

`while` is a subordinating conjunction joining the second clause to the first. Splitting that sentence into standalone atomic sub claims is what removes the need for it, so no sub claim carries it, and the completeness half requires every distinct parent content token to appear somewhere in the response.

### The rationale assertion stops on `instead`

Stable in all 3 runs:

```text
The Adzuna job discovery feature refetches data client side because it needs a
real database query against the `jobs` table for filtering, sorting, and
pagination, and building the client side refetch now contributes toward that
path instead of producing a response shape that would be discarded later.
```

`instead` is neither a wh word nor a subordinating conjunction. It is a conjunctive adverb, here inside the complex preposition `instead of`, and `of` is already in the closed set while `instead` is not. The mechanism is the same as `where` and `while`: it marks a contrast between two clauses, and a decomposition that states each clause on its own has nothing left for it to mark.

**Three tokens, three grammatical categories, one function.** A relative adverb, a subordinating conjunction, and a conjunctive adverb. What they share is not their part of speech, it is their job: they join or contrast clauses, and `DECOMPOSE_SYSTEM_PROMPT` asks for exactly the transformation that dissolves the join. This is the third form of the same defect. Experiment 0010 found it in morphology, where making a participle finite is what decomposition requires; experiment 0011 found it in set membership for one word; this finds that the membership question is not about one word or one category.

### The abstention shape differs from query 2

Query 2 abstained as `no_emitted_sentences`: it had one facet, wrote one sentence, and the drop was total (experiment 0009).

These two do not. Both drafts have two sentences, S2 survives verification, and coverage marks its facet covered:

| Fixture | S1 | S2 | F1 | F2 |
|---|---|---|---|---|
| `query-1` | dropped, `while` | emitted | uncovered | covered by S2 |
| `assertion-rationale-summary` | dropped, `instead` | emitted | uncovered | covered by S2 |

So the abstention is an uncovered facet whose cause is an AC-11 drop one stage earlier. The distinction matters for what a fix predicts: coverage is working correctly here, and it is reporting a real gap left by the dropped sentence.

**In both cases the dropped sentence is the one answering the question actually asked.** F1 is `Why was the private beta access gate added?` and `Why does the Adzuna job discovery feature refetch data client side?`. The surviving sentence answers the secondary half, the alternative and the rejected approach. This is the same reading experiment 0009 recorded for query 2, that the answer existed and the verifier discarded it, and it now holds on two more fixtures.

### Query 3 is a different failure

No decomposition was rejected and no sentence dropped in any of the 3 runs. S1 is emitted with `entailment=supported`, and F1 is covered. The abstention comes from F2.

The question is `Which decisions are still provisional rather than ratified?`. Facet extraction split it into two, and F2 varies across runs:

| Run | F2 |
|---|---|
| 1 | `Which decisions are ratified?` |
| 2 | `Which decisions are not ratified?` |
| 3 | `Which decisions are ratified?` |

Two things are wrong here and neither is AC-11. The `rather than ratified` clause is a contrast term narrowing the request, not a second thing being asked for, and it is being promoted to a facet the answer must satisfy. And the facet is unstable across runs in the strongest possible way: run 2's F2 is the negation of runs 1 and 3, meaning the same input produced opposite demands, and run 2's version is a restatement of F1 that S1 arguably already covers.

This fixture belongs to facet extraction. Attributing it to the function word set would be wrong.

## What this changes

- **The owed decision is about the completeness half only.** All three measured AC-11 failures are `failure_side=parent`. The additive half, the guard behind AC-2 and the only criterion in this chain green on live evidence, is implicated by nothing measured. A fix scoped to the completeness half puts no measured criterion at risk, which the shared matcher of OD-8 could not say.
- **The class is wider than experiment 0011's follow-up assumed.** That follow-up asks about subordinating relative adverbs and names `whose` as the next likely member. `while` fits that framing loosely and `instead` does not fit it at all. A rule stated over that category would ratify an edit that still fails on the rationale assertion.
- **Three of the five failing fixtures share one cause.** If the completeness half stops demanding a match for clause joining words, query 1, query 2, and the rationale assertion all have their blocking token removed at once. Whether they then pass is not established; see below.
- **Query 3 needs its own decision**, on facet extraction, and it is unrelated to the function word set.

## Threats to validity

- **First causes, not all causes.** `failure_token` is where the check stopped in token order. Removing `while`, `where`, and `instead` from the picture does not establish that these sentences pass; a later token can fail next, which is exactly what happened when `falls` gave way to `where`. This experiment says what blocks now. Only a re measurement after the edit says what clears.
- **One sentence per fixture.** Each token comes from one draft sentence on one question. Three fixtures agreeing on a mechanism is stronger than experiment 0011's one, and it is still three sentences.
- **Query 1 is 2 of 3, not 3 of 3.** Its third run failed earlier, as `duplicate` at the sub claim cap, so that run never reached the completeness half. The token is stable in the runs that reached it.
- **No corpus wide count.** Nothing here says how often a clause joining word appears in a generated sentence across the corpus, so the size of the win is unmeasured. The pair comparison instrument of task 18 counts token pairs, not this.
- **Coverage was not evaluated as a judge.** For query 1 and the rationale assertion, F1 is read as correctly uncovered because the sentence answering it was dropped. That the coverage verdict is itself right was not independently checked.

## Follow-up

- [ ] **The completeness half exemption (a decision, owed to `/architect`).** Which words the completeness half must not demand a parent match for. The measured members are `where`, `while`, and `instead`, spanning three grammatical categories and sharing one function, joining or contrasting clauses. The decision needs a membership rule that is decidable without looking at the next failure, and it should state whether the additive half shares the list, since nothing measured requires it to.
- [ ] **Query 3 and facet extraction.** A contrast term promoted to a required facet, and a facet that inverts between runs on identical input. Unrelated to AC-11 and currently unowned by any spec.
- [ ] **`MAX_SUB_CLAIMS` at 8.** Query 1 hit the cap with a `duplicate` verdict in 1 of 3 runs. One observation, recorded so a second one is not read as the first.
- [ ] **`assertion-unverifiable-claim`**, carried unchanged from experiment 0011. Not re measured here.
