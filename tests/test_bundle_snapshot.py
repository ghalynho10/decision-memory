"""Bundle snapshot reading and store path resolution (spec 0014).

Covers the snapshot schema and its strict validate or treat as absent rule
(AC-1b, AC-12), and the three step resolution order for the records manifest
and the corpus root (AC-1, AC-1c). No store is involved: these are the pure
path rules the reader wires in, tested against fixtures on disk.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from decision_memory.infrastructure.bundle_snapshot import (
    BundleSnapshot,
    DemoQuestion,
    read_snapshot,
    snapshot_layout,
    write_snapshot,
)
from decision_memory.infrastructure.store_resolution import (
    resolve_corpus_root,
    resolve_manifest_path,
)


def _snapshot(**overrides: object) -> dict[str, object]:
    """A structurally valid snapshot payload, overridable field by field."""
    payload: dict[str, object] = {
        "schema_version": 1,
        "generated_at": "2026-08-15T00:00:00Z",
        "commit": "abc1234",
        "pipeline_signature": "sig",
        "records_dir": "records",
        "store_dir": "query-index",
        "corpus_root": "../..",
        "records_indexed": 10,
        "specs_at_freeze": 13,
        "demo_questions": [
            {
                "question": "why?",
                "expected": "answered",
                "runs": 10,
                "stable": 10,
            }
        ],
    }
    payload.update(overrides)
    return payload


def _write(bundle: Path, payload: object) -> Path:
    bundle.mkdir(parents=True, exist_ok=True)
    path = bundle / "snapshot.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_valid_snapshot_reads_every_field(tmp_path: Path) -> None:
    bundle = tmp_path / "self-index"
    _write(bundle, _snapshot())
    snapshot = read_snapshot(bundle)
    assert snapshot is not None
    assert snapshot.commit == "abc1234"
    assert snapshot.records_indexed == 10
    assert snapshot.specs_at_freeze == 13
    assert snapshot.demo_questions == (
        DemoQuestion(question="why?", expected="answered", runs=10, stable=10),
    )


def test_layout_resolves_relative_to_the_snapshot_file(tmp_path: Path) -> None:
    """Every path field resolves against the bundle root, not the process cwd."""
    bundle = tmp_path / "nested" / "self-index"
    _write(bundle, _snapshot())
    layout = snapshot_layout(bundle)
    assert layout is not None
    assert layout.records_dir == (bundle / "records").resolve()
    assert layout.manifest_path == (bundle / "records" / "manifest.json").resolve()
    assert layout.corpus_root == tmp_path.resolve()


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param("not json at all", id="invalid-json"),
        pytest.param(["a", "list"], id="not-an-object"),
        pytest.param(_snapshot(schema_version=2), id="unrecognised-version"),
        pytest.param(_snapshot(schema_version="1"), id="version-wrong-type"),
    ],
)
def test_unusable_snapshot_reads_as_absent(tmp_path: Path, payload: object) -> None:
    """AC-1b: one rule, no partial acceptance, and never an exception."""
    bundle = tmp_path / "self-index"
    bundle.mkdir()
    if isinstance(payload, str):
        (bundle / "snapshot.json").write_text(payload, encoding="utf-8")
    else:
        _write(bundle, payload)
    assert read_snapshot(bundle) is None
    assert snapshot_layout(bundle) is None


@pytest.mark.parametrize(
    "field",
    [
        "generated_at",
        "commit",
        "pipeline_signature",
        "records_dir",
        "store_dir",
        "corpus_root",
        "records_indexed",
        "specs_at_freeze",
        "demo_questions",
    ],
)
def test_a_missing_required_field_reads_as_absent(tmp_path: Path, field: str) -> None:
    """Valid JSON at version 1 but short one field is still treated as absent."""
    bundle = tmp_path / "self-index"
    payload = _snapshot()
    del payload[field]
    _write(bundle, payload)
    assert read_snapshot(bundle) is None


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"records_dir": 3}, id="path-not-a-string"),
        pytest.param({"records_indexed": "10"}, id="count-not-an-int"),
        pytest.param({"records_indexed": True}, id="count-is-a-bool"),
        pytest.param({"demo_questions": {}}, id="questions-not-a-list"),
        pytest.param(
            {"demo_questions": [{"question": "q", "expected": "maybe"}]},
            id="unknown-disposition",
        ),
        pytest.param(
            {"demo_questions": [{"question": "q", "expected": "answered"}]},
            id="question-missing-counts",
        ),
    ],
)
def test_a_mistyped_field_reads_as_absent(
    tmp_path: Path, overrides: dict[str, object]
) -> None:
    bundle = tmp_path / "self-index"
    _write(bundle, _snapshot(**overrides))
    assert read_snapshot(bundle) is None


def test_absent_file_reads_as_absent(tmp_path: Path) -> None:
    assert read_snapshot(tmp_path / "nothing-here") is None
    assert snapshot_layout(tmp_path / "nothing-here") is None


def test_written_snapshot_round_trips(tmp_path: Path) -> None:
    bundle = tmp_path / "self-index"
    bundle.mkdir()
    original = BundleSnapshot(
        schema_version=1,
        generated_at="2026-08-15T12:00:00Z",
        commit="deadbee",
        pipeline_signature="sig",
        records_dir="records",
        store_dir="query-index",
        corpus_root="../..",
        records_indexed=10,
        specs_at_freeze=13,
        demo_questions=(
            DemoQuestion(question="a", expected="answered", runs=10, stable=10),
            DemoQuestion(question="b", expected="abstained", runs=10, stable=10),
        ),
    )
    write_snapshot(bundle, original)
    assert read_snapshot(bundle) == original


def test_writing_an_absolute_path_field_is_refused(tmp_path: Path) -> None:
    """AC-12: no absolute path may reach the published file, even by mistake."""
    bundle = tmp_path / "self-index"
    bundle.mkdir()
    snapshot = BundleSnapshot(
        schema_version=1,
        generated_at="2026-08-15T12:00:00Z",
        commit="deadbee",
        pipeline_signature="sig",
        records_dir="/Users/someone/records",
        store_dir="query-index",
        corpus_root="../..",
        records_indexed=10,
        specs_at_freeze=13,
        demo_questions=(),
    )
    with pytest.raises(ValueError, match="records_dir"):
        write_snapshot(bundle, snapshot)


def test_snapshot_json_holds_no_absolute_path(tmp_path: Path) -> None:
    bundle = tmp_path / "self-index"
    bundle.mkdir()
    write_snapshot(
        bundle,
        BundleSnapshot(
            schema_version=1,
            generated_at="2026-08-15T12:00:00Z",
            commit="deadbee",
            pipeline_signature="sig",
            records_dir="records",
            store_dir="query-index",
            corpus_root="../..",
            records_indexed=10,
            specs_at_freeze=13,
            demo_questions=(),
        ),
    )
    written = json.loads((bundle / "snapshot.json").read_text(encoding="utf-8"))
    for key in ("records_dir", "store_dir", "corpus_root"):
        assert not Path(str(written[key])).is_absolute()


# Resolution order (AC-1, AC-1c): stored path, then snapshot, then convention.


def test_manifest_resolution_prefers_a_stored_path_that_exists(tmp_path: Path) -> None:
    stored = tmp_path / "elsewhere" / "manifest.json"
    stored.parent.mkdir(parents=True)
    stored.write_text("{}", encoding="utf-8")
    store_dir = tmp_path / "bundle" / "query-index"
    store_dir.mkdir(parents=True)
    assert resolve_manifest_path(store_dir, str(stored)) == stored


def test_manifest_resolution_falls_back_to_the_snapshot(tmp_path: Path) -> None:
    """A stored path from another machine does not exist here, so the snapshot wins."""
    bundle = tmp_path / "bundle"
    store_dir = bundle / "query-index"
    store_dir.mkdir(parents=True)
    _write(bundle, _snapshot())
    resolved = resolve_manifest_path(store_dir, "/build/machine/records/manifest.json")
    assert resolved == (bundle / "records" / "manifest.json").resolve()


def test_manifest_resolution_falls_back_to_the_convention(tmp_path: Path) -> None:
    """No usable stored path and no snapshot: the default store layout applies."""
    bundle = tmp_path / "bundle"
    store_dir = bundle / "query-index"
    store_dir.mkdir(parents=True)
    assert resolve_manifest_path(store_dir, "") == (
        bundle / "records" / "manifest.json"
    )
    assert resolve_manifest_path(store_dir, None) == (
        bundle / "records" / "manifest.json"
    )


def test_corpus_root_prefers_a_stored_hint_that_exists(tmp_path: Path) -> None:
    hint = tmp_path / "checkout"
    hint.mkdir()
    store_dir = tmp_path / "bundle" / "query-index"
    store_dir.mkdir(parents=True)
    assert resolve_corpus_root(store_dir, str(hint)) == hint


def test_corpus_root_falls_back_to_the_snapshot(tmp_path: Path) -> None:
    bundle = tmp_path / "clone" / "examples" / "self-index"
    store_dir = bundle / "query-index"
    store_dir.mkdir(parents=True)
    _write(bundle, _snapshot())
    resolved = resolve_corpus_root(store_dir, "/build/machine/checkout")
    assert resolved == (tmp_path / "clone").resolve()


def test_corpus_root_falls_back_to_the_convention(tmp_path: Path) -> None:
    """AC-1c: a relocated ordinary store still resolves its citations."""
    project = tmp_path / "project"
    store_dir = project / ".decision-memory" / "query-index"
    store_dir.mkdir(parents=True)
    assert resolve_corpus_root(store_dir, "") == project
    assert resolve_corpus_root(store_dir, None) == project


def test_a_broken_snapshot_does_not_break_resolution(tmp_path: Path) -> None:
    """AC-1b: a corrupt companion file degrades to the convention, never raises."""
    bundle = tmp_path / "bundle"
    store_dir = bundle / "query-index"
    store_dir.mkdir(parents=True)
    (bundle / "snapshot.json").write_text("{ not json", encoding="utf-8")
    assert resolve_manifest_path(store_dir, None) == (
        bundle / "records" / "manifest.json"
    )
    assert resolve_corpus_root(store_dir, None) == tmp_path
