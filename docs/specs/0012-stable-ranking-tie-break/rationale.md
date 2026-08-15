# 0012. Stable ranking tie break: rationale

## Context

Retrieval ranks candidates by a score and breaks ties on `chunk_id`, in all three ranking paths (`query.py:436`, `:938`, `:979`). A chunk id is a SHA256 over a payload whose first content field is the generation id (`chunking.py:74`), and the generation id is fresh on every build. So a chunk id is deterministic within one build of the store and unrelated across builds, by construction: it names a chunk in a generation, not the content of that chunk.

[Experiment 0015](../../experiments/0015-the-store-is-deterministic-its-names-are-not.md) measured what that costs. Two independent builds of the JobPilot corpus produced byte identical content and no shared chunk id at all: 378 chunks each, identical text, identical fingerprints, and 378 of 378 ids different. `adapt` and `ingest` are deterministic in what they produce and not in what they call it.

That matters because a tie broken by a value that is fresh on every build makes the build an input to the answer. [Experiment 0014](../../experiments/0014-the-causes-pinned-and-the-store-split.md) found a batch holding every miss of one live criterion, answering one query three times out of three with a fluent, well cited, wrong answer, while three other batches agreed with each other. A batch is one `evaluate` invocation, which is one adapt plus one ingest, so the store is held constant inside a batch and varied between them. Experiment 0015 established a mechanism connecting a rebuild to a different evidence set that is entirely inside shipped code and needs no provider to be nondeterministic. It stopped short of attribution, and this decision does not claim one either.

The forces that shaped the choice:

- **The change has to be correct under a retrieval design that is already scheduled to change.** Spec 0011 AC-3 removes fusion eligibility and AC-4 retires the top 24 boundary. Those change which candidates exist and therefore which ties exist.
- **The store is not the only thing that varies between batches.** Provider session drift is the other candidate, named in experiment 0014 and never separated from the store. A fix whose proof is a deterministic test settles the store half without needing to settle the other.
- **This project has repeatedly been burned by a figure measured with a contaminated instrument.** Anything that claims a measurement here has to say what it holds constant.
- **The ranking path is shipped, verified, and test locked.** Spec 0008's retrieval behaviour is `done`, so the blast radius of any change to it has to be small enough to reason about completely.

## Measurements taken for this decision

Four, all reproducible, three of them needing no provider at all.

### 1. The top 24 boundary is not where this bites

Experiment 0015 reasoned that a tie at the top 24 cliff decides whether a chunk reaches fusion at all, and named measuring the tie frequency there as a follow up nobody had run. It is measurable offline: BM25 needs no embeddings, so the shipped scorer can be run over the real corpus directly. Adapting the JobPilot corpus, chunking with the shipped chunker, and running `bm25_lexical_scorer` for each battery question over all 378 chunks:

| Query | Positive scoring | Tied chunks | Tie groups | Tie straddling rank 24 |
|---|---|---|---|---|
| query-1 | 122 | 14 | 7 | no |
| query-2 | 118 | 6 | 3 | no |
| query-3 | 114 | 14 | 6 | no |
| query-4 | 135 | 2 | 1 | no |
| query-5 | 49 | 6 | 3 | no |
| rationale | 260 | 8 | 4 | no |

Lexical ties are common, between 2 and 14 chunks per query. None of them straddles the top 24 boundary on any of the six questions. So the cliff experiment 0015 pointed at is real and is not currently being crossed, and a fix justified only by that cliff would be justified by something not happening.

### 2. Fusion ties are structural, not incidental

The exposure is one level down, in reciprocal rank fusion. A chunk ranked by only one retriever at rank `r` contributes `1 / (60 + r)`, and a chunk ranked by only the other retriever at the same rank contributes exactly the same. That is not a coincidence of a corpus, it is arithmetic on the shipped constants.

Enumerated exhaustively in exact rational arithmetic over every `(lexical_rank, semantic_rank)` shape reachable with `RRF_CONSTANT = 60` and `CANDIDATE_LIMIT = 24`:

```
collision groups mixing a both ranked chunk with a single ranked chunk:  0
collision groups where all members are single retriever chunks:         24
collision groups where all members are both ranked chunks:             276
  of those, groups that are not simply (a, b) against (b, a):            1
    1/36  shared by (3, 24), (12, 12), and (24, 3)
```

Zero mixed groups, because the smallest score a both ranked chunk can carry is `2/84`, which is larger than the largest a single ranked chunk can carry, `1/61`. The 24 single retriever groups are each `(r, None)` against `(None, r)`. The 276 both ranked groups are symmetric pairs, except for exactly one three way group where `1/63 + 1/84` equals `1/72 + 1/72`.

These ties sit at the top of the fused list, which is the list the two pass diversity walk reads. That walk accepts at most eight chunks with at most two per record, and it defers a candidate at the record cap, so the order two tied candidates are visited in decides which one is accepted and which one is deferred. The tie break reaches the accepted context routinely, not on a rare coincidence.

