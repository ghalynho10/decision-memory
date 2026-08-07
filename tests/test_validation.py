"""Unit tests for the pure validator and the record file reader.

Each rule id from spec 0002 is exercised. No external services are called;
the validator is fed crafted records and contexts, and the file reader reads
temp files.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from decision_memory.domain.records import (
    Alternative,
    CanonicalDecisionRecord,
    Decision,
    Evidence,
    EvidenceKind,
    Severity,
    Status,
    ValidationContext,
    Violation,
)
from decision_memory.domain.validation import validate
from decision_memory.infrastructure.file_reader import parse_record_file

COMMIT_A = "a" * 40
COMMIT_B = "b" * 40


def make_record(**overrides: object) -> CanonicalDecisionRecord:
    record = CanonicalDecisionRecord(
        id="0001",
        title="A decision",
        status=Status.ACCEPTED,
        decision=Decision(chosen="Chosen option"),
        why=["Because it is better"],
        evidence=[Evidence(kind=EvidenceKind.FILE, target="docs/x.md")],
    )
    return dataclasses.replace(record, **overrides)


def make_context(**overrides: object) -> ValidationContext:
    context = ValidationContext(
        attempted_fields=frozenset(),
        unknown_fields=frozenset(),
        existing_paths=frozenset({"docs/x.md"}),
        known_commits=frozenset({COMMIT_A, COMMIT_B}),
        git_available=True,
    )
    return dataclasses.replace(context, **overrides)


def rules(violations: list[Violation]) -> set[str]:
    return {v.rule for v in violations}


def by_rule(violations: list[Violation], rule: str) -> list[Violation]:
    return [v for v in violations if v.rule == rule]


class TestHappyPath:
    def test_valid_record_passes_with_no_violations(self) -> None:
        assert validate(make_record(), make_context()) == []


class TestRequiredMissing:
    @pytest.mark.parametrize(
        ("field", "record"),
        [
            ("id", make_record(id=None)),
            ("title", make_record(title=None)),
            ("status", make_record(status=None)),
            (
                "decision.chosen",
                make_record(decision=Decision(chosen=None)),
            ),
            ("decision.chosen", make_record(decision=None)),
            ("evidence", make_record(evidence=None)),
        ],
    )
    def test_absent_required_field_errors(self, field: str, record: object) -> None:
        violations = validate(record, make_context())
        missing = by_rule(violations, "required.missing")
        assert any(v.field == field for v in missing)

    @pytest.mark.parametrize("title", ["", "   "])
    def test_blank_required_string_is_missing(self, title: str) -> None:
        violations = validate(make_record(title=title), make_context())
        assert by_rule(violations, "required.missing")
        assert any(v.field == "title" for v in violations)

    def test_empty_required_list_is_missing(self) -> None:
        violations = validate(make_record(evidence=[]), make_context())
        missing = by_rule(violations, "required.missing")
        assert any(v.field == "evidence" for v in missing)


class TestRationale:
    def test_neither_why_nor_summary_is_rejected(self) -> None:
        violations = validate(
            make_record(why=[], rationale_summary=None), make_context()
        )
        assert "rationale.missing" in rules(violations)

    def test_whitespace_only_why_does_not_populate(self) -> None:
        violations = validate(
            make_record(why=["   "], rationale_summary=None), make_context()
        )
        assert "rationale.missing" in rules(violations)

    def test_why_populates_on_its_own(self) -> None:
        assert validate(make_record(why=["A reason"]), make_context()) == []

    def test_summary_populates_on_its_own(self) -> None:
        assert (
            validate(
                make_record(why=[], rationale_summary="A summary"),
                make_context(),
            )
            == []
        )


class TestFormats:
    def test_malformed_id_errors(self) -> None:
        violations = validate(make_record(id="-bad id"), make_context())
        assert any(v.field == "id" and v.rule == "id.malformed" for v in violations)

    def test_impossible_calendar_date_errors(self) -> None:
        violations = validate(make_record(date="2026-02-30"), make_context())
        assert any(v.field == "date" and v.rule == "date.malformed" for v in violations)

    def test_valid_date_passes(self) -> None:
        assert validate(make_record(date="2026-08-07"), make_context()) == []


class TestSupersedes:
    def test_self_reference_errors(self) -> None:
        violations = validate(make_record(id="0001", supersedes="0001"), make_context())
        assert any(v.rule == "supersedes.self_reference" for v in violations)


class TestWarnings:
    def test_attempted_field_warns_and_does_not_reject(self) -> None:
        violations = validate(
            make_record(),
            make_context(attempted_fields=frozenset({"context.problem"})),
        )
        attempted = by_rule(violations, "field.attempted_unfilled")
        assert attempted
        assert attempted[0].severity == Severity.WARNING
        assert attempted[0].field == "context.problem"
        assert not any(v.severity == Severity.ERROR for v in violations)

    def test_alternative_without_rejection_reason_warns(self) -> None:
        record = make_record(
            decision=Decision(
                chosen="Chosen option",
                alternatives=[Alternative(title="Other option")],
            )
        )
        violations = validate(record, make_context())
        warned = by_rule(violations, "alternative.missing_rejection_reason")
        assert warned
        assert warned[0].field == "decision.alternatives[0].rejection_reason"

    def test_unknown_field_warns(self) -> None:
        violations = validate(
            make_record(),
            make_context(unknown_fields=frozenset({"author", "evidence[1].foo"})),
        )
        unknown = by_rule(violations, "field.unknown")
        fields = {v.field for v in unknown}
        assert "author" in fields
        assert "evidence[1].foo" in fields
        assert not any(v.severity == Severity.ERROR for v in violations)


class TestEvidence:
    def test_file_target_not_in_existing_paths_is_unresolved(self) -> None:
        violations = validate(
            make_record(
                evidence=[Evidence(kind=EvidenceKind.FILE, target="docs/missing.md")]
            ),
            make_context(existing_paths=frozenset({"docs/x.md"})),
        )
        unresolved = by_rule(violations, "evidence.path_unresolved")
        assert unresolved
        assert unresolved[0].field == "evidence[0].target"

    def test_spec_target_not_in_existing_paths_is_unresolved(self) -> None:
        record = make_record(
            evidence=[Evidence(kind=EvidenceKind.SPEC, target="docs/specs/0001.md")]
        )
        violations = validate(record, make_context(existing_paths=frozenset()))
        assert "evidence.path_unresolved" in rules(violations)

    def test_spec_target_outside_specs_dir_errors(self) -> None:
        record = make_record(
            evidence=[Evidence(kind=EvidenceKind.SPEC, target="README.md")]
        )
        violations = validate(
            record, make_context(existing_paths=frozenset({"README.md"}))
        )
        assert "evidence.spec_outside_specs_dir" in rules(violations)
        assert "evidence.path_unresolved" not in rules(violations)

    def test_spec_target_under_specs_dir_resolves(self) -> None:
        record = make_record(
            evidence=[
                Evidence(kind=EvidenceKind.SPEC, target="docs/specs/0001/index.md")
            ]
        )
        violations = validate(
            record,
            make_context(existing_paths=frozenset({"docs/specs/0001/index.md"})),
        )
        assert "evidence.path_unresolved" not in rules(violations)
        assert "evidence.spec_outside_specs_dir" not in rules(violations)

    @pytest.mark.parametrize(
        "target",
        ["", "   ", "/etc/passwd", "../outside.md", "docs/"],
    )
    def test_bad_target_shape_rejected_before_resolution(self, target: str) -> None:
        record = make_record(evidence=[Evidence(kind=EvidenceKind.FILE, target=target)])
        violations = validate(record, make_context())
        rules_fired = rules(violations)
        if target.strip() == "":
            assert "evidence.empty_target" in rules_fired
        else:
            assert "evidence.target_not_normalized" in rules_fired
        assert "evidence.path_unresolved" not in rules_fired

    def test_target_is_normalized_before_resolution(self) -> None:
        record = make_record(
            evidence=[Evidence(kind=EvidenceKind.FILE, target="./docs//x.md")]
        )
        violations = validate(record, make_context())
        assert "evidence.path_unresolved" not in rules(violations)

    def test_commit_unique_prefix_resolves(self) -> None:
        record = make_record(
            evidence=[Evidence(kind=EvidenceKind.COMMIT, target=COMMIT_A[:7])]
        )
        violations = validate(record, make_context())
        assert "evidence.commit_unresolved" not in rules(violations)
        assert "evidence.commit_ambiguous" not in rules(violations)

    def test_commit_unknown_prefix_is_unresolved(self) -> None:
        record = make_record(
            evidence=[Evidence(kind=EvidenceKind.COMMIT, target="f" * 7)]
        )
        violations = validate(record, make_context())
        assert "evidence.commit_unresolved" in rules(violations)

    def test_commit_ambiguous_prefix_errors(self) -> None:
        ambiguous = "a" * 39 + "b"
        record = make_record(
            evidence=[Evidence(kind=EvidenceKind.COMMIT, target="a" * 7)]
        )
        violations = validate(
            record,
            make_context(known_commits=frozenset({COMMIT_A, ambiguous})),
        )
        assert "evidence.commit_ambiguous" in rules(violations)

    def test_git_unavailable_skips_commits_and_warns_once(self) -> None:
        record = make_record(
            evidence=[
                Evidence(kind=EvidenceKind.COMMIT, target="f" * 7),
                Evidence(kind=EvidenceKind.COMMIT, target="e" * 7),
            ]
        )
        violations = validate(record, make_context(git_available=False))
        assert "evidence.commit_unresolved" not in rules(violations)
        git_warnings = by_rule(violations, "context.git_unavailable")
        assert len(git_warnings) == 1

    def test_git_unavailable_does_not_warn_without_commit_evidence(self) -> None:
        violations = validate(make_record(), make_context(git_available=False))
        assert "context.git_unavailable" not in rules(violations)


class TestExitCodeContract:
    def test_warnings_without_errors_means_no_errors(self) -> None:
        violations = validate(
            make_record(),
            make_context(unknown_fields=frozenset({"author"})),
        )
        assert not any(v.severity == Severity.ERROR for v in violations)


class TestFileReader:
    VALID_TEXT = (
        "---\n"
        'id: "0001"\n'
        "title: A decision\n"
        "status: accepted\n"
        "decision:\n"
        "  chosen: Chosen option\n"
        "why:\n"
        "  - Because it is better\n"
        "evidence:\n"
        "  - kind: file\n"
        "    target: docs/x.md\n"
        "---\n"
        "\n"
        "Body text.\n"
    )

    def _write(self, tmp_path: Path, text: str) -> Path:
        path = tmp_path / "record.md"
        path.write_text(text, encoding="utf-8")
        return path

    def test_parse_valid_record(self, tmp_path: Path) -> None:
        result = parse_record_file(self._write(tmp_path, self.VALID_TEXT))
        assert result.record is not None
        assert result.record.id == "0001"
        assert result.record.status == Status.ACCEPTED
        assert result.record.body == "Body text.\n"
        assert result.unknown_fields == frozenset()
        assert result.violations == []

    def test_parse_strips_one_leading_blank_line_from_body(
        self, tmp_path: Path
    ) -> None:
        text = self.VALID_TEXT.replace("---\n\nBody text.", "---\n\n\nBody text.")
        result = parse_record_file(self._write(tmp_path, text))
        assert result.record is not None
        assert result.record.body == "\nBody text.\n"

    def test_empty_body_is_allowed(self, tmp_path: Path) -> None:
        text = (
            "---\n"
            'id: "0001"\n'
            "title: A decision\n"
            "status: accepted\n"
            "decision:\n"
            "  chosen: Chosen option\n"
            "why:\n"
            "  - Because it is better\n"
            "evidence:\n"
            "  - kind: file\n"
            "    target: docs/x.md\n"
            "---\n"
        )
        result = parse_record_file(self._write(tmp_path, text))
        assert result.record is not None
        assert result.record.body == ""
        assert result.violations == []

    def test_no_frontmatter_fence(self, tmp_path: Path) -> None:
        result = parse_record_file(self._write(tmp_path, "id: 0001\ntitle: X\n"))
        assert result.record is None
        assert rules(result.violations) == {"file.no_frontmatter"}

    def test_missing_closing_fence(self, tmp_path: Path) -> None:
        result = parse_record_file(self._write(tmp_path, "---\nid: 0001\n"))
        assert result.record is None
        assert rules(result.violations) == {"file.no_frontmatter"}

    def test_unparseable_yaml(self, tmp_path: Path) -> None:
        result = parse_record_file(self._write(tmp_path, "---\nid: [unclosed\n---\n"))
        assert result.record is None
        assert rules(result.violations) == {"file.frontmatter_unparseable"}

    def test_frontmatter_not_a_mapping(self, tmp_path: Path) -> None:
        result = parse_record_file(self._write(tmp_path, "---\n- one\n- two\n---\n"))
        assert result.record is None
        assert rules(result.violations) == {"file.frontmatter_not_mapping"}

    def test_unreadable_file(self, tmp_path: Path) -> None:
        result = parse_record_file(tmp_path / "missing.md")
        assert result.record is None
        assert rules(result.violations) == {"file.unreadable"}

    def test_evidence_as_string_is_wrong_type(self, tmp_path: Path) -> None:
        text = self.VALID_TEXT.replace(
            "evidence:\n  - kind: file\n    target: docs/x.md\n",
            "evidence: not-a-list\n",
        )
        result = parse_record_file(self._write(tmp_path, text))
        assert result.record is None
        assert rules(result.violations) == {"field.wrong_type"}

    def test_bad_status_is_bad_enum(self, tmp_path: Path) -> None:
        text = self.VALID_TEXT.replace("status: accepted", "status: draft")
        result = parse_record_file(self._write(tmp_path, text))
        assert result.record is None
        assert rules(result.violations) == {"field.bad_enum"}

    def test_unknown_field_is_collected_nested(self, tmp_path: Path) -> None:
        text = self.VALID_TEXT.replace(
            "    target: docs/x.md\n",
            "    target: docs/x.md\n    stray: 1\n",
        )
        result = parse_record_file(self._write(tmp_path, text))
        assert result.record is not None
        assert "evidence[0].stray" in result.unknown_fields

    def test_unquoted_yaml_date_is_coerced_to_string(self, tmp_path: Path) -> None:
        text = self.VALID_TEXT.replace(
            "status: accepted\n", "status: accepted\ndate: 2026-08-07\n"
        )
        result = parse_record_file(self._write(tmp_path, text))
        assert result.record is not None
        assert result.record.date == "2026-08-07"
        assert result.violations == []

    def test_bom_and_crlf_parse_identically(self, tmp_path: Path) -> None:
        crlf = "\ufeff" + self.VALID_TEXT.replace("\n", "\r\n")
        plain = parse_record_file(self._write(tmp_path, self.VALID_TEXT))
        with_bom = parse_record_file(self._write(tmp_path, crlf))
        assert with_bom.record == plain.record
        assert with_bom.unknown_fields == plain.unknown_fields
        assert with_bom.violations == plain.violations
