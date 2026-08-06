# 0001. Foundational stack for decision-memory

**Date**: 2026-08-06
**Status**: Proposed

## Summary

This decides the technology stack for decision-memory's first version: a Python command line tool that answers "why was this built this way" with a cited answer, backed by real decision records. Embeddings and the final answer are produced by OpenAI's cloud API, stored and searched with ChromaDB plus a simple keyword search, and the answer generation step checks every claim it makes against the source text before showing it. This trades the project's original "local-first" goal for simplicity and answer quality, a conscious choice made by the engineer.

## Context

Decision-memory needs to turn a project's existing decision-shaped files (specs, records) into a small, queryable, cited answer engine. Three forces shape the stack:

The tool's whole value depends on trustworthy citations. An answer that sounds right but points at the wrong source, or invents a claim the source never made, fails the project's core promise (see `README.md`: "an uncited record is the exact failure mode this project exists to prevent"). This pushes hard toward a generation approach that can be checked, not just prompted to behave.

The expected corpus is small: `mvp.md` sizes it at "a dozen specs is enough to prove the pipeline runs end to end," with real doubt about whether it is large enough to evaluate retrieval quality at all. This rules out infrastructure sized for millions of vectors and favors whatever is simplest to run and reason about at dozens to low hundreds of records.

`mvp.md` already settles two things this stack must respect without re-deciding them: hybrid retrieval needs three stages available (structured metadata filter, lexical, semantic), and chunking must preserve canonical field boundaries (a long field may subdivide, but every subchunk keeps its record id, field identity, and source provenance).

`README.md` names local-first as a project goal (local embedding and inference favored for a local-first tool). The stack settled below does not fully honor that; see Rationale and Consequences.

## Options considered

### Option 1: Cloud API stack (OpenAI embeddings and generation, Chroma, BM25)

Embeddings and answer generation both call OpenAI's API; ChromaDB stores vectors and metadata locally; `rank_bm25` provides the lexical stage; a separate local SQLite database is the source of truth for canonical records.

