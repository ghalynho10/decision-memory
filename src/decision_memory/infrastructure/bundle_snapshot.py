"""Infrastructure: the shipped bundle's ``snapshot.json`` (spec 0014).

A bundle is a directory holding ``records/``, ``query-index/``, and a
``snapshot.json`` at its root. The snapshot carries the layout a reader needs
and the freeze point the documentation cites. Every path field in it is
relative to the snapshot file's own directory, so the bundle answers correctly
from any absolute path on any machine (AC-12).

Reading is strict in one direction only: a snapshot that is missing,
unreadable, not valid JSON, of an unrecognised ``schema_version``, or missing
or mistyping any required field is treated exactly as absent (AC-1b). One
rule, no partial acceptance, and never an exception into the query path. The
caller then falls back to the store layout convention.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

SNAPSHOT_FILENAME = "snapshot.json"
SNAPSHOT_SCHEMA_VERSION = 1
RECORDS_DIRNAME = "records"
MANIFEST_FILENAME = "manifest.json"


@dataclass(frozen=True)
class DemoQuestion:
    """One pinned question and the disposition measured for it (AC-13)."""

    question: str
    expected: str
    runs: int
    stable: int


@dataclass(frozen=True)
class BundleSnapshot:
    """The validated contents of a bundle's ``snapshot.json``."""

    schema_version: int
    generated_at: str
    commit: str
    pipeline_signature: str
    records_dir: str
    store_dir: str
    corpus_root: str
    records_indexed: int
    specs_at_freeze: int
    demo_questions: tuple[DemoQuestion, ...]


@dataclass(frozen=True)
class SnapshotLayout:
    """The absolute paths a snapshot resolves to, against its own directory."""

    records_dir: Path
    manifest_path: Path
    corpus_root: Path


def snapshot_path(bundle_root: Path) -> Path:
    """The snapshot file's path inside a bundle."""
    return bundle_root / SNAPSHOT_FILENAME


def read_snapshot(bundle_root: Path) -> BundleSnapshot | None:
    """The bundle's validated snapshot, or None when it is unusable (AC-1b).

    Every failure mode collapses to None: no file, an unreadable file, invalid
    JSON, a schema version this reader does not recognise, or a required field
    that is absent or of the wrong type. Nothing raises, because this sits on
    the query path and a broken companion file must degrade to the convention
    rather than fail a question.
    """
    path = snapshot_path(bundle_root)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    if data.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        return None
    strings = _required_strings(
        data,
        (
            "generated_at",
            "commit",
            "pipeline_signature",
            "records_dir",
            "store_dir",
            "corpus_root",
        ),
    )
    if strings is None:
        return None
    integers = _required_integers(data, ("records_indexed", "specs_at_freeze"))
    if integers is None:
        return None
    questions = _demo_questions(data.get("demo_questions"))
    if questions is None:
        return None
    return BundleSnapshot(
        schema_version=SNAPSHOT_SCHEMA_VERSION,
        generated_at=strings["generated_at"],
        commit=strings["commit"],
        pipeline_signature=strings["pipeline_signature"],
        records_dir=strings["records_dir"],
        store_dir=strings["store_dir"],
        corpus_root=strings["corpus_root"],
        records_indexed=integers["records_indexed"],
        specs_at_freeze=integers["specs_at_freeze"],
        demo_questions=questions,
    )


def snapshot_layout(bundle_root: Path) -> SnapshotLayout | None:
    """The bundle's resolved layout, or None when there is no usable snapshot.

    Each relative field resolves against the snapshot file's own directory,
    which is the bundle root, so a bundle carries no dependency on where it
    was built or where it now sits.
    """
    snapshot = read_snapshot(bundle_root)
    if snapshot is None:
        return None
    records_dir = _resolve_relative(bundle_root, snapshot.records_dir)
    return SnapshotLayout(
        records_dir=records_dir,
        manifest_path=records_dir / MANIFEST_FILENAME,
        corpus_root=_resolve_relative(bundle_root, snapshot.corpus_root),
    )


def write_snapshot(bundle_root: Path, snapshot: BundleSnapshot) -> None:
    """Write ``snapshot.json`` at the bundle root (AC-12).

    Refuses any absolute path field, so the artifact the regeneration script
    publishes cannot carry the building machine's layout even by mistake.
    """
    for field, value in (
        ("records_dir", snapshot.records_dir),
        ("store_dir", snapshot.store_dir),
        ("corpus_root", snapshot.corpus_root),
    ):
        if Path(value).is_absolute() or value.startswith("/"):
            raise ValueError(f"snapshot field {field} must be relative, got {value!r}")
    payload = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "generated_at": snapshot.generated_at,
        "commit": snapshot.commit,
        "pipeline_signature": snapshot.pipeline_signature,
        "records_dir": snapshot.records_dir,
        "store_dir": snapshot.store_dir,
        "corpus_root": snapshot.corpus_root,
        "records_indexed": snapshot.records_indexed,
        "specs_at_freeze": snapshot.specs_at_freeze,
        "demo_questions": [
            {
                "question": question.question,
                "expected": question.expected,
                "runs": question.runs,
                "stable": question.stable,
            }
            for question in snapshot.demo_questions
        ],
    }
    snapshot_path(bundle_root).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _required_strings(
    data: dict[str, object], names: tuple[str, ...]
) -> dict[str, str] | None:
    result: dict[str, str] = {}
    for name in names:
        value = data.get(name)
        if not isinstance(value, str):
            return None
        result[name] = value
    return result


def _required_integers(
    data: dict[str, object], names: tuple[str, ...]
) -> dict[str, int] | None:
    result: dict[str, int] = {}
    for name in names:
        value = data.get(name)
        # bool is an int subclass in Python; a flag here is a malformed field.
        if not isinstance(value, int) or isinstance(value, bool):
            return None
        result[name] = value
    return result


def _demo_questions(raw: object) -> tuple[DemoQuestion, ...] | None:
    if not isinstance(raw, list):
        return None
    questions: list[DemoQuestion] = []
    for item in raw:
        if not isinstance(item, dict):
            return None
        question = item.get("question")
        expected = item.get("expected")
        runs = item.get("runs")
        stable = item.get("stable")
        if not isinstance(question, str) or not isinstance(expected, str):
            return None
        if expected not in ("answered", "abstained"):
            return None
        if not isinstance(runs, int) or isinstance(runs, bool):
            return None
        if not isinstance(stable, int) or isinstance(stable, bool):
            return None
        questions.append(
            DemoQuestion(question=question, expected=expected, runs=runs, stable=stable)
        )
    return tuple(questions)


def _resolve_relative(bundle_root: Path, relative: str) -> Path:
    """Resolve one relative snapshot field against the bundle root."""
    return (bundle_root / relative).resolve()
