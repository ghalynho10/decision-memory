"""Deterministic sub claim verification tests (spec 0010).

These lock the sub claim verification stage against the real pipeline with
deterministic fakes: a controlled accepted context, crafted draft sentences,
and scripted decomposition and entailment callables. The whole pipeline runs,
so the coverage decision and the citation allocation are real; only the
provider calls are faked. The live gates (AC-2, AC-3, AC-9) stay in the
integration suite.

The contract these lock: decomposition is a **check** on a draft sentence,
not a rewrite of it. The verification unit is the sub claim, the output unit
is the sentence. A sentence reaches the answer only when its decomposition is
valid (adds nothing to the parent, omits nothing from it) and every sub claim
is supported; otherwise the whole sentence is dropped.
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
    DroppedSentence,
    QueryFilters,
    QueryRequest,
    QueryResult,
    QueryState,
    RejectedDecomposition,
    VerificationTrace,
)
from decision_memory.application.query import query_index
from decision_memory.application.verification import (
    MAX_SUB_CLAIMS,
    classify_decomposition,
    response_is_complete,
    sentence_tokens,
    sub_claim_is_additive_free,
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
    """Coverage that only covers when there is an emitted sentence to cover it."""
    sentence_ids = tuple(sentence.sentence_id for sentence in sentences)
    covered = bool(sentence_ids)
    label = "covered" if covered else "no sentences"
    return tuple(
        CoverageRow(facet.facet_id, covered, label, sentence_ids) for facet in facets
    )


def _no_call(*_args, **_kwargs):
    raise AssertionError("must not be called")


def _entail_by_text(unsupported: set[str]):
    """Entailment that fails only the named sub claim texts."""

    def _entail(text, evidence, attempts=None) -> tuple[bool, str]:
        if text in unsupported:
            return (False, "not supported")
        return (True, "direct support")

    return _entail


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


# The recurring weld: a verbatim borrowed clause welded to a fabrication.
_WELD_CHUNKS = {
    "ch_a": "The board approved the merger on Tuesday.",
    "ch_b": "The board hired a chief engineer in March.",
}
_WELD_TEXT = (
    "The board approved the merger on Tuesday, and the board accepted "
    "a bribe to rush it."
)
_WELD_GROUNDED = "The board approved the merger on Tuesday."
_WELD_FABRICATED = "The board accepted a bribe to rush it."


# ---------------------------------------------------------------------------
# AC-1 and AC-4: both attacks on the weld. A fabricated sub claim takes its
# whole parent down, and a decomposition that omits the fabricated clause
# fails completeness rather than making the parent look safe.
# ---------------------------------------------------------------------------


def test_fabricated_sub_claim_drops_the_whole_parent_sentence() -> None:
    """The first AC-1 attack: an explicit fabricated sub claim.

    The response is valid (it adds nothing and omits nothing), so every sub
    claim is verified. The fabricated one comes back unsupported and its whole
    parent sentence is dropped, so neither the fabrication nor the verbatim
    borrowed clause that was carrying it can reach output (AC-1, AC-4).
    """
    draft = (DraftSentence("S1", _WELD_TEXT, ("ch_a", "ch_b")),)
    result = _run(
        _WELD_CHUNKS,
        draft,
        decompose=lambda s, c, a=None: (_WELD_GROUNDED, _WELD_FABRICATED),
        entail=_entail_by_text({_WELD_FABRICATED}),
    )
    assert result.state == QueryState.ABSTAINED
    assert result.schema_version == 2
    # Neither clause reaches output: the grounded one does not survive alone.
    assert result.sentences == ()
    assert result.citations == ()
    # One drop row, naming the reason.
    assert result.trace.verification.dropped_sentences == (
        DroppedSentence("S1", "unsupported_sub_claim"),
    )
    assert result.trace.verification.rejected_decompositions == ()
    # The trace names the exact claim that caused the drop.
    rows = result.trace.verification.decomposed
    assert [(row.sub_claim_id, row.entailment) for row in rows] == [
        ("S1.1", "skipped"),
        ("S1.2", "unsupported"),
    ]
    assert rows[0].contained is True
    assert rows[0].citations == ("ch_a",)
    assert rows[1].reason == "not supported"


def test_omitted_fabricated_clause_fails_completeness_and_drops_the_parent() -> None:
    """The second AC-1 attack: the fabricated clause is omitted entirely.

    The decomposition returns only the grounded clause, which would verify
    perfectly on its own and make the fabricated parent look safe. It fails
    the completeness half instead, so the parent is dropped as ``incomplete``
    with no entailment call at all (AC-1, AC-11).
    """
    draft = (DraftSentence("S1", _WELD_TEXT, ("ch_a", "ch_b")),)
    result = _run(
        _WELD_CHUNKS,
        draft,
        decompose=lambda s, c, a=None: (_WELD_GROUNDED,),
        entail=_no_call,
    )
    assert result.state == QueryState.ABSTAINED
    assert result.sentences == ()
    assert result.trace.verification.rejected_decompositions == (
        RejectedDecomposition("S1", 1, "incomplete"),
    )
    assert result.trace.verification.dropped_sentences == (
        DroppedSentence("S1", "decomposition_invalid"),
    )
    # No sub claim was verified, so no row and no entailment call.
    assert result.trace.verification.decomposed == ()


def test_valid_fully_supported_response_emits_the_whole_parent() -> None:
    """A sentence whose decomposition is valid and fully supported is emitted
    verbatim, with its own sentence id and its parent citations. No sub claim
    text appears in output (AC-4)."""
    original = (
        "The board approved the merger on Tuesday, and the board hired a "
        "chief engineer in March."
    )
    draft = (DraftSentence("S1", original, ("ch_a", "ch_b")),)
    result = _run(
        _WELD_CHUNKS,
        draft,
        decompose=lambda s, c, a=None: (
            "The board approved the merger on Tuesday.",
            "The board hired a chief engineer in March.",
        ),
        entail=_no_call,
    )
    assert result.state == QueryState.ANSWERED
    # The parent sentence, whole, under its own id.
    assert [(sentence.sentence_id, sentence.text) for sentence in result.sentences] == [
        ("S1", original)
    ]
    # It cites the parent's available ids, not a sub claim's narrowed set.
    assert _cited_chunk_ids(result, result.sentences[0]) == ("ch_a", "ch_b")
    # The sub claims exist only in the trace, each with its own narrowed
    # citations, and neither is an answer sentence.
    rows = result.trace.verification.decomposed
    assert [(row.sub_claim_id, row.citations) for row in rows] == [
        ("S1.1", ("ch_a",)),
        ("S1.2", ("ch_b",)),
    ]
    assert all(row.contained for row in rows)
    assert result.trace.verification.dropped_sentences == ()


def test_draft_order_is_preserved_among_emitted_sentences() -> None:
    """A dropped sentence takes only itself down: the others are unaffected
    and keep draft order (AC-4)."""
    chunks = dict(_WELD_CHUNKS)
    draft = (
        DraftSentence("S1", "The board approved the merger on Tuesday.", ("ch_a",)),
        DraftSentence("S2", _WELD_TEXT, ("ch_a", "ch_b")),
        DraftSentence("S3", "The board hired a chief engineer in March.", ("ch_b",)),
    )
    result = _run(
        chunks,
        draft,
        decompose=lambda s, c, a=None: (_WELD_GROUNDED, _WELD_FABRICATED),
        entail=_entail_by_text({_WELD_FABRICATED}),
    )
    assert result.state == QueryState.ANSWERED
    # S1 and S3 are verbatim, so they are emitted whole in draft order; S2 is
    # dropped for its unsupported sub claim.
    assert [sentence.sentence_id for sentence in result.sentences] == ["S1", "S3"]
    assert result.trace.verification.dropped_sentences == (
        DroppedSentence("S2", "unsupported_sub_claim"),
    )
    assert not any("bribe" in sentence.text for sentence in result.sentences)


def test_entailment_grounded_sub_claim_keeps_full_available_cited_set() -> None:
    """An entailment grounded sub claim keeps the parent's full available
    cited set in the trace, since entailment names no supporting chunk. The
    emitted parent cites the same available ids (AC-4, AC-8)."""
    original = (
        "The board approved the merger on Tuesday, and the market reacted positively."
    )
    draft = (DraftSentence("S1", original, ("ch_a", "ch_b")),)
    result = _run(
        _WELD_CHUNKS,
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
    assert [sentence.sentence_id for sentence in result.sentences] == ["S1"]


# ---------------------------------------------------------------------------
# AC-5 and AC-8: the cost bound and the accepted context citation boundary.
# ---------------------------------------------------------------------------


def test_verbatim_sentence_skips_decomposition_call() -> None:
    """A fully contained sentence is emitted without any decomposition call
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
    assert result.trace.verification.dropped_sentences == ()


