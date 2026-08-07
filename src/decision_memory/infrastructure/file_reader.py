"""Infrastructure: read a canonical decision record file.

Owns the frontmatter grammar, the Pydantic models over the parsed YAML
mapping, and the parse result type. Framework code (Pydantic, YAML) lives
here, never in domain or application.

Reading a file and validating a record are separate steps with separate
failure modes. A file that is not a parseable record produces no record and
only `file.*` or `field.*` violations, which the CLI reports and stops on.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as calendar_date
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from decision_memory.domain.records import (
    Alternative,
    CanonicalDecisionRecord,
    Consequences,
    Context,
    Decision,
    Evidence,
    EvidenceKind,
    Severity,
    Status,
    Violation,
)

_FENCE = "---"


@dataclass(frozen=True)
class ParseResult:
    """The outcome of reading a record file.

    ``record`` is None when the file is not a parseable record; in that case
    ``violations`` holds only `file.*` or `field.*` errors and no rule
    validation runs. ``unknown_fields`` is collected from the frontmatter and
    carried into the validation context when a record exists.
    """

    record: CanonicalDecisionRecord | None
    violations: list[Violation]
    unknown_fields: frozenset[str]


class AlternativeModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str | None = None
    rejection_reason: str | None = None


class ContextModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    problem: str | None = None
    triggering_change: str | None = None


class ConsequencesModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    positive: list[str] = Field(default_factory=list)
    negative: list[str] = Field(default_factory=list)


class EvidenceModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    kind: EvidenceKind | None = None
    target: str | None = None
    note: str | None = None


class DecisionModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    chosen: str | None = None
    alternatives: list[AlternativeModel] = Field(default_factory=list)


class RecordModel(BaseModel):
    """Pydantic model over the parsed frontmatter mapping.

    Every field is optional because missing required fields are reported by the
    validator as `required.missing`, not rejected here. Type mismatches and bad
    enum values fail here as `field.wrong_type` and `field.bad_enum` with no
    record. Extra keys are allowed and collected as unknown fields.
    """

    model_config = ConfigDict(extra="allow")

    id: str | None = None
    title: str | None = None
    status: Status | None = None
    date: str | None = None
    context: ContextModel | None = None
    decision: DecisionModel | None = None
    why: list[str] = Field(default_factory=list)
    rationale_summary: str | None = None
    consequences: ConsequencesModel | None = None
    evidence: list[EvidenceModel] | None = None
    tags: list[str] = Field(default_factory=list)
    supersedes: str | None = None

    @field_validator("date", mode="before")
    @classmethod
    def coerce_yaml_date_scalar(cls, value: object) -> object:
        """Convert an unquoted YAML date scalar to its ISO string form."""
        if isinstance(value, calendar_date):
            return value.isoformat()
        return value


def parse_record_file(path: Path) -> ParseResult:
    """Read a record file into a parse result. Never raises for bad input."""
    text = _read_text(path)
    if text is None:
        return ParseResult(
            record=None,
            violations=[
                _violation(
                    "",
                    Severity.ERROR,
                    "file.unreadable",
                    f"cannot read {path} as UTF-8 text",
                )
            ],
            unknown_fields=frozenset(),
        )
    split = _split_frontmatter(text)
    if split is None:
        return ParseResult(
            record=None,
            violations=[
                _violation(
                    "",
                    Severity.ERROR,
                    "file.no_frontmatter",
                    "record file must open and close with a --- frontmatter fence",
                )
            ],
            unknown_fields=frozenset(),
        )
    frontmatter, body = split
    try:
        data = yaml.safe_load(frontmatter)
    except yaml.YAMLError:
        return ParseResult(
            record=None,
            violations=[
                _violation(
                    "",
                    Severity.ERROR,
                    "file.frontmatter_unparseable",
                    "frontmatter is not valid YAML",
                )
            ],
            unknown_fields=frozenset(),
        )
    if not isinstance(data, dict):
        return ParseResult(
            record=None,
            violations=[
                _violation(
                    "",
                    Severity.ERROR,
                    "file.frontmatter_not_mapping",
                    "frontmatter must parse to a YAML mapping",
                )
            ],
            unknown_fields=frozenset(),
        )
    try:
        model = RecordModel.model_validate(data)
    except ValidationError as exc:
        return ParseResult(
            record=None,
            violations=_field_violations_from_validation_error(exc),
            unknown_fields=frozenset(),
        )
    record, unknown_fields = _to_domain(model, body)
    return ParseResult(record=record, violations=[], unknown_fields=unknown_fields)


def _read_text(path: Path) -> str | None:
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None
    return raw.replace("\r\n", "\n").replace("\r", "\n")


def _split_frontmatter(text: str) -> tuple[str, str] | None:
    """Split a record file into (frontmatter YAML, markdown body).

    The file must open with a fence line, have a closing fence line, and the
    body is everything after the closing fence with one leading blank line
    stripped if present. Line endings are already normalized to LF.
    """
    lines = text.split("\n")
    if not lines or lines[0] != _FENCE:
        return None
    closing = None
    for index in range(1, len(lines)):
        if lines[index] == _FENCE:
            closing = index
            break
    if closing is None:
        return None
    frontmatter = "\n".join(lines[1:closing])
    body_lines = lines[closing + 1 :]
    if body_lines and body_lines[0] == "":
        body_lines = body_lines[1:]
    return frontmatter, "\n".join(body_lines)


def _loc_to_path(loc: tuple[int | str, ...]) -> str:
    """Convert a Pydantic loc tuple to a dotted path with bracket indices."""
    out = ""
    for part in loc:
        if isinstance(part, int):
            out += f"[{part}]"
        elif out == "":
            out += part
        else:
            out += f".{part}"
    return out


def _field_violations_from_validation_error(exc: ValidationError) -> list[Violation]:
    violations: list[Violation] = []
    for error in exc.errors():
        loc = tuple(error.get("loc", ()))
        field = _loc_to_path(loc)
        if error.get("type") == "enum":
            violations.append(
                _violation(
                    field,
                    Severity.ERROR,
                    "field.bad_enum",
                    f"{field} is not one of the allowed values",
                )
            )
        else:
            violations.append(
                _violation(
                    field,
                    Severity.ERROR,
                    "field.wrong_type",
                    f"{field} has the wrong type",
                )
            )
    return violations


def _collect_unknown_fields(model: RecordModel) -> frozenset[str]:
    unknown: set[str] = set()
    for key in model.model_extra or {}:
        unknown.add(str(key))
    if model.context is not None:
        for key in model.context.model_extra or {}:
            unknown.add(f"context.{key}")
    if model.decision is not None:
        for key in model.decision.model_extra or {}:
            unknown.add(f"decision.{key}")
        for index, alternative in enumerate(model.decision.alternatives):
            for key in alternative.model_extra or {}:
                unknown.add(f"decision.alternatives[{index}].{key}")
    if model.consequences is not None:
        for key in model.consequences.model_extra or {}:
            unknown.add(f"consequences.{key}")
    if model.evidence is not None:
        for index, evidence in enumerate(model.evidence):
            for key in evidence.model_extra or {}:
                unknown.add(f"evidence[{index}].{key}")
    return frozenset(unknown)


def _to_domain(
    model: RecordModel, body: str
) -> tuple[CanonicalDecisionRecord, frozenset[str]]:
    record = CanonicalDecisionRecord(
        id=model.id,
        title=model.title,
        status=model.status,
        date=model.date,
        body=body,
        context=(
            Context(
                problem=model.context.problem,
                triggering_change=model.context.triggering_change,
            )
            if model.context is not None
            else None
        ),
        decision=(
            Decision(
                chosen=model.decision.chosen,
                alternatives=[
                    Alternative(
                        title=alternative.title,
                        rejection_reason=alternative.rejection_reason,
                    )
                    for alternative in model.decision.alternatives
                ],
            )
            if model.decision is not None
            else None
        ),
        why=model.why,
        rationale_summary=model.rationale_summary,
        consequences=(
            Consequences(
                positive=model.consequences.positive,
                negative=model.consequences.negative,
            )
            if model.consequences is not None
            else None
        ),
        evidence=(
            [
                Evidence(
                    kind=evidence.kind,
                    target=evidence.target,
                    note=evidence.note,
                )
                for evidence in model.evidence
            ]
            if model.evidence is not None
            else None
        ),
        tags=model.tags,
        supersedes=model.supersedes,
    )
    return record, _collect_unknown_fields(model)


def _violation(field: str, severity: Severity, rule: str, reason: str) -> Violation:
    return Violation(field=field, severity=severity, rule=rule, reason=reason)
