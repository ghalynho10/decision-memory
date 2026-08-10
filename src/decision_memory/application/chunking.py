"""Application: canonical value paths, chunk ids, embedding prefix, chunking.

Spec 0007 AC-4 and AC-5 fix the chunking contract. The chunker walks canonical
values in schema order, preserves canonical field boundaries, normalizes line
endings without otherwise rewriting underlying text, packs paragraphs and
sentences to a token target, copies a trailing overlap into the next chunk,
and fails the record when any complete embedding input exceeds the pinned
model token limit. Deterministic chunk ids hash the generation, record, and
value path. The embedding prefix adds the record title and aggregate value
path to the embedding input but is never stored as evidence text.

This module is pure application code: it imports only the standard library,
the domain record, and the canonical helpers. Token counting is injected as a
callable so no third party library enters the application layer (AC-20).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeAlias

from decision_memory.application.canonical import (
    SourceReference,
    canonical_json,
    sha256_hex,
)
from decision_memory.application.dto import ChunkPlan
from decision_memory.application.pipeline import (
    MODEL_TOKEN_LIMIT,
    PipelineConfig,
)
from decision_memory.domain.records import Alternative, CanonicalDecisionRecord

TokenCounter: TypeAlias = Callable[[str], int]

# The exact value path grammar from spec 0007: name((.name)|(\[[0-9]+\]))*.
_VALUE_PATH_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*((\.[A-Za-z_][A-Za-z0-9_]*)|(\[[0-9]+\]))*$"
)

_H2_RE = re.compile(r"^##\s+(.*)$")

# Sentence terminators followed by zero or more closing characters, then one
# or more whitespace or end of text (spec 0007 AC-4). The closing characters
# are single and double quotes, right single and right double quotes, and
# closing parentheses, brackets, and braces.
_SENTENCE_END_RE = re.compile(r"[.!?]['\"\u2019\u201d)\]}]*(\s+|$)")
_CLOSING_CHARS = frozenset("'\"\u2019\u201d)}]")


class ChunkingError(Exception):
    """A record cannot be chunked: oversize embedding input or bad provenance."""


# A module singleton so function defaults never call a constructor (B008).
DEFAULT_PIPELINE_CONFIG = PipelineConfig()


@dataclass(frozen=True)
class _Unit:
    """One chunkable canonical value with its sources."""

    value_path: str
    text: str
    sources: tuple[SourceReference, ...]


def is_valid_value_path(path: str) -> bool:
    """Whether ``path`` matches the exact value path grammar."""
    return _VALUE_PATH_RE.fullmatch(path) is not None


def chunk_id(
    generation_id: str,
    record_id: str,
    fingerprint: str,
    value_path: str,
    ordinal: int,
) -> str:
    """Deterministic chunk id: ch_ plus SHA256 over the canonical payload."""
    payload = [
        "chunk-v1",
        generation_id,
        record_id,
        fingerprint,
        value_path,
        ordinal,
    ]
    return "ch_" + sha256_hex(canonical_json(payload))


def embedding_input(title: str, value_path: str, chunk_text: str) -> str:
    """The embedding prefix plus the chunk text (embedding-prefix-v1).

    Title whitespace collapses to one ASCII space with outer whitespace
    removed; value paths follow the declared grammar; chunk text is inserted
    literally after line ending normalization.
    """
    collapsed_title = " ".join(title.split())
    return f"Record title: {collapsed_title}\nValue path: {value_path}\n\n{chunk_text}"


def _paragraphs(text: str) -> list[str]:
    """Paragraphs delimited by blank lines, line endings normalized to LF.

    A blank line holds only spaces or tabs before LF; a run of one or more
    blank lines delimits paragraphs. Leading and trailing blank lines are
    discarded, while nonblank content and single line breaks inside a
    paragraph are preserved.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    stripped = normalized.strip(" \t\n")
    if not stripped:
        return []
    parts = re.split(r"\n[ \t]*\n(?:[ \t]*\n)*", stripped)
    return [part for part in parts if part.strip(" \t\n")]


def _split_sentences(text: str) -> list[str]:
    """Split text into complete sentences at the AC-4 boundaries.

    A sentence ends at ``.``, ``?``, or ``!`` followed by zero or more closing
    characters (single and double quotes, right single and double quotes,
    closing parentheses, brackets, and braces) and then one or more whitespace
    characters or the end of text. Trailing whitespace is not kept.
    """
    sentences: list[str] = []
    position = 0
    for match in _SENTENCE_END_RE.finditer(text):
        terminator = match.start(0)
        if terminator < position:
            continue
        sentence_end = terminator
        while sentence_end < len(text):
            if text[sentence_end] not in _CLOSING_CHARS:
                break
            sentence_end += 1
        if match.group(1):
            while sentence_end < len(text) and text[sentence_end].isspace():
                sentence_end += 1
        sentence = text[position:sentence_end].strip()
        if sentence:
            sentences.append(sentence)
        position = sentence_end
    remainder = text[position:].strip()
    if remainder:
        sentences.append(remainder)
    return sentences


