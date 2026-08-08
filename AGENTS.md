# decision-memory

## Stack

- **Language / Runtime**: Python 3.11+ (managed with uv, pinned 3.11)
- **Framework**: Typer (CLI), Pydantic v2 (schema)
- **Key dependencies**: typer, pydantic, pyyaml; later slices add openai, chromadb, rank_bm25
- **Package manager**: uv

## Build approach

Skateboard: ship the smallest usable whole first, then grow it release by release.

## Commands

```bash
uv sync                # install
uv run decision-memory # run the CLI
uv build               # build
uv run pytest          # test
```

## Specs

Stored in `docs/specs/`. Format: `docs/specs/NNNN-title.md`.

## Rules

Clean Architecture:
- Four layers: domain, application, infrastructure, presentation (the CLI). Domain has zero external imports.
- Dependency rule: outer layers depend inward; use cases orchestrate, they never implement business rules.
- Infrastructure implements interfaces from domain or application; no framework code (Typer, Pydantic, Chroma, OpenAI) in domain or application.
- Boundary crossing uses DTOs or plain objects; domain entities never reach the CLI. Domain and application unit tested without infrastructure mocks; infrastructure integration tested.

Additional standards:
- Strict types (mypy or pyright, no any); organize `src/decision_memory/` by layer: cli, ingest, retrieval, generation, storage.
- One consistent error handling pattern; validate required env vars at startup and fail loudly (`OPENAI_API_KEY` comes with Slice 1).
- Conventional commits; documented public APIs; consistent naming.
- Ruff for lint and format, wired into the verify and test step, not a manual optional step.
- Unit plus integration tests via pytest (integration marked, run separate from the fast unit suite); CI on push runs pre commit checks plus the unit suite only.

## Git

- integration: on
- branch prefix: feature/
- commit: per-milestone

## Agent skills

- [architect](.agents/skills/architect/): `ghalynho10/skills`, designs and records load bearing decisions in specs
- [audit](.agents/skills/audit/): `ghalynho10/skills`, bootstraps AGENTS.md context files
- [check](.agents/skills/check/): `ghalynho10/skills`, verifies builds and reviews code
- [checkpoint](.agents/skills/checkpoint/): `ghalynho10/skills`, saves and restores in session notes
- [debug](.agents/skills/debug/): `ghalynho10/skills`, finds and fixes root causes
- [develop](.agents/skills/develop/): `ghalynho10/skills`, builds features from approved specs
- [document](.agents/skills/document/): `ghalynho10/skills`, writes PR, changelog, and release notes
- [overview](.agents/skills/overview/): `ghalynho10/skills`, keeps the project overview current
- [recover](.agents/skills/recover/): `ghalynho10/skills`, recovers from failed or misbuilt sessions
- [scope](.agents/skills/scope/): `ghalynho10/skills`, plans features and keeps the scope current
- [sync](.agents/skills/sync/): `ghalynho10/skills`, reconciles durable docs after changes
- [test](.agents/skills/test/): `ghalynho10/skills`, writes test suites for changed code

MCP servers: chroma-core/chroma-mcp (recommended)

## Context files

<!-- Nested AGENTS.md files are listed here as they are created -->

_Drafted by /audit from the repo, worth a quick human pass. Edit freely: once a line stops matching this draft, later runs treat it as curated and will flag rather than overwrite it._
