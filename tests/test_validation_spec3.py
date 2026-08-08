"""Spec 0003 additions to the validation path (AC-22, AC-23).

AC-22: the validate command resolves evidence by checking each cited target
directly, and a target that names a directory resolves. AC-23: the
unresolved mention count is carried on the validation context and reported as
a warning.
"""

from __future__ import annotations

from pathlib import Path

from spec_factory import make_corpus
from typer.testing import CliRunner

from decision_memory.cli import app
from decision_memory.domain.records import (
    CanonicalDecisionRecord,
    Decision,
    Evidence,
    EvidenceKind,
    Severity,
    Status,
    ValidationContext,
)
from decision_memory.domain.validation import validate

runner = CliRunner()


def _record() -> CanonicalDecisionRecord:
    return CanonicalDecisionRecord(
        id="0001",
        title="A decision",
        status=Status.ACCEPTED,
        decision=Decision(chosen="Chosen"),
        why=["Because it is better"],
        evidence=[Evidence(kind=EvidenceKind.FILE, target="docs/x.md")],
    )


def test_mentions_unresolved_is_a_warning() -> None:
    context = ValidationContext(
        existing_paths=frozenset({"docs/x.md"}),
        unresolved_mention_count=4,
    )
    violations = validate(_record(), context)
    matches = [v for v in violations if v.rule == "evidence.mentions_unresolved"]
    assert len(matches) == 1
    assert matches[0].severity == Severity.WARNING
    assert "4" in matches[0].reason


def test_no_unresolved_mentions_produces_no_warning() -> None:
    context = ValidationContext(existing_paths=frozenset({"docs/x.md"}))
    violations = validate(_record(), context)
    assert not any(v.rule == "evidence.mentions_unresolved" for v in violations)


def test_validate_resolves_directory_target_directly(tmp_path: Path) -> None:
    corpus = make_corpus(tmp_path)
    (corpus / "lib").mkdir()
    record = tmp_path / "record.md"
    record.write_text(
        "---\n"
        'id: "0001"\n'
        "title: A decision\n"
        "status: accepted\n"
        "decision:\n"
        "  chosen: Chosen\n"
        "why:\n"
        "  - Because\n"
        "evidence:\n"
        "  - kind: file\n"
        "    target: lib\n"
        "---\n",
        encoding="utf-8",
    )
    result = runner.invoke(
        app, ["validate", str(record), "--project-root", str(corpus)]
    )
    assert result.exit_code == 0
    assert "valid record, no violations" in result.stdout