def _pack_oversize_paragraph(
    paragraph: str, count_tokens: TokenCounter, config: PipelineConfig
) -> list[str]:
    """A paragraph over the token target, split into complete sentences."""
    sentences = _split_sentences(paragraph)
    if not sentences:
        return [paragraph]
    chunks: list[str] = []
    current: list[str] = []
    for sentence in sentences:
        if count_tokens(sentence) > config.target:
            if current:
                chunks.append(" ".join(current))
                current = []
            chunks.append(sentence)
            continue
        candidate = current + [sentence]
        if count_tokens(" ".join(candidate)) <= config.target:
            current = candidate
        else:
            if current:
                chunks.append(" ".join(current))
            current = [sentence]
    if current:
        chunks.append(" ".join(current))
    return chunks


def _pack_paragraphs(
    paragraphs: list[str], count_tokens: TokenCounter, config: PipelineConfig
) -> list[str]:
    """Pack paragraphs into chunks, joined by exactly two LF characters."""
    chunks: list[str] = []
    current: list[str] = []
    for paragraph in paragraphs:
        if count_tokens(paragraph) > config.target:
            if current:
                chunks.append("\n\n".join(current))
                current = []
            chunks.extend(_pack_oversize_paragraph(paragraph, count_tokens, config))
            continue
        candidate = current + [paragraph]
        if count_tokens("\n\n".join(candidate)) <= config.target:
            current = candidate
        else:
            if current:
                chunks.append("\n\n".join(current))
            current = [paragraph]
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _overlap_text(
    chunk_text: str, count_tokens: TokenCounter, config: PipelineConfig
) -> str:
    """The largest complete trailing sentence sequence at most 15 percent.

    The copied sentences join with one space; if no complete sentence fits
    the bound the overlap is empty (spec 0007 AC-4).
    """
    limit = max(1, int(count_tokens(chunk_text) * 0.15))
    sentences = _split_sentences(chunk_text)
    for size in range(len(sentences), 0, -1):
        tail = sentences[-size:]
        joined = " ".join(tail)
        if count_tokens(joined) <= limit:
            return joined
    return ""


def _apply_overlap(
    packed: list[str], count_tokens: TokenCounter, config: PipelineConfig
) -> list[str]:
    """Prepend each chunk's trailing overlap to the following chunk."""
    if not packed:
        return packed
    result = [packed[0]]
    for index in range(1, len(packed)):
        overlap = _overlap_text(packed[index - 1], count_tokens, config)
        if overlap:
            result.append(overlap + "\n\n" + packed[index])
        else:
            result.append(packed[index])
    return result


def _alternative_text(alternative: Alternative) -> str:
    """The atomic alternative text: title plus the optional rejection reason."""
    text = f"Alternative: {alternative.title}"
    if alternative.rejection_reason:
        text += f"\nRejected because: {alternative.rejection_reason}"
    return text


def _alternative_sources(
    index: int, field_sources: dict[str, list[SourceReference]]
) -> tuple[SourceReference, ...]:
    """The sorted, deduplicated union of the two leaf source lists."""
    refs: list[SourceReference] = []
    for path in (
        f"decision.alternatives[{index}].title",
        f"decision.alternatives[{index}].rejection_reason",
    ):
        refs.extend(field_sources.get(path, []))
    return tuple(sorted(set(refs), key=lambda ref: (ref.path, ref.section)))


def _split_body_units(body: str) -> list[tuple[str, str]]:
    """Split the combined body into (heading, section text) units on H2.

    A unit runs from one ``## heading`` line to the next heading or the end of
    the body. Text that trails the last heading (a residue block) belongs to
    the last unit, matching how the adapter folds its provenance.
    """
    normalized = body.replace("\r\n", "\n").replace("\r", "\n")
    units: list[tuple[str, str]] = []
    current_heading: str | None = None
    current_lines: list[str] = []
    for line in normalized.split("\n"):
        match = _H2_RE.match(line)
        if match:
            if current_heading is not None or current_lines:
                units.append(
                    (current_heading or "", "\n".join(current_lines).strip("\n"))
                )
            current_heading = match.group(1).strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_heading is not None or current_lines:
        units.append((current_heading or "", "\n".join(current_lines).strip("\n")))
    return units


