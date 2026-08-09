"""Infrastructure: the jsmastery spec adapter.

Implements the SourceAdapter protocol from the application layer for jsmastery
style spec folders, a directory under docs/specs/ holding index.md plus an
optional rationale.md. Owns the section parsing, field mapping, winner ladder,
code path extraction, and fingerprinting fixed by spec 0003. Filesystem access
belongs here; the field mapping never invents a value, it flags gaps instead.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from decision_memory.application.adapter import (
    AdaptationResult,
    Collision,
    DiscoveredSpec,
    DiscoveryResult,
    SkippedSource,
)
from decision_memory.application.canonical import SourceReference
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
    ValidationContext,
    Violation,
)
from decision_memory.domain.validation import normalize_target, validate
from decision_memory.infrastructure.path_resolution import (
    path_resolves_case_sensitive,
    resolve_cited_paths,
)

# Bumped by hand when the mapping changes; part of every record's fingerprint.
ADAPTER_VERSION = "5"

# Known file extensions that make a non resolving inline token count toward
# the unresolved mention total (AC-6 step 7). Corpus calibration, not a
# principle: extending it is expected. Compared without regard to case.
_KNOWN_PATH_EXTENSIONS = frozenset(
    {
        ".md",
        ".py",
        ".json",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".toml",
        ".yaml",
        ".yml",
        ".txt",
        ".lock",
        ".cfg",
        ".ini",
        ".sh",
    }
)

_STATUS_MAP: dict[str, Status] = {
    "Accepted": Status.ACCEPTED,
    "Proposed": Status.PROPOSED,
    "Done": Status.ACCEPTED,
    "In Progress": Status.PROPOSED,
}

_STATUS_TAG_PREFIX = "source-status:"

# Sections the field mapping consumes. Everything else falls through to body.
_CONSUMED_SECTIONS = frozenset(
    {"Context", "Decision", "Options considered", "Rationale", "Consequences"}
)

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
_BOLD_LABEL_RE = re.compile(r"^\s*(?:[-*]\s+)?\*\*([^*]+?)\*\*\s*[:：]?\s*(.*)$")
_BACKTICK_RUN_RE = re.compile(r"`+")
_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_TRAILING_LINE_RE = re.compile(r":\d+$")
_OPTION_LINE_RE = re.compile(r"^\*\*Option\s+([A-Za-z0-9]+)\s*[:—-]\s*")
_CONS_LABEL_RE = re.compile(r"^\s*(?:[-*]\s+)?\*\*Cons\*\*\s*[:：]?\s*(.*)$")
_TRAILING_MARKER_RE = re.compile(r"\s*\((?:chosen|recommended)\)\s*$")
_TRAILING_PAREN_RE = re.compile(r"\([^)]*\)\s*$")
_TRAILING_PUNCT_RE = re.compile(r"[.,;:!?]+$")
_BULLET_RE = re.compile(r"^\s*[-*]\s+(.+)$", re.MULTILINE)


@dataclass(frozen=True)
class _Block:
    """One heading block: level, heading text, and body without the heading."""

    level: int
    heading: str
    body: str


@dataclass(frozen=True)
class _Option:
    """One option within a decision unit."""

    key: str
    title: str
    label_line: str
    cons: str | None


class JsmasteryAdapter:
    """Adapts jsmastery style spec folders into canonical decision records."""

    @property
    def adapter_id(self) -> str:
        """The built in adapter's selector name (spec 0005 AC-1)."""
        return "jsmastery-specs"

    @property
    def adapter_version(self) -> str:
        """The adapter version, read live so a bump invalidates fingerprints."""
        return ADAPTER_VERSION

    def discover(self, corpus_root: Path) -> DiscoveryResult:
        """Walk docs/specs/, derive ids, collect contributing files, report skips."""
        specs_dir = corpus_root / "docs" / "specs"
        specs: list[DiscoveredSpec] = []
        skipped: list[SkippedSource] = []
        seen: dict[str, Path] = {}
        colliding: dict[str, list[Path]] = {}
        if not specs_dir.is_dir():
            # The corpus root is a directory but lacks this adapter's required
            # layout; name the missing structure (spec 0005 AC-20).
            return DiscoveryResult(
                specs=[],
                skipped=[],
                collisions=[],
                corpus_error="no docs/specs/ directory",
            )
        for child in sorted(specs_dir.iterdir()):
            if not child.is_dir():
                continue
            index_path = child / "index.md"
            if not index_path.is_file():
                skipped.append(SkippedSource(path=child, reason="no index.md"))
                continue
            spec_id = _derive_id(child.name)
            if spec_id is None:
                skipped.append(
                    SkippedSource(
                        path=child,
                        reason="no leading digits in directory name",
                    )
                )
                continue
            index_text = _read_text(index_path)
            if index_text is None:
                skipped.append(SkippedSource(path=child, reason="cannot read index.md"))
                continue
            if "Decision" not in _h2_sections(index_text):
                skipped.append(
                    SkippedSource(path=child, reason="no ## Decision section")
                )
                continue
            status_raw = _bold_field(_preamble(index_text), "Status")
            if status_raw is None or status_raw not in _STATUS_MAP:
                skipped.append(
                    SkippedSource(
                        path=child,
                        reason=f"status {status_raw!r} is not a known status",
                    )
                )
                continue
            if spec_id in seen:
                colliding.setdefault(spec_id, [seen[spec_id]]).append(child)
                continue
            seen[spec_id] = child
            contributing = [index_path]
            rationale_path = child / "rationale.md"
            if rationale_path.is_file():
                contributing.append(rationale_path)
            specs.append(
                DiscoveredSpec(
                    id=spec_id,
                    root=child,
                    corpus_root=corpus_root,
                    contributing_files=contributing,
                )
            )
        return DiscoveryResult(
            specs=specs,
            skipped=skipped,
            collisions=[
                Collision(id=spec_id, paths=paths, used=paths[0])
                for spec_id, paths in colliding.items()
            ],
        )

    def parse(self, spec: DiscoveredSpec) -> AdaptationResult:
        """Turn one discovered spec into a validated canonical record."""
        index_text = _read_text(spec.root / "index.md")
        if index_text is None:
            return AdaptationResult(
                record=None,
                violations=[
                    _violation(
                        "",
                        Severity.ERROR,
                        "file.unreadable",
                        f"cannot read {spec.root / 'index.md'}",
                    )
                ],
                attempted_fields=frozenset(),
                unresolved_mention_count=0,
                fingerprint=self.fingerprint(spec),
                field_sources={},
            )
        rationale_path = spec.root / "rationale.md"
        rationale_text = (
            _read_text(rationale_path) if rationale_path.is_file() else None
        )
        index_sections = _h2_sections(index_text)
        rationale_sections = _h2_sections(rationale_text) if rationale_text else {}
        sibling_names = {path.name for path in spec.contributing_files}

        index_rel = (
            spec.root.joinpath("index.md").relative_to(spec.corpus_root).as_posix()
        )
        rationale_rel = (
            spec.root.joinpath("rationale.md").relative_to(spec.corpus_root).as_posix()
            if rationale_text is not None
            else ""
        )

        status_raw = _bold_field(_preamble(index_text), "Status")
        if status_raw is None or status_raw not in _STATUS_MAP:
            return AdaptationResult(
                record=None,
                violations=[
                    _violation(
                        "",
                        Severity.ERROR,
                        "status.unmapped",
                        f"status {status_raw!r} is not a known status",
                    )
                ],
                attempted_fields=frozenset(),
                unresolved_mention_count=0,
                fingerprint=self.fingerprint(spec),
                field_sources={},
            )

        attempted: set[str] = set()
        field_sources: dict[str, list[SourceReference]] = {}

        context_source = _section_with_source(
            rationale_sections,
            index_sections,
            "Context",
            sibling_names,
            rationale_rel,
            index_rel,
        )
        if context_source is not None:
            context_problem, context_rel = context_source
            field_sources["context.problem"] = [SourceReference(context_rel, "Context")]
        else:
            context_problem = None
            attempted.add("context.problem")

        decision_body = index_sections.get("Decision")
        chosen = (
            _bold_field(decision_body, "Chosen option")
            if decision_body is not None
            else None
        )
        if chosen is None:
            attempted.add("decision.chosen")
        elif decision_body is not None:
            field_sources["decision.chosen"] = [SourceReference(index_rel, "Decision")]

        options_source = _section_with_source(
            rationale_sections,
            index_sections,
            "Options considered",
            sibling_names,
            rationale_rel,
            index_rel,
        )
        if options_source is not None:
            options_body, options_rel = options_source
            alternatives, alternatives_attempted = _build_alternatives(
                options_body, chosen or ""
            )
            if alternatives_attempted:
                attempted.add("decision.alternatives")
            for alternative_index, alternative in enumerate(alternatives):
                if alternative.title is not None:
                    field_sources[
                        f"decision.alternatives[{alternative_index}].title"
                    ] = [SourceReference(options_rel, "Options considered")]
                if alternative.rejection_reason is not None:
                    field_sources[
                        f"decision.alternatives[{alternative_index}].rejection_reason"
                    ] = [SourceReference(options_rel, "Options considered")]
        else:
            alternatives, alternatives_attempted = _build_alternatives(
                None, chosen or ""
            )
            if alternatives_attempted:
                attempted.add("decision.alternatives")

        rationale_source = _section_with_source(
            rationale_sections,
            index_sections,
            "Rationale",
            sibling_names,
            rationale_rel,
            index_rel,
        )
        why: list[str] = []
        rationale_summary: str | None = None
        if rationale_source is None:
            attempted.add("why")
            attempted.add("rationale_summary")
        else:
            rationale_body, rationale_src_rel = rationale_source
            why = _bullets(rationale_body)
            summary = _paragraphs(rationale_body)
            rationale_summary = summary if summary else None
            for why_index, _item in enumerate(why):
                field_sources[f"why[{why_index}]"] = [
                    SourceReference(rationale_src_rel, "Rationale")
                ]
            if rationale_summary is not None:
                field_sources["rationale_summary"] = [
                    SourceReference(rationale_src_rel, "Rationale")
                ]

        title = _title_from_h1(_h1_title(index_text))
        if title is None:
            attempted.add("title")
        else:
            field_sources["title"] = [SourceReference(index_rel, "preamble")]
        date = _bold_field(_preamble(index_text), "Date")

        consequences_body = index_sections.get("Consequences")
        positive: list[str] = []
        negative: list[str] = []
        consequences_remainder = ""
        consumed = _CONSUMED_SECTIONS
        if (
            consequences_body is None
            or _is_stub(consequences_body, sibling_names)
            or not consequences_body.strip()
        ):
            attempted.add("consequences.positive")
            attempted.add("consequences.negative")
        else:
            positive = _list_under_label(consequences_body, "Positive")
            negative = _list_under_label(consequences_body, "Negative")
            if not positive and not negative:
                # Present, but written with labels the mapping does not know.
                # Flag it and let the whole section fall through to the body,
                # so an unrecognized heading loses no content.
                attempted.add("consequences.positive")
                attempted.add("consequences.negative")
                consumed = consumed - {"Consequences"}
            else:
                # The canonical fields took Positive and Negative; anything
                # else in the section (for example **Neutral**) is residue and
                # must survive in the body rather than vanish (AC-11).
                consequences_remainder = _unconsumed_remainder(consequences_body)
                for positive_index, _item in enumerate(positive):
                    field_sources[f"consequences.positive[{positive_index}]"] = [
                        SourceReference(index_rel, "Consequences")
                    ]
                for negative_index, _item in enumerate(negative):
                    field_sources[f"consequences.negative[{negative_index}]"] = [
                        SourceReference(index_rel, "Consequences")
                    ]

        body, body_sections = _residue_body_sections(
            index_sections,
            rationale_sections,
            sibling_names,
            consumed,
            index_rel,
            rationale_rel,
        )
        extra_body_sources: list[tuple[str, str]] = []
        if consequences_remainder:
            body = (
                f"{body}\n\n{consequences_remainder}"
                if body
                else consequences_remainder
            )
            # The residue trails the last retained H2 section (or stands alone
            # when no section was retained), so it becomes part of that body
            # unit's text. Its provenance points at the Consequences section
            # from which it came, matching how the chunker splits body[n].
            if body_sections:
                extra_body_sources.append(("Consequences", index_rel))
            else:
                body_sections.append(("Consequences", index_rel))
        for body_index, (heading, section_rel) in enumerate(body_sections):
            sources = [SourceReference(section_rel, heading)]
            if body_index == len(body_sections) - 1:
                sources.extend(
                    SourceReference(rel, name) for name, rel in extra_body_sources
                )
            field_sources[f"body[{body_index}]"] = sources

        supersedes = _bold_field(_preamble(index_text), "Supersedes")
        if supersedes is not None:
            field_sources["supersedes"] = [SourceReference(index_rel, "preamble")]

        evidence, unresolved = _evidence_and_unresolved(spec)

        record = CanonicalDecisionRecord(
            id=spec.id,
            title=title,
            status=_STATUS_MAP[status_raw],
            date=date,
            body=body,
            context=Context(problem=context_problem)
            if context_problem is not None
            else None,
            decision=Decision(chosen=chosen, alternatives=alternatives),
            why=why,
            rationale_summary=rationale_summary,
            consequences=Consequences(positive=positive, negative=negative)
            if positive or negative
            else None,
            evidence=evidence,
            tags=[f"{_STATUS_TAG_PREFIX}{status_raw}"],
            supersedes=supersedes,
        )

        context = ValidationContext(
            attempted_fields=frozenset(attempted),
            unknown_fields=frozenset(),
            existing_paths=resolve_cited_paths(record, spec.corpus_root),
            unresolved_mention_count=unresolved,
        )
        return AdaptationResult(
            record=record,
            violations=validate(record, context),
            attempted_fields=frozenset(attempted),
            unresolved_mention_count=unresolved,
            fingerprint=self.fingerprint(spec),
            field_sources=field_sources,
        )

    def fingerprint(self, spec: DiscoveredSpec) -> str:
        """A SHA-256 over contributing file paths and bytes, plus the version."""
        digest = hashlib.sha256()
        digest.update(ADAPTER_VERSION.encode("utf-8"))
        for path in spec.contributing_files:
            digest.update(path.relative_to(spec.corpus_root).as_posix().encode("utf-8"))
            digest.update(b"\x00")
            digest.update(_read_bytes(path))
            digest.update(b"\x00")
        return digest.hexdigest()


