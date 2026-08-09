"""Generation schema validation tests (spec 0007 AC-15).

The four structured outputs are validated with fixed bounds and rules: facet
counts and uniqueness, draft sentence shape and known chunk ids, entailment
verdict shape, and one coverage row per fixed facet.
"""

from __future__ import annotations

import pytest

from decision_memory.application.dto import Facet
from decision_memory.infrastructure.openai_generation import (
    GenerationError,
    validate_coverage,
    validate_draft,
    validate_facets,
    validate_verdict,
)


def test_validate_facets_accepts_valid_set() -> None:
    facets = validate_facets(
        {
            "facets": [
                {"id": "F1", "text": "Why was the gate added?"},
                {"id": "F2", "text": "What was the alternative?"},
            ]
        }
    )
    assert facets == (
        Facet(facet_id="F1", text="Why was the gate added?"),
        Facet(facet_id="F2", text="What was the alternative?"),
    )


def test_validate_facets_rejects_wrong_bounds() -> None:
    with pytest.raises(GenerationError):
        validate_facets({"facets": []})
    with pytest.raises(GenerationError):
        validate_facets(
            {
                "facets": [
                    {"id": f"F{index}", "text": f"facet {index}"}
                    for index in range(1, 10)
                ]
            }
        )


def test_validate_facets_rejects_duplicate_ids_and_text() -> None:
    with pytest.raises(GenerationError):
        validate_facets(
            {"facets": [{"id": "F1", "text": "a"}, {"id": "F1", "text": "b"}]}
        )
    with pytest.raises(GenerationError):
        validate_facets(
            {"facets": [{"id": "F1", "text": "a"}, {"id": "F2", "text": "a"}]}
        )
    with pytest.raises(GenerationError):
        validate_facets({"facets": [{"id": "F1", "text": "  "}]})


def test_validate_draft_accepts_valid_sentences() -> None:
    known = frozenset({"ch_1", "ch_2"})
    sentence = {
        "id": "S1",
        "text": "The gate covers the paid routes.",
        "chunk_ids": ["ch_1", "ch_2"],
    }
    draft = validate_draft({"sentences": [sentence]}, known)
    assert len(draft) == 1
    assert draft[0].sentence_id == "S1"
    assert draft[0].chunk_ids == ("ch_1", "ch_2")


def test_validate_draft_rejects_unknown_chunk_and_bad_sentence() -> None:
    known = frozenset({"ch_1"})
    with pytest.raises(GenerationError):
        bad = {"id": "S1", "text": "A sentence.", "chunk_ids": ["ch_nope"]}
        validate_draft({"sentences": [bad]}, known)
    with pytest.raises(GenerationError):
        bad = {"id": "S1", "text": "Two sentences. Here.", "chunk_ids": ["ch_1"]}
        validate_draft({"sentences": [bad]}, known)
    with pytest.raises(GenerationError):
        validate_draft(
            {"sentences": [{"id": "S1", "text": "A sentence.", "chunk_ids": []}]},
            known,
        )
    with pytest.raises(GenerationError):
        validate_draft(
            {
                "sentences": [
                    {"id": "S1", "text": "One sentence.", "chunk_ids": ["ch_1"]},
                    {"id": "S1", "text": "Another sentence.", "chunk_ids": ["ch_1"]},
                ]
            },
            known,
        )


def test_validate_verdict_accepts_and_rejects() -> None:
    assert validate_verdict({"supported": True, "reason": "direct support"}) == (
        True,
        "direct support",
    )
    with pytest.raises(GenerationError):
        validate_verdict({"reason": "no supported value"})
    with pytest.raises(GenerationError):
        validate_verdict({"supported": False, "reason": "  "})


def test_validate_coverage_requires_one_row_per_facet() -> None:
    facets = (Facet(facet_id="F1", text="a"), Facet(facet_id="F2", text="b"))
    row_one = {
        "facet_id": "F1",
        "covered": True,
        "reason": "yes",
        "sentence_ids": ["S1"],
    }
    row_two = {
        "facet_id": "F2",
        "covered": False,
        "reason": "no",
        "sentence_ids": [],
    }
    rows = validate_coverage({"rows": [row_one, row_two]}, facets)
    assert len(rows) == 2
    with pytest.raises(GenerationError):
        validate_coverage(
            {"rows": [{"facet_id": "F1", "covered": True, "reason": "yes"}]},
            facets,
        )
    with pytest.raises(GenerationError):
        validate_coverage(
            {
                "rows": [
                    {"facet_id": "F1", "covered": True, "reason": "yes"},
                    {"facet_id": "F1", "covered": True, "reason": "again"},
                ]
            },
            facets,
        )
    with pytest.raises(GenerationError):
        validate_coverage(
            {"rows": [{"facet_id": "F9", "covered": True, "reason": "yes"}]},
            facets,
        )
