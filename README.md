# decision-memory

A CLI that builds a local index of a project's decision records and answers "why is it built this way?" with citations back to the exact spec and field. Embeddings and answer generation run through OpenAI.

> **Experimental.** In the most recent 12-run evaluation the tool frequently declined to answer questions it should have answered, and on one fixture it returned a relevant-looking but incorrect answer in 4 of 12 runs. A citation proves a claim came from a real record. It does not prove the answer addresses your question. The run that produced those numbers is [experiment 0014](docs/experiments/0014-the-causes-pinned-and-the-store-split.md).

```console
$ decision-memory query "why was the entry point discovery approach rejected for third party adapters?"
The entry point discovery approach was rejected because it adds packaging work
before any external adapter exists, introduces new product behavior for discovery
and duplicate name policy, and still requires runtime object validation after
loading. [C1]
Sources
C1 DM-0005 ch_4a3ac89980c0... decision.alternatives[0] docs/specs/0005-runtime-adapter-loading/rationale.md Options considered

$ decision-memory query "why is the subscription priced at nine dollars per month?"
not enough evidence here
```

Both exit `0`. The citation resolves to a real file and heading, so you can check the answer yourself.

## What it's for

During spec-driven or agentic development, the reasoning behind a system scatters across planning documents, generated specs, commit messages, and sessions that end. Months later the code tells you *what* it does, rarely *why*: which alternatives were rejected, what invalidated the original design, which assumptions a feature stands on.

Codebases accumulate answers to *what*. The *why* evaporates.

This is a narrow tool for that one question. It won't replace reading the codebase, and it doesn't reconstruct history a project never wrote down. It pays off during onboarding and review, and on corpora large enough that a cited answer beats reading everything.

## Requirements

- **Python 3.11+** and [uv](https://docs.astral.sh/uv/)
- **An `OPENAI_API_KEY`** whenever `ingest`, `query`, or `evaluate` needs a provider call. Validation, adaptation, diagnostics, and dry runs work offline.
- **A supported corpus.** The built-in adapter reads directory-style specs at `docs/specs/NNNN-title/index.md`. Flat single-file specs are skipped, and ADR/MADR corpora need a Python adapter that doesn't ship yet. `doctor` reports a corpus's file counts and heading structure, which is what you compare against that shape to judge whether the adapter fits.

**What leaves your machine.** `ingest` sends each chunk's text, its record title, and its field path to OpenAI's embeddings API. `query` sends your question plus the text of the retrieved chunks. The index, the records, and the citations stay local. If your specs are confidential, that's the boundary to weigh.

## Quickstart

Try it on this repository:

```bash
git clone https://github.com/ghalynho10/decision-memory && cd decision-memory
uv sync
export OPENAI_API_KEY=sk-...

uv run decision-memory adapt .                                   # specs → canonical records
uv run decision-memory ingest .decision-memory/records           # records → query index
uv run decision-memory query "why was the entry point discovery approach rejected for third party adapters?"
```

Depending on provider output, that query may return the answer above or abstain. See [Current limitations](#current-limitations).

To use it on another project, install the CLI and work from that project's directory, so `.decision-memory.yml` and the default paths resolve against it:

```bash
uv tool install .                                                # from this repo, once
cd /path/to/project
decision-memory doctor .                                         # inspect the corpus structure
decision-memory adapt .
decision-memory ingest .decision-memory/records
decision-memory query "why was X chosen?"
```

Or stay where you are and pass explicit paths:

```bash
uv run decision-memory doctor /path/to/project                   # inspect the corpus structure
uv run decision-memory adapt /path/to/project --output /path/to/project/.decision-memory/records
uv run decision-memory ingest /path/to/project/.decision-memory/records \
    --store /path/to/project/.decision-memory/query-index
uv run decision-memory query "why was X chosen?" --store /path/to/project/.decision-memory/query-index
```

A `.decision-memory.yml` holding `adapter`, `corpus_root`, and `output` saves repeating the paths, but it is found by searching upward from the current directory to the Git root, so it only applies when you run from inside the project it describes, as in the first form above. `adapt` and `ingest` both take `--dry-run`; use it on `ingest` to see provider spend before it calls OpenAI.

## How it works

**1. Adapt.** Project-specific adapters translate native artifacts into a canonical decision record: what was decided, what was rejected and why, what it cost, what evidence backs it. The retrieval core only ever sees canonical records, so a project that looks nothing like the reference one needs an adapter, not a fork.

**2. Ingest.** Records are chunked on field boundaries, embedded, and indexed. Metadata stays queryable as structured fields, and the store is versioned so a rebuild is atomic.

**3. Query.** Metadata filters narrow the candidates, then BM25 and semantic search run and fuse by reciprocal rank. Every draft sentence is verified against its cited evidence before it is emitted; anything that can't be traced is dropped, and if nothing survives the tool abstains. `--debug` shows what was retrieved and why an answer was refused.

```
Sources (project-specific)
    ├── Adapters      translate artifacts that already exist
    └── Capture       create records directly, when nothing exists yet   [planned]
                ↓
    Canonical decision record
                ↓
    Generic core     ingestion · hybrid retrieval · verification · citation
```

## Current limitations

- **It over-abstains.** The common failure is a correct answer being assembled and then dropped because verification rejects part of it. That is the safe direction to fail in, but it leaves the tool quieter than it should be.
- **A citation is not proof of relevance.** The verifier checks that a claim is grounded in its evidence, not that it answers your question. That gap is where the 4-in-12 wrong answers come from.
- **Output varies between runs.** The same question does not always get the same treatment.
- **One input format.** Directory-style specs only; see [Requirements](#requirements).
- **Malformed statuses exclude records.** A parenthetical note attached to a `Status` line makes it unknown, and `adapt` reports the spec as skipped with its reason. After ingestion, though, `query` cannot tell you that the record is missing from the corpus it just searched.

The measurements behind these are in [`docs/experiments/`](docs/experiments/), along with the experiment log that produced them. Each one records its instrument, its method, and its threats to validity.

## Documentation

- [What is decision-memory?](docs/what-is-this.md), a one page explanation in plain language
- [User guide](docs/user-guide.md), covering the record schema, adapter internals, exit codes, and how to triage a bad answer
- [Adapter author guide](docs/reference/artifact/guide/adapter-author-guide.md), for writing an adapter for a format that is not supported
- [`docs/specs/`](docs/specs/), the build specs and the decisions behind them
- [`docs/experiments/`](docs/experiments/), the measured findings

## Development

```bash
uv sync
uv run ruff check . && uv run ruff format --check src tests
uv run mypy src
uv run pytest                    # unit suite, no provider calls
uv run pytest -m integration     # real OpenAI, Chroma, live corpus
uv build
```

Clean Architecture in four layers under `src/decision_memory/`: `domain` (no external imports), `application` (use cases and ports), `infrastructure` (adapters, OpenAI, SQLite, Chroma), and `cli.py` as the composition root. Dependencies point inward, and no framework code crosses into domain or application. Strict typing, lint, and format run in the pre-commit chain rather than as optional steps. Conventions are in [AGENTS.md](AGENTS.md).

## Roadmap

- Built-in ADR and MADR adapters, so the tool works on corpora it currently skips
- Declarative adapters, a YAML mapping instead of a Python package for simple formats
- An MCP server, so an agent can call query from inside the editor

Not planned: reconstructing history from a codebase that never recorded it, cross-repo querying, or auto-approving generated records without review.

## License

MIT, see [LICENSE](LICENSE).
