"""Manifest loading boundary tests (spec 0006 AC-2, AC-3, AC-4).

Every manifest failure exits 1 and names the failing field or path. These
tests drive the strict loader directly and assert the fixed rule id
(``manifest.load``, ``manifest.schema``, or ``manifest.paths``) and that the
message names the offending input.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from decision_memory.application.conformance import ConformanceManifest
from decision_memory.infrastructure.conformance_manifest import (
    ConformanceManifestError,
    is_canonical_field_path,
    load_conformance_manifest,
)

_RECORD_YAML = """\
---
id: one
title: A decision
status: accepted
date: '2026-08-09'
decision:
  chosen: Chosen
why:
- Because
evidence:
- kind: file
  target: decisions/one.md
---
"""

_MINIMAL_MANIFEST = """\
schema_version: 1
cases:
  - id: c1
    category: valid
    corpus: corpus
    expect:
      sources:
        - id: one
          root: decisions/one.md
          contributing_files:
            - decisions/one.md
          required_files:
            - decisions/one.md
          result:
            record: expected/one.md
            attempted_fields: []
            unresolved_mention_count: 0
            violations: []
      skips: []
      collisions: []
"""


def _write_manifest(tmp_path: Path, yaml_text: str = _MINIMAL_MANIFEST) -> Path:
    base = tmp_path / "manifest"
    (base / "corpus" / "decisions").mkdir(parents=True)
    (base / "corpus" / "decisions" / "one.md").write_text(
        "# one\n\n## Decision\n\nChosen.\n", encoding="utf-8"
    )
    (base / "expected").mkdir(parents=True)
    (base / "expected" / "one.md").write_text(_RECORD_YAML, encoding="utf-8")
    manifest = base / "adapter-conformance.yml"
    manifest.write_text(yaml_text, encoding="utf-8")
    return manifest


def _expect_schema_failure(manifest: Path, needle: str) -> None:
    with pytest.raises(ConformanceManifestError) as excinfo:
        load_conformance_manifest(manifest)
    assert excinfo.value.rule == "manifest.schema"
    assert needle in excinfo.value.detail


def _expect_path_failure(manifest: Path, needle: str) -> None:
    with pytest.raises(ConformanceManifestError) as excinfo:
        load_conformance_manifest(manifest)
    assert excinfo.value.rule == "manifest.paths"
    assert needle in excinfo.value.detail


class TestHappyPath:
    def test_a_minimal_valid_manifest_loads(self, tmp_path: Path) -> None:
        manifest = _write_manifest(tmp_path)
        loaded = load_conformance_manifest(manifest)
        assert isinstance(loaded, ConformanceManifest)
        assert loaded.schema_version == 1
        assert len(loaded.cases) == 1
        case = loaded.cases[0]
        assert case.id == "c1"
        assert case.expect.sources[0].id == "one"
        assert case.expect.sources[0].result.record is not None
        assert case.expect.sources[0].result.record.id == "one"


class TestSchemaBoundary:
    def test_unsupported_schema_version_is_rejected(self, tmp_path: Path) -> None:
        manifest = _write_manifest(
            tmp_path,
            _MINIMAL_MANIFEST.replace("schema_version: 1", "schema_version: 2"),
        )
        _expect_schema_failure(manifest, "schema_version")

    def test_unknown_key_is_rejected(self, tmp_path: Path) -> None:
        manifest = _write_manifest(tmp_path, _MINIMAL_MANIFEST + "extra_key: true\n")
        _expect_schema_failure(manifest, "extra_key")

    def test_duplicate_case_ids_are_rejected(self, tmp_path: Path) -> None:
        # Two case blocks sharing the same id.
        block = _MINIMAL_MANIFEST.split("  - id: c1")[1]
        text = "schema_version: 1\ncases:\n  - id: c1" + block + "  - id: c1" + block
        manifest = _write_manifest(tmp_path, text)
        _expect_schema_failure(manifest, "duplicate case id")

    def test_empty_cases_are_rejected(self, tmp_path: Path) -> None:
        manifest = _write_manifest(tmp_path, "schema_version: 1\ncases: []\n")
        _expect_schema_failure(manifest, "cases")

    def test_duplicate_declared_path_is_rejected(self, tmp_path: Path) -> None:
        text = _MINIMAL_MANIFEST.replace(
            "            - decisions/one.md\n          required_files:",
            "            - decisions/one.md\n"
            "            - decisions/one.md\n          required_files:",
        )
        manifest = _write_manifest(tmp_path, text)
        _expect_schema_failure(manifest, "duplicate contributing file")

    def test_required_file_must_be_a_contributing_file(self, tmp_path: Path) -> None:
        text = _MINIMAL_MANIFEST.replace(
            "required_files:\n            - decisions/one.md",
            "required_files:\n            - decisions/missing.md",
        )
        manifest = _write_manifest(tmp_path, text)
        _expect_schema_failure(manifest, "is not a contributing file")

    def test_skip_case_needs_subject_and_exact_skip(self, tmp_path: Path) -> None:
        text = """\
schema_version: 1
cases:
  - id: skip1
    category: skip
    corpus: corpus
    subject_path: decisions/one.md
    expect:
      sources: []
      skips: []
      collisions: []
