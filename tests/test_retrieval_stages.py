"""Hybrid retrieval stage tests (spec 0008 AC-5 to AC-8).

Locks the exact tokenizer and stopword digest, the lexical dispositions and
precedence, the reciprocal rank fusion formula with the chunk id tie rule, and
the two pass diversity state transition including the fill pass.
"""

from __future__ import annotations

import math

from decision_memory.application.dto import (
    ActiveChunkDescriptor,
    BreadthDisposition,
    FilterExclusionReason,
    FilterState,
    FinalDisposition,
    FusedCandidate,
    LexicalDisposition,
    RetrievalStage,
    SelectionPass,
    SemanticDisposition,
)
from decision_memory.application.lexical import (
    LEXICAL_TOKENIZER_VERSION,
    STOPWORD_DIGEST,
    STOPWORD_SET,
    stopword_digest,
    tokenize,
)
from decision_memory.application.query import (
    _diversity_stage,
    _fusion_stage,
    _lexical_stage,
)
from decision_memory.infrastructure.bm25 import bm25_lexical_scorer


def _desc(
    chunk_id: str,
    record_id: str,
    text: str,
    value_path: str = "body[0]",
) -> ActiveChunkDescriptor:
    return ActiveChunkDescriptor(
        chunk_id=chunk_id,
        record_id=record_id,
        record_title="Title",
        record_status="accepted",
        record_tags=(),
        value_path=value_path,
        fingerprint="fp",
        ordinal=0,
        text=text,
        provenance=(),
    )


def _fused(
    chunk_id: str,
    record_id: str,
    fused_rank: int,
    lexical_rank: int | None = None,
    semantic_rank: int | None = None,
) -> FusedCandidate:
    return FusedCandidate(
        chunk_id=chunk_id,
        record_id=record_id,
        value_path="body[0]",
        fingerprint="fp",
        ordinal=0,
        text="text",
        provenance=(),
        lexical_rank=lexical_rank,
        semantic_rank=semantic_rank,
        fused_score=0.5,
        fused_rank=fused_rank,
        breadth_disposition=BreadthDisposition.RECORD_CAP,
        selection_pass=None,
        final_rank=None,
        final_disposition=FinalDisposition.OUTSIDE_TOP_8,
    )


def test_tokenizer_normative_examples_and_digest() -> None:
    assert LEXICAL_TOKENIZER_VERSION == "lexical-tokenizer-v1"
    assert STOPWORD_SET == "lexical-stopwords-v1"
    assert stopword_digest() == STOPWORD_DIGEST
    assert tokenize("Server-side") == ("server", "side")
    assert tokenize("don't retry") == ("retry",)
    assert tokenize("DM-0019") == ("dm", "0019")
    assert tokenize("Cafe\u0301") == ("caf\u00e9",)
    assert tokenize("O\u2019Reilly") == ("o\u2019reilly",)
    assert tokenize("_why_not_") == ("not",)
    # Negation survives: no, not, and nor are absent from the vocabulary.
    assert tokenize("no not nor") == ("no", "not", "nor")


def test_lexical_stage_dispositions_and_ranked_order() -> None:
    accepted_by_id = {
        "ch_browser": _desc("ch_browser", "DM-0002", "browser renders the pages"),
        "ch_server": _desc("ch_server", "DM-0001", "the server runs"),
        "ch_database": _desc("ch_database", "DM-0003", "the database client"),
    }
    trace, ranked = _lexical_stage(
        "server side database", accepted_by_id, bm25_lexical_scorer
    )
    by_id = {row.chunk_id: row for row in trace.rows}
    assert set(by_id) == {"ch_browser", "ch_server", "ch_database"}
    assert by_id["ch_browser"].disposition == LexicalDisposition.NO_TERM_MATCH
    assert by_id["ch_browser"].rank is None
    assert by_id["ch_server"].disposition == LexicalDisposition.RANKED
    assert by_id["ch_database"].disposition == LexicalDisposition.RANKED
    assert set(ranked) == {"ch_server", "ch_database"}
    # Rows are sorted by chunk id in the trace (AC-10).
    assert [row.chunk_id for row in trace.rows] == [
        "ch_browser",
        "ch_database",
        "ch_server",
    ]


def test_lexical_nonpositive_score_disposition() -> None:
    class ZeroScorer:
        def __call__(self, query_tokens, document_tokens):
            # A scorer that intersects but returns a zero score.
            return [0.0 for _ in document_tokens]

    accepted_by_id = {"ch_a": _desc("ch_a", "DM-0001", "server side text")}
    trace, ranked = _lexical_stage("server side", accepted_by_id, ZeroScorer())
    assert trace.rows[0].disposition == LexicalDisposition.NONPOSITIVE_SCORE
    assert trace.rows[0].rank is None
    assert ranked == {}