def test_contained_parent_narrows_to_available_citations() -> None:
    """A whole contained sentence that also cites a missing chunk is emitted
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
    assert [sentence.sentence_id for sentence in result.sentences] == ["S1"]
    assert _cited_chunk_ids(result, result.sentences[0]) == ("ch_a",)


def test_parent_citing_no_accepted_chunk_is_dropped_and_counted() -> None:
    """A sentence whose cited chunk is absent from the accepted context is
    dropped without any provider call, with its own closed reason (AC-6,
    AC-8)."""
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
    assert result.trace.verification.dropped_sentences == (
        DroppedSentence("S1", "no_available_citations"),
    )
    assert result.trace.verification.missing_chunk_refs == (("S1", ("ch_missing",)),)
    assert result.trace.verification.decomposed == ()


def test_partial_missing_verifies_against_present_subset() -> None:
    """When only part of the parent's chunk ids are missing, the sub claims
    are verified against the present subset and the emitted parent cites only
    the available ids (AC-8)."""
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
    assert rows[0].citations == ("ch_a",)
    assert rows[1].entailment == "supported"
    assert rows[1].citations == ("ch_a",)
    assert [sentence.sentence_id for sentence in result.sentences] == ["S1"]
    assert _cited_chunk_ids(result, result.sentences[0]) == ("ch_a",)


# ---------------------------------------------------------------------------
# AC-6 and AC-11: the closed disposition set, the retry, and exactly one drop
# reason per unemitted sentence.
# ---------------------------------------------------------------------------


def test_over_cap_decomposition_is_rejected_without_a_retry() -> None:
    """More than the sanity bound is rejected as ``over_cap``, before the two
    half test and without the retry, which only a two half failure earns
    (AC-11, AC-6)."""
    chunks = {"ch_a": "The board approved the merger on Tuesday."}
    draft = (
        DraftSentence(
            "S1",
            "The board approved the merger on Tuesday, and the board stayed late.",
            ("ch_a",),
        ),
    )
    over_cap = tuple(f"the board stayed {index}" for index in range(MAX_SUB_CLAIMS + 1))
    calls = []

    def _decompose(s, c, a=None):
        calls.append(s)
        return over_cap

    result = _run(
        chunks,
        draft,
        decompose=_decompose,
        entail=_no_call,
        question="merger",
    )
    assert result.state == QueryState.ABSTAINED
    assert len(calls) == 1
    assert result.trace.verification.rejected_decompositions == (
        RejectedDecomposition("S1", len(over_cap), "over_cap"),
    )
    assert result.trace.verification.dropped_sentences == (
        DroppedSentence("S1", "decomposition_invalid"),
    )
    assert result.trace.verification.decomposed == ()


def test_duplicate_decomposition_is_rejected_without_a_retry() -> None:
    """A normalized duplicate row rejects the whole response as ``duplicate``,
    before the two half test and without the retry (AC-11, AC-6)."""
    chunks = {"ch_a": "The board approved the merger on Tuesday."}
    draft = (
        DraftSentence(
            "S1",
            "The board approved the merger on Tuesday, and the board stayed late.",
            ("ch_a",),
        ),
    )
    calls = []

    def _decompose(s, c, a=None):
        calls.append(s)
        return (
            "The board approved the merger on Tuesday.",
            "the board approved the merger on Tuesday.",
        )

    result = _run(
        chunks,
        draft,
        decompose=_decompose,
        entail=_no_call,
        question="merger",
    )
    assert result.state == QueryState.ABSTAINED
    assert len(calls) == 1
    assert result.trace.verification.rejected_decompositions == (
        RejectedDecomposition("S1", 2, "duplicate"),
    )
    assert result.trace.verification.dropped_sentences == (
        DroppedSentence("S1", "decomposition_invalid"),
    )


def test_empty_decomposition_is_traced_distinctly() -> None:
    """A decomposition returning zero sub claims drops the sentence and
    records the empty signal, which carries no rejection disposition of its
    own (AC-6)."""
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
    assert result.trace.verification.dropped_sentences == (
        DroppedSentence("S1", "decomposition_invalid"),
    )


def test_two_half_failure_retries_once_and_a_valid_retry_is_used() -> None:
    """A two half failure earns exactly one retry, and a valid retry response
    is verified normally: an invalid decomposition is usually a stochastic
    paraphrase, not a property of the sentence (AC-11)."""
    chunks = {"ch_a": "The board approved the merger on Tuesday."}
    original = "The board approved the merger on Tuesday, and the board stayed late."
    draft = (DraftSentence("S1", original, ("ch_a",)),)
    responses = [
        # Invalid: `yacht` is content the parent never had.
        ("The board bought a yacht.", "the board stayed late"),
        # Valid: adds nothing, omits nothing.
        ("The board approved the merger on Tuesday.", "the board stayed late"),
    ]
    calls = []

    def _decompose(s, c, a=None):
        calls.append(s)
        return responses[len(calls) - 1]

    result = _run(
        chunks,
        draft,
        decompose=_decompose,
        entail=lambda s, c, a=None: (True, "direct support"),
        question="merger",
    )
    assert result.state == QueryState.ANSWERED
    assert len(calls) == 2
    # The retry's rows are the ones verified; the rejected first response
    # leaves no row behind, so one sentence is never two events.
    assert result.trace.verification.rejected_decompositions == ()
    assert tuple(row.sub_claim_id for row in result.trace.verification.decomposed) == (
        "S1.1",
        "S1.2",
    )
    assert [sentence.sentence_id for sentence in result.sentences] == ["S1"]


def test_second_invalid_response_drops_the_parent_with_its_disposition() -> None:
    """A retry that is also invalid drops the parent, recording exactly one
    rejection row for the final response (AC-6, AC-11)."""
    chunks = {"ch_a": "The board approved the merger on Tuesday."}
    draft = (
        DraftSentence(
            "S1",
            "The board approved the merger on Tuesday, and the board stayed late.",
            ("ch_a",),
        ),
    )
    calls = []

    def _decompose(s, c, a=None):
        calls.append(s)
        return ("The board bought a yacht.", "The board hired a pilot.")

    result = _run(
        chunks,
        draft,
        decompose=_decompose,
        entail=_no_call,
        question="merger",
    )
    assert result.state == QueryState.ABSTAINED
    assert len(calls) == 2
    assert result.trace.verification.rejected_decompositions == (
        RejectedDecomposition("S1", 2, "not_additive"),
    )
    assert result.trace.verification.dropped_sentences == (
        DroppedSentence("S1", "decomposition_invalid"),
    )
    assert result.trace.verification.decomposed == ()
    assert not any("yacht" in sentence.text for sentence in result.sentences)


def test_exactly_one_drop_reason_per_unemitted_sentence() -> None:
    """Each of the three closed drop reasons appears exactly once, for its own
    sentence, and no sentence produces two rows (AC-6)."""
    chunks = {"ch_a": "The board approved the merger on Tuesday."}
    draft = (
        # No available citation at all.
        DraftSentence("S1", "The board approved the merger.", ("ch_missing",)),
        # An invalid decomposition.
        DraftSentence("S2", "The board approved the merger quietly.", ("ch_a",)),
        # A valid decomposition with an unsupported sub claim.
        DraftSentence("S3", "The board approved the merger loudly.", ("ch_a",)),
    )

    def _decompose(sentence_text, evidence, attempts=None):
        if sentence_text.endswith("quietly."):
            return ("The board bought a yacht.",)
        return ("The board approved the merger.", "The board approved it loudly.")

    result = _run(
        chunks,
        draft,
        decompose=_decompose,
        entail=lambda s, c, a=None: (False, "not supported"),
        question="merger",
    )
    assert result.state == QueryState.ABSTAINED
    assert result.trace.verification.dropped_sentences == (
        DroppedSentence("S1", "no_available_citations"),
        DroppedSentence("S2", "decomposition_invalid"),
        DroppedSentence("S3", "unsupported_sub_claim"),
    )
    sentence_ids = [
        row.sentence_id for row in result.trace.verification.dropped_sentences
    ]
    assert len(sentence_ids) == len(set(sentence_ids))
    # The `decomposition_invalid` row pairs with its specific disposition.
    assert result.trace.verification.rejected_decompositions == (
        RejectedDecomposition("S2", 1, "not_additive"),
    )


# ---------------------------------------------------------------------------
# AC-7: a provider failure fails the query rather than abstaining.
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
        DraftSentence("S1", "The board approved the merger on Tuesday.", ("ch_a",)),
    )

    def _boom(question, facets, sentences, a=None):
        raise RuntimeError("provider exploded")

    result = _run(
        chunks,
        draft,
        decompose=_no_call,
        entail=_no_call,
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
    """A malformed row, empty after trimming, fails at the provider boundary
    as ``provider.decompose``, before any application check could reach it.
    An over cap payload passes the validator and is classified by the
    application, never mislabeled as a provider failure (AC-7, AC-6, AC-11)."""
    with pytest.raises(GenerationError):
        validate_decompose({})
    with pytest.raises(GenerationError):
        validate_decompose({"sub_claims": "not a list"})
    with pytest.raises(GenerationError):
        validate_decompose({"sub_claims": [{"text": "  "}]})
    # Two malformed rows fail here rather than pairing as a duplicate later.
    with pytest.raises(GenerationError):
        validate_decompose({"sub_claims": [{"text": " "}, {"text": "  "}]})
    assert validate_decompose({"sub_claims": []}) == ()
    assert validate_decompose(
        {"sub_claims": [{"text": "x"}] * (MAX_SUB_CLAIMS + 1)}
    ) == ("x",) * (MAX_SUB_CLAIMS + 1)
    assert validate_decompose({"sub_claims": [{"text": "an atomic claim"}]}) == (
        "an atomic claim",
    )


# ---------------------------------------------------------------------------
# AC-10: the result schema stays version 2 and the additive fields resolve.
# ---------------------------------------------------------------------------


def test_schema_version_stays_two_and_trace_fields_resolve() -> None:
    """The trace addition is additive: schema stays 2 and the old and new
    fields all resolve on a real pipeline run (AC-10)."""
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
    assert result.schema_version == 2
    verification = result.trace.verification
    # Old fields still resolve.
    assert verification.containment
    assert verification.removed_sentences == ()
    # All five new fields resolve and are the additive signal.
    assert verification.decomposed
    assert verification.empty_decompositions == ()
    assert verification.rejected_decompositions == ()
    assert verification.dropped_sentences == ()
    assert verification.missing_chunk_refs == ()
    # An older constructor call, naming none of the five, remains valid.
    older = VerificationTrace(
        containment=(),
        entailment=(),
        removed_sentences=(),
        coverage=(),
        uncovered_facets=(),
    )
    assert older.dropped_sentences == ()


def test_under_split_emits_the_parent_under_its_own_id() -> None:
    """A single sub claim equal to the whole sentence is valid in both
    directions, stays visible in the trace, and emits the parent under the
    parent's own sentence id (AC-4, AC-6)."""
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
    assert [(row.sub_claim_id, row.text) for row in rows] == [("S1.1", original)]
    assert [(sentence.sentence_id, sentence.text) for sentence in result.sentences] == [
        ("S1", original)
    ]


