# Review, multi-source-retrieval, 2026-08-11

**Reviewed by**: claude-opus-5 (author on deepseek-v4-flash)
**Scope**: 34 files (25 named in the request; the diff also touches `uv.lock` and sibling test files), branch vs `main`
**Verdict**: Changes requested

## Summary

Feature 10 replaces the single semantic retrieval step with a filter → BM25 → cosine → RRF → diversity pipeline, advances the query DTO and store format to `2`, and adds a typed `RetrievalFailure` with a partial trace. The implementation is unusually disciplined: the application layer stays free of `rank_bm25`, Chroma, Typer, and Pydantic; the tokenizer is pinned by a self-checking digest that I verified matches the normative `lexical-stopwords-v1.txt` exactly (171 words, digest `fe2b33…`); filter, lexical, fusion, and diversity logic all match the spec's stated rules when traced by hand. `ruff check`, `ruff format --check`, `mypy src`, and the 438 test unit suite all pass. The headline problem is test adequacy at one specific spot: the semantic top-24 boundary, which the spec names as a critical scenario and `verify.md` gate 3 claims to prove, is covered only by a tautological test that asserts hand-written enum values back at itself. Below that sit several smaller trace-fidelity and coverage gaps.

## Major

### 🟠 The semantic top-24 boundary is untested, and the test that claims to cover it is a tautology, `tests/test_retrieval_stages.py:240`

**Problem**: `test_semantic_disposition_ranks_and_outside_top_24` constructs 26 `SemanticRow` objects with the disposition hardcoded into the constructor call, then asserts those same hardcoded values back. It never calls `query_index` or any production code, so it would pass unchanged if `query.py:419-423` assigned `RANKED` to every row or inverted the comparison. No other test drives the semantic stage with more than three chunks: `test_semantic_stage_sorts_locally_by_distance_then_chunk_id` uses three, and `test_lexical_outside_top_24_positive_rows_remain_visible` (a genuinely good test) covers only the lexical side.

**Why it matters**: Spec 0008 AC-6 and critical test scenario 6 require proving that "more than 24 eligible rows tie at the boundary, local chunk id order selects the same 24 every time"; `verify.md` gate 3 item 7 restates it, and the scope entry records gate 3 as passing with cited evidence. The gate is not actually held by anything. This is the exact rule invariant 11 exists to protect ("Chroma never decides the semantic top 24 boundary"), and the AC-5 fusion boundary defect that moved the query 2 `DM-0004` rate from 3/5 to 0/5 during verification was in the sibling code path, so the boundary logic here is demonstrably the kind of thing that goes wrong silently.

**Suggested fix**: Replace the tautology with a test that runs `query_index` (or the semantic block) against a fake index returning ~26 accepted chunks at identical distances, and assert that ranks 1-24 are `RANKED`, 25-26 are `OUTSIDE_TOP_24`, that the ranked set is exactly the 24 lowest chunk ids, that only ranked rows appear in fusion, and that repeating the call with the ids returned in a different order yields the same 24.

## Minor

### 🟡 The embedding provider attempt never reaches the trace, so AC-9's provider clause is unmet, `src/decision_memory/application/query.py:357`

**Problem**: `QueryDependencies.embed` is typed `Callable[[Sequence[str]], list[list[float]]]` and is called as `deps.embed([question])` with no `attempts` list, even though the infrastructure `embed_texts` accepts one (`openai_embeddings.py:41`). Separately, `_abstained_result` hardcodes `providers=()` (`query.py:1188`). Consequently `attempts` is still empty at every retrieval-stage failure point, and the `PartialQueryTrace.providers` tuple built at `query.py:373` and rendered by `_print_partial_query_debug` is always empty in practice.

**Why it matters**: AC-9 states "Any semantic embedding attempt remains in provider trace." A retrieval abstention or semantic integrity failure is precisely the case where a reviewer wants to see whether the embedding call happened, how long it took, and whether it retried. The trace section prints an empty heading instead. (The structural gap predates this branch, but AC-9 newly makes it a stated requirement of this feature.)

**Suggested fix**: Widen the `embed` dependency to accept the attempts list, pass `attempts` through at the call site, and let `_abstained_result` carry `providers=tuple(attempts)` like `_failed_result`'s answered-path sibling does.

### 🟡 Store parity corruption is masked as an honest abstention when a filter matches nothing, `src/decision_memory/application/query.py:329`

