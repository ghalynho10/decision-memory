# 0012. Stable ranking tie break

**Date**: 2026-08-14
**Status**: In Progress

## Summary

Retrieval breaks ties on `chunk_id`, and a chunk id is fresh on every build of the store even when the content behind it is byte identical. So two builds of one corpus can put a different set of chunks in front of the model, and the tool can answer the same question differently for no reason a reader could ever see. This decision replaces that tie break with a key made of values that do not move across builds: the record, the fingerprint, the value path, and the ordinal. Nothing about scoring or ranking changes, only what happens when two candidates score exactly the same.

## Requirements

**User stories**:
- As a user of the query command, I want the same corpus to give the same answer whichever build of the store it runs against, so that rebuilding the index is not a silent input to the result.
- As someone reading a trace from a failed run, I want to compare it against a trace from a passing run row by row, so that a run that deviates can be diagnosed instead of only noticed.

**Acceptance criteria** (the contract, each IDed and independently checkable):

- **AC-1**: The three ranking sorts break ties on the **stable quadruple** `(record_id, fingerprint, value_path, ordinal)`, through one named helper rather than three copies of the rule. `stable_sort_key(chunk: ActiveChunkDescriptor) -> tuple[str, str, str, int]` lives in `query.py` beside `CANDIDATE_LIMIT` and is the only definition of the key. The three call sites are `query.py:436` (semantic, distance ascending), `query.py:938` (lexical, score descending), and `query.py:979` (fusion, fused score descending), and the primary sort value at each is unchanged. **The fusion site is pinned separately because it does not have a chunk to hand.** Its `scored` list is `list[tuple[str, float, int | None, int | None]]` and `item[0]` is a chunk id string, not a descriptor, so the key is `stable_sort_key(accepted_by_id[item[0]])`; `accepted_by_id` is already a parameter of `_fusion_stage`. Restructuring that tuple to carry the descriptor is explicitly **not** in scope, because that is a wider change than this decision, and an implementer who reaches for it has left the spec.

- **AC-2**: The quadruple is **total** over the accepted chunk set, so the sort never falls back to anything and `chunk_id` leaves the ranking path entirely. This is not an assumption: the store's own schema enforces `UNIQUE (generation_id, record_id, active_fingerprint, value_path, ordinal)` (`sqlite_store.py:90`), and every chunk a single reader returns comes from one generation database, so the constraint reduces to the quadruple within any set `active_chunks()` can produce. A deterministic test asserts the totality directly, over a candidate set that includes two chunks sharing `(record_id, value_path, ordinal)` and differing only in fingerprint. That test is the point of the criterion rather than a formality, because the whole change is removing the last unstable key from ranking, and a key that silently ties would put it back.

- **AC-3**: **Permutation invariance, proven without a provider.** A deterministic test builds a fixed candidate set, ranks it, then re ranks the identical chunks with every `chunk_id` replaced by a different value, and asserts three things identical across the two runs: the semantic ranked order, the lexical ranked order, and the fused order, plus the accepted eight that the diversity walk returns. The test covers both tie populations, because they are not the same set: the pairs reachable today, where a chunk ranked by one retriever at rank `r` collides with a chunk ranked by the other at the same rank, and the pairs reachable once spec 0011 retires the top 24 boundary, where a chunk ranked by both collides with a chunk ranked only semantically. A test written against today's population alone would stop proving anything the moment feature 19 lands.

- **AC-4**: **`fingerprint` stays in the key permanently, and the reason is written where a later reader will find it.** It is load bearing today because a store can hold two chunks with the same `(record_id, value_path, ordinal)` (see AC-5), so the triple alone is not unique and would fall back to input order, which is `chunk_id` ordered, which is the defect. Once that is fixed the triple becomes unique and the fingerprint becomes redundant **for uniqueness only**. It stays anyway, and this criterion exists so that a later tidy up cannot simplify the quadruple back to a triple on the grounds that the triple is now enough: doing so would silently remove the guard that keeps the sort total if the duplication ever returns. The reason is stated in the helper's docstring, not only here, and the AC-2 test's name and docstring say what regression it is guarding.