# ---------------------------------------------------------------------------
# AC-11: the two half validity test itself, as a pure function.
# ---------------------------------------------------------------------------


def _additive(sub_claim: str, parent: str) -> bool:
    """Whether one sub claim passes the additive half against the parent."""
    return sub_claim_is_additive_free(
        sentence_tokens(sub_claim), sentence_tokens(parent)
    )


def _complete(sub_claims: tuple[str, ...], parent: str) -> bool:
    """Whether a response passes the completeness half against the parent."""
    return response_is_complete(sub_claims, sentence_tokens(parent))


def test_additive_half_accepts_a_subset_and_rejects_invented_content() -> None:
    """The additive half is deterministic per sub claim: a subset of the
    parent passes and invented content fails (AC-11)."""
    parent = "The board approved the merger on Tuesday."
    assert _additive("The board approved the merger.", parent)
    assert _additive("the merger on Tuesday", parent)
    assert not _additive("The board bought a yacht.", parent)
    # An empty parent has no token to match, so nothing is additive free.
    assert classify_decomposition(("The board approved",), "") == "not_additive"


def test_stem_rules_and_the_character_floor() -> None:
    """Each of the five stem rules matches, and the three character floor is
    measured on the untransformed token (AC-11)."""
    # Plain suffix, both directions.
    assert _additive("The board refetch the file.", "The board refetches the file.")
    assert _additive("The board refetches the files.", "The board refetch the file.")
    assert _additive("The team add a note.", "The team adding a note.")
    # A dropped final e plus ed or ing: use / using.
    assert _additive("The team use the store.", "The team using the store.")
    assert _additive("The team used the store.", "The team use the store.")
    # A repeated final character plus ed or ing: ship / shipped.
    assert _additive("The team ship the slice.", "The team shipped the slice.")
    assert _additive("The team shipping the slice.", "The team ship the slice.")
    # A final y traded for i plus es or ed: rely / relies.
    assert _additive("The team rely on the gate.", "The team relies on the gate.")
    assert _additive("The team relied on the gate.", "The team rely on the gate.")
    # The floor: a two character token never matches by stem.
    assert not _additive("The team go the slice.", "The team goes the slice.")
    # Exact equality carries no floor: a short parent token still matches
    # itself, since it is not new vocabulary.
    assert _additive("the db clients", "Keep the db clients together.")


