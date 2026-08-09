"""Starter adapter unit tests (spec 0005 AC-15, AC-16, AC-17, AC-20).

Exercises the bundled teaching adapter directly: metadata, discovery with the
valid and skipped fixtures, parsing into a valid canonical record, and the
content based fingerprint that includes the adapter version.
"""

from __future__ import annotations

import importlib
from pathlib import Path

from starter_adapter.adapter import ADAPTER_ID, ADAPTER_VERSION, StarterAdapter

from decision_memory.application.adapter import (
    DiscoveredSpec,
    DiscoveryResult,
)
from decision_memory.domain.records import Severity

_CORPUS = Path(__file__).resolve().parent.parent / "examples" / "starter-adapter"


def _adapter() -> StarterAdapter:
    return StarterAdapter()


def _discovered(spec_id: str = "valid") -> DiscoveredSpec:
    result = _adapter().discover(_CORPUS)
    for spec in result.specs:
        if spec.id == spec_id:
            return spec
    raise AssertionError(f"spec {spec_id!r} not discovered: {result}")


class TestIdentity:
    def test_adapter_id_and_version_are_nonempty(self) -> None:
        assert ADAPTER_ID == "starter-adapter"
        assert ADAPTER_VERSION
        assert _adapter().adapter_id == ADAPTER_ID
        assert _adapter().adapter_version == ADAPTER_VERSION


class TestDiscover:
    def test_missing_decisions_directory_reports_a_corpus_error(
        self,
        tmp_path: Path,
    ) -> None:
        corpus = tmp_path / "empty"
        corpus.mkdir()
        result = _adapter().discover(corpus)
        assert isinstance(result, DiscoveryResult)
        assert result.corpus_error == "no decisions/ directory"
        assert result.specs == []

    def test_discovers_the_valid_fixture_and_skips_the_skipped_fixture(
        self,
    ) -> None:
        result = _adapter().discover(_CORPUS)
        assert [spec.id for spec in result.specs] == ["valid"]
        assert [skip.path.name for skip in result.skipped] == ["skipped.md"]
        assert "Decision" in result.skipped[0].reason

    def test_contributing_file_is_the_decision_file(self) -> None:
        spec = _discovered()
        assert spec.root.name == "valid.md"
        assert spec.contributing_files == [spec.root]


class TestRecursiveDiscovery:
    """Spec 0006 AC-19: recursive discovery and the lexical collision rule."""

    def _write_decision(self, root: Path, relative: str) -> None:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "# A decision\n\n**Status**: Accepted\n\n## Context\n\nC.\n\n"
            "## Decision\n\nChosen.\n\n## Why\n\n- Because\n",
            encoding="utf-8",
        )

    def test_discovers_nested_and_flat_decision_files(self, tmp_path: Path) -> None:
        corpus = tmp_path / "corpus"
        self._write_decision(corpus, "decisions/flat.md")
        self._write_decision(corpus, "decisions/nested/deep.md")
        result = _adapter().discover(corpus)
        assert sorted(spec.id for spec in result.specs) == ["deep", "flat"]

    def test_a_collision_selects_the_lower_lexical_path(self, tmp_path: Path) -> None:
        corpus = tmp_path / "corpus"
        self._write_decision(corpus, "decisions/a/repeat.md")
        self._write_decision(corpus, "decisions/b/repeat.md")
        result = _adapter().discover(corpus)
        assert [spec.id for spec in result.specs] == ["repeat"]
        used = result.specs[0].root
        assert used == corpus / "decisions" / "a" / "repeat.md"
        assert len(result.collisions) == 1
        collision = result.collisions[0]
        assert collision.id == "repeat"
        assert [path.relative_to(corpus).as_posix() for path in collision.paths] == [
            "decisions/a/repeat.md",
            "decisions/b/repeat.md",
        ]
        assert collision.used == corpus / "decisions" / "a" / "repeat.md"


class TestParse:
    def test_valid_fixture_produces_a_valid_record(self) -> None:
        spec = _discovered()
        result = _adapter().parse(spec)
        assert result.record is not None
        assert not any(
            violation.severity == Severity.ERROR for violation in result.violations
        )
        record = result.record
        assert record.id == "valid"
        assert record.title == "Use Postgres for the catalog"
        assert record.status.value == "accepted"
        assert record.decision is not None
        assert record.decision.chosen == "Use Postgres for the catalog."
        assert record.why == ["It is transactional", "The team knows it well"]
        assert record.evidence is not None
        assert record.evidence[0].target == "decisions/valid.md"

    def test_unknown_status_is_unadaptable(self, tmp_path: Path) -> None:
        corpus = tmp_path / "corpus"
        (corpus / "decisions").mkdir(parents=True)
        (corpus / "decisions" / "draft.md").write_text(
            "# Draft\n\n**Status**: Draft\n\n## Decision\n\nSomething.\n",
            encoding="utf-8",
        )
        spec = _adapter().discover(corpus).specs[0]
        result = _adapter().parse(spec)
        assert result.record is None
        assert any(v.rule == "status.unmapped" for v in result.violations)


class TestFingerprint:
    def test_fingerprint_changes_when_only_the_version_changes(
        self,
        monkeypatch,
    ) -> None:
        # The package __init__ re-exports the adapter instance under the same
        # name as the submodule, which shadows the submodule attribute; import
        # via importlib to reach the real module for the monkeypatch.
        adapter_module = importlib.import_module("starter_adapter.adapter")
        spec = _discovered()
        before = _adapter().fingerprint(spec)
        monkeypatch.setattr(adapter_module, "ADAPTER_VERSION", "2")
        after = _adapter().fingerprint(spec)
        assert before != after

    def test_fingerprint_changes_when_the_file_changes(self, tmp_path: Path) -> None:
        corpus = tmp_path / "corpus"
        (corpus / "decisions").mkdir(parents=True)
        path = corpus / "decisions" / "one.md"
        path.write_text(
            "# One\n\n**Status**: Accepted\n\n## Decision\n\nA.\n\n## Why\n\n- x\n",
            encoding="utf-8",
        )
        adapter = _adapter()
        spec = DiscoveredSpec(
            id="one",
            root=path,
            corpus_root=corpus,
            contributing_files=[path],
        )
        before = adapter.fingerprint(spec)
        path.write_text(before.replace("A.", "B."), encoding="utf-8")
        after = adapter.fingerprint(spec)
        assert before != after
