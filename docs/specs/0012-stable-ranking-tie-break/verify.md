# Verify: stable ranking tie break · spec 0012 · updated 2026-08-14

_Steps derived from spec 0012 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

## Commands

- [ ] `uv run pytest -q tests/test_stable_ranking.py` → 10 pass → AC-1 to AC-6
- [ ] `uv run pytest -q` → full unit suite green (656 at build time) → AC-9
- [ ] `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/` → clean → AC-9
- [ ] `uv run mypy src/decision_memory` → no issues in 49 files → AC-9
- [ ] `uv run pytest -q -k "layer or import"` → 3 pass, the application and domain layers still import no framework code → AC-9
- [ ] `grep -c "key=lambda row: row.chunk_id" src/decision_memory/application/query.py` → `0`, no trace row sort still reads a chunk id → AC-5
- [ ] `grep -cE "key=lambda (pair|item): \(-?(pair|item)\[1\], (pair\[0\]\.chunk_id|item\[0\])\)" src/decision_memory/application/query.py` → `0`, no ranking sort still breaks ties on a chunk id → AC-1
- [ ] `grep -c "key=lambda chunk: chunk.chunk_id" src/decision_memory/application/query.py` → `1`, and exactly one. That single remaining use is the document order fed to the BM25 scorer, which AC-6 deliberately leaves alone because the scorer is order independent. A `0` means someone changed it unnecessarily; a `2` means a chunk id ordering came back → AC-6
- [ ] `grep -c "stable_sort_key" src/decision_memory/application/query.py` → 7, one definition plus six call sites (three ranking sorts, three trace row sorts) → AC-1, AC-5

## The property, not just the tests

- [ ] Re run the five permutation tests against the old rule and confirm every one fails. Monkeypatch `query.stable_sort_key` to `lambda chunk: (chunk.chunk_id,)`, then call `test_lexical_ranking_is_unchanged_when_every_chunk_id_moves`, `test_fusion_order_is_unchanged_when_every_chunk_id_moves_today`, `test_fusion_order_is_unchanged_under_the_post_0011_tie_class`, `test_accepted_context_is_unchanged_when_every_chunk_id_moves`, and `test_trace_row_order_is_unchanged_when_every_chunk_id_moves`. All five must raise `AssertionError`. A test that passes under both rules guards nothing, and one of these did before it was rewritten → AC-3
- [ ] Confirm the post feature 19 tie fixture really ties: `_fusion_stage` with lexical 62 and semantic 62 on one chunk and semantic 1 on another must give both the same `fused_score` (`1/122 + 1/122 == 1/61`). A tie that is not a tie proves nothing → AC-3

## Value sourcing

One step per row of the spec's Value sourcing table, exercising the source of each value rather than only its presence.

- [ ] Semantic tie key comes from the descriptor already in `scored`: two chunks at an identical distance whose `value_path` differs must rank by `value_path`, and the store's returned order must not decide it (`test_semantic_stage_sorts_locally_by_distance_then_chunk_id` uses a deliberately scrambled store order) → AC-1
- [ ] Lexical tie key comes from the descriptor in `positive`: with a scorer returning equal scores, rank must follow the stable key, and the ranks must still be a contiguous 1..N → AC-1
- [ ] Fusion tie key comes from `accepted_by_id[chunk_id]`, not off the `scored` tuple, which carries only an id. Confirm `_fusion_stage` still takes `accepted_by_id` and that the tuple was not restructured to carry the descriptor → AC-1
- [ ] Trace row order comes from a lookup map, never from re sorting the chunk collection. Confirm ranks and dispositions are unaffected: in `_lexical_stage`, rows must be in stable key order while rank still follows score descending, and the fusion eligible `ranked` set must equal exactly the rows dispositioned `ranked` → AC-5, AC-9
- [ ] `fingerprint` is load bearing in the key: two chunks sharing `(record_id, value_path, ordinal)` and differing only in fingerprint must get different keys. This is the stale chunk case from scope feature 21 and it is why the key is a quadruple → AC-2, AC-4

## Live, costs provider calls

- [ ] `bash docs/experiments/data/store-build-determinism.sh` → the store levels report content identical with every chunk id moved, and the retrieval level reports `same accepted set 3/3, same accepted order 3/3`. **Expect agreement, not divergence**: experiment 0016 measured the same result before the fix, because the accept boundary sits above the band where ties occur. A divergence here would be a new finding, not a confirmation → AC-7
- [ ] Regenerate the gate fixture into a temporary directory and confirm spec 0012 is copied in and spec 0010 is not: `bash docs/experiments/data/build-self-corpus-fixture.sh /tmp/fixture-check && ls /tmp/fixture-check/docs/specs/` → AC-8

## Acceptance-criteria coverage

- AC-1 covered by the pytest and grep steps plus the three tie key value sourcing steps
- AC-2 covered by `test_stable_key_is_total_over_a_realistic_accepted_set` and the fingerprint step
- AC-3 covered by the four permutation tests, the old rule re run, and the tie fixture guard
- AC-4 covered by the fingerprint value sourcing step
- AC-5 covered by the trace row order steps and the three corrected `Trace` docstrings
- AC-6 covered by `test_lexical_scorer_is_independent_of_document_order`
- AC-7 covered by the live determinism script step
- AC-8 covered by the fixture regeneration step
- AC-9 covered by the suite, ruff, mypy, and layering steps, and by the confinement check that `schema_version`, `CANDIDATE_LIMIT`, `ACCEPTED_LIMIT`, `RRF_CONSTANT`, and `DIVERSITY_CAP` are untouched in the diff

## Still owed, deliberately not verified here

- The capability re baseline AC-9 defers, at the AC-24 denominator of four `--runs 3` batches, which must not share runs with the spec 0010 task 21 prune.