**Problem**: The empty-filter abstention at `query.py:309` returns before both the question token-limit check (`:317`) and the Chroma parity check (`:329`). A store with missing or mismatched vectors, queried with a filter that happens to accept no chunk, returns `not enough evidence here` and exit `0` rather than the `store.parity` failure and exit `1`. An over-limit question with a nonmatching filter likewise returns exit `0` instead of the usage exit `2`.

**Why it matters**: "Not enough evidence here" is the tool's honesty contract; it should never be the answer given by a corrupt store. Neither check calls a provider, so running both before the filter gate still satisfies AC-4's "without embedding the question or calling any generation provider". (The empty-index path had the same ordering before this branch, so this extends an existing pattern rather than introducing it, but the filter path makes the masked-corruption case much more reachable.)

**Suggested fix**: Move the token-limit and parity checks above the `active_chunks()`/filter block, or at minimum above the `if not accepted_ids` early return.

### 🟡 The fusion section of a diversity-failure partial trace carries invented diversity fields, `src/decision_memory/application/query.py:797`

**Problem**: `_fusion_stage` stamps every candidate with placeholder `breadth_disposition=RECORD_CAP`, `selection_pass=None`, `final_rank=None`, `final_disposition=OUTSIDE_TOP_8`, intending the diversity stage to overwrite them. When diversity raises, the handler at `query.py:482` puts those unmodified placeholders into the partial trace's `FusionTrace`.

**Why it matters**: AC-9 and the `PartialQueryTrace` docstring both promise that "the failing section and every later section are absent rather than synthesized as empty". A reader debugging a diversity failure sees every candidate labelled `breadth=record_cap final=outside_top_8`, which is a plausible-looking lie about a stage that never ran, on exactly the surface that exists to localize the failure.

**Suggested fix**: Have `_fusion_stage` return a pre-diversity value (a plain tuple of `(chunk_id, score, ranks)` or a `FusedCandidate` variant with the diversity fields optional) and only materialize `FusedCandidate` after diversity, so a diversity failure cannot emit fabricated dispositions.

### 🟡 The live query 1 oracle was loosened, which spec Follow-up 5 explicitly forbids, `tests/test_query_live.py:143`

**Problem**: `test_query_one_against_real_jobpilot` dropped `assert "two agent routes" in joined` and replaced it with `assert all(sentence.citation_ids for sentence in result.sentences)`, which passes for any answer whose sentences carry any citation at all.

**Why it matters**: Follow-up 5 in `index.md` says to reground this test on "the cited record and its structured content instead of generated prose" and ends "reground it, do not loosen it." The follow-up box is still unticked, so the test was weakened without the replacement assertion the follow-up asks for. The test now cannot distinguish a correct answer about the rejected alternative from any cited answer about anything in DM-0012.

**Suggested fix**: Either restore the prose assertion until Follow-up 5 is done, or complete the regrounding now: assert against the structured record content (for example that the citation resolves to the DM-0012 `decision.alternatives[*]` chunk), not against citation-id non-emptiness.

### 🟡 AC-16's architecture import check has no test, tests/

**Problem**: Critical test scenario 10 requires "an import check proves application has no third party retrieval import." Nothing in `tests/` does this; I confirmed the property holds today by grep, but nothing keeps it holding.

**Why it matters**: The single most load-bearing convention in this project's `AGENTS.md` (no framework code in application) is currently enforced by discipline alone, and the temptation to `from rank_bm25 import BM25Okapi` inside `lexical.py` is one refactor away.

**Suggested fix**: Add a test that walks `src/decision_memory/application` and `src/decision_memory/domain` with `ast.parse` and asserts no import of `rank_bm25`, `chromadb`, `openai`, `typer`, or `pydantic`.

### 🟡 Schema version `2` is hardcoded three times and `QUERY_SCHEMA_VERSION` is dead, `src/decision_memory/application/dto.py:184`

**Problem**: `QUERY_SCHEMA_VERSION = 2` is defined and exported in `__all__` but referenced nowhere; `query.py:685`, `:1197`, and `:1229` each write the literal `schema_version=2`. No test asserts `result.schema_version == 2` either, despite AC-10 and `verify.md` gate 6 item 1.

**Why it matters**: A future schema bump has three literals to find and a constant that looks authoritative but is inert, and no test would catch missing one of the three.

**Suggested fix**: Use the constant at all three sites and assert it in one query test.

## Nits