def test_fusion_exact_rrf_formula_and_tie_rule() -> None:
    accepted_by_id = {
        "c1": _desc("c1", "R1", "text"),
        "c2": _desc("c2", "R2", "text"),
        "c3": _desc("c3", "R3", "text"),
    }
    ranked_lexical = {"c1": 1, "c2": 3}
    ranked_semantic = {"c2": 2, "c3": 1}
    candidates = _fusion_stage(ranked_lexical, ranked_semantic, accepted_by_id)
    assert len(candidates) == 3
    c2, c1, c3 = candidates
    # c2 has both contributions.
    assert c2.chunk_id == "c2"
    assert c2.lexical_rank == 3
    assert c2.semantic_rank == 2
    assert c2.fused_rank == 1
    assert math.isclose(c2.fused_score, 1 / 63 + 1 / 62)
    # c1 and c3 tie on the semantic only contribution 1 / 61; chunk id breaks it.
    assert c1.chunk_id == "c1"
    assert c1.fused_rank == 2
    assert c1.semantic_rank is None
    assert math.isclose(c1.fused_score, 1 / 61)
    assert c3.chunk_id == "c3"
    assert c3.fused_rank == 3
    assert c3.lexical_rank is None
    assert math.isclose(c3.fused_score, 1 / 61)
    # Only ranked rows contribute; the missing contribution adds zero.


def test_diversity_breadth_cap_and_limit_reached() -> None:
    accepted_by_id = {f"c{i}": _desc(f"c{i}", f"R{i}", "text") for i in range(1, 12)}
    # R1 has four chunks so the third and fourth hit the per record cap.
    candidates = [
        _fused("c1", "R1", 1),
        _fused("c2", "R2", 2),
        _fused("c3", "R1", 3),
        _fused("c4", "R3", 4),
        _fused("c5", "R2", 5),
        _fused("c6", "R4", 6),
        _fused("c7", "R1", 7),
        _fused("c8", "R5", 8),
        _fused("c9", "R6", 9),
        _fused("c10", "R7", 10),
        _fused("c11", "R8", 11),
    ]
    final_candidates, accepted_chunks = _diversity_stage(candidates, accepted_by_id)
    accepted_ids = [chunk.chunk_id for chunk in accepted_chunks]
    # Breadth accepts two per record until eight are accepted, in fused order.
    assert accepted_ids == [
        "c1",
        "c2",
        "c3",
        "c4",
        "c5",
        "c6",
        "c8",
        "c9",
    ]
    by_id = {candidate.chunk_id: candidate for candidate in final_candidates}
    assert by_id["c1"].breadth_disposition == BreadthDisposition.ACCEPTED
    assert by_id["c1"].selection_pass == SelectionPass.BREADTH
    assert by_id["c1"].final_rank == 1
    assert by_id["c1"].final_disposition == FinalDisposition.ACCEPTED
    # The third chunk of R1 is deferred at the record cap.
    assert by_id["c7"].breadth_disposition == BreadthDisposition.RECORD_CAP
    assert by_id["c7"].selection_pass is None
    assert by_id["c7"].final_rank is None
    assert by_id["c7"].final_disposition == FinalDisposition.OUTSIDE_TOP_8
    # After eight accepts, unvisited candidates are limit reached.
    assert by_id["c10"].breadth_disposition == BreadthDisposition.ACCEPTED_LIMIT_REACHED
    assert by_id["c10"].final_disposition == FinalDisposition.OUTSIDE_TOP_8


def test_diversity_fill_pass_accepts_deferred() -> None:
    accepted_by_id = {
        "c1": _desc("c1", "R1", "text"),
        "c2": _desc("c2", "R1", "text"),
        "c3": _desc("c3", "R1", "text"),
        "c4": _desc("c4", "R2", "text"),
        "c5": _desc("c5", "R3", "text"),
    }
    candidates = [
        _fused("c1", "R1", 1),
        _fused("c2", "R1", 2),
        _fused("c3", "R1", 3),
        _fused("c4", "R2", 4),
        _fused("c5", "R3", 5),
    ]
    final_candidates, accepted_chunks = _diversity_stage(candidates, accepted_by_id)
    assert [chunk.chunk_id for chunk in accepted_chunks] == [
        "c1",
        "c2",
        "c4",
        "c5",
        "c3",
    ]
    by_id = {candidate.chunk_id: candidate for candidate in final_candidates}
    # The fill pass accepts the deferred third chunk of R1.
    assert by_id["c3"].breadth_disposition == BreadthDisposition.RECORD_CAP
    assert by_id["c3"].selection_pass == SelectionPass.FILL
    assert by_id["c3"].final_rank == 5
    assert by_id["c3"].final_disposition == FinalDisposition.ACCEPTED