def test_function_word_allowance_and_exact_only_matching() -> None:
    """At most two function word tokens may be added per sub claim, counted as
    instances, and a function word never matches by stem (AC-11)."""
    parent = "The board refetches the merger file."
    # Two added function word instances pass.
    assert _additive("The board refetches the merger file is not.", parent)
    # A third added instance fails, whatever the words are.
    assert not _additive("The board refetches the merger file is not there.", parent)
    # Two instances of the same function word count as two.
    assert not _additive("The board refetches a merger file and a and.", parent)
    # A word outside the closed set is content and must find a parent match.
    assert not _additive("The board refetches the merger file whilst.", parent)
    # A function word never matches by stem: the parent `not` cannot stand in
    # for the content token `notes`, which has no other parent match.
    assert not _additive("The board notes the merger.", "The board did not merger.")


def test_additive_half_is_scoped_per_sub_claim_not_response_wide() -> None:
    """The experiment 0002 regression: three sub claims each restating the
    shared subject against a parent naming it once.

    The pool resets per sub claim, so this passes. A build that consumed the
    parent pool across the whole response would reject it, and would reject a
    correct split of any sentence with a repeated subject (AC-11).
    """
    parent = "The hybrid retrieval system fuses lexical ranks and semantic ranks."
    response = (
        "The hybrid retrieval system fuses ranks.",
        "The hybrid retrieval system fuses lexical ranks.",
        "The hybrid retrieval system fuses semantic ranks.",
    )
    assert classify_decomposition(response, parent) is None
    # Each sub claim alone is additive free against the full parent pool.
    assert all(_additive(text, parent) for text in response)