- **AC-5**: The **trace rows are ordered by the stable key too**, at `query.py:328` (filter rows), `query.py:453` (semantic rows), and `query.py:951` (lexical rows). This is not cosmetic. Task 20 shipped `--traces DIR`, which writes a deviating run's full debug trace to disk for the stated purpose of comparing it against a run from another batch, and two traces from two builds currently show every row displaced, so the one comparison the instrument exists to support is the one it cannot do. **The row types are not widened.** `SemanticRow` carries `chunk_id`, `rank`, `distance`, `similarity`, `disposition`; `LexicalRow` carries `chunk_id`, `score`, `rank`, `disposition`; `FilterRow` carries `chunk_id`, `record_id`, `record_status`, `record_tags`, `value_path`, `state`, `exclusion_reasons`. None carries the full quadruple, so `sorted(rows, key=stable_sort_key)` is not available at any of them.

  **The rows are sorted in place through a descriptor lookup, and the chunk bearing collections are never re sorted.** This is pinned rather than described, because the obvious alternative is wrong and it is wrong silently:

  ```python
  rows.sort(key=lambda row: stable_sort_key(chunk_by_id[row.chunk_id]))
  ```

  `accepted_by_id` is already in scope at the semantic site (a local of `query_index`, built at `query.py:362`) and at the lexical site (a parameter of `_lexical_stage`); the filter site builds its map from `active`, the descriptor tuple it already holds. This is the same lookup shape AC-1 pins for the fusion site, so one pattern serves all four rather than two mechanisms serving three sites.

  **Re sorting the chunk bearing collection instead would change retrieval results, not only trace order.** `SemanticRow.rank` comes from `enumerate(scored, start=1)` (`query.py:450`) and `LexicalRow.rank` from `enumerate(positive, start=1)` (`query.py:940`), so those collections' order *is* the rank order. At the lexical site the damage runs further than the rank field: rank decides `RANKED` against `OUTSIDE_TOP_24` and populates the `ranked` dict that feeds fusion (`query.py:941` to `:949`). So a pre sort there would reassign ranks, change dispositions, and change which chunks reach fusion, which AC-9 forbids outright. Only the filter site would survive that approach, because `filter_descriptors` maps one to one and `accepted_ids` is a frozenset; that one safe case is exactly what makes the wrong mechanism look uniform.

  Every existing deterministic test that asserts trace row order is updated in the same task, not discovered failing in the suite afterwards. The three `Trace` docstrings that state the old rule (`dto.py:465`, `:472`, `:479`, each reading "sorted by chunk id") are corrected in the same task, since a docstring stating the superseded ordering is the next reader's source of truth.

- **AC-6**: **Nothing else in the ranking path depends on build order**, and the one real candidate is pinned by a test. The lexical stage feeds documents to the scorer in `chunk_id` order (`query.py:912`), which is fresh on every build, so a scorer with any order sensitivity would leave retrieval build dependent even with a stable tie key. Measured: `bm25_lexical_scorer` is exactly order independent, zero score difference on any of 378 documents under a shuffled corpus. A deterministic test pins that property, so a future scorer swap cannot reintroduce the dependency without failing. The document order itself is left as it is, since the property makes it irrelevant.

- **AC-7**: **Build independence is measured end to end, not only argued.** `docs/experiments/data/store-build-determinism.sh` already builds one corpus twice into persistent directories; it gains a retrieval comparison. For each of a small fixed question set it runs the shipped `query` command against build a and build b, extracts the accepted chunk set from the debug trace, keys it by the stable quadruple rather than by chunk id, and reports whether the two builds accepted the same chunks. **The keying is part of the criterion**, because experiment 0015 showed that keying this comparison by chunk id does not merely obscure the answer, it inverts it: the same data read one way says the stores are unrelated and read the other way says they are identical. **This proves something AC-3 holds constant.** AC-3 proves ranking is id independent given a candidate set; this proves two independently built stores produce the same candidate set in the first place, which is the half that includes the embedding vectors, the one retrieval input experiment 0015 lists in its own threats to validity as never compared. The script runs before the fix and after it, and both readings are recorded as a numbered experiment.