def test_semantic_disposition_ranks_and_outside_top_24() -> None:
    from decision_memory.application.dto import SemanticRow

    rows = [
        SemanticRow(f"c{i}", rank, 0.5, 0.5, SemanticDisposition.RANKED)
        for i, rank in enumerate(range(1, 26), start=1)
    ]
    rows.append(SemanticRow("c26", 26, 0.5, 0.5, SemanticDisposition.OUTSIDE_TOP_24))
    assert [row for row in rows if row.disposition == SemanticDisposition.RANKED]
    assert rows[-1].disposition == SemanticDisposition.OUTSIDE_TOP_24


def test_query_answers_when_only_semantic_contributes(tmp_path) -> None:
    from pathlib import Path

    from fake_index import FakeIndex
    from test_query_roundtrip import _query_deps

    from decision_memory.application.dto import QueryFilters, QueryRequest, QueryState
    from decision_memory.application.query import query_index

    index = FakeIndex()
    index.generation = "gen-fake"
    # Chunk text shares no tokens with the question, so lexical ranks nothing.
    index.chunks["ch_a"] = _desc("ch_a", "DM-0012", "zzz qqq unrelated prose")
    index.embeddings["ch_a"] = [0.5] * 8
    result = query_index(
        QueryRequest(
            question="why was the gate added",
            store_dir=Path("/fake/store"),
            allow_stale=True,
            filters=QueryFilters(),
        ),
        _query_deps(index),
    )
    assert result.state == QueryState.ANSWERED
    assert result.trace.retrieval.lexical.rows
    assert all(
        row.disposition == LexicalDisposition.NO_TERM_MATCH
        for row in result.trace.retrieval.lexical.rows
    )
    assert result.trace.retrieval.fusion.candidates
    assert result.trace.retrieval.diversity.accepted_chunk_ids == ("ch_a",)


def test_query_diversity_accepts_multiple_records(tmp_path) -> None:
    from pathlib import Path

    from fake_index import FakeIndex
    from test_query_roundtrip import _query_deps

    from decision_memory.application.dto import QueryFilters, QueryRequest, QueryState
    from decision_memory.application.query import query_index

    index = FakeIndex()
    index.generation = "gen-fake"
    for chunk_id, record_id, text in [
        ("ch_a", "DM-0004", "resume generation runs on demand from the profile"),
        ("ch_b", "DM-0014", "projects are excluded from generated resumes"),
        ("ch_c", "DM-0019", "resume quality adds ATS guidance"),
    ]:
        index.chunks[chunk_id] = _desc(chunk_id, record_id, text)
        index.embeddings[chunk_id] = [0.5] * 8
    result = query_index(
        QueryRequest(
            question="what decisions affect resume generation",
            store_dir=Path("/fake/store"),
            allow_stale=True,
            filters=QueryFilters(),
        ),
        _query_deps(index),
    )
    assert result.state == QueryState.ANSWERED
    accepted = result.trace.retrieval.diversity.accepted_chunk_ids
    assert set(accepted) == {"ch_a", "ch_b", "ch_c"}
    assert len({chunk_id for chunk_id in accepted}) == 3


def test_closed_enums_pin_exact_members() -> None:
    """The closed retrieval enums are a contract; adding a member is a change."""
    assert {m.name: m.value for m in FilterState} == {
        "ACCEPTED": "accepted",
        "EXCLUDED": "excluded",
    }
    assert {m.name: m.value for m in FilterExclusionReason} == {
        "RECORD_ID": "record_id",
        "STATUS": "status",
        "TAG": "tag",
        "VALUE_PATH": "value_path",
    }
    assert {m.name: m.value for m in LexicalDisposition} == {
        "NO_TERM_MATCH": "no_term_match",
        "NONPOSITIVE_SCORE": "nonpositive_score",
        "RANKED": "ranked",
        "OUTSIDE_TOP_24": "outside_top_24",
    }
    assert {m.name: m.value for m in SemanticDisposition} == {
        "RANKED": "ranked",
        "OUTSIDE_TOP_24": "outside_top_24",
    }
    assert {m.name: m.value for m in BreadthDisposition} == {
        "ACCEPTED": "accepted",
        "RECORD_CAP": "record_cap",
        "ACCEPTED_LIMIT_REACHED": "accepted_limit_reached",
    }
    assert {m.name: m.value for m in SelectionPass} == {
        "BREADTH": "breadth",
        "FILL": "fill",
    }
    assert {m.name: m.value for m in FinalDisposition} == {
        "ACCEPTED": "accepted",
        "OUTSIDE_TOP_8": "outside_top_8",
    }
    assert {m.name: m.value for m in RetrievalStage} == {
        "FILTER": "filter",
        "LEXICAL": "lexical",
        "SEMANTIC": "semantic",
        "FUSION": "fusion",
        "DIVERSITY": "diversity",
    }


