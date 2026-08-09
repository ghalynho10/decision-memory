# starter-adapter

A self contained teaching package that shows how to write a decision-memory
adapter. It reads a tiny neutral Markdown format under a corpus's `decisions/`
directory and turns each decision file into a canonical record.

## Layout

- `src/starter_adapter/adapter.py` holds the whole adapter: metadata,
  discovery, parsing, and content based fingerprinting in one module.
- `decisions/` ships one valid fixture (`valid.md`) and one skipped fixture
  (`skipped.md`, no Decision section).
- `pyproject.toml` is the minimal installable package manifest.

## Install and run

The package uses the `src/` layout that `uv_build` expects. Install it into
the decision-memory environment, then use the selector through the CLI:

```bash
uv pip install -e ./examples/starter-adapter
uv run decision-memory validate <corpus> --adapter starter_adapter.adapter:adapter
uv run decision-memory adapt <corpus> --adapter starter_adapter.adapter:adapter
```

## Conventions

- The selector is the absolute module path `starter_adapter.adapter:adapter`;
  the CLI loads the attribute as an already created instance (spec 0005).
- Discovery skips any file with no `## Decision` heading rather than guessing.
- `ADAPTER_VERSION` participates in the content based fingerprint, so a version
  bump changes every fingerprint (spec 0005 AC-15).
- The record cites its contributing file as `file` evidence relative to the
  corpus root, so it resolves when validated against the corpus.

## Guidance

The full author guide lives at `docs/adapter-author-guide.md`. Spec 0005
(`docs/specs/0005-runtime-adapter-loading/`) governs the adapter contract;
feature 7 reuses the same `load_adapter` boundary.

_Drafted by /sync from the introducing change, worth a quick human pass._