- ⚪ `src/decision_memory/application/filters.py:37`, `_INDEX_RE = r"[0-9]|[1-9][0-9]*"` is equivalent to the spec's `0|[1-9][0-9]*` under `fullmatch` (I checked `01`, `0`, `10`), but writing the spec's literal grammar removes the need for that check.
- ⚪ `src/decision_memory/application/filters.py:86`, the final `return chunk_path == f"{prefix}[{index_text}]"` is unreachable-false: the preceding prefix, bracket, and index checks already guarantee it.
- ⚪ `src/decision_memory/application/query.py:94`, `BM25_PARAMETERS = "k1=1.5,b=0.75"` omits `BM25Okapi`'s `epsilon=0.25`, which does affect scores; the settings trace claims to record "actual BM25 parameters".
- ⚪ `src/decision_memory/infrastructure/index_store.py:112`, `STORE_FORMAT_VERSION` is imported inside `open_generation`; `application.store_format` has no imports, so no cycle justifies the function-local import.
- ⚪ `src/decision_memory/cli.py`, `_print_partial_query_debug` omits the `Settings` section that `_print_query_debug` prints, so the two debug renderers disagree on section list.
- ⚪ `src/decision_memory/application/lexical.py:25`, the vocabulary is duplicated from the normative `docs/specs/0008-.../lexical-stopwords-v1.txt`. The import-time digest guard protects the module, but nothing detects drift in the file; a test hashing the file against `STOPWORD_DIGEST` would close that.
- ⚪ `tests/test_retrieval_stages.py:315`, `assert len({chunk_id for chunk_id in accepted}) == 3` is redundant after the `set(accepted) == {...}` assertion on the line above.
- ⚪ The scorer cardinality guard (`query.py:715-716`, "lexical scorer returned a wrong count") and the `FUSION`/`DIVERSITY` terminal stages are never reached through `query_index` in any test, though `verify.md` gate 5 item 7 lists the cardinality mismatch.

## Strengths

- The layer boundary genuinely holds: `rank_bm25` appears only in `infrastructure/bm25.py` and in docstrings, and the `LexicalScorer` protocol keeps the application pure while still letting tests inject scripted scorers. This is the cleanest part of the change.
- `stopword_digest()` is verified against the pinned constant at import time, so a vocabulary edit fails loudly rather than silently changing retrieval. I independently confirmed the module vocabulary and the normative spec file both hash to `fe2b3373…` with 171 words.
- `test_lexical_ranks_score_desc_then_chunk_id_with_precedence` and `test_lexical_outside_top_24_positive_rows_remain_visible` are exactly right: they pin the AC-5 precedence including the case where the highest raw score loses to `no_term_match`, and the second builds a corpus where BM25 idf stays positive on purpose, with a comment explaining why.
- `test_filters.py` covers normalization, case sensitivity asymmetry, every usage-error class, the `[01]`/descendant/partial-path selector rejections, the fixed reason ordering, OR-within/AND-across, and the zero-provider abstention with an `_raise_if_called` embedder that proves no provider ran.
- `verify.md` and `docs/scope/scope.md` record the live gates as *run and failed* with per-run counts and an explicit "this feature does not declare AC-15 passed", including the observation that the `DM-0004` rate moved 5/5 → 3/5 → 0/5 across samples. Reporting a smoke gate against yourself like that is the opposite of the usual failure mode.
- The `RetrievalFailure` boundary is well covered end to end: scorer explosion, out-of-range distance, NaN distance, duplicate ids, mismatched id set, and misaligned distances each assert the terminal stage *and* which partial sections survived.

## Test coverage

438 unit tests pass; 16 integration tests are deselected by the default marker filter. `ruff check`, `ruff format --check`, and `mypy src` are clean. Filter behavior (AC-1 to AC-4), lexical dispositions and the top-24 boundary, RRF arithmetic with the chunk-id tie rule, the two-pass diversity transition including a fill accept, store format 1 refusal, and every semantic integrity failure mode are all covered by tests that exercise real code.

The gaps: the semantic top-24 boundary has only a tautological test (Major above); there is no architecture import check; `schema_version == 2` is never asserted; the scorer cardinality guard and the `FUSION`/`DIVERSITY` terminal stages are unreached through `query_index`; and the live query 1 assertion was weakened rather than regrounded. The live AC-13/14/15 gates are correctly written as a real, currently-failing integration test rather than being softened to pass, which is the right call.
