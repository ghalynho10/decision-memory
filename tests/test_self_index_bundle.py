"""The committed self index bundle must match the pipeline that reads it.

Spec 0014 AC-9. This runs in the default suite, with no API key, on every push.
It is the whole reason a committed binary is safe to ship: the risk is silent
rot when chunking or embedding changes, and a check that runs every suite
catches that where a one time human review would not.

It also holds AC-6 (no absolute path in the shipped store), AC-7 (the bundle
has the shape the reader expects), and AC-8 (every file the bundle needs is
tracked by git, which catches a missed ``.bin`` or a negation written against
a stale generation id).

Every test here skips with a stated reason when the bundle is absent. A source
tarball or a sparse checkout has no bundle, and a missing bundle is not a
broken one.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path

import pytest

from decision_memory.application.adapter import semantic_manifest_digest
from decision_memory.application.dto import ResolutionState
from decision_memory.application.pipeline import pipeline_signature
from decision_memory.infrastructure.bundle_snapshot import read_snapshot
from decision_memory.infrastructure.index_reader import SqliteChromaIndexReader
from decision_memory.infrastructure.manifest_reader import load_manifest, manifest_path
from decision_memory.infrastructure.store import generation_paths, read_active
from decision_memory.infrastructure.store_resolution import store_resolution

REPO_ROOT = Path(__file__).resolve().parent.parent
BUNDLE = REPO_ROOT / "examples" / "self-index"
RECORDS_DIR = BUNDLE / "records"
STORE_DIR = BUNDLE / "query-index"
LOCK_DATABASE = "lock.sqlite3"

_ABSENT = (
    "the self index bundle is not present in this checkout; a missing bundle "
    "is not a broken one (source tarball or sparse checkout)"
)


def _require_bundle() -> None:
    if not BUNDLE.is_dir() or not STORE_DIR.is_dir():
        pytest.skip(_ABSENT)


def _metadata_row() -> tuple[list[str], tuple[object, ...]]:
    """Every column of the shipped store's single ``index_metadata`` row."""
    generation_id = read_active(STORE_DIR)
    assert generation_id is not None, "the shipped store has no active generation"
    database, _generation_json, _chroma = generation_paths(STORE_DIR, generation_id)
    connection = sqlite3.connect(database)
    try:
        cursor = connection.execute("SELECT * FROM index_metadata WHERE id = 1")
        columns = [description[0] for description in cursor.description]
        row = cursor.fetchone()
    finally:
        connection.close()
    assert row is not None, "the shipped store has no metadata row"
    return columns, tuple(row)


def _is_absolute_on_any_platform(value: str) -> bool:
    """Absolute on POSIX or Windows, so the check does not depend on the host."""
    if not value:
        return False
    if value.startswith("/") or value.startswith("\\"):
        return True
    if len(value) >= 2 and value[1] == ":" and value[0].isalpha():
        return True
    return Path(value).is_absolute()


# AC-9: the guard.


def test_stored_pipeline_signature_matches_the_running_one() -> None:
    """A pipeline change must fail the build, not degrade a reader's answer.

    The expected value is computed live and never copied into this test as a
    constant, so the assertion cannot go stale alongside the thing it guards.
    """
    _require_bundle()
    reader = SqliteChromaIndexReader(STORE_DIR)
    assert reader.pipeline_signature() == pipeline_signature()


def test_stored_semantic_digest_matches_the_committed_manifest() -> None:
    """The records and the index in the bundle must not have drifted apart."""
    _require_bundle()
    reader = SqliteChromaIndexReader(STORE_DIR)
    stored_semantic = reader.manifest_metadata()[1]
    committed = load_manifest(manifest_path(RECORDS_DIR))
    assert stored_semantic == semantic_manifest_digest(committed)


def test_snapshot_parses_and_passes_the_readers_own_validation() -> None:
    """A corrupted snapshot fails the build rather than degrading citations.

    The reader treats an invalid snapshot as absent and falls back silently,
    which is right at query time and wrong at build time, so the same
    validation is asserted here where it can still fail loudly.
    """
    _require_bundle()
    snapshot = read_snapshot(BUNDLE)
    assert snapshot is not None, "the committed snapshot.json is missing or invalid"
    assert snapshot.records_dir == "records"
    assert snapshot.store_dir == "query-index"
    assert snapshot.corpus_root == "../.."
    assert snapshot.records_indexed > 0
    assert snapshot.specs_at_freeze >= snapshot.records_indexed
    assert snapshot.demo_questions, "the snapshot pins no demo questions"
    for question in snapshot.demo_questions:
        assert question.stable == question.runs, (
            f"{question.question!r} published at {question.stable}/{question.runs}, "
            "which AC-13 forbids"
        )


def test_snapshot_records_the_pipeline_it_was_built_under() -> None:
    _require_bundle()
    snapshot = read_snapshot(BUNDLE)
    assert snapshot is not None
    assert snapshot.pipeline_signature == pipeline_signature()


# AC-6: no absolute path may ship.


def test_the_shipped_store_holds_no_absolute_path() -> None:
    """Every column of the metadata row, not only the two that are blanked.

    Reading the whole row rather than the two known fields is deliberate: the
    point is to remove the disclosure class, so a path arriving in a column
    nobody thought about must fail too.
    """
    _require_bundle()
    columns, row = _metadata_row()
    for name, value in zip(columns, row, strict=True):
        if isinstance(value, str):
            assert not _is_absolute_on_any_platform(value), (
                f"index_metadata.{name} holds an absolute path: {value!r}"
            )