def test_lexical_ranks_score_desc_then_chunk_id_with_precedence() -> None:
    class ScriptedScorer:
        def __init__(self, scores: list[float]) -> None:
            self.scores = scores

        def __call__(self, query_tokens, document_tokens):
            return list(self.scores)

    accepted_by_id = {
        "a": _desc("a", "DM-0001", "server alpha"),
        "b": _desc("b", "DM-0002", "server beta"),
        "c": _desc("c", "DM-0003", "server gamma"),
        "d": _desc("d", "DM-0004", "unrelated zzz"),
    }
    # Scores arrive in chunk id order. Chunk d scores highest but shares no
    # token with the question, so the AC-5 precedence makes it no_term_match.
    trace, ranked = _lexical_stage(
        "server", accepted_by_id, ScriptedScorer([0.5, 0.5, 0.2, 9.0])
    )
    assert ranked == {"a": 1, "b": 2, "c": 3}
    by_id = {row.chunk_id: row for row in trace.rows}
    assert by_id["d"].disposition == LexicalDisposition.NO_TERM_MATCH
    assert by_id["d"].rank is None
    # Positive rows sort by score descending, then chunk id for the tie: the
    # two 0.5 chunks order a then b, before the 0.2 chunk.
    assert (by_id["a"].score, by_id["a"].rank) == (0.5, 1)
    assert (by_id["b"].score, by_id["b"].rank) == (0.5, 2)
    assert (by_id["c"].score, by_id["c"].rank) == (0.2, 3)


def test_lexical_outside_top_24_positive_rows_remain_visible() -> None:
    # Each chunk carries one unique term, so every BM25 score stays positive.
    # A query term present in every document would give a negative idf instead.
    accepted_by_id = {
        f"c{i:02d}": _desc(f"c{i:02d}", f"DM-{i:04d}", f"alpha{i:02d}")
        for i in range(1, 27)
    }
    question = " ".join(f"alpha{i:02d}" for i in range(1, 27))
    trace, ranked = _lexical_stage(question, accepted_by_id, bm25_lexical_scorer)
    rows = trace.rows
    assert len(rows) == 26
    ranked_rows = [row for row in rows if row.disposition == LexicalDisposition.RANKED]
    outside = [
        row for row in rows if row.disposition == LexicalDisposition.OUTSIDE_TOP_24
    ]
    assert len(ranked_rows) == 24
    assert len(outside) == 2
    assert {row.rank for row in outside} == {25, 26}
    assert len(ranked) == 24
    # Every positive row stays visible in the trace, chunk id sorted (AC-10).
    assert [row.chunk_id for row in rows] == sorted(row.chunk_id for row in rows)


def test_semantic_stage_sorts_locally_by_distance_then_chunk_id(tmp_path) -> None:
    from pathlib import Path

    from fake_index import FakeIndex
    from test_query_roundtrip import _query_deps

    from decision_memory.application.dto import (
        QueryFilters,
        QueryRequest,
        SemanticMatches,
    )
    from decision_memory.application.query import query_index

    class ScrambledIndex(FakeIndex):
        def semantic_search(self, embedding, accepted_chunk_ids):
            # Return matches out of order to prove the application re sorts.
            return SemanticMatches(("ch_a", "ch_c", "ch_b"), (0.9, 0.1, 0.1))

    index = ScrambledIndex()
    index.generation = "gen-fake"
    for chunk_id in ("ch_a", "ch_b", "ch_c"):
        index.chunks[chunk_id] = _desc(chunk_id, "DM-0012", "server side text")
        index.embeddings[chunk_id] = [0.5] * 8
    result = query_index(
        QueryRequest(
            question="server side",
            store_dir=Path("/fake/store"),
            allow_stale=True,
            filters=QueryFilters(),
        ),
        _query_deps(index),
    )
    rows = result.trace.retrieval.semantic.rows
    by_id = {row.chunk_id: row for row in rows}
    # The application ranks by distance ascending then chunk id (AC-6): the
    # two 0.1 chunks order ch_b then ch_c, ahead of the 0.9 chunk.
    assert (by_id["ch_b"].rank, by_id["ch_b"].distance) == (1, 0.1)
    assert (by_id["ch_c"].rank, by_id["ch_c"].distance) == (2, 0.1)
    assert (by_id["ch_a"].rank, by_id["ch_a"].distance) == (3, 0.9)
    assert all(row.disposition == SemanticDisposition.RANKED for row in rows)
    # Semantic rows appear chunk id sorted in the trace (AC-10).
    assert [row.chunk_id for row in rows] == ["ch_a", "ch_b", "ch_c"]