### 3. The tie population changes shape under feature 19

Spec 0011 AC-3 lets every chunk carrying a rank contribute at any rank, and AC-4 deletes `CANDIDATE_LIMIT`. Every accepted chunk gets a semantic rank, while only term matching chunks get a lexical rank, so lexical only chunks stop existing. Enumerated over the real corpus size with a measured lexical count:

```
K=60  corpus=378  lexically ranked=122
collision groups mixing a both ranked with a semantic only chunk:  51
collision groups where all members are both ranked:              7603
```

Today's dominant class, the 24 single retriever pairs, disappears entirely. A class that is structurally impossible today, a both ranked chunk colliding with a semantic only one, appears with 51 groups, because the score ranges stop being disjoint once ranks run past 24.

This is the measurement that decided the shape of the fix rather than merely supporting it. Any rule that ranks tied candidates by a retrieval signal would be tuned against a population that feature 19 replaces.

### 4. The stable triple is not unique, and finding out why turned up a second defect

The obvious key, `(record_id, value_path, ordinal)`, is unique on a fresh build. It is not unique in general. Ingesting one record with the real store writer, editing its source, and reingesting into the same store without `--rebuild`, which resumes the same generation:

```
chunks after first ingest:   7
chunks after second ingest: 14
distinct triples:            7      duplicate triples: 7  (every one, twice)
distinct fingerprints among active chunks: 2
```

`write_record` never deletes the record's prior chunk rows. `INSERT OR REPLACE INTO chunk` replaces on the `chunk_id` primary key, and an edited record's fingerprint moves, so its new chunks get new ids and the old rows survive. `active_chunks()` joins `chunk` to `record_snapshot` on `record_id` alone, so both versions come back as active.

That is why the key here is the quadruple. It is also a defect in its own right, with a second and louder symptom: the old vectors are deleted from Chroma after parity has already passed (`ingest.py:231`), so the store ends up with 14 SQLite chunks and 7 vectors, and the semantic identity check at `query.py:401` then fails. Measured: `semantic returned: 7 for 14 asked`. Every query against a store with an updated record fails at retrieval.

It fails safe, which is why it is enrolled rather than folded in. It is invisible to the evaluation harness because every `evaluate` batch is a fresh build, and no test covers it.

### 5. Nothing else in the ranking path depends on build order

The lexical stage sorts documents into `chunk_id` order before scoring them (`query.py:912`), so a scorer with any order sensitivity would leave retrieval build dependent even after the tie key is fixed. Running `bm25_lexical_scorer` over the real corpus and over a shuffled permutation of it, then mapping scores back:

```
query-1: max abs score delta 0.000e+00, documents differing exactly: 0
query-5: max abs score delta 0.000e+00, documents differing exactly: 0
```

Bit for bit identical. The tie key is the last build dependent input to ranking, which is what makes the fix complete rather than partial.

## Options considered

### Option 1: break ties on the stable quadruple

Sort on `(record_id, fingerprint, value_path, ordinal)` at the three ranking sorts, through one shared helper. `chunk_id` and the store format are untouched.

**Pros**:
- Correct under both the current and the post feature 19 tie populations, because it reads no retrieval signal.
- Unique by the store's own `UNIQUE` constraint, so the sort is total and nothing falls back.
- Changes no stored data, no schema, no store format, and reverts by reverting one commit.
- Provable outright by a deterministic test, with no provider and no store.

**Cons**:
- Leaves chunk ids unstable across builds, so a citation still names a generation rather than content.
- The order between two tied candidates stays arbitrary, just stably arbitrary.
- Carries `fingerprint` in the key, which will read as redundant once the stale chunk defect is fixed.

### Option 2: content address the chunk id

Remove `generation_id` from the `chunk_id` payload, making the id itself a name for content. The three sorts need no change at all, and citations become stable across rebuilds.

**Pros**:
- Fixes the cause at its source rather than at three call sites; nothing downstream can reintroduce it.
- Also fixes citation instability, which experiment 0015 recorded as a real consequence.
- Leaves the ranking code untouched, so no ranking behaviour has to be re proven.

**Cons**:
- Blast radius reaches fingerprints, parity verification, and incremental reingest, all of which are shipped and test locked.
- Every stored chunk id moves once, so any existing store is invalidated.
- Buys the fix for the measured problem plus a fix for an unmeasured one, at a cost that is dominated by the second.
- Does not fix the stale chunk defect either, since an updated record's ids still move with its fingerprint.

### Option 3: a rank aware fusion tie break

Break fused ties on a retrieval signal before falling back to a stable key: prefer a chunk ranked by both retrievers over one ranked by a single retriever, then prefer the better single rank.

**Pros**:
- Would make the tie order mean something rather than being arbitrary.
- Addresses the fusion collision where it actually occurs.

