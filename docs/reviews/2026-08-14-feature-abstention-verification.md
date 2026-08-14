# Review, feature/abstention-verification, 2026-08-14

**Reviewed by**: Claude Sonnet 5 (author on an earlier session, per commit history)
**Scope**: 18 files (9 source, 9 test), `db340af..HEAD` restricted to `src/` and `tests/` — spec 0010 build, tasks 5 through 17
**Verdict**: Approve

## Summary

This diff replaces per-sub-claim fragment output with whole-sentence output verified by sub claim decomposition (AC-1, AC-4), adds the two-directional AC-11 lexical validity test with a single retry, strips inline chunk-id markers at the generation boundary (AC-13), strengthens the self-corpus gate's oracle with co-located citations and abstention causes (AC-15), tells generation which part of the record each evidence chunk is via a `Field:` label (AC-18), and instruments the `not_additive` split (AC-19). I read every changed source file in full against spec 0010's Requirements/Decision/Feature design/Consequences, cross-checked the two AC-17/AC-18 review obligations by hand, and ran `ruff check`, `mypy src`, and the unit suite (596 passed, ruff and mypy clean). I found no blockers and no majors. The implementation is unusually faithful to an unusually precise spec: every pinned prompt string, regex, retry order, and disposition-ordering rule I checked matches verbatim, and the test suite (`tests/test_sub_claim_verification.py`, 1382 new lines) exercises the two AC-1 weld attacks, the AC-11 two-half test in both directions, the AC-13 marker strip and its regression on AC-5, the AC-15 covering-sentence-scope oracle, and the AC-19 first-cause category rule with the exact edge cases the spec calls out.

## AC-17 / AC-18 named-owner checks (spec 0010 explicitly asks `/check review` to make these)

- **AC-17**: the one schema property description in `src/decision_memory/infrastructure/openai_generation.py` (`_coverage_schema`'s `sentence_ids` property, lines 288–297) restates a rule enforced by `validate_coverage` (same file, lines 521–590): an uncovered row naming a sentence is rejected (`"uncovered row {facet_id} names sentences"`), and a covered row naming none is rejected (`"covered row {facet_id} names no sentence"`). Confirmed this is the only schema description in the module (locked by `test_only_the_ratified_description_exists_and_it_is_verbatim`) and that removing it changes no validator outcome (`test_descriptions_carry_no_deterministic_weight`).
- **AC-18**: `CHUNK_VALUE_PATHS` (lines 137–147) is the nine value paths — I diffed it against the nine `add()` calls in `src/decision_memory/application/chunking.py` (lines 302–356) and they match exactly, including the bracket-index convention. `FIELD_LABELS` covers all nine base keys with the spec-pinned label text verbatim.

## Strengths

- Every pinned prompt constant (`ANSWER_SYSTEM_PROMPT`, `DECOMPOSE_SYSTEM_PROMPT`, `COVERAGE_SYSTEM_PROMPT`, the `sentence_ids` schema description) and both AC-13 marker regexes match the spec's Provider contracts section character-for-character — I diffed them by hand.
- `application/verification.py` and `application/query.py` implement the AC-11 fixed check order (malformed → genuine empty → over_cap → duplicate → not_additive/incomplete, single retry only on the last two) exactly, including the subtlety that a stale `rejection` value from a prior retry attempt is correctly shadowed by the `if not sub_claim_texts` genuine-empty branch taking priority.
- Clean Architecture boundaries hold: no Typer/Pydantic/OpenAI/Chroma imports in `application/`, `battery_manifest.py` and `evaluation_runner.py` correctly sit in `infrastructure/`.
- The self-corpus gate's abstention-cause guard (`abstention_cause` in `application/evaluation.py`, lines 241–263) correctly refuses to read a cause from an empty coverage tuple rather than defaulting it to "no sentences emitted" — this is the exact vacuous-pass bug class AC-15 exists to close, and it's regression-locked (`test_abstention_cause_is_unreadable_from_an_empty_coverage_tuple`).
- `RejectedDecomposition.additive_failure` (AC-19) is a genuinely observational addition: `classify_decomposition` and `classify_decomposition_detail` share one implementation so the disposition and the category can never disagree, and `test_the_category_changes_no_decision_the_pipeline_makes` locks that the retry/drop/rejection behavior is unchanged.

## Test coverage

Thorough. `test_sub_claim_verification.py` covers both AC-1 attacks, draft-order preservation, citation narrowing on contained vs. entailed sub claims, the retry mechanics (valid retry used, second-invalid-response drop), one-drop-reason-per-sentence, provider failure propagation, the AC-11 two-half test in isolation (stem rules, additive scope, completeness presence-semantics, tie-break determinism, semantic-limits documentation), and the full AC-19 category matrix including the "both causes present, first one wins" case. `test_generation_validation.py`, `test_battery_manifest.py`, `test_evaluation.py`, and `test_self_corpus_fixture.py` (integration-marked, correctly, since they shell out to the committed fixture-generator script and the real adapter) round out AC-13, AC-14, AC-15, and AC-17/AC-18. `test_cli_evaluate.py` locks the `--battery` wiring: the corpus-argument conflict, the unsatisfiable-oracle usage error firing before any query, and that the JobPilot battery is never oracle-checked. I did not find a test that only covers the happy path or asserts nothing meaningful.

## Nits

- ⚪ `src/decision_memory/application/dto.py:627`, `VerificationTrace`'s docstring still reads `"(AC-15, spec 0010)"`, a stale citation left over from before spec 0010 had its own unrelated AC-15. This diff doesn't introduce it, and it's already tracked verbatim in spec 0010's Follow-up list as an open item — flagging only so it doesn't get missed once that item is picked up.
