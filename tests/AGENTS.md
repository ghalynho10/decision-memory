# Tests

## Overview

The pytest suite guards every feature through all four Clean Architecture
layers. Fast unit tests run on every push; integration tests call the real
OpenAI and Chroma services and run separately, so API cost and flakiness stay
out of the default run.

## Key files

| File | Owns |
|---|---|
| `conftest.py` | Puts `examples/starter-adapter/src` on `sys.path` so unit tests import the starter adapter directly and integration tests load it by selector |
| `fake_adapter.py` | `FakeAdapter`, a configurable in memory adapter with every failure mode the adapter contract names (discover, parse, fingerprint exceptions) |
| `fake_index.py` | `FakeIndex`, an in memory `IndexWriter`/`IndexReader` plus a deterministic embedder, so the full ingest to query path runs without Chroma or OpenAI |
| `spec_factory.py` | Builds jsmastery style spec directories (index.md plus optional rationale.md) mirroring the real JobPilot conventions the adapter is tuned to |
| `fixtures/adapter_conformance/jsmastery_specs/` | The built in conformance manifest (adapter-conformance.yml with cases/ and expected/) that must pass the engine in the fast unit suite |

## Commands

```bash
uv run pytest                # unit suite only (default; integration excluded)
uv run pytest -m integration # integration suite: real OpenAI, Chroma, live JobPilot
```

## Conventions

- Two suites by marker: `integration` calls real external services and is excluded from the default run by `addopts = "-m 'not integration'"`; everything else is unit.
- Ingest, query, freshness, and supersession behavior runs through `FakeIndex` (deterministic vectors, no network), not the real store.
- Adapter behavior is exercised through `FakeAdapter` and the starter adapter; the conformance engine is proven against the committed built in manifest (no git or import tricks).
- The live JobPilot check (`test_query_live.py`) is skipped unless both `OPENAI_API_KEY` and `DECISION_MEMORY_JOBPILOT_DIR` are set.

## Gotchas

- `uv run` does not auto load `.env`; live provider runs need `uv run --env-file .env decision-memory ...`.
- Record comparison is exact: a `None` body is a mismatch against `""`; the starter parse sets `body=""`.
- The mypy gate is `mypy src` only (CI and pre commit); test files are still kept mypy clean.

## Related specs

- [0006 adapter conformance test adapter](../docs/specs/0006-adapter-conformance-test-adapter/)
- [0007 core cited query](../docs/specs/0007-core-cited-query/)

_Drafted by /audit from the repo, worth a quick human pass. Edit freely: once a line stops matching this draft, later runs treat it as curated and will flag rather than overwrite it._