def _evidence_and_unresolved(
    spec: DiscoveredSpec,
) -> tuple[list[Evidence], int]:
    """Spec evidence from contributing files, file evidence from code paths.

    Returns (evidence, unresolved mention count) from one pass over the
    contributing files, so extraction does not run twice.
    """
    evidence: list[Evidence] = [
        Evidence(
            kind=EvidenceKind.SPEC,
            target=path.relative_to(spec.corpus_root).as_posix(),
        )
        for path in spec.contributing_files
    ]
    seen: set[str] = set()
    unresolved = 0
    for path in spec.contributing_files:
        text = _read_text(path)
        if text is None:
            continue
        targets, count = _extract_code_paths(text, spec.corpus_root)
        unresolved += count
        for target in targets:
            if target not in seen:
                seen.add(target)
                evidence.append(Evidence(kind=EvidenceKind.FILE, target=target))
    return evidence, unresolved


def _derive_id(directory_name: str) -> str | None:
    match = re.match(r"^(\d+)", directory_name)
    if match is None:
        return None
    return f"DM-{match.group(1)}"


def _h1_title(text: str) -> str | None:
    for block in _blocks(text):
        if block.level == 1:
            return block.heading
    return None


def _title_from_h1(title: str | None) -> str | None:
    if title is None:
        return None
    return re.sub(r"^\d+\.\s*", "", title)