- **AC-8**: This spec is **deliberately inside the AC-14 self corpus fixture corpus**, and the membership rule is written down rather than left as a second undocumented entry beside the first. The rule: a spec is excluded from that fixture when its own prose contains the gate's queries, its expected records, or its expected states, because a spec that names the gate's answers becomes a source for them. `0010-abstention-verification-reliability` is excluded under that rule and not under any other, which is checkable in its text, and its own Follow-up already names holding it out as the fixture level fix. This spec contains none of that material, so it is copied in on the next regeneration and that is correct. **The rule constrains this spec's own prose**: it states the rule by reference and never by quotation, because a spec that quoted the gate's queries in order to explain why quoting them matters would put itself on the exclusion list.

- **AC-9**: **The change is confined to ordering.** No scoring, no rank assignment, no disposition, no threshold, and no accept limit changes. `schema_version` stays 2, no DTO gains or loses a field, no store format or stored data changes, and the whole change reverts by reverting one commit. **The live re baseline is deferred, not dropped**, and this criterion says so to keep it from being lost: changing tie order can move fixture results, so a capability figure read after this lands must be measured at the AC-24 denominator of four `--runs 3` batches, by whichever task next measures capability, and **not in the same runs as the spec 0010 task 21 prune**, because two behaviour changes in one measurement is the attribution error this project has refused throughout.

## Decision

**Chosen option**: Option 1: break ties on the stable quadruple, leaving `chunk_id` and the store format untouched.

The three ranking sorts stop reading `chunk_id` and read `(record_id, fingerprint, value_path, ordinal)` instead, through one shared helper. The trace row orderings follow, so traces from different builds can be compared row by row.

The key is chosen so that it does not depend on the shape of the tie population, and that is the load bearing property rather than a convenience. The ties reachable today and the ties reachable after feature 19 are different sets, so any policy that ranks tied candidates by a retrieval signal would be designed against a population that is about to be replaced. A key built from stable identity is correct under both, and under whatever the population becomes next.

## Feature design

**Data model sketch**: unchanged. No table, column, DTO field, or store format changes. Every value the key reads is already on `ActiveChunkDescriptor` (`dto.py:268`): `record_id`, `fingerprint`, `value_path`, `ordinal`.

**The key**:

```python
def stable_sort_key(chunk: ActiveChunkDescriptor) -> tuple[str, str, str, int]:
    """The build stable tie break for every ranking sort (AC-1).

    ``fingerprint`` stays in this key permanently (AC-4). It is what keeps the
    key total while a store can hold two chunks sharing the other three, and it
    stays after that is fixed so the guard cannot be tidied away.
    """
    return (chunk.record_id, chunk.fingerprint, chunk.value_path, chunk.ordinal)
```

**Call sites**:

| Site | Sort today | Sort after |
|---|---|---|
| `query.py:436` semantic | `(distance, chunk_id)` | `(distance, *stable_sort_key(chunk))` |
| `query.py:938` lexical | `(-score, chunk_id)` | `(-score, *stable_sort_key(chunk))` |
| `query.py:979` fusion | `(-fused, chunk_id)` | `(-fused, *stable_sort_key(accepted_by_id[chunk_id]))` |
| `query.py:328` filter trace rows | `row.chunk_id` | `stable_sort_key(chunk_by_id[row.chunk_id])`, map built from `active` |
| `query.py:453` semantic trace rows | `row.chunk_id` | `stable_sort_key(accepted_by_id[row.chunk_id])` |
| `query.py:951` lexical trace rows | `row.chunk_id` | `stable_sort_key(accepted_by_id[row.chunk_id])` |

**Explicitly unchanged**: `index_reader.active_chunks()` keeps returning a chunk id sorted tuple, which is spec 0008 AC-16's stated contract, and `cited_chunk_ids` (`query.py:571`) keeps its chunk id ordering. Neither decides anything, and amending a stated infrastructure contract for no decision change is a worse trade than the diffability is worth.

**Value sourcing**:

| Action | Value produced | Source |
|---|---|---|
| semantic ranking | tie break key | `ActiveChunkDescriptor` fields on the chunk already in `scored` |
| lexical ranking | tie break key | `ActiveChunkDescriptor` fields on the chunk already in `positive` |
| fusion ranking | tie break key | `accepted_by_id[chunk_id]`, already a parameter of `_fusion_stage` |
| trace row order | tie break key | the chunk bearing collection, sorted before the rows are built |
| AC-7 comparison | accepted chunk set per build | the shipped `query --debug` trace, keyed by the quadruple |

