# decision-memory

A local, cited RAG system that makes software decision history queryable.

Point it at a project's decision records and ask why something is built the way it is. Answers come back cited to a source spec, commit, or file, or an honest "not enough evidence here" when the history doesn't support one.

**Status: early development.** Seven commands ship (`version`, `validate`, `doctor`, `adapt`, `test-adapter`, `ingest`, `query`), verified live against a real project's specs: a known-answer question returns a correct, cited answer, and an unsupported question returns `not enough evidence here`, exit `0`. Hybrid retrieval ships with the query index: explicit metadata filters, BM25 keyword and cosine semantic search, reciprocal rank fusion, and record diversity. Built-in ADR adapters are planned, not shipped yet.

## What this is for

decision-memory answers one question about one project: **why is it built this way?** It's a narrow tool, not a general assistant, and it won't replace reading the codebase. The value is the evidence contract: every claim is cited to a source spec and section, or the tool abstains rather than guess.

It pays off during onboarding and code review, when checking whether an earlier choice was already tried and rejected, and on corpora large enough that a focused, cited answer beats reading everything.

## The problem

During spec-driven or agentic development, the reasoning behind a system lives in scattered places: planning documents, generated specs, commit messages, pull requests, and conversations that vanish when the session ends. Months later the code tells you *what* it does. It rarely tells you:

- Why this database, this schema, this API shape?
- What problem invalidated the original design?
- Which alternatives were considered and rejected, and why?
- Which decisions is this feature standing on?
- If this breaks, which assumptions should be checked first?

Codebases accumulate answers to *what*. The *why* evaporates.

## Quickstart

```bash
uv sync
uv run decision-memory doctor <project-path>            # check whether a built-in adapter fits
uv run decision-memory adapt <project-path>              # turn decision specs into canonical records
uv run decision-memory ingest .decision-memory/records   # build the local query index
uv run decision-memory query "why was the private beta gate added?"
```

`doctor` reports file counts and heading patterns for a corpus you haven't adapted before. `adapt` supports `--dry-run` to preview without writing. `ingest` supports `--dry-run` to preview provider spend before it calls OpenAI.

Here's a real run against this repo's own specs:

```console
$ decision-memory query "why was the entry point discovery approach rejected for third party adapters?"
The entry point discovery approach was rejected because it adds packaging work
before any external adapter exists, introduces new product behavior with discovery
and duplicate name policy, and still requires runtime object validation after
loading. [C1]
Sources
C1 DM-0005 ch_b728a86a8b08... decision.alternatives[0] docs/specs/0005-runtime-adapter-loading/rationale.md Options considered
```

The citation resolves to the exact spec section the claim came from, so you can check it yourself. On an unsupported question:

```console
$ decision-memory query "why is the subscription priced at nine dollars per month?"
not enough evidence here
```

That's an honest abstention, not a failure, and the tool exits `0` either way.

## The approach

**Structured records, not RAG over prose.** Each decision gets a small structured record: what was decided, what was rejected and why, what it cost, what evidence backs it. Retrieval runs over those records, which is what makes citations reliable instead of plausible.

**A generic core with project-specific adapters.** The retrieval engine knows nothing about any particular project's conventions. Adapters translate a project's native artifacts into a canonical record shape; the core only ever sees canonical records. A project that looks nothing like the reference one needs an adapter, not a fork.

```
Sources (project-specific)
    ├── Adapters      translate artifacts that already exist
    └── Capture       create records directly, when nothing exists yet   [planned]
                ↓
    Canonical decision record
                ↓
    Generic RAG core     ingestion · semantic retrieval (hybrid planned) · citation
```

See the [user guide](docs/user-guide.md) for the canonical record schema, adapter internals, exit codes, and how to triage a bad answer.

## Scope

**MVP**

- Canonical record schema, with a validator
- First adapter, for spec-driven pipeline output
- `doctor`, runtime adapter loading, a conformance suite, and built-in ADR adapters
- Ingestion: parse, chunk on canonical field boundaries, embed, index; metadata stays queryable as structured fields
- Hybrid retrieval: structured filters, keyword, and semantic search, filtering able to constrain the candidate set before semantic similarity chooses among it
- Query interface (CLI) returning answers with resolving citations, plus a debug view showing what was retrieved and why an answer was refused
- Evaluation harness: fixed questions with known-correct sources, so retrieval changes are measured rather than guessed at

**Not in v1:** capture, declarative adapters, a Model Context Protocol (MCP) server and web UI (see Roadmap), reconstructing history from a codebase that never recorded it, cross-repo querying, auto-approving generated records without human review.

Built in Python. The CLI is one interface onto the retrieval core, not the product. The core keeps a clean query boundary so other interfaces can sit on top of it without touching retrieval logic.

## Roadmap

The retrieval core stays interface-agnostic; everything below is a wrapper, not a rewrite.

- **Capture.** For projects that don't produce decision-shaped artifacts at all: at the end of a working session it interviews for what was built, decided, and rejected, then writes a canonical record directly. Deferred past v1 because validating retrieval against records that already exist is faster than building record creation first and discovering retrieval doesn't work.
- **Declarative adapters.** For simple formats, a YAML mapping file instead of a Python package. Best built after a second hand-written adapter exists, so the schema is designed against two real formats rather than one.
- **MCP server and web UI.** The MCP server exposes the query function as a tool an agent calls inside the editor, where the day-to-day utility lives. The web UI is a frontend over a thin HTTP layer on the core.

## Prior art

[Token Saver](https://github.com/Marktechpost/Token-Saver) is a useful reference: local-first, hybrid keyword and semantic retrieval, page-level citations, built as an MCP extension. It names cross-document source selection as its weaker area, which is the gap this project's structured records and metadata filtering target.

## License

MIT, see [LICENSE](LICENSE).