def _h2_sections(text: str) -> dict[str, str]:
    """Map of H2 heading to body (including any nested H3), in document order.

    A duplicated heading concatenates its bodies instead of overwriting, so a
    later occurrence's content is never silently lost; the first occurrence
    keeps its place in the order.
    """
    sections: dict[str, str] = {}
    for block in _blocks(text):
        if block.level != 2:
            continue
        if block.heading in sections:
            sections[block.heading] = f"{sections[block.heading]}\n\n{block.body}"
        else:
            sections[block.heading] = block.body
    return sections


def _fenced_line_numbers(lines: list[str]) -> frozenset[int]:
    """Line numbers covered by a fenced code block that is actually closed.

    A fence closes only on the same delimiter character, repeated at least as
    many times as the opening run, so a ``~~~`` inside a ```` ``` ```` block
    does not end it. A fence that is never closed covers nothing: treating it
    as running to the end of file would let one stray delimiter swallow every
    heading after it, which loses whole sections rather than one snippet.
    """
    fenced: set[int] = set()
    opened_at: int | None = None
    opening = ""
    for index, line in enumerate(lines):
        match = _FENCE_RE.match(line)
        if match is None:
            continue
        marker = match.group(1)
        if opened_at is None:
            opened_at = index
            opening = marker
        elif marker[0] == opening[0] and len(marker) >= len(opening):
            fenced.update(range(opened_at, index + 1))
            opened_at = None
            opening = ""
    return frozenset(fenced)