def test_the_two_path_columns_ship_empty() -> None:
    _require_bundle()
    columns, row = _metadata_row()
    values = dict(zip(columns, row, strict=True))
    assert values["records_manifest_path"] == ""
    assert values["source_root_hint"] == ""


def test_the_committed_manifest_holds_no_absolute_path() -> None:
    """The manifest ships too, and ``adapt`` writes an absolute root into it.

    ``source_root_hint`` is blanked before ingest by the regeneration script,
    because the field is inside the semantic digest: blanking it afterwards
    would leave the stored digest computed over the old value and the bundle
    would read ``DRIFT`` against its own manifest.
    """
    _require_bundle()
    raw = json.loads(manifest_path(RECORDS_DIR).read_text(encoding="utf-8"))
    assert raw["source_root_hint"] == ""
    for entry in raw["entries"]:
        for contributing in entry["contributing_files"]:
            assert not _is_absolute_on_any_platform(contributing)


# AC-5 through the shipped bundle: citations must resolve, not go quiet.


def test_shipped_citations_resolve_through_the_corpus_root_fallback() -> None:
    """An empty hint is ``HINT_UNAVAILABLE``, which is silent, so assert it here.

    Without this, a snapshot whose ``corpus_root`` is wrong would degrade every
    citation to unresolvable while the guard above still passed, and nothing
    would fail. That is the more dangerous failure of the two, because it looks
    like success.
    """
    _require_bundle()
    reader = SqliteChromaIndexReader(STORE_DIR)
    resolved_hint = reader.manifest_metadata()[3]
    assert resolved_hint, "the corpus root fallback produced no hint at all"
    assert Path(resolved_hint).resolve() == REPO_ROOT.resolve(), (
        "the shipped bundle's corpus root does not resolve to this checkout"
    )

    resolution = store_resolution(reader.manifest_metadata)
    manifest = load_manifest(manifest_path(RECORDS_DIR))
    checked = 0
    for entry in manifest.entries:
        for contributing in entry.contributing_files:
            state = resolution.resolve_source(contributing)
            assert state is ResolutionState.RESOLVED, (
                f"{contributing} resolved {state.value}, not resolved"
            )
            checked += 1
    assert checked > 0, "no contributing file was checked"


def test_the_shipped_bundle_resolves_its_own_manifest() -> None:
    """AC-1: the stored path is empty, so resolution must find it another way."""
    _require_bundle()
    reader = SqliteChromaIndexReader(STORE_DIR)
    resolved = reader.manifest_metadata()[0]
    assert resolved is not None
    assert Path(resolved) == manifest_path(RECORDS_DIR).resolve()


# AC-7 and AC-8: the bundle's shape, and everything it needs is tracked.


def test_the_bundle_has_the_shape_the_reader_expects() -> None:
    _require_bundle()
    assert (BUNDLE / "snapshot.json").is_file()
    assert manifest_path(RECORDS_DIR).is_file()
    assert (STORE_DIR / "FORMAT").is_file()
    assert (STORE_DIR / "ACTIVE").is_file()


def test_every_file_the_bundle_needs_is_tracked_by_git() -> None:
    """AC-8: proved by comparison, not assumed from reading the ignore rules.

    Two existing patterns collide with the bundle: ``*.sqlite3`` catches the
    records and Chroma databases, and ``*.bin`` catches the four HNSW segments,
    which are the vector index itself. Both directory levels underneath are
    fresh UUIDs on every regeneration, so a negation written against a stale
    generation id would silently commit a bundle with no vectors in it. This
    compares the two sets instead of trusting the patterns.
    """
    _require_bundle()
    try:
        completed = subprocess.run(
            ["git", "ls-files", "--", str(BUNDLE.relative_to(REPO_ROOT))],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        pytest.skip(f"git is not available to check tracking: {error}")

    tracked = {line for line in completed.stdout.splitlines() if line}
    on_disk = {
        path.relative_to(REPO_ROOT).as_posix()
        for path in BUNDLE.rglob("*")
        if path.is_file() and path.name != LOCK_DATABASE
    }
    assert on_disk, "the bundle directory holds no files"
    assert on_disk == tracked, (
        "the files the bundle needs and the files git tracks differ; "
        f"untracked: {sorted(on_disk - tracked)}; "
        f"tracked but absent: {sorted(tracked - on_disk)}"
    )


def test_the_four_vector_segments_are_present_and_tracked() -> None:
    """The ``.bin`` HNSW segments are the vector index; without them there is none."""
    _require_bundle()
    segments = sorted(path.name for path in STORE_DIR.rglob("*.bin"))
    assert segments == [
        "data_level0.bin",
        "header.bin",
        "length.bin",
        "link_lists.bin",
    ], f"expected the four HNSW segments, found {segments}"


def test_the_lock_database_is_not_committed() -> None:
    """AC-7: asking a question must never dirty the working tree."""
    _require_bundle()
    try:
        completed = subprocess.run(
            ["git", "ls-files", "--", str(BUNDLE.relative_to(REPO_ROOT))],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        pytest.skip(f"git is not available to check tracking: {error}")
    assert not [
        line for line in completed.stdout.splitlines() if line.endswith(LOCK_DATABASE)
    ]
