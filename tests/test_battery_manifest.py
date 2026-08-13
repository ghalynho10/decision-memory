"""Battery manifest loading tests (spec 0010 AC-15).

The self corpus gate's expectations are data in the fixture's manifest, never
a literal in code and never prose in a spec. This suite locks the loud half of
that: every key present and recognized, every closed value known, and every
expectation the corpus cannot satisfy reported before a query runs.

A manifest written before the oracle was strengthened must stop the run rather
than quietly run the gate under the old, weaker oracle, so almost every test
here is a rejection.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from decision_memory.application.dto import QueryState
from decision_memory.application.evaluation import AbstentionCause
from decision_memory.infrastructure.battery_manifest import (
    BatteryManifestError,
    battery_corpus_root,
    load_battery,
)

_FIXTURE_MANIFEST = (
    Path(__file__).resolve().parent.parent
    / "docs"
    / "experiments"
    / "data"
    / "self-corpus-fixture"
    / "manifest.json"
)


def _manifest(*queries: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_commit": "abc1234",
        "generated": "2026-08-13",
        "excluded_specs": ["0010-abstention-verification-reliability"],
        "files": [{"path": "docs/specs/x/index.md", "sha256": "0" * 64}],
        "queries": list(queries),
    }


def _answering(**overrides: Any) -> dict[str, Any]:
    query = {
        "id": "decision",
        "text": "What was decided?",
        "expected_record": "DM-0008",
        "expected_state": "answered",
        "expected_value_paths": ["decision.chosen"],
        "expected_abstention": None,
    }
    query.update(overrides)
    return query


def _abstaining(**overrides: Any) -> dict[str, Any]:
    query = {
        "id": "reason",
        "text": "Why?",
        "expected_record": None,
        "expected_state": "abstained",
        "expected_value_paths": [],
        "expected_abstention": "uncovered_facet",
    }
    query.update(overrides)
    return query


def _write(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _reject(tmp_path: Path, payload: object, fragment: str) -> None:
    with pytest.raises(BatteryManifestError) as caught:
        load_battery(_write(tmp_path, payload))
    assert fragment in caught.value.detail


def test_a_full_manifest_loads_into_fixtures(tmp_path: Path) -> None:
    fixtures = load_battery(_write(tmp_path, _manifest(_answering(), _abstaining())))
    assert [fixture.id for fixture in fixtures] == ["decision", "reason"]

    decision = fixtures[0].oracle
    assert decision is not None
    assert decision.expected_state == QueryState.ANSWERED
    assert decision.required_record_ids == frozenset({"DM-0008"})
    assert decision.required_value_path_prefixes == ("decision.chosen",)
    assert decision.expected_abstention is None
    # A manifest battery always scopes a value path match to the sentence that
    # did the covering; the JobPilot battery keeps its whole answer rule.
    assert decision.covering_sentence_scope is True

    reason = fixtures[1].oracle
    assert reason is not None
    assert reason.expected_state == QueryState.ABSTAINED
    assert reason.expected_abstention == AbstentionCause.UNCOVERED_FACET
    assert reason.required_record_ids == frozenset()


def test_the_committed_fixture_manifest_loads(tmp_path: Path) -> None:
    """The manifest the gate actually runs is loadable by this build.

    A shape the loader refuses would fail the gate at load time, which is the
    right direction but would be found late; this finds it in the fast suite.
    """
    fixtures = load_battery(_FIXTURE_MANIFEST)
    assert [fixture.id for fixture in fixtures] == ["decision", "reason"]
    assert fixtures[1].oracle is not None
    assert fixtures[1].oracle.expected_abstention == AbstentionCause.UNCOVERED_FACET


def test_the_corpus_root_is_the_manifest_parent_directory() -> None:
    assert battery_corpus_root(_FIXTURE_MANIFEST) == _FIXTURE_MANIFEST.parent


def test_a_missing_query_key_stops_the_load(tmp_path: Path) -> None:
    """The key that would have defaulted is exactly the one AC-15 closes: a
    manifest written before the oracle was strengthened."""
    older = _answering()
    del older["expected_value_paths"]
    _reject(tmp_path, _manifest(older), "missing key(s) expected_value_paths")

    older = _abstaining()
    del older["expected_abstention"]
    _reject(tmp_path, _manifest(older), "missing key(s) expected_abstention")


def test_an_unknown_query_key_stops_the_load(tmp_path: Path) -> None:
    _reject(
        tmp_path,
        _manifest(_answering(must_state=["hybrid"])),
        "unrecognized key(s) must_state",
    )


def test_an_unknown_top_level_key_stops_the_load(tmp_path: Path) -> None:
    payload = _manifest(_answering(), _abstaining())
    payload["oracle_version"] = 2
    _reject(tmp_path, payload, "unrecognized key(s) oracle_version")


def test_a_missing_top_level_key_stops_the_load(tmp_path: Path) -> None:
    payload = _manifest(_answering())
    del payload["files"]
    _reject(tmp_path, payload, "missing key(s) files")


def test_an_unknown_abstention_cause_stops_the_load(tmp_path: Path) -> None:
    _reject(
        tmp_path,
        _manifest(_abstaining(expected_abstention="every_sentence_dropped")),
        "unrecognized expected_abstention",
    )


def test_an_unknown_state_stops_the_load(tmp_path: Path) -> None:
    """``failed`` is never an expected state: a provider hiccup is not a gate
    outcome."""
    _reject(
        tmp_path,
        _manifest(_answering(expected_state="failed")),
        "unrecognized expected_state",
    )


def test_a_cause_on_an_answering_query_stops_the_load(tmp_path: Path) -> None:
    _reject(
        tmp_path,
        _manifest(_answering(expected_abstention="uncovered_facet")),
        "sets expected_abstention on an answering query",
    )


def test_an_abstaining_query_must_name_its_cause(tmp_path: Path) -> None:
    """A null cause would be the old state only oracle, which an abstention
    caused by every sentence being dropped satisfies while proving nothing."""
    _reject(
        tmp_path,
        _manifest(_abstaining(expected_abstention=None)),
        "names no expected_abstention",
    )


def test_an_abstaining_query_cannot_carry_record_or_value_paths(
    tmp_path: Path,
) -> None:
    """An abstention cites nothing, so either constraint could only ever be
    ignored: refused rather than silently dropped."""
    _reject(
        tmp_path,
        _manifest(_abstaining(expected_record="DM-0008")),
        "names an expected_record",
    )
    _reject(
        tmp_path,
        _manifest(_abstaining(expected_value_paths=["decision.chosen"])),
        "names expected_value_paths",
    )


def test_an_answering_query_must_name_its_record(tmp_path: Path) -> None:
    _reject(
        tmp_path,
        _manifest(_answering(expected_record=None)),
        "names no expected_record",
    )


def test_malformed_values_stop_the_load(tmp_path: Path) -> None:
    _reject(tmp_path, _manifest(_answering(id="  ")), "id must be a nonempty string")
    _reject(tmp_path, _manifest(_answering(text="")), "text must be a nonempty string")
    _reject(
        tmp_path,
        _manifest(_answering(expected_value_paths="decision.chosen")),
        "expected_value_paths must be a list",
    )
    _reject(
        tmp_path,
        _manifest(_answering(expected_record=8)),
        "expected_record must be a string or null",
    )


def test_repeated_query_ids_stop_the_load(tmp_path: Path) -> None:
    _reject(
        tmp_path,
        _manifest(_answering(), _answering()),
        "repeats query id",
    )


def test_a_malformed_or_missing_file_stops_the_load(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(BatteryManifestError) as caught:
        load_battery(path)
    assert "not valid JSON" in caught.value.detail

    with pytest.raises(BatteryManifestError) as caught:
        load_battery(tmp_path / "absent.json")
    assert "cannot read battery manifest" in caught.value.detail

    _reject(tmp_path, ["not", "an", "object"], "not a JSON object")
    _reject(tmp_path, _manifest(), "queries must be a nonempty list")