def _blocks(text: str, split_levels: tuple[int, ...] = (1, 2)) -> list[_Block]:
    """Split text into heading blocks on the given levels.

    A section is an H2 block running from its heading to the next H2 or end
    of file, including any nested H3 headings, so H3 headings stay inside the
    parent block's body. Content before the first split heading is dropped.
    A ``#`` line inside a closed fenced code block is body text, never a
    heading, since a fence can hold a shell comment or a markdown snippet
    that looks like one. See ``_fenced_line_numbers`` for what counts.
    """
    lines = text.split("\n")
    fenced = _fenced_line_numbers(lines)
    blocks: list[_Block] = []
    current: _Block | None = None
    body: list[str] = []
    for index, line in enumerate(lines):
        match = None if index in fenced else _HEADING_RE.match(line)
        if match and len(match.group(1)) in split_levels:
            if current is not None:
                blocks.append(
                    _Block(
                        current.level,
                        current.heading,
                        "\n".join(body).strip("\n"),
                    )
                )
            current = _Block(len(match.group(1)), match.group(2).strip(), "")
            body = []
        elif current is not None:
            body.append(line)
    if current is not None:
        blocks.append(
            _Block(current.level, current.heading, "\n".join(body).strip("\n"))
        )
    return blocks


def _section_with_source(
    preferred: dict[str, str],
    fallback: dict[str, str],
    name: str,
    sibling_names: set[str],
    preferred_rel: str,
    fallback_rel: str,
) -> tuple[str, str] | None:
    """A section's body and its source relative path, else None.

    The preferred file wins (``rationale.md``), the fallback follows
    (``index.md``), both under the precedence and stub rules. The returned
    relative path names the file that supplied the body, for field_sources
    provenance (spec 0007 AC-2).
    """
    for sections, rel in ((preferred, preferred_rel), (fallback, fallback_rel)):
        body = sections.get(name)
        if body is None:
            continue
        if not body.strip():
            continue
        if _is_stub(body, sibling_names):
            continue
        return body, rel
    return None


