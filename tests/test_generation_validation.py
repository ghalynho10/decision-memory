"""Generation schema validation tests (spec 0007 AC-15).

The four structured outputs are validated with fixed bounds and rules: facet
counts and uniqueness, draft sentence shape and known chunk ids, entailment
verdict shape, and one coverage row per fixed facet.
"""

from __future__ import annotations

import pytest

from decision_memory.application.dto import Facet
from decision_memory.infrastructure.openai_generation import (
    ANSWER_SYSTEM_PROMPT,
    COVERAGE_SYSTEM_PROMPT,
    FACETS_SYSTEM_PROMPT,
    GenerationError,
    _coverage_schema,
    _draft_schema,
    _facets_schema,
    _verdict_schema,
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
    rows = validate_coverage({"rows": [row_one, row_two]}, facets, ("S1",))
    assert len(rows) == 2
    with pytest.raises(GenerationError):
        validate_coverage(
            {"rows": [{"facet_id": "F1", "covered": True, "reason": "yes"}]},
            facets,
            ("S1",),
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
            ("S1",),
        )
    with pytest.raises(GenerationError):
        validate_coverage(
            {"rows": [{"facet_id": "F9", "covered": True, "reason": "yes"}]},
            facets,
            ("S1",),
        )


def test_validate_coverage_enforces_order_and_sentence_references() -> None:
    """Coverage rows must be in canonical facet order, and sentence ids must
    be known, unique, in kept order, and present only on covered rows
    (spec 0010 AC-12)."""
    facets = (Facet(facet_id="F1", text="a"), Facet(facet_id="F2", text="b"))
    known = ("S1", "S2")
    valid = [
        {
            "facet_id": "F1",
            "covered": True,
            "reason": "yes",
            "sentence_ids": ["S1", "S2"],
        },
        {"facet_id": "F2", "covered": False, "reason": "no", "sentence_ids": []},
    ]
    assert len(validate_coverage({"rows": valid}, facets, known)) == 2

    def reject(rows: list[dict]) -> None:
        with pytest.raises(GenerationError):
            validate_coverage({"rows": rows}, facets, known)

    # Facet rows out of canonical order are rejected.
    reject(
        [
            {"facet_id": "F2", "covered": False, "reason": "no", "sentence_ids": []},
            {
                "facet_id": "F1",
                "covered": True,
                "reason": "yes",
                "sentence_ids": ["S1"],
            },
        ]
    )
    # An unknown sentence id is rejected.
    reject(
        [
            {
                "facet_id": "F1",
                "covered": True,
                "reason": "yes",
                "sentence_ids": ["S9"],
            },
            {"facet_id": "F2", "covered": False, "reason": "no", "sentence_ids": []},
        ]
    )
    # A repeated sentence id is rejected.
    reject(
        [
            {
                "facet_id": "F1",
                "covered": True,
                "reason": "yes",
                "sentence_ids": ["S1", "S1"],
            },
            {"facet_id": "F2", "covered": False, "reason": "no", "sentence_ids": []},
        ]
    )
    # Sentence ids out of kept order are rejected.
    reject(
        [
            {
                "facet_id": "F1",
                "covered": True,
                "reason": "yes",
                "sentence_ids": ["S2", "S1"],
            },
            {"facet_id": "F2", "covered": False, "reason": "no", "sentence_ids": []},
        ]
    )
    # A covered row with no sentence id is rejected.
    reject(
        [
            {"facet_id": "F1", "covered": True, "reason": "yes", "sentence_ids": []},
            {"facet_id": "F2", "covered": False, "reason": "no", "sentence_ids": []},
        ]
    )
    # An uncovered row with sentence ids is rejected.
    reject(
        [
            {
                "facet_id": "F1",
                "covered": True,
                "reason": "yes",
                "sentence_ids": ["S1"],
            },
            {
                "facet_id": "F2",
                "covered": False,
                "reason": "no",
                "sentence_ids": ["S2"],
            },
        ]
    )


def _assert_strict_object(schema: object, path: str) -> None:
    """OpenAI strict structured output rules for one object (regression).

    A live gpt-4o call rejects a schema with a 400 unless every object sets
    ``additionalProperties: false`` and lists every property as required.
    The deterministic fakes never hit the API, so this is the only guard.
    """
    assert isinstance(schema, dict), f"{path} is not an object"
    assert schema.get("type") == "object", f"{path} is not typed object"
    assert schema.get("additionalProperties") is False, (
        f"{path} lacks additionalProperties false"
    )
    properties = schema.get("properties")
    required = schema.get("required", [])
    assert isinstance(properties, dict), f"{path} lacks properties"
    assert set(required) == set(properties), f"{path} properties not all required"
    for name, child in properties.items():
        if isinstance(child, dict) and child.get("type") == "object":
            _assert_strict_object(child, f"{path}.{name}")


def test_generation_schemas_are_strict_output_conformant() -> None:
    """Every structured output schema passes OpenAI strict mode (regression).

    This regression came from a live 400: the schemas omitted
    ``additionalProperties: false`` and the coverage schema had an optional
    ``sentence_ids`` field, which strict mode rejects.
    """
    for schema in (
        _facets_schema(),
        _draft_schema(),
        _verdict_schema(),
        _coverage_schema(),
    ):
        _assert_strict_object(schema, "schema")


def test_facets_prompt_instructs_f_ids() -> None:
    """The facets prompt must state the F1, F2 id convention the validator
    enforces, or a live model returns ids like 1 and 2 and every validation
    attempt fails (regression)."""
    assert "F1, F2" in FACETS_SYSTEM_PROMPT


def test_answer_prompt_instructs_s_ids_and_bracket_chunk_ids() -> None:
    """The answer prompt must state the S1, S2 id convention and give the
    model the real chunk ids to cite, or a live model invents ids and cites
    nothing valid (regression)."""
    assert "S1, S2" in ANSWER_SYSTEM_PROMPT
    assert "brackets" in ANSWER_SYSTEM_PROMPT


def test_coverage_prompt_instructs_directness() -> None:
    """The coverage prompt must require a sentence to directly state the
    answer and forbid a reason, context, consequence, premise, or anaphoric
    fragment from covering a decision facet (spec 0010 AC-4, AC-12)."""
    assert "directly states its answer" in COVERAGE_SYSTEM_PROMPT
    assert "Do not combine sentences" in COVERAGE_SYSTEM_PROMPT
    assert "does not state a decision" in COVERAGE_SYSTEM_PROMPT