**Key invariants**:
- The quadruple is unique across any chunk set one `IndexReader` returns, enforced by `UNIQUE (generation_id, record_id, active_fingerprint, value_path, ordinal)` in the store schema, since one reader reads one generation.
- Ranking output depends on chunk content and scores only, never on chunk identity.
- Nothing outside ordering changes, so any behaviour difference after this lands is a defect in this change, not a consequence of it.

**Security model**: not applicable. Local CLI, no new data, no new surface, no change to what any caller may read.

**Configuration required**: none.

**Critical test scenarios**:
- Permutation: identical chunks, every chunk id replaced, identical semantic order, lexical order, fused order, and accepted eight, over both the current and the post feature 19 tie populations, verifies **AC-3**
- Totality: a candidate set holding two chunks that share `(record_id, value_path, ordinal)` and differ only in fingerprint ranks deterministically and never ties, verifies **AC-2**, **AC-4**
- Order independence: the lexical scorer returns identical scores under a shuffled document corpus, verifies **AC-6**
- Trace comparability: two candidate sets differing only in chunk ids produce trace rows in the same order, verifies **AC-5**
- Rank preservation: the trace reordering leaves every `rank`, every disposition, and the fusion `ranked` dict unchanged, which is the failure the pinned mechanism exists to avoid, verifies **AC-5**, **AC-9**
- Confinement: scores, ranks, dispositions, accept limits, and `schema_version` are unchanged by the edit, verifies **AC-9**

## Build plan

Ordered by the Skateboard approach, and by this project's standing rule that the instrument goes before the change it measures. This is the ninth application of that rule in this codebase, and it applies here for the usual reason: a comparison that has never been run against the current code cannot tell a fixed defect from an instrument that was never able to see it.

**All seven tasks shipped 2026-08-14** (656 unit tests passing, ruff, format, strict mypy, and the layering check green). The measurement is [experiment 0016](../../experiments/0016-the-tie-break-was-real-and-never-fired.md), and **it falsified task 1's stated expectation**: both builds accepted the same eight chunks in the same order, 3 of 3 questions, before the fix as well as after. The tie break is real in code and was not changing answers on this corpus, because reciprocal rank fusion puts every both ranked chunk above every single ranked one and the accept boundary sits inside the upper band. That expectation should not have been written into the task that ordered the measurement, and the correction lives in the experiment rather than being edited away here.

1. **Extend the determinism script and take the pre fix reading.** Add the retrieval comparison to `docs/experiments/data/store-build-determinism.sh`: run the shipped `query` command against both builds for a small fixed question set, extract each run's accepted chunk set from the debug trace, key it by the stable quadruple, and report agreement. Run it and record the result, which is expected to show the two builds accepting different chunks. Satisfies **AC-7** (first half).
2. **Add the helper and move the three ranking sorts onto it.** Write `stable_sort_key` with the AC-4 reason in its docstring, then change `query.py:436`, `:938`, and `:979`, using the pinned `accepted_by_id` lookup form at the fusion site. Add the permutation test and the totality test. Satisfies **AC-1**, **AC-2**, **AC-3**, **AC-4**.
3. **Re run the script and write the numbered experiment.** Record both readings, before and after, with the keying stated, and note what the comparison does and does not cover. Satisfies **AC-7** (second half).
4. **Order the trace rows by the stable key.** Sort the rows in place at all three sites through the pinned descriptor lookup, leaving `SemanticRow`, `LexicalRow`, and `FilterRow` untouched and never re sorting `scored` or `positive`. Correct the three `Trace` docstrings that still state the chunk id rule (`dto.py:465`, `:472`, `:479`), and update every existing test that asserts row order, both in this same task. Then assert what the mechanism exists to protect: ranks, dispositions, and the fusion `ranked` dict are byte identical before and after this task. Satisfies **AC-5**.
5. **Pin the scorer's order independence.** Add the deterministic test that a shuffled document corpus produces identical scores. Satisfies **AC-6**.
6. **Write the fixture membership rule.** State the rule and the reason `0010-abstention-verification-reliability` is excluded under it, in `build-self-corpus-fixture.sh` beside the `EXCLUDED` assignment and in spec 0010 AC-14, so the one existing entry stops being a bare fact. Change no exclusion. Satisfies **AC-8**.
7. **Lock it.** Full unit suite, ruff, format, strict mypy, and the layering check green, with the confinement test in place. Satisfies **AC-9**.