def _is_stub(body: str, sibling_names: set[str]) -> bool:
    """A short pointer to a sibling contributing file, treated as absent.

    A stub is a section whose whole collapsed body points at a sibling file,
    for example ``See `rationale.md`.`` or ``See [rationale.md](rationale.md).``.
    The 80 character bound keeps the test to short bodies, and the pointer
    shape check stops a section that merely mentions a sibling in passing
    (``This supersedes rationale.md entirely.``) from being discarded.
    """
    collapsed = _collapse_whitespace(_reduce_links(body))
    if len(collapsed) > 80:
        return False
    return any(_is_pointer(collapsed, name) for name in sibling_names)


def _is_pointer(collapsed: str, name: str) -> bool:
    """Whether ``collapsed`` points at ``name`` rather than just mentions it.

    A pointer is the sibling's name alone, or a short phrase that points at
    it (``See rationale.md.``); a mention embedded in a real sentence
    (``This supersedes rationale.md entirely.``) is not a pointer, so real
    content is never discarded as a stub.
    """
    lowered = collapsed.lower()
    name_lower = name.lower()
    if lowered.strip(" .,;:!?") == name_lower:
        return True
    remainder = lowered.replace(name_lower, "", 1).strip(" .,;:!?")
    # "check" is deliberately absent: it reads more like a command to inspect
    # than a pure pointer, and a body such as "Check `rationale.md` for
    # details." has substance of its own.
    return remainder.startswith(("see", "read", "refer", "point to", "look at"))


def _residue_body_sections(
    index_sections: dict[str, str],
    rationale_sections: dict[str, str],
    sibling_names: set[str],
    consumed: frozenset[str] = _CONSUMED_SECTIONS,
    index_rel: str = "index.md",
    rationale_rel: str = "rationale.md",
) -> tuple[str, list[tuple[str, str]]]:
    """Every unconsumed section from both files with its source, headings kept.

    Returns (body, [(heading, relative source path), ...]) in source order.
    ``consumed`` lets the caller narrow the default set when a section the
    mapping normally claims turned out to yield nothing, so its content falls
    through to the body instead of being dropped. A heading present in both
    files is emitted once with the ``rationale.md`` body and source, the same
    precedence every other section rule applies (AC-8), so nothing is
    duplicated.
    """
    parts: list[str] = []
    sources: list[tuple[str, str]] = []
    seen: set[str] = set()
    for heading in (*index_sections.keys(), *rationale_sections.keys()):
        if heading in consumed or heading in seen:
            continue
        body = rationale_sections.get(heading)
        used_rel = rationale_rel
        if body is None or not body.strip() or _is_stub(body, sibling_names):
            body = index_sections.get(heading)
            used_rel = index_rel
        if body is None or not body.strip() or _is_stub(body, sibling_names):
            continue
        parts.append(f"## {heading}\n\n{body}")
        sources.append((heading, used_rel))
        seen.add(heading)
    return "\n\n".join(parts), sources


def _bold_field(text: str, label: str) -> str | None:
    """The value of a ``**Label**`` line in ``text``, else None."""
    for line in text.split("\n"):
        match = _BOLD_LABEL_RE.match(line.strip())
        if match and match.group(1).strip() == label:
            value = match.group(2).strip()
            return value if value else None
    return None


def _preamble(text: str) -> str:
    """The content before the first H2: the title line and metadata fields.

    ``**Date**``, ``**Status**``, and ``**Supersedes**`` live in the preamble;
    a mention of one inside a section body must not populate the field, so
    the field mapping reads them only from here (the parsing model already
    defines the preamble as the metadata block).
    """
    lines = text.split("\n")
    for index, line in enumerate(lines):
        match = _HEADING_RE.match(line)
        if match is not None and len(match.group(1)) >= 2:
            return "\n".join(lines[:index])
    return text


def _matches_label(heading: str, label: str) -> bool:
    """Whether ``heading`` names ``label``, allowing a trailing qualifier.

    The corpus writes both a bare ``Negative`` and a qualified
    ``Negative / tradeoffs``; both name the same list, so a heading counts
    as a match when it starts with the label and the next character (if
    any) is not itself a letter or digit, e.g. ``Negative / tradeoffs``
    matches but ``Negatively`` does not.
    """
    heading = heading.strip().lower()
    label = label.strip().lower()
    if not heading.startswith(label):
        return False
    return len(heading) == len(label) or not heading[len(label)].isalnum()