**Cons**:
- Both criteria are provably inert on the current scoring function. There are zero collisions mixing a both ranked chunk with a single ranked one, so the first branch never fires; every single retriever collision is `(r, None)` against `(None, r)`, so the second cannot separate them either. Of 300 collision groups it changes the outcome of one, the three way `1/36` group, where `(12, 12)` has a better best single rank than `(3, 24)` and `(24, 3)`.
- It is a retrieval policy change wearing a determinism fix's clothes, and it would need a measurement behind it that nobody has taken.
- It is designed against a tie population that feature 19 replaces.

### Option 4: fix the stale chunk defect first, then use the triple

Delete a record's prior chunk rows on the update path, which makes `(record_id, value_path, ordinal)` unique, then break ties on that triple.

**Pros**:
- Fixes a real defect that can currently serve superseded text, and does it sooner.
- Yields a smaller, more obviously meaningful key.

**Cons**:
- Sequences the change with measured evidence behind it after the one without any.
- Two behaviour changes land together, so a moved fixture result cannot be attributed to either.
- The dependency it assumes is not real: the quadruple separates duplicated triples deterministically whether or not the defect is fixed.

## Rationale

Option 1, on three of the forces from Context.

**The scheduled retrieval change decides the shape.** The tie population today is dominated by 24 single retriever pairs. Under spec 0011 that class stops existing and a class that is impossible today appears with 51 groups. A key built from stable identity is the only one of the four options that needs no revision when that lands, which is why option 3 fails on a stronger ground than its branches being inert: even a version of it whose branches did fire would be tuned against a population about to be replaced.

**Blast radius decides between options 1 and 2.** Option 2 is the better fix for the cause and buys something option 1 does not, a citation that names content. But citation instability is causing no measured failure anywhere in the fixtures, while the ranking instability has a measured mechanism behind it and a batch of fluent wrong answers waiting for an explanation. Option 2 pays a store format cost for a fix to something nothing has yet shown is a problem, in a codebase where parity and incremental reingest are shipped and test locked. Option 1 changes no stored data and reverts by reverting one commit. Option 2 stays enrolled and undesigned rather than pre committed, which is the posture that keeps it available to be decided when something shows it is needed.

**Attribution decides the sequencing against option 4.** The stale chunk defect is the more alarming of the two findings, because retrieval can serve superseded text from a record whose source has since changed. It still goes second. It has no measured evidence behind it and could not have: every `evaluate` batch is a fresh build, so no run this project has ever taken could reach it. The tie break has experiment 0014's batch and experiment 0015's traced mechanism. Option 4's stated reason for going first, that it makes the triple unique, dissolves once the key is the quadruple, which separates duplicated triples deterministically either way. That leaves no dependency, and with no dependency the ordering is decided by evidence, and by this project's standing refusal to move two things in one measurement.

**On the engineer's own framing.** The topic proposed the triple `(record_id, value_path, ordinal)` as "already unique and on every candidate". It is unique on a fresh build and not in general, which the probe above measured directly. The correction is the reason `fingerprint` is in the key, and AC-4 exists so that a later reader who checks uniqueness after the stale chunk fix cannot remove it on the narrow ground of redundancy.

## References

**Project sources** (verifiable, in this repo):

1. [Experiment 0015](../../experiments/0015-the-store-is-deterministic-its-names-are-not.md), the two build comparison establishing that content is stable and chunk identity is not, and the three ranking sites that read it.
2. [Experiment 0014](../../experiments/0014-the-causes-pinned-and-the-store-split.md), the between batch spread that made the store a suspect, and the batch that answered with a fluent wrong answer.
3. `docs/specs/0008-reliable-multi-source-retrieval/`, AC-6 and AC-7 for the chunk id tie rule being superseded here, and AC-16 for the reader contract deliberately left alone.
4. `docs/specs/0011-field-aware-retrieval-ranking/`, AC-3 and AC-4 for the fusion eligibility and top 24 changes that reshape the tie population.
5. `docs/specs/0010-abstention-verification-reliability/`, AC-14 for the fixture exclusion rule, AC-23 for the trace writer that makes trace row order load bearing, and AC-24 for the denominator a deferred re measurement must use.
6. `docs/experiments/data/store-build-determinism.sh` and `compare-stores.py`, the instruments extended by AC-7.
7. `src/decision_memory/application/query.py`, the three ranking sorts, the three trace row orderings, the diversity walk, and the semantic identity check.
8. `src/decision_memory/application/chunking.py` and `src/decision_memory/infrastructure/sqlite_store.py`, the chunk id payload and the uniqueness constraint the quadruple rests on.
9. `AGENTS.md`, Clean Architecture layering, strict typing, and the Skateboard build approach.

**Practices and standards**:

- Measure before you optimise: every claim in this spec that a mechanism reaches the answer is backed by a run, and the one claim that could not be measured offline is enrolled as a follow up rather than asserted.
- Change one thing per measurement, which is why the stale chunk defect and the spec 0010 prune are both kept out of this change's runs.
- Reciprocal rank fusion, whose collision structure here follows from the shipped constant rather than from any property of the corpus.