def _body_unit_text(heading: str, section_text: str) -> str:
    """The body unit's underlying text: heading rendered, then the section."""
    if heading:
        return f"## {heading}\n\n{section_text}"
    return section_text


def _chunkable_units(
    record: CanonicalDecisionRecord,
    field_sources: dict[str, list[SourceReference]],
) -> list[_Unit]:
    """The canonical chunkable values in schema order, empty values dropped."""
    units: list[_Unit] = []

    def add(value_path: str, text: str | None, sources: list[SourceReference]) -> None:
        if text is not None and text.strip(" \t\n"):
            units.append(_Unit(value_path, text, tuple(sources)))

    if record.context is not None:
        add(
            "context.problem",
            record.context.problem,
            field_sources.get("context.problem", []),
        )
        add(
            "context.triggering_change",
            record.context.triggering_change,
            field_sources.get("context.triggering_change", []),
        )
    if record.decision is not None:
        add(
            "decision.chosen",
            record.decision.chosen,
            field_sources.get("decision.chosen", []),
        )
        for index, alternative in enumerate(record.decision.alternatives):
            add(
                f"decision.alternatives[{index}]",
                _alternative_text(alternative),
                list(_alternative_sources(index, field_sources)),
            )
    for index, item in enumerate(record.why):
        add(f"why[{index}]", item, field_sources.get(f"why[{index}]", []))
    add(
        "rationale_summary",
        record.rationale_summary,
        field_sources.get("rationale_summary", []),
    )
    if record.consequences is not None:
        for index, item in enumerate(record.consequences.positive):
            add(
                f"consequences.positive[{index}]",
                item,
                field_sources.get(f"consequences.positive[{index}]", []),
            )
        for index, item in enumerate(record.consequences.negative):
            add(
                f"consequences.negative[{index}]",
                item,
                field_sources.get(f"consequences.negative[{index}]", []),
            )
    body = record.body or ""
    for index, (heading, section_text) in enumerate(_split_body_units(body)):
        add(
            f"body[{index}]",
            _body_unit_text(heading, section_text),
            field_sources.get(f"body[{index}]", []),
        )
    return units


def chunk_record(
    record: CanonicalDecisionRecord,
    field_sources: dict[str, list[SourceReference]],
    generation_id: str,
    fingerprint: str,
    count_tokens: TokenCounter,
    config: PipelineConfig = DEFAULT_PIPELINE_CONFIG,
) -> tuple[ChunkPlan, ...]:
    """Chunk one canonical record into its complete deterministic plan.

    Raises ``ChunkingError`` when any complete embedding input exceeds the
    pinned model token limit (AC-4).
    """
    title = record.title or ""
    if record.id is None:
        raise ChunkingError("record has no id")
    plans: list[ChunkPlan] = []
    for unit in _chunkable_units(record, field_sources):
        packed = _pack_paragraphs(_paragraphs(unit.text), count_tokens, config)
        packed = _apply_overlap(packed, count_tokens, config)
        for ordinal, chunk_text in enumerate(packed):
            embedding_text = embedding_input(title, unit.value_path, chunk_text)
            embedding_tokens = count_tokens(embedding_text)
            if embedding_tokens > MODEL_TOKEN_LIMIT:
                raise ChunkingError(
                    f"record {record.id} chunk {unit.value_path}[{ordinal}] "
                    f"embedding input is {embedding_tokens} tokens, over the "
                    f"model limit of {MODEL_TOKEN_LIMIT}"
                )
            plans.append(
                ChunkPlan(
                    chunk_id=chunk_id(
                        generation_id,
                        record.id,
                        fingerprint,
                        unit.value_path,
                        ordinal,
                    ),
                    record_id=record.id,
                    fingerprint=fingerprint,
                    value_path=unit.value_path,
                    ordinal=ordinal,
                    text=chunk_text,
                    evidence_token_count=count_tokens(chunk_text),
                    embedding_input_token_count=embedding_tokens,
                    sources=unit.sources,
                )
            )
    return tuple(plans)


def missing_provenance(
    record: CanonicalDecisionRecord,
    field_sources: dict[str, list[SourceReference]],
) -> tuple[str, ...]:
    """Value paths populated but lacking a source (spec 0007 AC-3, AC-19).

    Every populated chunkable leaf, the title, and a populated supersedes
    value must name at least one source. Returns the offending value paths in
    schema order so ingest can fail the record and name them all.
    """
    missing: list[str] = []
    for unit in _chunkable_units(record, field_sources):
        if not unit.sources:
            missing.append(unit.value_path)
    if record.title and not field_sources.get("title"):
        missing.append("title")
    if record.supersedes and not field_sources.get("supersedes"):
        missing.append("supersedes")
    return tuple(missing)
