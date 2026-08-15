# Experiment 0015: the store is deterministic, its names are not

**Date**: 2026-08-14
**Status**: Complete
**Follows**: [Experiment 0014](0014-the-causes-pinned-and-the-store-split.md)
**Result**: Two independent builds of the JobPilot corpus produce **byte identical content and no shared chunk id at all**. Same 378 chunks under the stable triple `(record_id, value_path, ordinal)`, zero text differences, zero fingerprint differences, and **378 of 378 chunk ids different**. `adapt` and `ingest` are deterministic; `chunk_id` is not, by construction, because it hashes the generation id. This matters because **retrieval breaks ties on `chunk_id`** in three places, so which chunk reaches the context on a tie is decided by a value that is fresh on every build. That is a mechanism connecting a store rebuild to a different answer, which is the shape experiment 0014's batch D showed.

## Why this run happened

Experiment 0014 found batch D holding every AC-2 miss, answering `query-5-uploaded-files` 3 of 3 with a fluent, well cited, wrong answer, and putting `assertion-rationale-summary` at 0 of 3, while batches A, B, and C agreed with each other. A batch is one `evaluate` invocation, which is one adapt plus one ingest, so the store is held constant within a batch and varied between them.

That experiment could not check the store. `evaluate` builds into temporary directories removed on exit, and its traces record what the pipeline did with a store, never how the store was built. The deferred item's first named step is to compare chunk identity and ordering across two builds of the same corpus, and nothing had run it.

The fabrication direction is why this went ahead of task 21. Task 21 addresses over abstention, which fails safe. Batch D is the fabrication direction, which does not.

## Method

`docs/experiments/data/store-build-determinism.sh` builds the same corpus twice into persistent directories, with explicit `--output` and `--store` so nothing is temporary, then compares. `docs/experiments/data/compare-stores.py` does the comparison in two keyings, and the pair is the point:

- **by `chunk_id`**, which is how the rest of the system refers to a chunk
- **by `(record_id, value_path, ordinal)`**, the stable triple, which shows whether the content behind those names moved

Both read through the shipped `SqliteChromaIndexReader.active_chunks`, not off the SQLite or Chroma files, so the comparison sees what retrieval sees.

Runtime: about 25 seconds per build. Kept in `docs/experiments/data/store-build-determinism/`.

## Result

```text
--- records ---
records: identical apart from manifest generated_at

--- chunks ---
chunk count: a=378 b=378
chunk ids DIFFER: 378 only in a, 378 only in b

--- chunks by (record_id, value_path, ordinal) ---
key count: a=378 b=378 | same key set: True
shared keys:        378
text differs:       0
fingerprint differs:0
chunk_id differs:   378
verdict: content identical, every chunk id moved
```

The adapted records differ only in `manifest.json`'s `generated_at` wall clock stamp. Under the stable triple every chunk matches on text and on fingerprint. Under `chunk_id` the two builds share nothing.

**Read the first keying alone and it says the stores are unrelated. Read the second alone and it says they are identical.** Both are true, and neither is the finding without the other.

### Why the ids move

`chunking.py`'s `chunk_id` hashes a canonical payload of `["chunk-v1", generation_id, record_id, fingerprint, value_path, ordinal]`. `generation_id` is fresh per build. So a chunk id is deterministic **within** a generation and unrelated **across** generations, by design, and the id is a name for a chunk in a generation rather than a name for its content.

Example, from `DM-0001 body[0] ordinal 0`, identical text and identical fingerprint `ed66dcdfe33e6f9a...`:

| Build | chunk id |
|---|---|
| a | `ch_730843f76770c9c98e39f1f86ccb72df3bd6992fe4c98c088a5f6eb3bb900dd0` |
| b | `ch_7e6453c031cd33c823857f4ae5f788b8d137486f89b892c72cae8d0c478228aa` |

**Reproduced on a second, independent pair of builds.** The first pair, run before the comparison script was fixed, gave the same three figures (378 shared keys, 0 text differences, 378 ids moved) and different ids again, which is itself the finding: the ids are fresh per build rather than fresh per code change.

### Why that reaches the answer

`query.py` breaks ties on `chunk_id` in three ranking paths:

| Line | Sort |
|---|---|
| 436 | semantic: distance ascending, then `chunk_id` |
| 938 | lexical: score descending, then `chunk_id` |
| 979 | fusion: fused score descending, then `chunk_id` |

A tie broken by `chunk_id` is a tie broken by a hash that is fresh on every build. Ties are not exotic on the lexical side, where many chunks share a BM25 score, and spec 0011's second finding is that only the top 24 of each retriever contribute, so a tie **at that boundary** decides whether a chunk reaches the context at all rather than merely where it sits in a list.

So: same corpus, same text, different names, different tie order, different evidence set, different generated answer. Every link is in shipped code and none of it needs a provider to be nondeterministic.

**This is a mechanism, not yet an attribution.** Nothing here measures how often a tie occurs at the cliff on this corpus, and nothing here replays batch D. What it establishes is that a store rebuild can change retrieval output through a deterministic path, which experiment 0014 could only hypothesise.

## What this changes

- **The store nondeterminism item is no longer a hypothesis about noise.** Content is stable, identity is not, and identity is load bearing in ranking. The item should leave the Deferred list.
- **`adapt` and `ingest` are cleared.** Two builds agree on every record, every chunk, every text, and every fingerprint. Whatever moved between experiment 0014's batches, it was not the content.
- **Between batch spread has a candidate that is not provider variance.** Experiment 0014 named provider session drift as a threat it could not separate from the store. This gives the store half of that a concrete route.
- **A citation is not stable across a rebuild.** `ch_...` in an emitted answer names a chunk in one generation. Anything that stores, quotes, or compares a chunk id across rebuilds is comparing names, not content. Nothing in the fixtures does this today; it is recorded because the ids look content addressed and are not.

## Threats to validity

- **One corpus, two builds.** 378 chunks, one adapt and ingest each. Determinism of content is shown on this pair, not proven in general.
- **A mechanism is not the cause.** The tie break path is real and reachable, but no measurement here shows a tie at the top 24 boundary on this corpus, and batch D was not replayed against a kept store. The stores from experiment 0014 are gone.
- **The embedding half was not compared.** Text and fingerprints match; the vectors behind them were not read, and an embedding provider returning slightly different values for identical input would show up as retrieval drift without any content difference.
- **`generation_id` in `chunk_id` may be deliberate.** It gives every generation its own id space, which is plausibly what the incremental reingest and parity checks want. This experiment says what it costs in ranking, not that the payload is wrong.

## Follow-up

- [ ] **Break ties on a stable key (a decision, owed to `/architect`).** The three sorts in `query.py` want a key that is the same across builds; `(record_id, value_path, ordinal)` is available on every candidate and already unique. This is the small fix. Removing `generation_id` from the `chunk_id` payload is the large one, and it reaches fingerprints, parity, and incremental reingest, so it is a separate decision rather than the same one.
- [ ] **Measure tie frequency at the fusion cliff** on this corpus, which is what would turn the mechanism into an attribution. It needs no provider call: the lexical and fused scores are computable offline from a built store.
- [ ] **Replay batch D.** With `--store` kept, an `evaluate` run that reproduces the query 5 fabrication can be re run against the same store to see whether the answer is stable given the store, which separates the store effect from provider variance directly.
- [ ] **Compare the vectors**, the one input to retrieval this experiment did not read.