def _list_under_label(body: str, label: str) -> list[str]:
    """Bullet items following a ``**Label**`` line until the next section label.

    Only a line that opens directly with ``**`` is a section label; a bullet
    whose text happens to start with a bold lead in (``- **Term**: ...``)
    stays a bullet, since ``_BOLD_LABEL_RE`` alone can't tell the two apart.
    """
    items: list[str] = []
    collecting = False
    for line in body.split("\n"):
        stripped = line.strip()
        label_match = (
            _BOLD_LABEL_RE.match(stripped) if stripped.startswith("**") else None
        )
        if label_match and _matches_label(label_match.group(1), label):
            collecting = True
            inline = label_match.group(2).strip()
            if inline:
                items.append(inline)
            continue
        if not collecting:
            continue
        if label_match:
            break
        bullet = re.match(r"^[-*]\s+(.+)$", stripped)
        if bullet:
            items.append(bullet.group(1).strip())
    return items


def _unconsumed_remainder(body: str) -> str:
    """The parts of a Consequences body no canonical field consumes.

    Positive and Negative become canonical fields through their bullet items;
    everything else in the section survives in the record body (AC-11) so
    content is never silently lost. That includes any other bold labeled
    block (for example **Neutral**), and any non bullet prose anywhere in the
    section, including a sentence that sits between two labeled blocks: such
    a sentence is not attributed to the block that precedes it, so it is not
    dropped when that block is a consumed Positive or Negative list.
    """
    parts: list[str] = []
    current: list[str] = []
    current_label: str | None = None

    def flush() -> None:
        if not current:
            return
        lines = list(current)
        current.clear()
        if current_label is not None and (
            _matches_label(current_label, "Positive")
            or _matches_label(current_label, "Negative")
        ):
            # The label and its bullets are consumed by the fields; keep any
            # non bullet prose so it falls through to the body.
            kept = [
                line
                for line in lines
                if re.match(r"^\s*[-*]\s+", line) is None
                and _BOLD_LABEL_RE.match(line.strip()) is None
            ]
        else:
            kept = lines
        text = "\n".join(kept).strip()
        if text:
            parts.append(text)

    for line in body.split("\n"):
        stripped = line.strip()
        label_match = (
            _BOLD_LABEL_RE.match(stripped) if stripped.startswith("**") else None
        )
        if label_match is not None:
            flush()
            current_label = label_match.group(1)
        current.append(line)
    flush()
    return "\n\n".join(parts)


def _build_alternatives(
    options_body: str | None, chosen_line: str
) -> tuple[list[Alternative], bool]:
    """Alternatives pooled across decision units, plus whether any unit failed.

    A unit whose winner does not resolve contributes no alternatives and marks
    decision.alternatives as attempted, while units that did resolve still
    contribute theirs (AC-9).
    """
    if options_body is None:
        return [], True
    alternatives: list[Alternative] = []
    any_unresolved = False
    for heading, body, options in _parse_units(options_body):
        winner = _resolve_winner(heading, body, options, chosen_line)
        if winner is None:
            any_unresolved = True
            continue
        question = _panel_question(heading, body)
        for option in options:
            if option is winner:
                continue
            title = option.title
            if heading.startswith("Panel") and question:
                title = f"{question}: {title}"
            alternatives.append(Alternative(title=title, rejection_reason=option.cons))
    return alternatives, any_unresolved


def _panel_question(heading: str, body: str) -> str | None:
    """A panel's question, from a **Question**: line or the heading itself.

    The real corpus writes the question into the heading as
    ``### Panel 1: Which routes the gate covers``, and a ``**Question**:`` line
    as a fixture only, so the heading is the source when the line is absent.
    """
    question = _bold_field(body, "Question")
    if question is not None:
        return question
    match = re.match(r"^Panel\s+\w+\s*[:：—-]\s*(.+)$", heading)
    if match is None:
        return None
    return match.group(1).strip()


def _parse_units(
    options_body: str,
) -> list[tuple[str, str, list[_Option]]]:
    """Split an Options considered body into (heading, body, options) units.

    A panel spec has one unit per ### Panel N block; every other spec has one
    unit, the whole section. Options inside a unit are either bold label lines
    or ### Option N headings, and `_parse_options` accepts both.
    """
    panel_blocks = [
        block
        for block in _blocks(options_body, (3,))
        if block.heading.startswith("Panel")
    ]
    if panel_blocks:
        return [
            (block.heading, block.body, _parse_options(block.body))
            for block in panel_blocks
        ]
    return [("", options_body, _parse_options(options_body))]


def _parse_options(unit_body: str) -> list[_Option]:
    """Options within a unit, as bold label lines or ### Option N headings.

    The real corpus uses bold `**Option N:**` or `**Option A — ...**` lines in
    panel specs and `### Option N:` H3 headings in plain option specs, so both
    shapes are parsed, each option bounded by the next option or heading.
    """
    inline = _parse_inline_options(unit_body)
    if inline:
        return inline
    return _parse_heading_options(unit_body)