## Consequences

**Positive**:
- A store rebuild stops being a silent input to the answer. This is the fabrication direction: experiment 0014's batch D answered a query three times out of three with a fluent, well cited, wrong answer, and this closes the one path from a rebuild to a different evidence set that is entirely inside shipped code.
- Traces from different builds become comparable row by row, which is what makes the task 20 trace writer able to do the job it was built for.
- The fix is correct under feature 19's retirement of the top 24 boundary without revision, because the key does not read the tie population.

**Negative / tradeoffs**:
- Tie order changes, so fixture results can move. That cost is real and is not absorbed here: AC-9 defers a capability re measurement to the AC-24 denominator rather than folding one into this change.
- The sort key grows from one string to a four field tuple at three hot sites. The cost is negligible at 48 fused candidates and a few hundred accepted chunks, and it is stated only so nobody discovers it and wonders.
- `fingerprint` in the key will read as redundant to anyone who checks uniqueness after the stale chunk defect is fixed. AC-4 exists because that reader would otherwise be right on the narrow question and wrong on the decision.

**Neutral**:
- Citations remain unstable across rebuilds. A `ch_...` in an emitted answer still names a chunk in one generation rather than its content. Nothing in the fixtures compares a chunk id across builds, so this causes no measured failure, and content addressing the chunk id stays available as its own decision rather than being pre committed to here.
- The preference between a lexically ranked and a semantically ranked chunk at equal rank is now decided by a stable but arbitrary key. That was already true, only unstably, so this changes nothing about the retrieval policy question; it belongs to spec 0011 with a measurement behind it.
- This spec joins the self corpus gate's corpus on the next fixture regeneration, deliberately and under a stated rule.

## Follow-up

- [x] **Enrolled 2026-08-14 as scope feature 21, sequenced after this one.** Stale chunks survive an in place record update, and retrieval can serve superseded text. Measured while designing this spec: ingesting one record, editing its source, and reingesting into the same store leaves the store with both versions active, 14 chunks where 7 are current, every triple duplicated, two fingerprints live. `write_record` never deletes the record's prior chunk rows, and `active_chunks()` joins on `record_id` alone, so the superseded chunks stay retrievable and citable. That is closer to the fabrication direction than to housekeeping and deserves its own gate rather than a passing note. It has a second, loud symptom: the old vectors are deleted after parity, so SQLite and Chroma disagree, and the semantic identity check at `query.py:401` then fails every query against that store. This is invisible to the evaluation harness because every `evaluate` batch is a fresh build, and no test covers it. It is a separate decision with a different blast radius, the ingest write path rather than ranking, and it is **sequenced after this one**: the quadruple is correct whether or not it is fixed, so nothing here waits on it.
- [ ] Decide whether a lexically ranked chunk or a semantically ranked chunk should win at equal rank. This is a retrieval policy question, not a determinism one, and it needs a measurement behind it. It belongs to spec 0011. Worth knowing before it is designed: the collision population changes shape under that spec's own AC-3 and AC-4, and the class that dominates today does not survive them.
- [ ] Content address the chunk id, by removing `generation_id` from its payload, so a citation names content rather than a generation. Not taken here: the blast radius reaches fingerprints, parity, and incremental reingest, and citation instability is causing no measured failure. Enrolled rather than pre committed, so it is decided when something shows it is needed.
- [ ] `active_chunk_id_digest` (`index_store.py:483`) is a sha256 over the sorted chunk ids, so it moves on every build of identical content, for the same reason the chunk ids do. It is a store level fingerprint rather than a ranking input, so nothing in this decision depends on it, but anyone comparing two stores by that digest is comparing names.
- [ ] Spec 0008 AC-6 and AC-7 state the tie rule as `chunk_id`. They are superseded on that point by this spec and should be marked as such where they state it, which is an edit to spec 0008 rather than to this one.

## Rationale

Reasoning and options: see [rationale.md](rationale.md).
