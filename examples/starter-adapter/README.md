# starter-adapter

A minimal teaching adapter for decision-memory. It reads a tiny neutral
Markdown format under a corpus's `decisions/` directory and turns each decision
file into a canonical decision record. Everything about the adapter contract
lives in one module, `starter_adapter/adapter.py`: metadata, discovery,
parsing, and content based fingerprinting.

The format it reads:

```markdown
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
```

Discovery skips any file with no `## Decision` heading, so a file that is not
a decision produces no record and does not fail the run.

The full how to write your own adapter guide lives at
`docs/adapter-author-guide.md` in the decision-memory repository.

## Install

The adapter needs `decision-memory` importable in the same environment. From a
checkout of decision-memory, install it into that environment:

```bash
uv pip install -e ./examples/starter-adapter
```

## Try it

Point the CLI at a corpus that holds a `decisions/` directory:

```bash
uv run decision-memory validate ./examples/starter-adapter --adapter starter_adapter.adapter:adapter
uv run decision-memory adapt ./examples/starter-adapter --adapter starter_adapter.adapter:adapter
```

The bundled fixtures in `decisions/` demonstrate both outcomes: `valid.md` is
adapted into a valid record, `skipped.md` is reported as skipped because it has
no Decision section.