def _parse_inline_options(unit_body: str) -> list[_Option]:
    """Options written as bold label lines, bounded by the next option or heading."""
    lines = unit_body.split("\n")
    fenced = _fenced_line_numbers(lines)
    starts = [index for index, line in enumerate(lines) if _OPTION_LINE_RE.match(line)]
    options: list[_Option] = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        for index in range(start + 1, end):
            if index not in fenced and _HEADING_RE.match(lines[index]):
                end = index
                break
        block_lines = lines[start:end]
        parts = _option_parts(block_lines[0])
        if parts is None:
            continue
        key, rest = parts
        options.append(
            _Option(
                key=key,
                title=_clean_title(rest),
                label_line=block_lines[0],
                cons=_cons_for_block(block_lines[1:]),
            )
        )
    return options


def _parse_heading_options(unit_body: str) -> list[_Option]:
    """Options written as ### Option N headings with Pros/Cons sections."""
    options: list[_Option] = []
    for block in _blocks(unit_body, (3,)):
        if not block.heading.startswith("Option"):
            continue
        key_match = re.match(r"^Option\s+([A-Za-z0-9]+)", block.heading)
        if key_match is None:
            continue
        title = _clean_title(
            re.sub(r"^Option\s+[A-Za-z0-9]+\s*[:：—-]\s*", "", block.heading)
        )
        options.append(
            _Option(
                key=key_match.group(1),
                title=title,
                label_line=block.heading,
                cons=_cons_for_block(block.body.split("\n")),
            )
        )
    return options


def _option_parts(line: str) -> tuple[str, str] | None:
    """The option key and raw title from an option label line.

    Handles the jsmastery shapes: a label only bold (`**Option 1:** Title` and
    `**Option A —** Title`), a title inside the bold ending the line
    (`**Option A — Title (chosen)**`), and a title inside the bold followed by
    a description (`**Option A — Title**: gate ...`).
    """
    match = _OPTION_LINE_RE.match(line)
    if match is None:
        return None
    rest = line[match.end() :]
    # A label only bold: the label's own closing ** follows the separator.
    if rest.startswith("**"):
        rest = rest[2:]
    # A title inside the bold: cut at the closing **, discarding any description.
    close = rest.find("**")
    if close != -1:
        rest = rest[:close]
    return match.group(1), rest.strip()


def _clean_title(rest: str) -> str:
    """The stored title: trailing chosen or recommended marker removed."""
    return _TRAILING_MARKER_RE.sub("", rest).strip()


def _cons_for_block(body_lines: list[str]) -> str | None:
    """The option's Cons text, bounded by the next bold label or heading."""
    cons_start: int | None = None
    for index, line in enumerate(body_lines):
        if _CONS_LABEL_RE.match(line.strip()):
            cons_start = index
            break
    if cons_start is None:
        return None
    match = _CONS_LABEL_RE.match(body_lines[cons_start].strip())
    if match is None:
        return None
    fenced = _fenced_line_numbers(body_lines)
    parts: list[str] = []
    inline = match.group(1).strip()
    if inline:
        parts.append(inline)
    for index in range(cons_start + 1, len(body_lines)):
        if index in fenced:
            parts.append(body_lines[index])
            continue
        stripped = body_lines[index].strip()
        if not stripped:
            parts.append("")
            continue
        if _BOLD_LABEL_RE.match(stripped):
            break
        if _HEADING_RE.match(stripped):
            break
        parts.append(_strip_bullet_marker(stripped))
    text = "\n".join(parts).strip()
    return text if text else None


def _strip_bullet_marker(line: str) -> str:
    """Remove a leading list marker from a line, if present."""
    return re.sub(r"^[-*]\s+", "", line)


def _resolve_winner(
    heading: str, body: str, options: list[_Option], chosen_line: str
) -> _Option | None:
    """The winning option within a unit, by the spec 0003 ladder, in order."""
    if heading.startswith("Panel"):
        letter = _panel_decision_letter(body)
        if letter is not None:
            for option in options:
                if option.key == letter:
                    return option
    ordinal = _chosen_ordinal(chosen_line)
    if ordinal is not None:
        for option in options:
            if option.key == ordinal:
                return option
    match = _title_match(chosen_line, options)
    if match is not None:
        return match
    marked = [option for option in options if "(chosen)" in option.label_line]
    if len(marked) == 1:
        return marked[0]
    return None


def _panel_decision_letter(unit_body: str) -> str | None:
    """The letter after the first Option in a panel's **Decision**: line."""
    decision = _bold_field(unit_body, "Decision")
    if decision is None:
        return None
    match = re.search(r"\bOption\s+([A-Za-z])\b", decision)
    return match.group(1) if match is not None else None


