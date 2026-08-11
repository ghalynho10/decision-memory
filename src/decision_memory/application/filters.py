"""Application: explicit query filters (spec 0008 AC-1 to AC-4).

Pure filter vocabulary, normalization, matching, and snapshot filtering. No
third party imports by project rule. The CLI builds normalized filters with
``build_query_filters`` and the query use case filters an immutable
``ActiveChunkDescriptor`` snapshot with ``filter_descriptors``.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from decision_memory.application.chunking import is_valid_value_path
from decision_memory.application.dto import (
    ActiveChunkDescriptor,
    FilterExclusionReason,
    FilterRow,
    FilterState,
    QueryFilters,
)
from decision_memory.domain.records import Status

# AC-2: status is normalized to the lowercase closed values.
FILTER_STATUSES = tuple(status.value for status in Status)

# AC-3: the complete fixed value path selectors, each matching one indexed leaf.
FIXED_VALUE_PATH_SELECTORS = (
    "decision.alternatives[*]",
    "why[*]",
    "consequences.positive[*]",
    "consequences.negative[*]",
    "body[*]",
)

# AC-3: [*] matches exactly one ASCII decimal index with grammar 0|[1-9][0-9]*.
_INDEX_RE = re.compile(r"[0-9]|[1-9][0-9]*")

_STAR = "[*]"


class FilterUsageError(Exception):
    """A malformed filter value; the CLI exits 2 (AC-2)."""


def build_query_filters(
    record_ids: Sequence[str] = (),
    statuses: Sequence[str] = (),
    tags: Sequence[str] = (),
    value_paths: Sequence[str] = (),
) -> QueryFilters:
    """Normalize and validate raw filter values into sorted unique tuples.

    Surrounding whitespace is removed. An empty value, an unknown status, or a
    malformed value path selector raises ``FilterUsageError``. A valid value
    that matches nothing is not an error (AC-2, AC-3).
    """
    cleaned_ids = _validate_scalar("record id", record_ids)
    cleaned_tags = _validate_scalar("tag", tags)
    cleaned_statuses = _validate_statuses(statuses)
    cleaned_paths = _validate_value_paths(value_paths)
    return QueryFilters(
        record_ids=tuple(sorted(set(cleaned_ids))),
        statuses=tuple(sorted(set(cleaned_statuses))),
        tags=tuple(sorted(set(cleaned_tags))),
        value_paths=tuple(sorted(set(cleaned_paths))),
    )


def matches_value_path(selector: str, chunk_path: str) -> bool:
    """Whether a value path filter matches a chunk value path (AC-3).

    A fixed selector such as ``body[*]`` matches exactly one valid ASCII index
    leaf and no descendant. An exact selector matches only the whole path.
    """
    if selector.endswith(_STAR):
        prefix = selector[: -len(_STAR)]
        if not chunk_path.startswith(prefix + "["):
            return False
        remainder = chunk_path[len(prefix) :]
        if not (remainder.startswith("[") and remainder.endswith("]")):
            return False
        index_text = remainder[1:-1]
        if _INDEX_RE.fullmatch(index_text) is None:
            return False
        return chunk_path == f"{prefix}[{index_text}]"
    return chunk_path == selector


def filter_descriptors(
    descriptors: Sequence[ActiveChunkDescriptor],
    filters: QueryFilters,
) -> tuple[FilterRow, ...]:
    """One FilterRow per active chunk, even when no filter is present (AC-4).

    Values use OR within one field and AND across fields. Every failed
    constraint is reported in the fixed order record id, status, tag, and
    value path. A record with a missing status fails every nonempty status
    constraint.
    """
    rows: list[FilterRow] = []
    for chunk in descriptors:
        reasons: list[FilterExclusionReason] = []
        if filters.record_ids and chunk.record_id not in filters.record_ids:
            reasons.append(FilterExclusionReason.RECORD_ID)
        if filters.statuses and (
            chunk.record_status is None or chunk.record_status not in filters.statuses
        ):
            reasons.append(FilterExclusionReason.STATUS)
        if filters.tags and not any(tag in filters.tags for tag in chunk.record_tags):
            reasons.append(FilterExclusionReason.TAG)
        if filters.value_paths and not any(
            matches_value_path(selector, chunk.value_path)
            for selector in filters.value_paths
        ):
            reasons.append(FilterExclusionReason.VALUE_PATH)
        rows.append(
            FilterRow(
                chunk_id=chunk.chunk_id,
                record_id=chunk.record_id,
                record_status=chunk.record_status,
                record_tags=chunk.record_tags,
                value_path=chunk.value_path,
                state=FilterState.EXCLUDED if reasons else FilterState.ACCEPTED,
                exclusion_reasons=tuple(reasons),
            )
        )
    return tuple(rows)


def _validate_scalar(label: str, values: Sequence[str]) -> list[str]:
    cleaned: list[str] = []
    for value in values:
        stripped = value.strip()
        if not stripped:
            raise FilterUsageError(f"empty {label} value")
        cleaned.append(stripped)
    return cleaned


def _validate_statuses(statuses: Sequence[str]) -> list[str]:
    cleaned: list[str] = []
    for value in statuses:
        stripped = value.strip()
        if not stripped:
            raise FilterUsageError("empty status value")
        normalized = stripped.lower()
        if normalized not in FILTER_STATUSES:
            raise FilterUsageError(
                f"unknown status {stripped!r}; expected one of "
                f"{', '.join(FILTER_STATUSES)}"
            )
        cleaned.append(normalized)
    return cleaned


def _validate_value_paths(value_paths: Sequence[str]) -> list[str]:
    cleaned: list[str] = []
    for value in value_paths:
        stripped = value.strip()
        if not stripped:
            raise FilterUsageError("empty value path value")
        if _STAR in stripped:
            if stripped not in FIXED_VALUE_PATH_SELECTORS:
                raise FilterUsageError(f"malformed value path selector {stripped!r}")
            cleaned.append(stripped)
            continue
        if not is_valid_value_path(stripped):
            raise FilterUsageError(f"malformed value path {stripped!r}")
        cleaned.append(stripped)
    return cleaned
