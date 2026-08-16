# decision-memory

## Stack

- **Language / Runtime**: Python 3.11+ (managed with uv, pinned 3.11)
- **Framework**: Typer (CLI), Pydantic v2 (schema)
- **Key dependencies**: typer, pydantic, pyyaml, openai, chromadb, tiktoken; rank_bm25 comes with Slice 2 (lexical retrieval)
- **Package manager**: uv

## Build approach

Skateboard: ship the smallest usable whole first, then grow it release by release.

## Commands

```bash
uv sync                # install
uv run decision-memory # run the CLI
uv build               # build
uv run pytest          # test (unit suite; integration excluded)
uv run pytest -m integration   # integration suite: real OpenAI, Chroma, live JobPilot
uv run --env-file .env decision-memory evaluate CORPUS --runs N   # evaluation harness, live
# evaluate --battery PATH runs a fixture battery from a manifest; its parent directory is the corpus root
# live provider runs: uv run --env-file .env decision-memory ... (uv run does not auto load .env)
```

## Specs

Stored in `docs/specs/`. Format: `docs/specs/NNNN-title.md`.

## Experiments

Measured findings live in `docs/experiments/NNNN-title.md`, with their instruments and data in `docs/experiments/data/`. Specs and scope rows cite them by number. Read the cited experiment before re measuring or re deriving a figure, and add a new numbered one rather than editing a past result; a correction goes in the new experiment, with the superseded reading kept and marked.

## Rules

Clean Architecture:
- Four layers: domain, application, infrastructure, presentation (the CLI). Domain has zero external imports.
- Dependency rule: outer layers depend inward; use cases orchestrate, they never implement business rules.
- Infrastructure implements interfaces from domain or application; no framework code (Typer, Pydantic, Chroma, OpenAI) in domain or application.
- Boundary crossing uses DTOs or plain objects; domain entities never reach the CLI. Domain and application unit tested without infrastructure mocks; infrastructure integration tested.

Additional standards:
- Strict types (mypy or pyright, no any); organize `src/decision_memory/` by Clean Architecture layer: domain, application, infrastructure, and cli.
- One consistent error handling pattern; validate required env vars at startup and fail loudly (`OPENAI_API_KEY` comes with Slice 1).
- Conventional commits; documented public APIs; consistent naming.
- Ruff for lint and format, wired into the verify and test step, not a manual optional step.
- Unit plus integration tests via pytest (integration marked, run separate from the fast unit suite); CI on push runs pre commit checks plus the unit suite only.
- Third party adapters load by an absolute selector `package.module:attribute`; the built in `jsmastery-specs` stays the default. The teaching package and author guide live at `examples/starter-adapter/` and `docs/reference/artifact/guide/adapter-author-guide.md`. Adapters prove protocol compliance with `test-adapter SELECTOR --cases PATH`; the built in adapter must pass it.
- `.decision-memory.yml` persists `adapter`, `corpus_root`, and `output`; `adapt` and directory `validate` read the nearest file upward, stopping at the Git root, with CLI input winning over config.

Evidence:
- Verify a claim against the source before asserting it, including a claim made by a spec, an experiment writeup, or another session. This project has repeatedly produced plausible reasoning the code contradicted, and [experiment 0003](docs/experiments/0003-whole-sentence-gate-and-a-misdiagnosis.md) keeps one such case on purpose. Cite the file and line you read.
- A claim about **how often** something happens needs a measurement with its denominator, never an instance. A claim about **what a field contains** is read from the field, never from a rendered view.
- A figure nobody can re derive does not settle a decision. A reproducible measurement gets a committed script under `docs/experiments/data/`, not a recorded command.

## Circuit breaker

If the same problem persists after one corrective prompt, stop and run `/recover` before trying again. It diagnoses whether this is an isolated bug (routes to `/debug`), a session that has gone wrong through repeated patching (hard reset), or a foundation built on a wrong assumption (rethink).

`/recover` states its diagnosis without asking, but pauses for confirmation before a hard reset ends the session or a rethink changes code. A hard reset records a reset note in `docs/session-notes.md` for the next session, which `/checkpoint` reads and ages out.

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

- [examples/starter-adapter/AGENTS.md](examples/starter-adapter/AGENTS.md): the teaching adapter package (install, selector, tiny format, fixtures)
- [tests/AGENTS.md](tests/AGENTS.md): the pytest suite: unit vs integration markers, shared fakes (FakeIndex, FakeAdapter), conformance fixtures, live JobPilot requirements

<!-- Nested AGENTS.md files are listed here as they are created -->

_Drafted by /audit from the repo, worth a quick human pass. Edit freely: once a line stops matching this draft, later runs treat it as curated and will flag rather than overwrite it._