def _chosen_ordinal(chosen_line: str) -> str | None:
    """An ordinal in the chosen line, for example from 'Option 1: ...'."""
    match = re.search(r"\bOption\s+(\d+)\b", chosen_line)
    return match.group(1) if match is not None else None


def _title_match(chosen_line: str, options: list[_Option]) -> _Option | None:
    """Match the chosen line's text against option titles, stripped to compare."""
    target = _strip_for_compare(chosen_line)
    if not target:
        return None
    for option in options:
        if _strip_for_compare(option.title) == target:
            return option
    return None


def _strip_for_compare(text: str) -> str:
    """Lowercase text with trailing parentheticals and punctuation removed."""
    out = text.strip()
    changed = True
    while changed:
        changed = False
        new = _TRAILING_PAREN_RE.sub("", out).strip()
        if new != out:
            out = new
            changed = True
        new = _TRAILING_PUNCT_RE.sub("", out).strip()
        if new != out:
            out = new
            changed = True
    return out.lower()


def _bullets(section_body: str) -> list[str]:
    return [match.group(1).strip() for match in _BULLET_RE.finditer(section_body)]


def _paragraphs(section_body: str) -> str:
    """The section's prose: bullet lines removed, whitespace collapsed."""
    lines = [
        line
        for line in section_body.split("\n")
        if re.match(r"^\s*[-*]\s+", line) is None
    ]
    return _collapse_whitespace("\n".join(lines))


def _looks_like_path(token: str) -> bool:
    """True when a non resolving token is shaped like a code path (AC-6).

    A token is path shaped when it contains a slash, ends in a known file
    extension compared without regard to case, or starts with a dot. The
    caller passes ``shape_token``, the token as it stood before the trailing
    slash was stripped, so a trailing slash counts as a path signal in its
    own right.
    """
    if "/" in token:
        return True
    if token.startswith("."):
        return True
    lowered = token.lower()
    return any(lowered.endswith(ext) for ext in _KNOWN_PATH_EXTENSIONS)


def _inline_code_spans(text: str) -> list[str]:
    """Return CommonMark style inline code span bodies."""
    text = _without_closed_fenced_blocks(text)
    spans: list[str] = []
    run_matches = list(_BACKTICK_RUN_RE.finditer(text))
    opener_index = 0
    while opener_index < len(run_matches):
        opener = run_matches[opener_index]
        opener_length = len(opener.group(0))
        closer_index = opener_index + 1
        while closer_index < len(run_matches):
            closer = run_matches[closer_index]
            if len(closer.group(0)) == opener_length:
                spans.append(text[opener.end() : closer.start()])
                opener_index = closer_index + 1
                break
            closer_index += 1
        else:
            opener_index += 1
    return spans


def _without_closed_fenced_blocks(text: str) -> str:
    """Replace closed fenced code block lines with blanks."""
    lines = text.split("\n")
    fenced = _fenced_line_numbers(lines)
    return "\n".join(
        "" if index in fenced else line for index, line in enumerate(lines)
    )


def _extract_code_paths(text: str, corpus_root: Path) -> tuple[list[str], int]:
    """Resolved code path targets plus the count of unresolved mentions.

    Applies the AC-4 pipeline to every inline code span: split on whitespace,
    strip a trailing line number and slash, discard absolute, package, and
    glob tokens, then resolve each survivor case sensitively against the
    corpus root. A survivor that does not resolve counts toward the unresolved
    total only when it is shaped like a path (AC-6 step 7), tested against
    the token as it stood before the trailing slash was stripped.
    """
    resolved: list[str] = []
    seen: set[str] = set()
    unresolved = 0
    listdir_cache: dict[Path, frozenset[str]] = {}
    for span in _inline_code_spans(text):
        for token in span.split():
            token = token.strip()
            if not token:
                continue
            token = _TRAILING_LINE_RE.sub("", token)
            shape_token = token
            if token.endswith("/"):
                token = token[:-1]
            if not token:
                continue
            if token.startswith("/") or token.startswith("@") or "*" in token:
                continue
            normalized = normalize_target(token)
            if path_resolves_case_sensitive(corpus_root, normalized, listdir_cache):
                if normalized not in seen:
                    seen.add(normalized)
                    resolved.append(normalized)
            elif _looks_like_path(shape_token):
                unresolved += 1
    return resolved, unresolved


def _read_text(path: Path) -> str | None:
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None
    return raw.replace("\r\n", "\n").replace("\r", "\n")


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError:
        return b""


def _collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _reduce_links(text: str) -> str:
    return _LINK_RE.sub(r"\1", text)


def _violation(field: str, severity: Severity, rule: str, reason: str) -> Violation:
    return Violation(field=field, severity=severity, rule=rule, reason=reason)
