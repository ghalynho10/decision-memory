# decision-memory

A local, cited RAG system that makes software decision history queryable.

Point it at a project's decision records and ask why something is built the way it is. Answers come back cited to a source spec, commit, or file, or an honest "not enough evidence here" when the history doesn't support one.

**Status: working end to end, with a measured gap.** Eight commands ship (`version`, `validate`, `doctor`, `adapt`, `test-adapter`, `ingest`, `query`, `evaluate`). Against a real 20-spec corpus the pipeline runs the whole way: records adapt, chunks embed, hybrid retrieval fuses BM25 and cosine search with reciprocal rank fusion and record diversity, and answers come back cited to the exact record and field. The evaluation harness runs five queries plus three assertions and reports a rate per fixture.

**The abstention guarantee in the next paragraph is not met, and the gap is characterised rather than estimated.** Measured over twelve runs across four independent index builds, the tool over-abstains on questions it should answer, and on one fixture it returns a fluent, well-cited, *wrong* answer in three runs of twelve. See [Known limitations](#known-limitations) for the numbers and [`docs/experiments/`](docs/experiments/) for the sixteen experiments that established them. Built-in ADR adapters are planned, not shipped yet.

## What this is for

decision-memory answers one question about one project: **why is it built this way?** It's a narrow tool, not a general assistant, and it won't replace reading the codebase. The value is the evidence contract: every claim is cited to a source spec and section, or the tool abstains rather than guess. That is the design goal, and [Known limitations](#known-limitations) records how reliably it currently holds.

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
The entry point discovery approach was rejected. [C1]
The entry point discovery approach adds packaging work before any external adapter exists. [C1]
The entry point discovery approach introduces new product behavior for discovery. [C1]
The entry point discovery approach introduces a duplicate name policy. [C1]
The entry point discovery approach still requires runtime object validation after loading. [C1]
Sources
C1 DM-0005 ch_c5895e9ab5af... decision.alternatives[0] docs/specs/0005-runtime-adapter-loading/rationale.md Options considered
```

The citation resolves to the exact spec section the claim came from, so you can check it yourself. Answers currently arrive as separate short sentences rather than flowing prose, because each claim is verified independently before it is emitted; see [Known limitations](#known-limitations). On an unsupported question:

```console
$ decision-memory query "why is the subscription priced at nine dollars per month?"
not enough evidence here
```

That's an honest abstention, not a failure, and the tool exits `0` either way. Both transcripts above are real runs, and neither is the whole story: the same question does not always get the same treatment, and the measured rates are in [Known limitations](#known-limitations).

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
    Generic RAG core     ingestion · hybrid retrieval · citation
```

New here? [What is decision-memory?](docs/what-is-this.md) is a one-page plain-language explanation. See the [user guide](docs/user-guide.md) for the canonical record schema, adapter internals, exit codes, and how to triage a bad answer.

## Known limitations

Measured, not estimated. Every figure below comes from a committed harness with its runs and traces kept in [`docs/experiments/`](docs/experiments/).

**The abstention guarantee is not met.** Twelve runs across four independent index builds against a real 20-spec corpus ([experiment 0014](docs/experiments/0014-the-causes-pinned-and-the-store-split.md)):

| Fixture | Expected | Result |
|---|---|---|
| `assertion-incremental-reingest` | chunks change | 4/4 |
| `query-4-db-clients` | abstain | 9/12 |
| `assertion-unverifiable-claim` | abstain | 5/12 |
| `assertion-rationale-summary` | answer | 4/12 |
| `query-1-private-beta-gate` | answer | 3/12 |
| `query-5-uploaded-files` | abstain | 3/12 |
| `query-2-resume-generation` | answer | 0/12 |
| `query-3-provisional` | answer | 0/12 |

Two readings. The tool **over-abstains** on questions it should answer, which fails in the safe direction. And on `query-5` it does the thing this project exists to prevent: four runs in twelve produce a confident, cited, wrong answer.

**Why, as far as it has been established.** The failure is not invention — every sub-claim in those answers was genuinely supported by its cited evidence. The answer simply was not *about* the question: it asked about uploaded files and the retrieved record discussed upload keys. The verification stack proves a claim is **grounded** in its evidence, deterministically and well. Nothing in it proves a claim is **about** the question; that judgment sits in a model stage, and it has been observed extracting a facet and its own negation from identical input at temperature zero. An unqualified "never guesses" is not reachable by verifying harder, which is the most useful thing the experiment chain found.

- **Answers arrive as separate short sentences, not prose.** Each claim is verified independently and emitted on its own, so a single source sentence can become several. The content is correct and the citations resolve, but it reads poorly. Under active revision.
- **A decision that takes more than one clause to state can be refused.** Coverage requires one sentence to state a full answer and cannot combine sentences, so a correct multi-part answer sometimes returns `not enough evidence here`. Same revision as above.
- **One source format.** The built-in adapter reads directory-style specs (`docs/specs/NNNN-title/index.md`). Flat single-file specs are skipped, and ADR/MADR corpora need an adapter that does not exist yet.
- **A malformed `Status` line silently drops a record.** The status must be a known value; a parenthetical note attached to it causes the whole spec to be skipped at `adapt` time, and nothing warns you again at query time.
- **Requires an `OPENAI_API_KEY`** for `ingest` and `query`. Everything else runs offline.

## Scope

**MVP**

- Canonical record schema, with a validator
- First adapter, for spec-driven pipeline output
- `doctor`, runtime adapter loading, and a conformance suite (built-in ADR adapters still to come)
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