**Pros**:
- Highest quality embeddings and generation with the least setup; no local model to install, download, or manage
- OpenAI's instruction following is strong enough to support a real claim-verification step (generate from chunks only, then check every claim against the source), which is the actual reliability lever, not the vendor name
- Cost is negligible at this corpus size (OpenAI's `text-embedding-3-small` runs about $0.02 per million tokens)

**Cons**:
- Not local-first: every ingest and every query needs network access and an API key, and indexing a personal decision corpus now means sending its contents to a third party
- Ongoing per-query cost, small but nonzero, unlike a fully local setup
- A different provider's later outage or pricing change is an external dependency this tool now carries

### Option 2: Fully local stack (sentence-transformers, Chroma, BM25, Ollama)

Embeddings run through a local `sentence-transformers` model, generation runs through a local model served by Ollama, storage and lexical search stay the same as Option 1.

**Pros**:
- Matches the project's stated local-first goal exactly; no network dependency, no per-query cost, no data leaves the machine
- No API key management or provider outage risk

**Cons**:
- Local models are meaningfully weaker at the specific behavior this tool depends on: reliably refusing to answer, or flagging a claim as unverifiable, when the evidence is thin. That is a correctness requirement here, not a nice-to-have.
- Adds Ollama as a running local service, another moving part to install and keep alive, working against the "keep it simple at this scale" force from Context
- Slower on typical laptop hardware than a cloud call, though not disqualifying at this corpus size

### Option 3: Hybrid stack (local embeddings, cloud generation)

Embeddings run locally (`sentence-transformers`), only the final answer generation step calls a cloud API.

**Pros**:
- Indexing (the more frequent, more sensitive operation, since it touches the whole corpus) stays local and free; only the query-time generation step touches the network
- Middle ground on the local-first tradeoff

**Cons**:
- Two different provider setups (a local embedding runtime and a cloud generation client) for one project, more moving parts than either pure option
- Re-embedding is still needed if the embedding model is ever swapped for a stronger one later, so this does not actually protect against the main cost Option 2 avoids
- Splits the "is this tool local or not" story into an inconsistent middle that is harder to explain than either clean option

## Decision

**Chosen option**: Option 1: Cloud API stack (OpenAI embeddings and generation, Chroma, BM25)

Use OpenAI's API for both embeddings and answer generation, ChromaDB as the embedded vector and metadata store, `rank_bm25` for lexical retrieval, and a separate SQLite database as the canonical record source of truth.

## Rationale

The engineer chose the cloud API stack over the fully local option I would have recommended by the project's own stated local-first goal. Given the corpus size in Context (a dozen to a few hundred specs) and the negligible cost at that scale, this is a reasonable tradeoff to make consciously: it buys higher answer quality and, more importantly, avoids running and maintaining a local model server (Ollama) as an extra moving part, at the cost of no longer being local-first in the strict sense. Note that the claim-verification mechanism itself (below) is a separate, checkable safeguard that would also work over a locally-hosted generator; the deciding factor here is genuinely setup simplicity at this project's scale, not a claim that local models cannot be made to abstain reliably, since no direct evidence for that was gathered. The project should treat this as an explicit, documented deviation from the README's framing, not an accidental one; Consequences and Follow-up record it as such rather than quietly rewriting the goal.

ChromaDB over LanceDB or a raw index: at this corpus scale (dozens to low hundreds of records, per `mvp.md`), Chroma remains the standard default, simple to embed with no server to run, with metadata filtering built in. LanceDB's advantage (efficient disk-based indexing past roughly a million vectors) does not apply here; its ecosystem is also younger and less documented for edge cases. `rank_bm25` over SQLite FTS5: since the canonical record store is a separate SQLite database, `rank_bm25` avoids syncing a second index inside that same database, rebuilding its in-memory corpus from stored chunk text at query time, which is fine at this scale.

The claim-level verification step is the load bearing piece that makes Option 1 defensible against Option 2's real weakness (unreliable "not enough evidence" behavior). It generates an answer from retrieved chunks only, then checks every factual claim against the source chunks before returning it; an unverifiable claim is dropped or the answer falls back to more literal source text rather than being shown unverified. This is a build requirement in its own right, not a prompt instruction, and needs a dedicated evaluation harness fixture (a question with a deliberately unverifiable claim, confirming the check actually catches it) alongside the five queries and two assertions `mvp.md` already defines.

## Proposed stack

| Layer | Choice | Reason |
|---|---|---|
| Language / packaging | Python, managed with `uv` | Already settled in `README.md`/`mvp.md`; the RAG ecosystem (embeddings, vector stores, chunking, eval tooling) is Python-first (basis: `mvp.md`, Stack section) |
| Package layout | `src/decision_memory/` (src layout), single console-script entry point `decision-memory` | `uv`'s own default scaffold; avoids tests silently importing the working-directory copy instead of the installed package |
| CLI framework | Typer | Type-hint driven, minimal boilerplate, pairs naturally with Pydantic models used for the canonical record schema |
| Schema validation | Pydantic v2 | The canonical record YAML schema maps directly onto models; gives the field-rule cross-checks (e.g. "at least one of `why`/`rationale_summary`") without hand-written validators |
| Embedding model | OpenAI API, `text-embedding-3-small` by default | Negligible cost at this corpus size ($0.02 per million tokens standard pricing); `-large` is a drop-in upgrade if retrieval quality later demands it |
| Vector store | ChromaDB | Embedded, no server, standard default at this corpus scale (dozens to low hundreds of records); stores vectors and queryable metadata together |
| Lexical retrieval | `rank_bm25` | Pure Python, in-memory BM25 rebuilt from the SQLite record store's chunk text at query time; avoids a second persistent index to keep in sync |
| Canonical record store | Separate SQLite database | Source of truth for full canonical records and structured metadata (status, tags, date, id); kept in sync with Chroma via the adapter's fingerprint / re-ingest path |
| Chunking | Custom field-boundary chunker (project code, no library) | `mvp.md` fixes the chunking invariant (canonical field boundaries are the retrieval unit); a generic splitter (LangChain, semantic-text-splitter) splits by length or semantics, not by schema field identity, so it would need to be overridden anyway |
| Answer generation | OpenAI API, `gpt-4o` (generation) + `gpt-4o-mini` (verification), constrained with claim-level verification | Generates only from retrieved chunks, then checks every factual claim against the source chunks before returning; a stronger model for prose quality, a cheaper model for the more mechanical verification pass |
| Observability | Python stdlib `logging` | Adapter and degradation warnings (missing rationale, no `rejected_because`, no Decision section, and so on) visible by default; a `--verbose` flag surfaces retrieval-path timing and detail |
| Testing | pytest, hand-written stubs by default, a small marked subset hitting the real OpenAI API | Stubs keep the normal suite free and fast; the marked subset validates real embedding discrimination and real claim verification behavior, the two places a stub could hide a genuine regression |

Auth, hosting, background jobs, and file storage are not applicable: this is a local, single-user command line tool with no server and no deployment target.

## Pinned configuration

These were open questions the cross check (below) flagged as things a build would otherwise have to invent; each is now a decision, not a build-time guess.

**Generation**: `gpt-4o` for answer generation, `gpt-4o-mini` for claim verification, temperature 0 for both (determinism over creativity for a citation tool).

**Chunking**: target chunk size ~400 tokens, 15% overlap between adjacent chunks of the same field, list items (`why` entries, `decision.alternatives` entries) always kept atomic and never split mid-item regardless of size.

**Claim verification**: the answer is split into sentences. Each sentence is first checked against its cited source chunk(s) by literal substring/keyword overlap (cheap, deterministic); only when that check is inconclusive does the sentence escalate to an LLM entailment call (`gpt-4o-mini`, yes/no, not a score). A sentence that fails verification is dropped from the answer. If what remains no longer addresses the question, the tool returns the "not enough evidence" response instead of a hollowed-out partial answer.

**Embedding function**: ChromaDB's collection is configured with OpenAI's embedding function explicitly (`text-embedding-3-small`); Chroma's bundled default local embedding function is never used, since a silent fallback there would desync ingest-time and query-time vectors.

**Lexical search**: `rank_bm25`'s corpus is normalized by lowercasing, splitting on word boundaries, and removing a standard English stopword list before indexing; no stemming.

**Retrieval**: top 8 chunks returned per query. Abstention ("not enough evidence") is retrieval's decision, gated on nothing retrieved clearing a minimum relevance floor, not deferred to the generation/verification step. The specific floor value is tuned against the evaluation harness (Slice 3) once it runs against real data, not hardcoded here.

**Storage layout**: a project-local `.decision-memory/` directory (sibling to `.git/`) holds `records.db` (the canonical-record SQLite database) and `chroma/` (Chroma's persistent client directory).

**Minimum Python version**: 3.11.

## Consequences

**Positive**:
- Highest quality retrieval and generation available with the least setup burden, at negligible cost for the expected corpus size
- The claim-verification step gives the "not enough evidence" and "don't invent a claim" behaviors a real check, not just a hopeful prompt, which is the tool's core promise
- ChromaDB and SQLite are both embedded, no service to run or operate; the whole system stays a single local process

**Negative / tradeoffs**:
- No longer local-first in the strict sense `README.md` describes: every ingest and every query needs network access and an OpenAI API key, and a personal decision corpus's contents are sent to a third party to be embedded and to generate answers
- Ongoing per-query and per-ingest cost, small at this scale but nonzero, and dependent on OpenAI's pricing and availability
- `rank_bm25`'s in-memory index is rebuilt from the record store at query time rather than persisted; fine at the expected corpus size, but would need reconsideration if the corpus grows into the thousands
- Total unavailability risk: with both embeddings and generation on OpenAI's API, an outage, an expired key, or no network access makes an already-indexed corpus completely unqueryable, not just slower. Cheap to mitigate later (a retrieval-only mode using cached embeddings, no generation) but not built in this spec

**Neutral**:
- `README.md`'s "local-first" framing should be revisited to reflect this decision, so the project's own docs stay honest about what shipped (see Follow-up)
- The embedding model choice (`text-embedding-3-small` vs `-large`) is deliberately left open as a cheap later upgrade, not re-litigated here

## Follow-up

- [ ] Reconcile `README.md`'s "local-first" framing with this decision (cloud embeddings and generation); either soften the claim or scope it to "local storage and retrieval, cloud embedding/generation"
- [ ] Build the claim-level verification step's dedicated evaluation harness fixture (a question with a deliberately unverifiable claim) as part of Slice 3's evaluation harness, not folded silently into Slice 1
- [ ] Agent Skills / MCP servers for this stack (Chroma, OpenAI SDK, Typer, Pydantic, `rank_bm25`) were deliberately deferred at spec time (engineer's choice: "not now, later"); revisit at `/develop` or `/audit` time
- [ ] The open `mvp.md` / `docs/index.md` inconsistency noted in `docs/session-notes.md` (a commit claims `mvp.md` was removed as superseded by `docs/index.md`, but neither `docs/index.md` nor a CLI package exist yet, and `mvp.md` is still present) is worth resolving before `/audit` runs and captures conventions from this repo state
- [ ] `OPENAI_API_KEY` will be a required environment variable once the scaffold is built; document it in the project's setup instructions

## References

**Project sources** (verifiable, in this repo):
- `README.md`, the local-first goal and the canonical record schema
- `mvp.md`, the chunking invariant, hybrid retrieval requirement, corpus size discussion, and the Python/`uv` packaging decision
- `docs/scope/scope.md`, Feature 1 (Stack & architecture)

**Practices & standards**:
- Retrieval-augmented generation with claim-level verification (generate from retrieved context only, verify each claim against source text before returning it)
- Embedded, server-less storage as the right default at small (sub-million-row) scale

**Links** (web verified 2026-08-06):
- [Vector Database Comparison 2026: ChromaDB vs. LanceDB and others](https://4xxi.com/articles/vector-database-comparison/)
- [OpenAI Embeddings API Pricing (Aug 2026)](https://costgoat.com/pricing/openai-embeddings)
- [Typer (FastAPI-author's CLI framework) on GitHub](https://github.com/fastapi/typer)