def test_completeness_half_is_presence_based_across_the_response() -> None:
    """Every distinct parent content token must appear in some sub claim, by
    presence rather than by multiset, and parent function words need no match
    (AC-11)."""
    parent = "The team shipped the release, and the release shipped late."
    # A repeated parent token is satisfied by one occurrence in one sub claim.
    assert _complete(
        ("The team shipped the release.", "The release shipped late."), parent
    )
    # Splitting one parent clause across two sub claims still passes.
    assert _complete(
        ("The team shipped the release.", "The release was late."),
        "The team shipped the release late.",
    )
    # Dropping a content bearing clause fails.
    assert not _complete(("The team shipped the release.",), parent)
    # Parent function words need no match at all.
    assert _complete(("release",), "the release")


def test_not_additive_and_incomplete_are_distinct_dispositions() -> None:
    """The two halves report separately, and the additive half runs first, so
    a response failing both is reported as ``not_additive`` (AC-11)."""
    parent = "The board approved the merger and hired an engineer."
    assert (
        classify_decomposition(("The board approved the merger.",), parent)
        == "incomplete"
    )
    assert classify_decomposition(("The board bought a yacht.",), parent) == (
        "not_additive"
    )
    # Valid in both directions.
    assert (
        classify_decomposition(
            ("The board approved the merger.", "The board hired an engineer."), parent
        )
        is None
    )


