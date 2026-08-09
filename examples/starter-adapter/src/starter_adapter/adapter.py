"""Starter adapter: a minimal teaching adapter for decision-memory.

Reads a tiny neutral Markdown format under a corpus's ``decisions/`` directory
and turns each decision file into a canonical decision record. The format is
deliberately minimal so an author can see every piece of the adapter contract
in one module: metadata, discovery, parsing, and content based fingerprinting
(spec 0005 AC-16, AC-17). It copies no jsmastery specific parsing rules.

The tiny format:

.. code-block:: markdown

    # Title of the decision

    **Status**: Accepted
    **Date**: 2026-08-09

    ## Context

    The problem this decision answers.

    ## Decision

    What was chosen.

    ## Why

    - One reason
    - Another reason

Discovery skips any file that has no ``## Decision`` heading, so a file that
is not a decision produces no record and does not fail the run (degrade rather
than guess). A file with an unknown status is reported as unadaptable.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from decision_memory.application.adapter import (
    AdaptationResult,
    Collision,
    DiscoveredSpec,
    DiscoveryResult,
    SkippedSource,
)
from decision_memory.domain.records import (
    CanonicalDecisionRecord,
    Context,
    Decision,
    Evidence,
    EvidenceKind,
    Severity,
    Status,
    ValidationContext,
    Violation,
)
from decision_memory.domain.validation import validate

ADAPTER_ID = "starter-adapter"
ADAPTER_VERSION = "1"

# A status word maps to its canonical status; anything else is unadaptable.
_STATUS_BY_WORD = {
    "accepted": Status.ACCEPTED,
    "proposed": Status.PROPOSED,
    "rejected": Status.REJECTED,
    "superseded": Status.SUPERSEDED,
}

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_LABEL_LINE_RE = re.compile(r"^\s*\*{0,2}(Status|Date)\*{0,2}\s*[:：]\s*(.+?)\s*$")
_BULLET_RE = re.compile(r"^\s*[-*]\s+(.+)$", re.MULTILINE)


class StarterAdapter:
    """Adapts the tiny neutral Markdown format under ``decisions/``."""

    @property
    def adapter_id(self) -> str:
        return ADAPTER_ID

    @property
    def adapter_version(self) -> str:
        return ADAPTER_VERSION

    def discover(self, corpus_root: Path) -> DiscoveryResult:
        """Find decision files under ``decisions/``, skipping non decisions.

        Discovery walks every Markdown file recursively (``decisions/**/*.md``,
        which includes the original flat ``decisions/*.md`` shape), derives ids
        from filename stems, orders candidate files by corpus relative POSIX
        path in ascending lexical order, and for a duplicated id selects the
        first path and reports every colliding path in that same order (spec
        0006 AC-19).
        """
        decisions_dir = corpus_root / "decisions"
        if not decisions_dir.is_dir():
            return DiscoveryResult(
                specs=[],
                skipped=[],
                collisions=[],
                corpus_error="no decisions/ directory",
            )
        candidates: list[Path] = []
        skipped: list[SkippedSource] = []
        for path in sorted(decisions_dir.glob("**/*.md")):
            text = _read_text(path)
            if text is None:
                skipped.append(SkippedSource(path=path, reason="cannot read file"))
                continue
            if "Decision" not in _h2_heading_texts(text):
                skipped.append(
                    SkippedSource(path=path, reason="no ## Decision section")
                )
                continue
            candidates.append(path)
        candidates.sort(key=lambda path: path.relative_to(corpus_root).as_posix())
        by_id: dict[str, list[Path]] = {}
        for path in candidates:
            by_id.setdefault(path.stem, []).append(path)
        specs: list[DiscoveredSpec] = []
        collisions: list[Collision] = []
        for spec_id, paths in by_id.items():
            used = paths[0]
            specs.append(
                DiscoveredSpec(
                    id=spec_id,
                    root=used,
                    corpus_root=corpus_root,
                    contributing_files=[used],
                )
            )
            if len(paths) > 1:
                collisions.append(Collision(id=spec_id, paths=paths, used=used))
        return DiscoveryResult(specs, skipped, collisions)

    def parse(self, spec: DiscoveredSpec) -> AdaptationResult:
        """Turn one decision file into a validated canonical record."""
        text = _read_text(spec.root)
        if text is None:
            return _failure(
                spec,
                "file.unreadable",
                f"cannot read {spec.root}",
            )
        status = _status(text)
        if status is None:
            return _failure(
                spec,
                "status.unmapped",
                "Status value is not a known status word",
            )

        attempted: set[str] = set()
        context_text = _paragraph(text, "Context")
        if context_text is None:
            attempted.add("context.problem")
        decision_text = _paragraph(text, "Decision")
        if decision_text is None:
            attempted.add("decision.chosen")
        why = _bullets(text, "Why")
        if not why:
            attempted.add("why")

        relative_path = spec.root.relative_to(spec.corpus_root).as_posix()
        record = CanonicalDecisionRecord(
            id=spec.id,
            title=_title(text),
            status=status,
            date=_date(text),
            body="",
            context=Context(problem=context_text) if context_text else None,
            decision=Decision(chosen=decision_text) if decision_text else None,
            why=why,
            evidence=[Evidence(kind=EvidenceKind.FILE, target=relative_path)],
        )
        context = ValidationContext(
            attempted_fields=frozenset(attempted),
            existing_paths=frozenset({relative_path}),
        )
        return AdaptationResult(
            record=record,
            violations=validate(record, context),
            attempted_fields=frozenset(attempted),
            unresolved_mention_count=0,
            fingerprint=self.fingerprint(spec),
        )

    def fingerprint(self, spec: DiscoveredSpec) -> str:
        """A SHA-256 over the adapter version and each contributing file.

        The version participates in the digest, so changing only the version
        changes every fingerprint (AC-15).
        """
        digest = hashlib.sha256()
        digest.update(ADAPTER_VERSION.encode("utf-8"))
        for path in spec.contributing_files:
            digest.update(path.relative_to(spec.corpus_root).as_posix().encode("utf-8"))
            digest.update(b"\x00")
            digest.update(path.read_bytes())
            digest.update(b"\x00")
        return digest.hexdigest()


def _failure(spec: DiscoveredSpec, rule: str, reason: str) -> AdaptationResult:
    """An unadaptable source: no record, one clear violation."""
    violation = Violation("", Severity.ERROR, rule, reason)
    return AdaptationResult(
        record=None,
        violations=[violation],
        attempted_fields=frozenset(),
        unresolved_mention_count=0,
        fingerprint=_fingerprint_or_empty(spec),
    )


def _fingerprint_or_empty(spec: DiscoveredSpec) -> str:
    """A fingerprint even when a file cannot be read, so reporting stays stable."""
    try:
        return StarterAdapter().fingerprint(spec)
    except OSError:
        return ""


def _read_text(path: Path) -> str | None:
    """Read a file as UTF-8 text, or None when unreadable or not UTF-8.

    Degrades rather than raises: a file that cannot be read or does not decode
    as UTF-8 is reported as a skip, never a crash (spec 0005 AC-7, spec 0006
    AC-8 corruption behavior).
    """
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _h2_heading_texts(text: str) -> list[str]:
    """Every H2 heading text in ``text``."""
    return [
        match.group(2).strip()
        for line in text.split("\n")
        if (match := _HEADING_RE.match(line)) is not None and len(match.group(1)) == 2
    ]


def _section(text: str, heading: str) -> str | None:
    """The raw body of the named ``##`` section, or None when absent."""
    sections: dict[str, str] = {}
    current: str | None = None
    body: list[str] = []
    for line in text.split("\n"):
        match = _HEADING_RE.match(line)
        if match is not None and len(match.group(1)) == 2:
            if current is not None:
                sections[current] = "\n".join(body).strip()
            current = match.group(2).strip()
            body = []
        elif current is not None:
            body.append(line)
    if current is not None:
        sections[current] = "\n".join(body).strip()
    value = sections.get(heading)
    if value is None or not value:
        return None
    return value


def _paragraph(text: str, heading: str) -> str | None:
    """The section's prose with whitespace collapsed, or None when absent."""
    section = _section(text, heading)
    if section is None:
        return None
    return re.sub(r"\s+", " ", section).strip()


def _bullets(text: str, heading: str) -> list[str]:
    """The bullet list inside the named section, or an empty list.

    Bullets are extracted from the raw section body so the newlines that
    separate them survive; ``_paragraph`` collapses those newlines and is only
    used for the prose fields.
    """
    section = _section(text, heading)
    if section is None:
        return []
    return [match.group(1).strip() for match in _BULLET_RE.finditer(section)]


def _title(text: str) -> str | None:
    for line in text.split("\n"):
        match = _HEADING_RE.match(line)
        if match is not None and len(match.group(1)) == 1:
            return match.group(2).strip()
    return None


def _label(text: str, name: str) -> str | None:
    for line in text.split("\n"):
        match = _LABEL_LINE_RE.match(line)
        if match is not None and match.group(1) == name:
            return match.group(2)
    return None


def _status(text: str) -> Status | None:
    raw = _label(text, "Status")
    if raw is None:
        return None
    return _STATUS_BY_WORD.get(raw.strip().lower())


def _date(text: str) -> str | None:
    return _label(text, "Date")


adapter = StarterAdapter()
