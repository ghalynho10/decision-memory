# Where things stand

Written 2026-08-12, after a `/recover` diagnosis on feature 16. Read this first when coming back cold.

## What this project is

A local, cited RAG system that makes software decision history queryable. Point it at a project's decision records, ask why something is built the way it is, and get an answer with citations back to the source, or an honest "not enough evidence here."

## The state in one line

Eleven of eleven version one features are built and passing. One hardening feature on top of them is stuck, and the reason it is stuck is now understood.

## What is built and working

| Area | State |
|---|---|
| Features 1 to 11 | done |
| Unit suite | 524 passing |
| Source | about 15,000 lines |
| Tests | about 12,900 lines |
| Ruff, format, strict mypy, build | passing |
| Real corpus | JobPilot, 15 directory specs read today |

Concretely, the tool ingests a real corpus, retrieves over it with hybrid semantic plus lexical search, generates an answer, verifies that answer against cited evidence, and abstains when the evidence does not hold. There is an evaluation harness with five defining queries plus three assertions that runs the whole thing live against real providers.

**The tool works today.** Everything below is about making its abstentions honest, not about making it run.

## What is stuck

Feature 16, "abstention verification reliability", spec 0010. Four of five build milestones are done. The fifth fails its live gate.

The goal: query 4 and query 5 must abstain in all six runs across two live batches, while the other fixtures keep passing.

Two mechanisms have been tried for the lexical guard that gates decomposition:

| | query 4 | query 5 | unverifiable | rationale summary |
|---|---|---|---|---|
| whole response guard | 6/6 pass | 6/6 pass | pass | 0/6 fail |
| per sub claim guard | 5/6 fail | 0/6 fail | 3/6 fail | 2/6 fail |

Tightening broke one fixture. Loosening broke four, including the one it was meant to repair.

## Why it is stuck (the diagnosis)

Not a bug. A wrong assumption, and the guard is not where the problem lives.

**Assumed:** decomposing a draft sentence into atomic sub claims is purely a safety operation. It only removes unsupported content, so the surviving fragments can be emitted as the answer and judged for facet coverage the same way whole sentences were.

**Reality:** decomposition rewrites context bound clauses into self contained sentences. That strips the binding that made them dependent. Both downstream gates then judge them as if they were self contained.

Query 5 asks "What changed the original approach to storing uploaded files?" and should abstain. Its answer sentence splits into eight sub claims. Five come back supported and kept:

```text
S1.1 The original approach was changed.
S1.2 The critique found a gap in the safety reasoning.
S1.3 The critique suggested a more robust alternative for handling upload keys.
S1.4 The suggested alternative was adopted.
S1.8 The change avoided potential collisions.
```

"The original approach was changed" names nothing. Inside its parent sentence its referent was bound. Standing alone it is unmoored, and entailment charitably finds support for it while coverage accepts it as directly stating a decision. The AC-12 directness rule explicitly forbids an anaphoric fragment from covering a decision facet, but decomposition destroys the evidence that the fragment was ever anaphoric.

Splitting a claim makes each piece easier to support and easier to accept as coverage at the same time. Both gates weaken together.

The lexical guard compares vocabulary. It cannot see reference binding at all. That is why moving it in either direction moves every gate the wrong way: it sits upstream of the actual leak.

One consequence worth holding onto: query 5's earlier 6 of 6 abstention was an artifact. It abstained because three cosmetic violations were destroying the whole response, not because the evidence failed to support the answer. The earlier passing state was passing for the wrong reason.

## The likely shape of the fix (not yet decided)

Use decomposition to **judge** the parent sentence, not to **replace** it. Emit surviving parent sentences whole so coverage sees real sentences with their references intact.

That reopens the omission attack the cross check found: a decomposition can omit the fabricated clause, return only grounded material, and make a fabricated parent look safe. The guard as built checks that sub claims do not **add** content. The missing check is that they do not **omit** it, that every content bearing clause of the parent is accounted for by some sub claim.

This is a load bearing design decision. It belongs in `/architect` against spec 0010, not in a code patch.

## What survives the rethink

Almost everything.

Keep, unchanged:
- Features 1 to 11 entirely
- AC-1, never restore a decomposed parent, proven and correct
- AC-5, containment skips decomposition, a correct cost bound
- AC-6, AC-7, AC-10, trace shape, provider failure contract, schema stability
- AC-8, the citation boundary between available and missing ids
- The decomposition provider itself
- The evaluation harness, which is what caught this

Revisit:
- AC-4, "every kept sub claim becomes its own answer sentence." This is the load bearing error.
- AC-11, the lexical guard. Its role shrinks a great deal once it is not gatekeeping answer text.
- AC-12, what coverage judges.

## Two things that are not the problem

**Feature 8 (built in ADR adapters)** ships adapters for MADR and plain ADR, meant for other people's repositories. JobPilot is jsmastery-specs format, already handled by feature 4. Feature 8 would add zero records to the corpus being tested.

**Corpus size.** Five of JobPilot's twenty specs are flat `.md` files the adapter cannot read yet, which is feature 12. Adding them would not fix query 5, because a vacuous fragment stays vacuous no matter how much evidence exists, and more evidence makes it easier to support, not harder. Feature 12 is plausibly relevant to query 2's known intermittent DM-0004 citation, since `0019-resume-generation-quality` exists as both a flat file and a directory. That is a separate problem.

## A process note

Spec 0010 runs to 630 lines. AC-11 alone is roughly 400 words pinning five exact string transformations, a character floor, and a closed function word set, all for a heuristic the live evidence now says was never doing the safety work.

The specification precision outgrew the signal it was tracking. That is the main reason this stopped feeling legible. It is not a sign the project is failing.

## Next step

Run `/architect` against spec 0010 to settle what the verification unit and the output unit each are, and whether decomposition judges or replaces. Do not turn the lexical guard knob a third time.

## Open items unrelated to this

Carried from `docs/session-notes.md`, still unresolved:
- Spec 0002 does not mention the Pydantic date coercion validator
- The `evidence.mentions_unresolved` warning never reaches CLI output
- Commit `abe5f86` is mislabelled `fix(adapter):` but is docs only, already pushed
- Feature 11 has no spec `index.md`, only a `verify.md`, so `/architect` sees 0009 as taken with no decision record behind it
- Current branch is `evaluation-harness`, not the `feature/` prefix the git convention prescribes
