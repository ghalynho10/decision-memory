"""Deterministic sub claim verification tests (spec 0010).

These lock the sub claim verification stage against the real pipeline with
deterministic fakes: a controlled accepted context, crafted draft sentences,
and scripted decomposition and entailment callables. The whole pipeline runs,
so the coverage decision and the citation allocation are real; only the
provider calls are faked. The live gates (AC-2, AC-3, AC-9) stay in the
integration suite.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fake_index import FakeIndex
from test_query_roundtrip import _query_deps

from decision_memory.application.canonical import SourceReference
from decision_memory.application.dto import (
    ActiveChunkDescriptor,
    CoverageRow,
    DraftSentence,
    QueryFilters,
    QueryRequest,
    QueryResult,
    QueryState,
    RejectedDecomposition,
)
from decision_memory.application.query import query_index
from decision_memory.application.verification import (
    MAX_SUB_CLAIMS,
    decompose_disposition,
    decomposition_is_near_subset,
)
from decision_memory.infrastructure.openai_generation import (
    GenerationError,
    validate_decompose,
)


def _chunk(chunk_id: str, text: str) -> ActiveChunkDescriptor:
    return ActiveChunkDescriptor(
        chunk_id=chunk_id,
        record_id="DM-0012",
        record_title="Title",
        record_status="accepted",
        record_tags=(),
        value_path="body[0]",
        fingerprint="fp",
        ordinal=0,
        text=text,
        provenance=(SourceReference("docs/specs/0012-portfolio/index.md", "Decision"),),
    )


def _cover_all(question, facets, sentences, attempts=None) -> tuple[CoverageRow, ...]:
    """Coverage that only covers when there is a kept unit to cover it."""
    sentence_ids = tuple(sentence.sentence_id for sentence in sentences)
    covered = bool(sentence_ids)
    label = "covered" if covered else "no sentences"
    return tuple(
        CoverageRow(facet.facet_id, covered, label, sentence_ids) for facet in facets
    )


def _no_call(*_args, **_kwargs):
    raise AssertionError("must not be called")


def _run(
    chunks: dict[str, str],
    sentences: tuple[DraftSentence, ...],
    *,
    decompose,
    entail,
    coverage=_cover_all,
    question: str = "merger engineer",
) -> QueryResult:
    """Run the full pipeline over a controlled accepted context."""
    index = FakeIndex()
    index.generation = "gen-fake"
    for chunk_id, text in chunks.items():
        index.chunks[chunk_id] = _chunk(chunk_id, text)
        index.embeddings[chunk_id] = [0.5] * 8
    result = query_index(
        QueryRequest(
            question=question,
            store_dir=Path("/fake/store"),
            allow_stale=True,
            filters=QueryFilters(),
        ),
        _query_deps(
            index,
            generate_answer=lambda *_args, **_kwargs: sentences,
            decompose=decompose,
            entail=entail,
            coverage=coverage,
        ),
    )
    accepted = set(result.trace.retrieval.diversity.accepted_chunk_ids)
    if result.state != QueryState.FAILED:
        seeded = set(chunks)
        not_accepted = seeded - accepted
        assert seeded <= accepted, f"seeded chunks not all accepted: {not_accepted}"
    return result


def _cited_chunk_ids(result: QueryResult, sentence) -> tuple[str, ...]:
    by_id = {citation.citation_id: citation for citation in result.citations}
    return tuple(
        sorted(
            by_id[citation_id].chunk_id
            for citation_id in sentence.citation_ids
            if citation_id in by_id
        )
    )


# ---------------------------------------------------------------------------
# AC-1 and AC-4: a fused sentence is split, the borrowed clause is kept and
# narrowed, the invented decision is dropped, and coverage decides.
# ---------------------------------------------------------------------------


def test_fused_clause_is_split_and_invented_decision_dropped() -> None:
    """A weld of a verbatim clause and an invented decision (AC-1, AC-4)."""
    chunks = {
        "ch_a": "The board approved the merger on Tuesday.",
        "ch_b": "The board hired a chief engineer in March.",
    }
    draft = (
        DraftSentence(
            "S1",
            "The board approved the merger on Tuesday, and the board "
            "accepted a bribe to rush it.",
            ("ch_a", "ch_b"),
        ),
    )
    result = _run(
        chunks,
        draft,
        decompose=lambda s, c, a=None: (
            "The board approved the merger on Tuesday.",
            "The board accepted a bribe to rush it.",
        ),
        entail=lambda s, c, a=None: (False, "not supported"),
    )
    assert result.state == QueryState.ANSWERED
    assert result.schema_version == 2
    # The invented sub claim never reaches the answer.
    assert [sentence.text for sentence in result.sentences] == [
        "The board approved the merger on Tuesday."
    ]
    assert not any("bribe" in sentence.text for sentence in result.sentences)
    # The kept fragment's citation narrows to the chunk that contains it.
    assert _cited_chunk_ids(result, result.sentences[0]) == ("ch_a",)
    # The trace records the split and both verdicts.
    rows = result.trace.verification.decomposed
    assert [(row.sub_claim_id, row.kept) for row in rows] == [
        ("S1.1", True),
        ("S1.2", False),
    ]
    assert rows[0].contained is True
    assert rows[0].entailment == "skipped"
    assert rows[0].citations == ("ch_a",)
    assert rows[1].contained is False
    assert rows[1].entailment == "unsupported"
    assert rows[1].reason == "not supported"


def test_omission_attack_never_restores_the_parent() -> None:
    """A decomposition that omits the fabricated clause entirely still emits
    only the returned sub claims; the parent, which would hide the omission,
    is never restored (AC-1, AC-4)."""
    chunks = {
        "ch_a": "The board approved the merger on Tuesday.",
        "ch_b": "The board hired a chief engineer in March.",
    }
    original = (
        "The board approved the merger on Tuesday, and the board accepted "
        "a bribe to rush it."
    )
    draft = (DraftSentence("S1", original, ("ch_a", "ch_b")),)
    result = _run(
        chunks,
        draft,
        # The decomposition drops the fabricated clause entirely and returns
        # only the grounded clause, which is fully supported on its own.
        decompose=lambda s, c, a=None: ("The board approved the merger on Tuesday.",),
        entail=lambda s, c, a=None: (True, "direct support"),
    )
    assert result.state == QueryState.ANSWERED
    # Only the returned fragment is emitted; the parent sentence text never
    # reappears in the answer, so the omitted fabrication stays dropped.
    assert [sentence.text for sentence in result.sentences] == [
        "The board approved the merger on Tuesday."
    ]
    assert not any("bribe" in sentence.text for sentence in result.sentences)
    assert result.sentences[0].sentence_id == "S1.1"


def test_all_kept_sub_claims_emit_fragments_not_the_parent() -> None:
    """Two sub claims verbatim in different chunks each cite only its own
    chunk, and even when every sub claim is kept the parent sentence is never
    re emitted: the fragments become the answer sentences (AC-1, AC-4)."""
    chunks = {
        "ch_a": "The board approved the merger on Tuesday.",
        "ch_b": "The board hired a chief engineer in March.",
    }
    original = (
        "The board approved the merger on Tuesday, and the board hired a "
        "chief engineer in March."
    )
    draft = (DraftSentence("S1", original, ("ch_a", "ch_b")),)
    result = _run(
        chunks,
        draft,
        decompose=lambda s, c, a=None: (
            "The board approved the merger on Tuesday.",
            "The board hired a chief engineer in March.",
        ),
        entail=_no_call,
    )
    assert result.state == QueryState.ANSWERED
    # Every sub claim kept, but the parent is never restored: the fragments
    # are emitted as answer sentences with sub claim ids (AC-4).
    assert [(sentence.sentence_id, sentence.text) for sentence in result.sentences] == [
        ("S1.1", "The board approved the merger on Tuesday."),
        ("S1.2", "The board hired a chief engineer in March."),
    ]
    rows = result.trace.verification.decomposed
    assert [(row.sub_claim_id, row.citations) for row in rows] == [
        ("S1.1", ("ch_a",)),
        ("S1.2", ("ch_b",)),
    ]
    assert all(row.contained for row in rows)
    assert all(row.entailment == "skipped" for row in rows)


def test_entailment_grounded_sub_claim_keeps_full_cited_set() -> None:
    """An entailment grounded sub claim keeps the parent's full available
    cited set, since entailment names no supporting chunk; the missing id
    boundary is locked by ``test_partial_missing_verifies_against_present_
    subset`` (AC-4, AC-8)."""
    chunks = {
        "ch_a": "The board approved the merger on Tuesday.",
        "ch_b": "The board hired a chief engineer in March.",
    }
    original = (
        "The board approved the merger on Tuesday, and the market reacted positively."
    )
    draft = (DraftSentence("S1", original, ("ch_a", "ch_b")),)
    result = _run(
        chunks,
        draft,
        decompose=lambda s, c, a=None: (
            "The board approved the merger on Tuesday.",
            "the market reacted positively",
        ),
        entail=lambda s, c, a=None: (True, "direct support"),
    )
    assert result.state == QueryState.ANSWERED
    rows = result.trace.verification.decomposed
    assert rows[0].citations == ("ch_a",)
    assert rows[1].contained is False
    assert rows[1].entailment == "supported"
    assert rows[1].citations == ("ch_a", "ch_b")


def test_all_sub_claims_unsupported_abstains_and_differs_from_empty() -> None:
    """A sentence whose sub claims are all unsupported is fully removed and
    the trace keeps its rows, distinct from an empty decomposition (AC-6)."""
    chunks = {"ch_a": "The board met to discuss the merger on Tuesday."}
    draft = (
        DraftSentence(
            "S1",
            "The board approved the merger, and the board made a secret plan.",
            ("ch_a",),
        ),
    )
    result = _run(
        chunks,
        draft,
        decompose=lambda s, c, a=None: (
            "The board approved the merger.",
            "The board made a secret plan.",
        ),
        entail=lambda s, c, a=None: (False, "not supported"),
        question="merger",
    )
    assert result.state == QueryState.ABSTAINED
    assert result.abstention_stage.value == "claim_verification"
    assert result.trace.verification.removed_sentences == ("S1",)
    assert result.trace.verification.empty_decompositions == ()
    rows = result.trace.verification.decomposed
    assert len(rows) == 2
    assert all(row.kept is False for row in rows)


def test_no_kept_sentences_skips_coverage_call() -> None:
    """With no kept sentences, every canonical facet gets a deterministic
    uncovered row and the coverage provider is never called (AC-12)."""
    chunks = {"ch_a": "The board met to discuss the merger on Tuesday."}
    draft = (
        DraftSentence(
            "S1",
            "The board approved the merger, and the board made a secret plan.",
            ("ch_a",),
        ),
    )
    result = _run(
        chunks,
        draft,
        decompose=lambda s, c, a=None: (
            "The board approved the merger.",
            "The board made a secret plan.",
        ),
        entail=lambda s, c, a=None: (False, "not supported"),
        coverage=_no_call,
        question="merger",
    )
    assert result.state == QueryState.ABSTAINED
    facets = result.trace.generation.facets
    assert facets
    assert result.trace.verification.coverage == tuple(
        CoverageRow(facet.facet_id, False, "no kept answer sentence", ())
        for facet in facets
    )
    assert result.trace.verification.uncovered_facets == facets


def test_abstained_public_output_is_empty_while_trace_keeps_rows() -> None:
    """An abstention at claim verification exposes no public sentences or
    citations while the trace keeps the verification rows (AC-4, AC-12)."""
    chunks = {"ch_a": "The board met to discuss the merger on Tuesday."}
    draft = (
        DraftSentence(
            "S1",
            "The board approved the merger, and the board made a secret plan.",
            ("ch_a",),
        ),
    )
    result = _run(
        chunks,
        draft,
        decompose=lambda s, c, a=None: (
            "The board approved the merger.",
            "The board made a secret plan.",
        ),
        entail=lambda s, c, a=None: (False, "not supported"),
        question="merger",
    )
    assert result.state == QueryState.ABSTAINED
    assert result.abstention_stage.value == "claim_verification"
    assert result.sentences == ()
    assert result.citations == ()
    # The trace keeps the verification detail.
    assert len(result.trace.verification.decomposed) == 2
    assert result.trace.verification.coverage


# ---------------------------------------------------------------------------
# AC-5: verbatim sentences never pay a decomposition call.
# ---------------------------------------------------------------------------


def test_verbatim_sentence_skips_decomposition_call() -> None:
    """A fully verbatim sentence is kept without any decomposition call
    (AC-5)."""
    chunks = {"ch_a": "The board approved the merger on Tuesday."}
    draft = (
        DraftSentence("S1", "The board approved the merger on Tuesday.", ("ch_a",)),
    )
    result = _run(
        chunks,
        draft,
        decompose=_no_call,
        entail=_no_call,
        question="merger",
    )
    assert result.state == QueryState.ANSWERED
    assert [sentence.text for sentence in result.sentences] == [
        "The board approved the merger on Tuesday."
    ]
    assert result.trace.verification.decomposed == ()
    assert result.trace.verification.empty_decompositions == ()
    assert result.trace.verification.missing_chunk_refs == ()


def test_contained_parent_narrows_to_available_citations() -> None:
    """A whole contained sentence that also cites a missing chunk is kept
    without decomposition but narrowed to its available citations only; the
    missing id never reaches an output citation (AC-5, AC-8)."""
    chunks = {"ch_a": "The board approved the merger on Tuesday."}
    draft = (
        DraftSentence(
            "S1",
            "The board approved the merger on Tuesday.",
            ("ch_a", "ch_missing"),
        ),
    )
    result = _run(
        chunks,
        draft,
        decompose=_no_call,
        entail=_no_call,
        question="merger",
    )
    assert result.state == QueryState.ANSWERED
    assert result.trace.verification.missing_chunk_refs == (("S1", ("ch_missing",)),)
    # The whole sentence is contained, so it is kept without decomposition,
    # but narrowed to the available citation (AC-8).
    assert [sentence.sentence_id for sentence in result.sentences] == ["S1"]
    assert _cited_chunk_ids(result, result.sentences[0]) == ("ch_a",)


# ---------------------------------------------------------------------------
# AC-11 and AC-6: the contract guardrail rejects a violating nonempty
# response with a closed disposition, never verified as written; a genuine
# empty response stays a distinct signal.
# ---------------------------------------------------------------------------


def test_invented_decomposition_is_rejected_by_the_lexical_guard() -> None:
    """A sub claim introducing content absent from the parent sentence is
    rejected with the closed lexical guard disposition, distinct from a
    genuine empty response (AC-11, AC-6)."""
    chunks = {"ch_a": "The board approved the merger on Tuesday."}
    draft = (
        DraftSentence(
            "S1",
            "The board approved the merger on Tuesday, and the board stayed late.",
            ("ch_a",),
        ),
    )
    result = _run(
        chunks,
        draft,
        decompose=lambda s, c, a=None: (
            "The board approved the merger on Tuesday.",
            "The board bought a yacht.",
        ),
        entail=_no_call,
        question="merger",
    )
    assert result.state == QueryState.ABSTAINED
    assert result.trace.verification.rejected_decompositions == (
        RejectedDecomposition("S1", 2, "lexical_guard"),
    )
    assert result.trace.verification.empty_decompositions == ()
    assert result.trace.verification.decomposed == ()
    assert result.trace.verification.removed_sentences == ("S1",)
    assert not any("yacht" in sentence.text for sentence in result.sentences)


def test_over_cap_decomposition_is_rejected_with_disposition() -> None:
    """More than the sanity bound of sub claims is rejected with the over cap
    disposition, never verified (AC-11, AC-6)."""
    chunks = {"ch_a": "The board approved the merger on Tuesday."}
    draft = (
        DraftSentence(
            "S1",
            "The board approved the merger on Tuesday, and the board stayed late.",
            ("ch_a",),
        ),
    )
    over_cap = tuple(f"the board stayed {index}" for index in range(MAX_SUB_CLAIMS + 1))
    result = _run(
        chunks,
        draft,
        decompose=lambda s, c, a=None: over_cap,
        entail=_no_call,
        question="merger",
    )
    assert result.state == QueryState.ABSTAINED
    assert result.trace.verification.rejected_decompositions == (
        RejectedDecomposition("S1", len(over_cap), "over_cap"),
    )
    assert result.trace.verification.empty_decompositions == ()
    assert result.trace.verification.decomposed == ()


def test_duplicate_decomposition_is_rejected_with_disposition() -> None:
    """A normalized duplicate row rejects the complete response with the
    duplicate disposition, so ids never skip on an accepted response
    (AC-11, AC-6)."""
    chunks = {"ch_a": "The board approved the merger on Tuesday."}
    draft = (
        DraftSentence(
            "S1",
            "The board approved the merger on Tuesday, and the board stayed late.",
            ("ch_a",),
        ),
    )
    result = _run(
        chunks,
        draft,
        decompose=lambda s, c, a=None: (
            "The board approved the merger on Tuesday.",
            "the board approved the merger on Tuesday.",
        ),
        entail=_no_call,
        question="merger",
    )
    assert result.state == QueryState.ABSTAINED
    assert result.trace.verification.rejected_decompositions == (
        RejectedDecomposition("S1", 2, "duplicate"),
    )
    assert result.trace.verification.empty_decompositions == ()
    assert result.trace.verification.decomposed == ()


def test_empty_decomposition_is_traced_distinctly() -> None:
    """A decomposition returning zero sub claims removes the sentence and
    records the empty signal separately from a rejected response and from
    all unsupported (AC-6)."""
    chunks = {"ch_a": "The board approved the merger on Tuesday."}
    draft = (
        DraftSentence(
            "S1",
            "The board approved the merger on Tuesday, and the board stayed late.",
            ("ch_a",),
        ),
    )
    result = _run(
        chunks,
        draft,
        decompose=lambda s, c, a=None: (),
        entail=_no_call,
        question="merger",
    )
    assert result.state == QueryState.ABSTAINED
    assert result.trace.verification.empty_decompositions == ("S1",)
    assert result.trace.verification.rejected_decompositions == ()
    assert result.trace.verification.decomposed == ()
    assert result.trace.verification.removed_sentences == ("S1",)


def test_under_split_is_visible_in_the_trace() -> None:
    """A single sub claim equal to the whole sentence stays visible in the
    trace rather than silent (AC-6)."""
    chunks = {"ch_a": "The board approved the merger on Tuesday."}
    original = "The board approved the merger on Tuesday, and the board stayed late."
    draft = (DraftSentence("S1", original, ("ch_a",)),)
    result = _run(
        chunks,
        draft,
        decompose=lambda s, c, a=None: (original,),
        entail=lambda s, c, a=None: (True, "direct support"),
        question="merger",
    )
    assert result.state == QueryState.ANSWERED
    rows = result.trace.verification.decomposed
    assert [(row.sub_claim_id, row.text, row.kept) for row in rows] == [
        ("S1.1", original, True)
    ]
    # The under split emits the single fragment with its sub claim id; the
    # parent sentence id is never restored (AC-4).
    assert [(sentence.sentence_id, sentence.text) for sentence in result.sentences] == [
        ("S1.1", original)
    ]


# ---------------------------------------------------------------------------
# AC-7: a provider failure during decomposition fails the query.
# ---------------------------------------------------------------------------


def test_decomposition_provider_failure_fails_the_query() -> None:
    """A raising decomposition call returns a failed query with a provider
    failure trace (AC-7)."""
    chunks = {"ch_a": "The board approved the merger on Tuesday."}
    draft = (
        DraftSentence(
            "S1",
            "The board approved the merger on Tuesday, and the board stayed late.",
            ("ch_a",),
        ),
    )

    def _boom(s, c, a=None):
        raise RuntimeError("provider exploded")

    result = _run(
        chunks,
        draft,
        decompose=_boom,
        entail=_no_call,
        question="merger",
    )
    assert result.state == QueryState.FAILED
    assert result.exit_code == 1
    assert result.abstention_stage is None
    assert result.failure is not None
    assert result.failure.code == "provider.decompose"
    assert result.failure.stage == "claim_verification"


def test_coverage_provider_failure_fails_the_query() -> None:
    """A raising coverage call returns a failed query with a provider
    failure trace at claim verification (AC-7, AC-12)."""
    chunks = {"ch_a": "The board approved the merger on Tuesday."}
    draft = (
        DraftSentence(
            "S1",
            "The board approved the merger on Tuesday, and the board stayed late.",
            ("ch_a",),
        ),
    )

    def _boom(question, facets, sentences, a=None):
        raise RuntimeError("provider exploded")

    result = _run(
        chunks,
        draft,
        decompose=lambda s, c, a=None: ("The board approved the merger on Tuesday.",),
        entail=lambda s, c, a=None: (True, "direct support"),
        coverage=_boom,
        question="merger",
    )
    assert result.state == QueryState.FAILED
    assert result.exit_code == 1
    assert result.abstention_stage is None
    assert result.failure is not None
    assert result.failure.code == "provider.coverage"
    assert result.failure.stage == "claim_verification"


def test_malformed_decomposition_payload_is_rejected_by_the_validator() -> None:
    """A malformed decomposition payload raises at the provider boundary; an
    over cap payload passes the validator and is classified by the
    application, never mislabeled as a provider failure (AC-7, AC-6)."""
    with pytest.raises(GenerationError):
        validate_decompose({})
    with pytest.raises(GenerationError):
        validate_decompose({"sub_claims": "not a list"})
    with pytest.raises(GenerationError):
        validate_decompose({"sub_claims": [{"text": "  "}]})
    assert validate_decompose({"sub_claims": []}) == ()
    assert validate_decompose(
        {"sub_claims": [{"text": "x"}] * (MAX_SUB_CLAIMS + 1)}
    ) == ("x",) * (MAX_SUB_CLAIMS + 1)
    assert validate_decompose({"sub_claims": [{"text": "an atomic claim"}]}) == (
        "an atomic claim",
    )


# ---------------------------------------------------------------------------
# AC-8: missing chunk refs are counted; partial missing verifies against the
# present subset.
# ---------------------------------------------------------------------------


def test_parent_citing_no_accepted_chunk_is_dropped_and_counted() -> None:
    """A sentence whose cited chunk is absent from the accepted context is
    never supported and the missing refs are recorded (AC-8)."""
    chunks = {"ch_a": "The board approved the merger on Tuesday."}
    draft = (
        DraftSentence(
            "S1",
            "The board approved the merger on Tuesday, and the board stayed late.",
            ("ch_missing",),
        ),
    )
    result = _run(
        chunks,
        draft,
        decompose=_no_call,
        entail=_no_call,
        question="merger",
    )
    assert result.state == QueryState.ABSTAINED
    assert result.trace.verification.removed_sentences == ("S1",)
    assert result.trace.verification.missing_chunk_refs == (("S1", ("ch_missing",)),)
    assert result.trace.verification.decomposed == ()


def test_partial_missing_verifies_against_present_subset() -> None:
    """When only part of the parent's chunk ids are missing, the sub claims
    are verified against the present subset rather than dropped outright
    (AC-8)."""
    chunks = {"ch_a": "The board approved the merger on Tuesday."}
    draft = (
        DraftSentence(
            "S1",
            "The board approved the merger on Tuesday, and the board hired "
            "a chief engineer.",
            ("ch_a", "ch_missing"),
        ),
    )
    result = _run(
        chunks,
        draft,
        decompose=lambda s, c, a=None: (
            "The board approved the merger on Tuesday.",
            "the board hired a chief engineer",
        ),
        entail=lambda s, c, a=None: (True, "direct support"),
        question="merger",
    )
    assert result.state == QueryState.ANSWERED
    assert result.trace.verification.missing_chunk_refs == (("S1", ("ch_missing",)),)
    rows = result.trace.verification.decomposed
    # The verbatim sub claim still narrows to the present chunk.
    assert rows[0].citations == ("ch_a",)
    # The entailment grounded fragment cites only available ids: the missing
    # id is trace only and never reaches a trace or output citation (AC-8).
    assert rows[1].entailment == "supported"
    assert rows[1].citations == ("ch_a",)
    assert [sentence.sentence_id for sentence in result.sentences] == ["S1.1", "S1.2"]
    assert _cited_chunk_ids(result, result.sentences[1]) == ("ch_a",)


# ---------------------------------------------------------------------------
# AC-10: the result schema stays version 2 and the additive fields resolve.
# ---------------------------------------------------------------------------


def test_debug_trace_renders_sub_claim_section(capsys) -> None:
    """The debug trace shows the split, each sub claim, and its verdict
    (AC-6)."""
    from decision_memory.cli import _print_query_debug

    chunks = {"ch_a": "The board met to discuss the merger on Tuesday."}
    draft = (
        DraftSentence(
            "S1",
            "The board approved the merger, and the board made a secret plan.",
            ("ch_a",),
        ),
    )
    result = _run(
        chunks,
        draft,
        decompose=lambda s, c, a=None: (
            "The board approved the merger.",
            "The board made a secret plan.",
        ),
        entail=lambda s, c, a=None: (False, "not supported"),
        question="merger",
    )
    _print_query_debug(result)
    out = capsys.readouterr().out
    assert "Sub claims" in out
    assert "S1.1" in out and "S1.2" in out
    assert "The board approved the merger." in out
    assert "kept=False" in out
    assert "entailment=unsupported" in out


def test_schema_version_stays_two_and_trace_fields_resolve() -> None:
    """The trace addition is additive: schema stays 2 and the old and new
    fields all resolve on a real pipeline run (AC-10)."""
    chunks = {"ch_a": "The board approved the merger on Tuesday."}
    draft = (
        DraftSentence(
            "S1",
            "The board approved the merger on Tuesday, and the board stayed late.",
            ("ch_a",),
        ),
    )
    result = _run(
        chunks,
        draft,
        decompose=lambda s, c, a=None: ("The board approved the merger on Tuesday.",),
        entail=_no_call,
        question="merger",
    )
    assert result.schema_version == 2
    verification = result.trace.verification
    # Old fields still resolve.
    assert verification.containment
    assert verification.removed_sentences == ()
    # New fields resolve and are the additive signal.
    assert verification.decomposed
    assert verification.empty_decompositions == ()
    assert verification.rejected_decompositions == ()
    assert verification.missing_chunk_refs == ()


# ---------------------------------------------------------------------------
# The deterministic contract check itself.
# ---------------------------------------------------------------------------


def test_near_subset_contract_check() -> None:
    """The near subset rule is deterministic and catches invented content."""
    parent = "The board approved the merger on Tuesday."
    assert decomposition_is_near_subset(
        ("The board approved the merger.", "the merger on Tuesday"), parent
    )
    assert not decomposition_is_near_subset(
        ("The board approved the merger.", "The board bought a yacht."), parent
    )
    assert not decomposition_is_near_subset(("The board approved",), "")


def test_near_subset_lexical_tolerance_and_limits() -> None:
    """The matcher allows one inflection suffix and one added grammar token
    each, but rejects a new content token (AC-11)."""
    parent = "The board refetches the merger file."
    # refetch / refetches and file / files match through the suffix rule.
    assert decomposition_is_near_subset(("The board refetch the merger file.",), parent)
    assert decomposition_is_near_subset(
        ("The board refetches the merger files.",), parent
    )
    # Each grammar token may be added at most once without a parent match.
    assert decomposition_is_near_subset(
        ("The board refetch a merger file and that which the.",), parent
    )
    # A second added instance of the same grammar token is rejected.
    assert not decomposition_is_near_subset(
        ("The board refetch a merger file and a.",), parent
    )
    # A new content token is rejected.
    assert not decomposition_is_near_subset(
        ("The board refetches the merger yacht.",), parent
    )


def test_near_subset_makes_no_semantic_guarantee() -> None:
    """The matcher is lexical only: dropped negation and reversed order pass
    it, so only individually verified fragments may emit (AC-11, AC-1)."""
    parent = "The board did not approve the merger."
    assert decomposition_is_near_subset(("The board approve the merger.",), parent)
    assert decomposition_is_near_subset(("the merger approve the board",), parent)


def test_decompose_disposition_classification() -> None:
    """The classifier returns None for an accepted response and one closed
    rejection disposition otherwise (AC-6, AC-11)."""
    parent = "The board approved the merger on Tuesday."
    assert decompose_disposition(("The board approved the merger.",), parent) is None
    assert decompose_disposition(("x",) * (MAX_SUB_CLAIMS + 1), parent) == "over_cap"
    assert (
        decompose_disposition(
            ("The board approved the merger.", "THE board APPROVED the merger."),
            parent,
        )
        == "duplicate"
    )
    assert decompose_disposition(("The board bought a yacht.",), parent) == (
        "lexical_guard"
    )


def test_debug_trace_renders_rejected_decomposition(capsys) -> None:
    """The debug trace shows a rejected decomposition's sentence, count, and
    disposition, never its rejected text (AC-6)."""
    from decision_memory.cli import _print_query_debug

    chunks = {"ch_a": "The board approved the merger on Tuesday."}
    draft = (
        DraftSentence(
            "S1",
            "The board approved the merger on Tuesday, and the board stayed late.",
            ("ch_a",),
        ),
    )
    result = _run(
        chunks,
        draft,
        decompose=lambda s, c, a=None: (
            "The board approved the merger on Tuesday.",
            "The board bought a yacht.",
        ),
        entail=_no_call,
        question="merger",
    )
    _print_query_debug(result)
    out = capsys.readouterr().out
    assert "rejected_decomposition S1 count=2 disposition=lexical_guard" in out
    assert "yacht" not in out