def test_whole_response_checks_run_before_the_two_half_test() -> None:
    """Over cap and duplicate are classified first, in that order, before the
    two half test could reach the response (AC-6, AC-11)."""
    parent = "The board approved the merger on Tuesday."
    # Over cap is classified first, even though every row here would also fail
    # the additive half on its own.
    over_cap = ("a yacht",) * (MAX_SUB_CLAIMS + 1)
    assert classify_decomposition(over_cap, parent) == "over_cap"
    # Duplicate is classified before the two half test.
    duplicate = (
        "The board approved the merger.",
        "THE board APPROVED the merger.",
    )
    assert classify_decomposition(duplicate, parent) == "duplicate"


def test_greedy_first_unused_parent_token_in_parent_order() -> None:
    """A token eligible against two parent tokens takes the first unused one
    in parent order, the assignment never backtracks, and the same input
    always reaches the same verdict (AC-11)."""
    parent = "The team ships and shipped the release."
    # One `ship` consumes `ships`; a second consumes `shipped`.
    assert _additive("The team ship the release.", parent)
    assert _additive("The team ship ship the release.", parent)
    # A third has no unused parent token left to consume.
    assert not _additive("The team ship ship ship the release.", parent)
    # Determinism: the same input reaches the same verdict every time.
    response = ("The team ship the release.", "The team shipped the release.")
    verdicts = {classify_decomposition(response, parent) for _ in range(5)}
    assert verdicts == {None}


