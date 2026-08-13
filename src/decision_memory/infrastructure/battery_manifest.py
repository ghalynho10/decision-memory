"""Infrastructure: strict loading of a fixture battery manifest (spec 0010).

The self corpus gate's queries and their expectations live in the fixture's
own ``manifest.json``, outside ``docs/specs/`` entirely, so no spec can become
a source for the answer its own gate checks (AC-14). This module turns that
file into the application's ``EvaluationFixture`` values, and refuses anything
it does not fully recognize.

Loading is deliberately loud (AC-15). Every key must be present on every
query, including the ones that do not apply, written as ``null`` or ``[]``. A
manifest written before the oracle was strengthened therefore stops the run
rather than quietly running the gate under the old, weaker oracle, which is
the exact failure this loader exists to close. The same reasoning rules out
defaulting a missing key: a silently weakened gate reports success it has not
measured.

Two rules are stricter than the manifest shape alone requires, for the same
reason: an abstaining query must name its expected cause (a null cause would
be the old state only oracle), and an abstaining query may not carry an
expected record or value paths (an abstention names no record, so those
constraints could only ever be ignored).

The corpus root for a battery run is the manifest's parent directory, since
the manifest lives inside the fixture it describes; ``battery_corpus_root``
is the one place that is decided.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from decision_memory.application.dto import QueryState
from decision_memory.application.evaluation import (
    AbstentionCause,
    EvaluationFixture,
    FixtureKind,
    QueryOracle,
)

# Every key the loader recognizes, at both levels. Anything outside these sets
# stops the load: an unknown key is either a typo or a shape this build does
# not implement, and both are safer read as a broken manifest than ignored.
MANIFEST_KEYS = frozenset(
    {"source_commit", "generated", "excluded_specs", "files", "queries"}
)
QUERY_KEYS = frozenset(
    {
        "id",
        "text",
        "expected_record",
        "expected_state",
        "expected_value_paths",
        "expected_abstention",
    }
)

_STATES = {state.value: state for state in QueryState if state != QueryState.FAILED}
_CAUSES = {cause.value: cause for cause in AbstentionCause}


class BatteryManifestError(Exception):
    """A battery manifest that cannot be loaded, with a legible detail.

    Follows the project's manifest error pattern (see
    ``ConformanceManifestError``): one exception type per manifest kind,
    carrying sanitized text the CLI reports as a usage error.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def battery_corpus_root(manifest_path: Path) -> Path:
    """The corpus root a battery run adapts: the manifest's parent directory.

    Not a separate argument, because the manifest lives inside the fixture it
    describes. A battery run against some other corpus adapts and ingests
    happily and then fails on record ids and citations, which looks like a
    broken pipeline and is not one.
    """
    return manifest_path.parent


def load_battery(manifest_path: Path) -> tuple[EvaluationFixture, ...]:
    """Read a battery manifest into fixtures, or raise ``BatteryManifestError``."""
    try:
        raw = manifest_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BatteryManifestError(
            f"cannot read battery manifest {manifest_path}: {exc.strerror}"
        ) from None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BatteryManifestError(
            f"battery manifest {manifest_path} is not valid JSON: line {exc.lineno}"
        ) from None
    if not isinstance(payload, dict):
        raise BatteryManifestError(
            f"battery manifest {manifest_path} is not a JSON object"
        )
    _require_exact_keys(payload, MANIFEST_KEYS, "manifest")

    queries = payload["queries"]
    if not isinstance(queries, list) or not queries:
        raise BatteryManifestError("manifest queries must be a nonempty list")
    fixtures: list[EvaluationFixture] = []
    seen: set[str] = set()
    for index, query in enumerate(queries):
        if not isinstance(query, dict):
            raise BatteryManifestError(f"manifest query {index} is not an object")
        fixture = _fixture_from(query, index)
        if fixture.id in seen:
            raise BatteryManifestError(f"manifest repeats query id {fixture.id!r}")
        seen.add(fixture.id)
        fixtures.append(fixture)
    return tuple(fixtures)


def _require_exact_keys(
    payload: Mapping[str, Any], expected: frozenset[str], label: str
) -> None:
    """Every expected key present and no other, or raise."""
    present = frozenset(payload)
    missing = sorted(expected - present)
    unknown = sorted(present - expected)
    if missing:
        raise BatteryManifestError(f"{label} is missing key(s) {', '.join(missing)}")
    if unknown:
        raise BatteryManifestError(
            f"{label} carries unrecognized key(s) {', '.join(unknown)}"
        )


def _fixture_from(query: Mapping[str, Any], index: int) -> EvaluationFixture:
    """One manifest query as a fixture, with every value checked."""
    _require_exact_keys(query, QUERY_KEYS, f"manifest query {index}")
    query_id = _nonempty_string(query["id"], f"manifest query {index} id")
    label = f"query {query_id!r}"
    text = _nonempty_string(query["text"], f"{label} text")

    state_raw = query["expected_state"]
    if not isinstance(state_raw, str) or state_raw not in _STATES:
        raise BatteryManifestError(
            f"{label} has unrecognized expected_state {state_raw!r}; "
            f"expected one of {', '.join(sorted(_STATES))}"
        )
    state = _STATES[state_raw]

    cause_raw = query["expected_abstention"]
    cause: AbstentionCause | None = None
    if cause_raw is not None:
        if not isinstance(cause_raw, str) or cause_raw not in _CAUSES:
            raise BatteryManifestError(
                f"{label} has unrecognized expected_abstention {cause_raw!r}; "
                f"expected one of {', '.join(sorted(_CAUSES))} or null"
            )
        cause = _CAUSES[cause_raw]

    record = query["expected_record"]
    if record is not None and not isinstance(record, str):
        raise BatteryManifestError(f"{label} expected_record must be a string or null")
    prefixes_raw = query["expected_value_paths"]
    if not isinstance(prefixes_raw, list) or not all(
        isinstance(item, str) and item.strip() for item in prefixes_raw
    ):
        raise BatteryManifestError(
            f"{label} expected_value_paths must be a list of nonempty strings"
        )
    prefixes = tuple(prefixes_raw)

    if state == QueryState.ANSWERED:
        if cause is not None:
            raise BatteryManifestError(
                f"{label} sets expected_abstention on an answering query; the "
                "cause could only ever be ignored there"
            )
        if not record:
            raise BatteryManifestError(
                f"{label} expects an answer but names no expected_record"
            )
    else:
        if cause is None:
            raise BatteryManifestError(
                f"{label} expects an abstention but names no "
                "expected_abstention; a state only expectation is satisfied by "
                "an abstention that proves nothing about abstention"
            )
        if record is not None:
            raise BatteryManifestError(
                f"{label} expects an abstention but names an expected_record; "
                "an abstention cites no record"
            )
        if prefixes:
            raise BatteryManifestError(
                f"{label} expects an abstention but names expected_value_paths; "
                "an abstention carries no citations to match them against"
            )

    return EvaluationFixture(
        id=query_id,
        kind=FixtureKind.QUERY,
        question=text,
        oracle=QueryOracle(
            expected_state=state,
            required_record_ids=frozenset({record}) if record else frozenset(),
            required_value_path_prefixes=prefixes,
            expected_abstention=cause,
            # A manifest battery always scopes a value path match to the
            # sentence that did the covering (AC-15). The JobPilot battery
            # keeps the whole answer semantics it already had.
            covering_sentence_scope=True,
        ),
    )


def _nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BatteryManifestError(f"{label} must be a nonempty string")
    return value
