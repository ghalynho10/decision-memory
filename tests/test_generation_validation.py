"""Generation schema validation tests (spec 0007 AC-15).

The four structured outputs are validated with fixed bounds and rules: facet
counts and uniqueness, draft sentence shape and known chunk ids, entailment
verdict shape, and one coverage row per fixed facet.
"""

from __future__ import annotations

import pytest

from decision_memory.application.dto import Facet
from decision_memory.infrastructure import openai_generation
from decision_memory.infrastructure.openai_generation import (
    ANSWER_SYSTEM_PROMPT,
    CHUNK_VALUE_PATHS,
    COVERAGE_SYSTEM_PROMPT,
    FACETS_SYSTEM_PROMPT,
    GenerationError,
    _coverage_schema,
    _draft_schema,
    _evidence_block,
    _facets_schema,
    _verdict_schema,
    field_label,
    generate_answer,
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


_HEX_A = "a" * 64
_HEX_B = "b" * 64
_MARKER_A = f"ch_{_HEX_A}"
_MARKER_B = f"ch_{_HEX_B}"
_KNOWN = frozenset({_MARKER_A, _MARKER_B})


def _one(text: str, chunk_ids: list[str] | None = None) -> dict[str, object]:
    return {
        "id": "S1",
        "text": text,
        "chunk_ids": chunk_ids if chunk_ids is not None else [_MARKER_A],
    }


def _text_of(text: str, chunk_ids: list[str] | None = None) -> str:
    draft = validate_draft({"sentences": [_one(text, chunk_ids)]}, _KNOWN)
    return draft[0].text


def test_marker_never_survives_into_draft_text() -> None:
    """A bracketed group, a bare mid sentence id, and a trailing group all
    reach ``DraftSentence.text`` with no chunk id and single spaced prose,
    while ``chunk_ids`` is untouched (spec 0010 AC-13)."""
    expected = "The board approved the merger on Tuesday."
    bracketed = _one(
        f"The board approved the merger [{_MARKER_A}, {_MARKER_B}] on Tuesday.",
        [_MARKER_A, _MARKER_B],
    )
    bare = _one(f"The board approved {_MARKER_A} the merger on Tuesday.")
    trailing = _one(f"The board approved the merger on Tuesday [{_MARKER_A}].")
    for payload in (bracketed, bare, trailing):
        draft = validate_draft({"sentences": [payload]}, _KNOWN)
        assert draft[0].text == expected
        assert "ch_" not in draft[0].text
        assert draft[0].chunk_ids == tuple(payload["chunk_ids"])  # type: ignore[arg-type]


def test_marker_only_sentence_fails_as_empty_text() -> None:
    """A sentence whose whole text is a marker is empty once stripped, so it
    fails the empty text check rather than reaching output (AC-13)."""
    for text in (f"[{_MARKER_A}]", _MARKER_A, f"  [{_MARKER_A}]  "):
        with pytest.raises(GenerationError, match="empty text"):
            validate_draft({"sentences": [_one(text)]}, _KNOWN)


def test_one_sentence_check_reads_the_cleaned_text() -> None:
    """The strip runs before the one sentence check, so a sentence whose
    period was swallowed by a directly attached marker is judged on the
    cleaned string and passes (AC-13)."""
    assert _text_of(f"The board approved it.[{_MARKER_A}]") == "The board approved it."


def test_marker_regex_is_case_insensitive() -> None:
    """An uppercased hash cannot smuggle a marker through, even though
    ``chunk_id`` only ever emits lowercase (AC-13)."""
    upper = f"CH_{_HEX_A.upper()}"
    assert _text_of(f"The board approved it [{upper}].") == "The board approved it."


def test_wrong_hex_length_is_not_a_marker() -> None:
    """``ch_`` with 63 or 65 hex characters is not an id, and the word
    boundary stops a 64 character prefix match (AC-13)."""
    short = "ch_" + "a" * 63
    long = "ch_" + "a" * 65
    assert _text_of(f"The token {short} is prose.") == f"The token {short} is prose."
    assert _text_of(f"The token {long} is prose.") == f"The token {long} is prose."


def test_group_separator_tolerates_either_comma_spacing() -> None:
    """The model writes ``", "`` and the debug renderer writes ``","``, so
    both spacings parse inside one group (AC-13)."""
    tight = f"It shipped [{_MARKER_A},{_MARKER_B}]."
    spaced = f"It shipped [{_MARKER_A} , {_MARKER_B}]."
    assert _text_of(tight, [_MARKER_A, _MARKER_B]) == "It shipped."
    assert _text_of(spaced, [_MARKER_A, _MARKER_B]) == "It shipped."


def test_mixed_bracket_group_keeps_its_brackets_and_prose() -> None:
    """A bracket group holding anything besides markers and separators is not
    a marker group, so it loses only its bare marker (AC-13)."""
    assert _text_of(f"See [see {_MARKER_A}] for the rule.") == "See [see] for the rule."


def test_whitespace_repair_after_the_strip() -> None:
    """The three repair steps pin the readable prose AC-4 emits verbatim."""
    # A trailing group before a full stop leaves no space before it.
    assert _text_of(f"The store was rebuilt [{_MARKER_A}].") == "The store was rebuilt."
    # A mid sentence group leaves no space before the following comma.
    assert (
        _text_of(f"The store was rebuilt [{_MARKER_A}], then ingested.")
        == "The store was rebuilt, then ingested."
    )
    # A parenthetical with no marker in it is untouched.
    untouched = "The store was rebuilt (twice) on Tuesday."
    assert _text_of(untouched) == untouched
    # A sentence with no marker at all is returned unchanged.
    plain = "The store was rebuilt on Tuesday."
    assert _text_of(plain) == plain


def test_strip_makes_two_marked_sentences_collide_as_duplicates() -> None:
    """Two draft sentences whose prose is identical and whose markers differ
    become identical after stripping and fail the response as a duplicate.
    That reading is deliberate: the marker was never content (AC-13)."""
    with pytest.raises(GenerationError, match="repeated sentence text"):
        validate_draft(
            {
                "sentences": [
                    {
                        "id": "S1",
                        "text": f"The board approved it [{_MARKER_A}].",
                        "chunk_ids": [_MARKER_A],
                    },
                    {
                        "id": "S2",
                        "text": f"The board approved it [{_MARKER_B}].",
                        "chunk_ids": [_MARKER_B],
                    },
                ]
            },
            _KNOWN,
        )


def test_answer_prompt_forbids_a_chunk_id_inside_the_sentence_text() -> None:
    """The prompt is the soft half of AC-13: it keeps naming the real
    bracketed ids (load bearing, or a live model invents its own) while
    moving them into the ``chunk_ids`` field and out of the prose."""
    assert "chunk_ids field" in ANSWER_SYSTEM_PROMPT
    assert "Never write a chunk id inside the sentence text" in ANSWER_SYSTEM_PROMPT


def test_coverage_prompt_instructs_directness() -> None:
    """The coverage prompt must require a sentence to directly state the
    answer and forbid a reason, context, consequence, premise, or anaphoric
    fragment from covering a decision facet (spec 0010 AC-4, AC-12)."""
    assert "directly states its answer" in COVERAGE_SYSTEM_PROMPT
    assert "Do not combine sentences" in COVERAGE_SYSTEM_PROMPT
    assert "does not state a decision" in COVERAGE_SYSTEM_PROMPT


def test_coverage_prompt_excludes_a_caveat_from_covering_a_decision() -> None:
    """The AC-16 exclusion, stated to the model rather than only in the spec.

    Experiment 0004 recorded coverage accepting a sentence about what the
    evidence does not establish as the answer to a decision facet. AC-12
    already forbade it; the instruction is the soft half that tells the model
    so. The deterministic guard is deliberately not built yet and is held
    behind the AC-16 miss count.
    """
    assert (
        "A statement about what the evidence does or does not establish is a "
        "limitation, not a decision, and never covers a decision facet."
    ) in COVERAGE_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Schema property descriptions are soft guidance only (spec 0010 AC-17)
# ---------------------------------------------------------------------------


def _descriptions(schema: object, path: str = "schema") -> dict[str, str]:
    """Every ``description`` in a schema, keyed by its property path."""
    found: dict[str, str] = {}
    if isinstance(schema, dict):
        for key, value in schema.items():
            if key == "description" and isinstance(value, str):
                found[path] = value
            else:
                found.update(_descriptions(value, f"{path}.{key}"))
    elif isinstance(schema, list):
        for index, item in enumerate(schema):
            found.update(_descriptions(item, f"{path}[{index}]"))
    return found


def _without_descriptions(schema: object) -> object:
    """The same schema with every ``description`` key removed."""
    if isinstance(schema, dict):
        return {
            key: _without_descriptions(value)
            for key, value in schema.items()
            if key != "description"
        }
    if isinstance(schema, list):
        return [_without_descriptions(item) for item in schema]
    return schema


def test_only_the_ratified_description_exists_and_it_is_verbatim() -> None:
    """Exactly one schema property carries a description, and it is the text
    AC-17 pins (spec 0010 AC-17).

    A description is prompt text under another name, so its exact wording is
    a spec constant. Its validator is ``validate_coverage``, whose uncovered
    row check enforces the same rule; a second description may only be added
    under the same bound.
    """
    found: dict[str, str] = {}
    for schema in (
        _facets_schema(),
        _draft_schema(),
        _verdict_schema(),
        _coverage_schema(),
    ):
        found.update(_descriptions(schema))
    assert list(found) == ["schema.properties.rows.items.properties.sentence_ids"], (
        f"unexpected schema descriptions: {sorted(found)}"
    )
    assert found["schema.properties.rows.items.properties.sentence_ids"] == (
        "Sentence ids that directly state this facet's answer, in the order "
        "the sentences were given. Leave this empty when covered is false: "
        "never name a sentence you judged and rejected."
    )


def test_descriptions_carry_no_deterministic_weight() -> None:
    """Removing every description leaves every validator outcome unchanged
    (spec 0010 AC-17).

    This is what keeps a description guidance rather than a second contract:
    the rule it restates is enforced by ``validate_coverage``, which never
    reads the schema. The uncovered row naming a sentence, the covered row
    naming none, and the valid row are rejected or accepted identically with
    the descriptions gone.
    """
    facets = (Facet("F1", "what"), Facet("F2", "why"))
    known = ("S1", "S2")
    valid = [
        {
            "facet_id": "F1",
            "covered": True,
            "reason": "states it",
            "sentence_ids": ["S1"],
        },
        {"facet_id": "F2", "covered": False, "reason": "absent", "sentence_ids": []},
    ]
    uncovered_names_a_sentence = [
        valid[0],
        {
            "facet_id": "F2",
            "covered": False,
            "reason": "absent",
            "sentence_ids": ["S2"],
        },
    ]
    covered_names_none = [
        {"facet_id": "F1", "covered": True, "reason": "states it", "sentence_ids": []},
        valid[1],
    ]

    def outcomes() -> list[bool]:
        results: list[bool] = []
        for rows in (valid, uncovered_names_a_sentence, covered_names_none):
            try:
                validate_coverage({"rows": rows}, facets, known)
            except GenerationError:
                results.append(False)
            else:
                results.append(True)
        return results

    with_descriptions = outcomes()
    stripped = _without_descriptions(_coverage_schema())
    assert _descriptions(stripped) == {}
    # The schema is otherwise untouched, and the validator's verdicts do not
    # move: it takes the payload, the facets, and the known sentence ids, and
    # never the schema at all.
    assert stripped != _coverage_schema()
    assert outcomes() == with_descriptions == [True, False, False]


# ---------------------------------------------------------------------------
# AC-18: the chunk field label generation reads above each evidence block.
# ---------------------------------------------------------------------------


def test_field_label_covers_every_pinned_value_path() -> None:
    """Every one of the nine pinned value paths renders a nonempty label
    (spec 0010 AC-18).

    A chunk's ``value_path`` is set in exactly one place, the nine ``add()``
    calls in ``chunking.py``, so the pinned tuple and the mapping have to stay
    in step with it. ``/check review`` owns comparing the tuple against
    ``chunking.py``; this test owns the mapping covering the tuple.
    """
    labels = [field_label(value_path) for value_path in CHUNK_VALUE_PATHS]
    assert all(labels), dict(zip(CHUNK_VALUE_PATHS, labels, strict=True))
    assert len(CHUNK_VALUE_PATHS) == 9
    # The label is prose, never the dotted token: the failure class AC-18
    # exists to remove is a token no decomposition can reproduce.
    assert not any("." in label or "[" in label for label in labels)


def test_field_label_ignores_the_index() -> None:
    """The index is not rendered and the lookup ignores it, so ``why[0]`` and
    ``why[3]`` find the same entry (spec 0010 AC-18).

    An ordinal carries no meaning to a reader, and an echoed number would be
    noise in the sentence text. The transform is pinned: look up the substring
    before the first ``[`` and ignore everything from that bracket onward.
    """
    assert field_label("why[0]") == field_label("why[3]") == field_label("why[17]")
    assert field_label("why[0]") == "a reason this record gives for its decision"
    assert field_label("consequences.negative[2]") == (
        "a negative consequence this record accepts"
    )
    # A path with no bracket is looked up whole.
    assert field_label("decision.chosen") == "the decision this record chose"


def test_unmapped_value_path_omits_the_field_line() -> None:
    """An unmapped path renders no label and its block carries no ``Field:``
    line, degrading to the previous behaviour (spec 0010 AC-18).

    The fallback is deliberately not the dotted token: that would introduce
    the unmatchable token the mapping exists to avoid.
    """
    assert field_label("title") == ""
    assert field_label("supersedes") == ""
    assert field_label("something.new[0]") == ""
    block = _evidence_block(0, _MARKER_A, "supersedes", "Superseded by DM-0009.")
    assert "Field:" not in block
    assert block == f"CHUNK 0 ({_MARKER_A})\nSuperseded by DM-0009."


def test_evidence_block_matches_the_pinned_shape() -> None:
    """The block is the pinned AC-18 shape, with the chunk id still in
    parentheses (spec 0010 AC-18).

    ``ANSWER_SYSTEM_PROMPT`` says the ids are shown in brackets, which is
    inaccurate about this rendering and is deliberately left alone: rendering
    ids in brackets would put the literal marker group shape in front of a
    model that already echoes markers.
    """
    block = _evidence_block(2, _MARKER_A, "decision.chosen", "Hybrid retrieval.")
    assert block == (
        f"CHUNK 2 ({_MARKER_A})\n"
        "Field: the decision this record chose\n"
        "Hybrid retrieval."
    )
    assert "[" not in block


def test_answer_prompt_frames_a_decision_and_forbids_copying_the_field_line() -> None:
    """The AC-18 prompt half: point the model at the ``Field:`` line, ask a
    decision facet to be answered with the decision, and forbid copying the
    line into the sentence text.

    The prohibition is narrowed rather than mirrored from AC-13: the label is
    prose, so forbidding its vocabulary would forbid ordinary words the answer
    needs.
    """
    assert "Field line says which part of the record that chunk is" in (
        ANSWER_SYSTEM_PROMPT
    )
    assert "never copy a Field line into the sentence text" in ANSWER_SYSTEM_PROMPT
    assert "answer it with the decision the record chose" in ANSWER_SYSTEM_PROMPT
    assert "rather than as a description of how the system works" in (
        ANSWER_SYSTEM_PROMPT
    )


def test_record_title_never_reaches_the_generation_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The evidence block carries the id, the label, and the text, and never
    the record title (spec 0010 AC-18).

    The title is adapter extracted corpus content at the same trust level as
    the chunk text, inside a block already fenced to the model as untrusted,
    so giving it authority in the prompt adds injection surface for no gain.
    It cannot reach the prompt because generation is never given it.
    """
    captured: list[dict[str, str]] = []

    def _fake_call(concern, messages, schema, model, attempts):
        captured.extend(messages)
        return {
            "sentences": [
                {
                    "id": "S1",
                    "text": "Hybrid retrieval was chosen.",
                    "chunk_ids": [_MARKER_A],
                }
            ]
        }

    monkeypatch.setattr(openai_generation, "_structured_call", _fake_call)
    draft = generate_answer(
        (Facet("F1", "what was decided?"),),
        ((_MARKER_A, "decision.chosen", "The project chose hybrid retrieval."),),
        (),
        _KNOWN,
    )
    assert draft[0].sentence_id == "S1"
    prompt = "\n".join(message["content"] for message in captured)
    assert _MARKER_A in prompt
    assert "Field: the decision this record chose" in prompt
    assert "The project chose hybrid retrieval." in prompt
    assert "Reliable multi source retrieval" not in prompt


def test_labels_carry_no_deterministic_weight(monkeypatch: pytest.MonkeyPatch) -> None:
    """With every field label removed, every validator rejects and accepts
    exactly the same shapes (spec 0010 AC-17, AC-18).

    A label is prompt text under another name, like a schema description: it
    changes what the model is told, never what a validator decides. Nothing
    downstream of generation reads it, and ``validate_draft`` never sees the
    evidence blocks at all.
    """

    def outcomes() -> list[bool]:
        results: list[bool] = []
        for text in (
            "Hybrid retrieval was chosen.",
            f"Hybrid retrieval was chosen {_MARKER_A}.",
            "",
        ):
            try:
                validate_draft({"sentences": [_one(text)]}, _KNOWN)
            except GenerationError:
                results.append(False)
            else:
                results.append(True)
        return results

    with_labels = outcomes()
    monkeypatch.setattr(openai_generation, "FIELD_LABELS", {})
    assert all(field_label(path) == "" for path in CHUNK_VALUE_PATHS)
    assert "Field:" not in _evidence_block(0, _MARKER_A, "decision.chosen", "text")
    assert outcomes() == with_labels == [True, True, False]