def test_validity_test_makes_no_semantic_guarantee() -> None:
    """The test is lexical only: dropped negation, reversed actors, and
    reordered relations all pass it, so entailment is the only defence
    against a meaning inverting split (AC-11, AC-1)."""
    parent = "The board did not approve the merger."
    # `not` is a parent function word, so dropping it breaks neither half.
    assert classify_decomposition(("The board approve the merger.",), parent) is None
    # Reordering is allowed.
    assert classify_decomposition(("the merger approve the board",), parent) is None


# ---------------------------------------------------------------------------
# AC-12: coverage judges whole emitted sentences.
# ---------------------------------------------------------------------------


def test_no_emitted_sentences_skips_the_coverage_call() -> None:
    """With no emitted sentences, every canonical facet gets a deterministic
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
        CoverageRow(facet.facet_id, False, "no emitted answer sentence", ())
        for facet in facets
    )
    assert result.trace.verification.uncovered_facets == facets


def test_abstained_public_output_is_empty_while_trace_keeps_rows() -> None:
    """An abstention at claim verification exposes no public sentences or
    citations while the trace keeps the sub claim and dropped sentence rows
    (AC-4, AC-12)."""
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
    assert len(result.trace.verification.decomposed) == 2
    assert result.trace.verification.dropped_sentences == (
        DroppedSentence("S1", "unsupported_sub_claim"),
    )
    assert result.trace.verification.coverage


def test_one_multi_clause_sentence_can_cover_several_facets() -> None:
    """The case experiment 0002 recorded as wrongly abstaining under the
    fragment contract: a decision that takes several clauses to state is one
    emitted sentence, so coverage sees it whole (AC-4, AC-12)."""
    chunks = {"ch_a": "The board approved the merger on Tuesday."}
    original = (
        "The board approved the merger on Tuesday, and the board approved it "
        "to settle the dispute."
    )
    draft = (DraftSentence("S1", original, ("ch_a",)),)

    def _coverage(question, facets, sentences, attempts=None):
        # Every facet is covered by the one whole sentence, which is only
        # possible because the sentence reaches coverage intact.
        assert [sentence.text for sentence in sentences] == [original]
        return tuple(
            CoverageRow(facet.facet_id, True, "stated", ("S1",)) for facet in facets
        )

    result = _run(
        chunks,
        draft,
        decompose=lambda s, c, a=None: (
            "The board approved the merger on Tuesday.",
            "The board approved the merger to settle the dispute.",
        ),
        entail=lambda s, c, a=None: (True, "direct support"),
        coverage=_coverage,
    )
    assert result.state == QueryState.ANSWERED
    assert [sentence.text for sentence in result.sentences] == [original]


# ---------------------------------------------------------------------------
# AC-6: the debug trace answers, for each draft sentence, whether it reached
# the answer and why not.
# ---------------------------------------------------------------------------


def test_debug_trace_renders_sub_claim_section(capsys) -> None:
    """The debug trace shows the split, each sub claim, and its verdict, with
    no sub claim level survival flag (AC-6)."""
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
    assert "entailment=unsupported" in out
    # A sub claim no longer survives or fails on its own.
    assert "kept=" not in out


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
            "The board bought a yacht.",
            "The board hired a pilot.",
        ),
        entail=_no_call,
        question="merger",
    )
    _print_query_debug(result)
    out = capsys.readouterr().out
    assert "rejected_decomposition S1 count=2 disposition=not_additive" in out
    assert "yacht" not in out
    assert "pilot" not in out


def test_debug_trace_renders_dropped_sentence(capsys) -> None:
    """The debug trace names every sentence that did not reach the answer and
    the closed reason why, with no claim text (AC-6)."""
    from decision_memory.cli import _print_query_debug

    draft = (DraftSentence("S1", _WELD_TEXT, ("ch_a", "ch_b")),)
    result = _run(
        _WELD_CHUNKS,
        draft,
        decompose=lambda s, c, a=None: (_WELD_GROUNDED, _WELD_FABRICATED),
        entail=_entail_by_text({_WELD_FABRICATED}),
    )
    _print_query_debug(result)
    out = capsys.readouterr().out
    assert "dropped_sentence S1 reason=unsupported_sub_claim" in out
