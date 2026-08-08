"""Helpers for building jsmastery style spec directories in tests.

These mirror the real JobPilot spec conventions the adapter is tuned to: a
directory under docs/specs/ holding index.md plus an optional rationale.md,
with bold date and status lines, a chosen option line inside the Decision
section, and Options considered in rationale.md when it exists.
"""

from __future__ import annotations

from pathlib import Path

INDEX = """\
# 0012. Portfolio private access gate

**Date**: 2026-08-07
**Status**: Accepted

## Summary

Adds a gate before the private portfolio pages.

## Context

The portfolio is public today; private projects need a gate before they can be shown.

## Decision

**Chosen option**: Option 1: Build an internal state machine

## Options considered

**Option 1:** Build an internal state machine
**Pros**: Full control over the flow.
**Cons**: More code to maintain.

**Option 2:** Use a hosted provider
**Pros**: Less code.
**Cons**: Cost and a third party.

## Consequences

**Positive**:
- The gate is self contained.

**Negative**:
- More code to maintain.

## Rationale

See [rationale.md](rationale.md).
"""

RATIONALE = """\
# 0012. Portfolio private access gate

## Context

The full context lives here, and it wins over index.md when both files carry one.

## Options considered

**Option 1:** Build an internal state machine
**Pros**: Full control.
**Cons**: More code to maintain.

**Option 2:** Use a hosted provider
**Pros**: Less code.
**Cons**: Cost and a third party.

## Rationale

The internal state machine gives the team full control over the access flow and
keeps the dependency surface small.
"""


def make_corpus(tmp_path: Path) -> Path:
    """A corpus root with an empty docs/specs/ directory."""
    corpus = tmp_path / "corpus"
    (corpus / "docs" / "specs").mkdir(parents=True)
    return corpus


def write_spec(
    corpus: Path,
    name: str,
    *,
    index: str = INDEX,
    rationale: str | None = RATIONALE,
) -> Path:
    """Write one spec directory under corpus/docs/specs/ and return it."""
    spec_dir = corpus / "docs" / "specs" / name
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "index.md").write_text(index, encoding="utf-8")
    if rationale is not None:
        (spec_dir / "rationale.md").write_text(rationale, encoding="utf-8")
    return spec_dir
