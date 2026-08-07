"""Canonical decision record domain types.

The record shape is fixed by spec 0002. Every field is optional at the type
level because the validator's job is to detect missing required fields; a
record that is missing something must still be representable so it can be
checked. Zero external imports by project rule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Status(StrEnum):
    """Allowed record statuses, in the order the schema lists them."""

    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


class EvidenceKind(StrEnum):
    """Kinds of evidence a record can cite."""

    SPEC = "spec"
    FILE = "file"
    COMMIT = "commit"


class Severity(StrEnum):
    """Violation severity. Warnings never change the exit code."""

    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class Violation:
    """One problem found while parsing or validating a record.

    ``field`` uses dotted paths with zero based bracket indices for list
    members, for example ``decision.alternatives[1].rejection_reason``. The
    whole record is named by the empty string for rules that are not about one
    field.
    """

    field: str
    severity: Severity
    rule: str
    reason: str


@dataclass(frozen=True)
class Context:
    """The record's optional context block."""

    problem: str | None = None
    triggering_change: str | None = None


@dataclass(frozen=True)
class Alternative:
    """A rejected alternative to the chosen decision."""

    title: str | None = None
    rejection_reason: str | None = None


@dataclass(frozen=True)
class Decision:
    """What was chosen, plus the rejected alternatives."""

    chosen: str | None = None
    alternatives: list[Alternative] = field(default_factory=list)


@dataclass(frozen=True)
class Consequences:
    """Expected positive and negative consequences."""

    positive: list[str] = field(default_factory=list)
    negative: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Evidence:
    """One cited source backing the record."""

    kind: EvidenceKind | None = None
    target: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class CanonicalDecisionRecord:
    """The canonical in memory decision record.

    ``body`` is the markdown body that follows the frontmatter fence, kept
    verbatim with one leading blank line stripped. ``supersedes`` holds at most
    one record id and never this record's own id.
    """

    id: str | None = None
    title: str | None = None
    status: Status | None = None
    date: str | None = None
    body: str | None = None
    context: Context | None = None
    decision: Decision | None = None
    why: list[str] = field(default_factory=list)
    rationale_summary: str | None = None
    consequences: Consequences | None = None
    evidence: list[Evidence] | None = None
    tags: list[str] = field(default_factory=list)
    supersedes: str | None = None


@dataclass(frozen=True)
class ValidationContext:
    """Everything the validator needs beyond the record, supplied by callers.

    Supplying these sets keeps the validator pure: it performs no filesystem or
    git access of its own. ``attempted_fields`` is empty in this slice; feature
    4's adapter is what fills it.
    """

    attempted_fields: frozenset[str] = frozenset()
    unknown_fields: frozenset[str] = frozenset()
    existing_paths: frozenset[str] = frozenset()
    known_commits: frozenset[str] = frozenset()
    git_available: bool = False