"""
        manifest = _write_manifest(tmp_path, text)
        _expect_schema_failure(manifest, "exactly once in skips")

    def test_valid_case_needs_a_nonnull_expected_record(self, tmp_path: Path) -> None:
        text = _MINIMAL_MANIFEST.replace("record: expected/one.md", "record: null")
        manifest = _write_manifest(tmp_path, text)
        _expect_schema_failure(manifest, "nonnull expected record")

    def test_collision_needs_two_paths(self, tmp_path: Path) -> None:
        text = """\
schema_version: 1
cases:
  - id: coll
    category: collision
    corpus: corpus
    expect:
      sources: []
      skips: []
      collisions:
        - id: one
          paths:
            - decisions/one.md
          used: decisions/one.md
"""
        manifest = _write_manifest(tmp_path, text)
        _expect_schema_failure(manifest, "at least two paths")

    def test_wrong_heading_needs_target_fields(self, tmp_path: Path) -> None:
        text = """\
schema_version: 1
cases:
  - id: drift
    category: wrong_heading
    corpus: corpus
    subject_path: decisions/one.md
    expect:
      sources: []
      skips: []
      collisions: []
"""
        manifest = _write_manifest(tmp_path, text)
        _expect_schema_failure(manifest, "nonempty target_fields")

    def test_unknown_canonical_field_is_rejected(self, tmp_path: Path) -> None:
        text = _MINIMAL_MANIFEST.replace(
            "attempted_fields: []",
            "attempted_fields: [made.up.field]",
        )
        manifest = _write_manifest(tmp_path, text)
        _expect_schema_failure(manifest, "not canonical")

    def test_manifest_requires_at_least_one_required_file(self, tmp_path: Path) -> None:
        text = _MINIMAL_MANIFEST.replace(
            "required_files:\n            - decisions/one.md\n",
            "required_files: []\n",
        )
        manifest = _write_manifest(tmp_path, text)
        _expect_schema_failure(manifest, "at least one required file")


class TestPathBoundary:
    def test_missing_corpus_is_rejected(self, tmp_path: Path) -> None:
        manifest = _write_manifest(
            tmp_path, _MINIMAL_MANIFEST.replace("corpus: corpus", "corpus: absent")
        )
        _expect_path_failure(manifest, "is not a directory")

    def test_path_escape_is_rejected(self, tmp_path: Path) -> None:
        text = _MINIMAL_MANIFEST.replace("corpus: corpus", "corpus: ../corpus")
        manifest = _write_manifest(tmp_path, text)
        _expect_path_failure(manifest, "escapes")

    def test_missing_subject_is_rejected(self, tmp_path: Path) -> None:
        text = """\
schema_version: 1
cases:
  - id: s
    category: skip
    corpus: corpus
    subject_path: decisions/absent.md
    expect:
      sources: []
      skips:
        - path: decisions/absent.md
      collisions: []
  - id: c1
    category: valid
    corpus: corpus
    expect:
      sources:
        - id: one
          root: decisions/one.md
          contributing_files:
            - decisions/one.md
          required_files:
            - decisions/one.md
          result:
            record: expected/one.md
            attempted_fields: []
            unresolved_mention_count: 0
            violations: []
      skips: []
      collisions: []
"""
        manifest = _write_manifest(tmp_path, text)
        _expect_path_failure(manifest, "does not exist")

    def test_a_symlink_in_the_case_corpus_is_rejected(self, tmp_path: Path) -> None:
        manifest = _write_manifest(tmp_path)
        link = manifest.parent / "corpus" / "decisions" / "link.md"
        link.symlink_to(manifest.parent / "corpus" / "decisions" / "one.md")
        _expect_path_failure(manifest, "symlink")

    def test_a_non_regular_expected_record_is_rejected(self, tmp_path: Path) -> None:
        manifest = _write_manifest(tmp_path)
        record = manifest.parent / "expected" / "one.md"
        record.unlink()
        record.mkdir()  # directory, not a file
        _expect_path_failure(manifest, "not a regular file")

    def test_an_invalid_expected_record_is_rejected(self, tmp_path: Path) -> None:
        manifest = _write_manifest(tmp_path)
        (manifest.parent / "expected" / "one.md").write_text(
            "not a canonical record", encoding="utf-8"
        )
        _expect_path_failure(manifest, "not a canonical record")

    def test_an_unparseable_yaml_manifest_is_a_load_failure(
        self, tmp_path: Path
    ) -> None:
        manifest = _write_manifest(tmp_path, "schema_version: [unclosed\n")
        with pytest.raises(ConformanceManifestError) as excinfo:
            load_conformance_manifest(manifest)
        assert excinfo.value.rule == "manifest.load"


class TestCanonicalFieldVocabulary:
    def test_known_and_indexed_fields_are_canonical(self) -> None:
        assert is_canonical_field_path("id")
        assert is_canonical_field_path("decision.chosen")
        assert is_canonical_field_path("decision.alternatives[1].rejection_reason")
        assert is_canonical_field_path("evidence[0].target")
        assert is_canonical_field_path("")

    def test_unknown_fields_are_not_canonical(self) -> None:
        assert not is_canonical_field_path("made.up")
        assert not is_canonical_field_path("decision.chosen[0]")
