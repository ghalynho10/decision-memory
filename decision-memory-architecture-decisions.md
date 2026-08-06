# decision-memory — Architecture Decisions

A complete record of every technical decision made during `/architect`, why each one was chosen over its alternatives, and what the underlying concepts mean. Written so this document is useful on its own, without needing to have sat through the original conversation.

---

## How to read this document

Each decision below follows the same shape: **what was chosen**, **what it does**, **why it won over the alternatives**, and **plain-language definitions** of any term that isn't everyday vocabulary. If a term appears in multiple sections, it's explained the first time and referenced afterward.

---

## 1. Embedding model — OpenAI `text-embedding-3-small`

**What it does:** An embedding model turns text into a list of numbers (a *vector*) that represents its meaning. Two pieces of text with similar meaning end up with similar vectors, even if they don't share the same words. This is what makes *semantic search* possible — finding text that means the same thing, not just text containing the same words.

**Alternatives considered:**
- A local model (e.g., via `sentence-transformers`) — runs entirely on your machine, no API key, no network call, genuinely "local-first."
- Other cloud providers (Voyage AI, Cohere).

**Why this one won:** Two reasons, in order of importance.
1. **Discrimination quality.** This project's core value depends on retrieval correctly distinguishing a *chosen* decision from its *rejected alternatives* — text that's often semantically close on purpose, since both describe the same problem from different angles. A weak embedding model's failure mode here isn't "no results," it's "confidently retrieves the wrong alternative and cites it as the decision." That's worse than finding nothing, so this was judged the wrong place to gamble on an unproven model.
2. **Already validated.** This exact model was proven end-to-end in an earlier learning project, on data of a similar shape (structured technical prose). Reusing it means building on evidence, not a guess.

**The named tradeoff:** this makes the "local-first" framing untrue for the embedding step specifically — it requires an OpenAI API key and a network call per embedding. Accepted deliberately, revisitable later against real evaluation numbers if it ever matters more than retrieval precision does.

---

## 2. Vector store — ChromaDB (embedded, `PersistentClient`)

**What it does:** A *vector store* (or *vector database*) is a database built specifically to store embeddings and quickly find the ones most similar to a given query vector — this is the engine behind semantic search. "Embedded" means it runs as a library inside your own program, not as a separate server you have to start and manage.

**Alternatives considered:** LanceDB, SQLite + the `sqlite-vec` extension, FAISS (a lower-level vector search library from Meta).

**Why this one won:** Already validated in the earlier learning project, and nothing about this project's data volume (one repository's decision history — realistically low thousands of chunks) comes close to stressing any of these options' limits. Since capability wasn't the deciding factor, there was no reason to re-validate a new, unfamiliar tool for no proven benefit.

---

## 3. Lexical retrieval — `rank_bm25`

**What it does:** *Lexical retrieval* (also called *keyword search*) finds text based on shared literal words, as opposed to *semantic search*, which finds text based on shared meaning. **BM25** (Best Matching 25) is a well-established scoring algorithm for ranking documents by keyword relevance — an improved, more principled version of older approaches like TF-IDF (Term Frequency–Inverse Document Frequency, a way of weighting words by how distinctive they are). `rank_bm25` is a small, standalone Python library implementing BM25.

**Why keyword search matters alongside semantic search ("hybrid retrieval"):** Semantic search is good at understanding paraphrased meaning but can sometimes miss an exact, specific term (like an exact decision ID or a precise technical name) that a keyword search would catch instantly. Combining both — *hybrid retrieval* — covers each approach's blind spot.

**Alternatives considered:** LanceDB's or SQLite's built-in full-text search (FTS5).

**Why `rank_bm25` won:** This was mostly a *consequence* of the vector store decision, not an independent choice. Since Chroma (the vector store) has no built-in keyword search, and lexical retrieval needed a home regardless, `rank_bm25` is the standard lightweight choice — pure Python, no separate database engine to keep synchronized with the vector index.

---

## 4. Chunking library — custom field-boundary chunker (not LangChain, not `semantic-text-splitter`)

**What "chunking" means:** Before text can be embedded or searched, it's broken into smaller pieces called *chunks* — usually because a whole document is too large or too unfocused to embed as one unit, and because retrieval works better when it can return a small, precise piece of text rather than an entire document.

**Alternatives considered:** LangChain's text splitters, `semantic-text-splitter` — both popular, general-purpose libraries for splitting continuous prose (an article, a document) into chunks.

**Why a custom chunker won, and why this one actually matters:** This project's data isn't continuous prose — it's structured YAML records with named fields (`context.problem`, `decision.chosen`, each item in a list of alternatives, etc.). A core design rule (see "The Chunking Invariant" below) requires that a chunk never crosses a field boundary — the boundary between, say, `context.problem` and `decision.chosen` must always be respected. Off-the-shelf prose-chunking libraries have no concept of "this is a structured field boundary, never cross it" — using one would mean either fighting the tool to respect a rule it doesn't understand, or silently reverting to naive prose-chunking behavior, which would undo a deliberate design decision. A custom chunker here is small (roughly 30–50 lines) and is the one place where using an off-the-shelf library would actively work against an already-settled decision rather than just being unproven.

---

## 5. The Chunking Invariant (parameters and rules)

This isn't a tool choice — it's the actual rule for how records get split into chunks, settled independent of any library.

- **Canonical field boundaries are the retrieval unit.** A chunk is built from one field (or, for long fields, a piece of one field) — never spanning two different fields.
- **Threshold: 400 tokens, with 60 tokens of overlap (~15%).** A *token* is roughly a word or word-piece — the unit language models actually process text in. This 400/60 pairing comes from an earlier, already-validated pipeline, but its role changed: it's now a **ceiling applied only to individual fields that run long**, not a flat window applied to the whole document. Most fields (a title, a single reason in a `why` list) are well under 400 tokens and become one whole chunk each, with no subdivision.
- **Overlap** means that when a long field does need subdividing, consecutive chunks share a small amount of text at the boundary — this prevents a sentence or idea from being awkwardly cut exactly in half between two unrelated chunks.
- **List items are chunked individually**, not concatenated. Each entry in `why`, each `alternatives[]` object, each `evidence[]` entry becomes its own chunk. This lets a query surface "which alternative was rejected and why" as one directly-matched chunk, instead of only ever retrieving an entire list as one blob.
- **Nested fields chunk at the leaf, not the parent** — `context.problem` and `context.triggering_change` are separate chunks, since they answer different questions, even though they live under the same `context` key.
- **Every chunk (and every sub-chunk of a long field) carries its own provenance:** the record's `id`, which field it came from, and the exact source file/section — this is what allows a citation to be exact, and what allows chunks to be reassembled back into their parent record.

---

## 6. Answer generation — OpenAI GPT-4o, constrained (not free-form)

**What "generation" means here:** Retrieval finds relevant chunks of text; *generation* is the separate step where a language model writes a readable answer from those chunks, rather than just handing back a raw list of matched fragments.

**The real decision here wasn't just "which model" — it was "how much freedom does the model get."** Two shapes were considered:
- **Free-form generation** (the common RAG pattern): the model writes an answer drawing on the retrieved chunks plus its own general knowledge, producing fluent prose but with a real risk of stating something that sounds right but isn't actually supported by the source material.
- **Constrained generation** (what was chosen): the model is only allowed to use the retrieved chunks — nothing from its general training — as if handed a fixed stack of sticky notes and told "answer using only what's written here."

**Why constrained generation won:** The entire premise of this project is that every answer can be trusted because it's cited to a real source. Free-form generation reopens exactly the fabrication risk that this project's schema (with its requirement that every alternative have a `rejected_because`, every record resolve to real `evidence`) was built to avoid — except at the answer layer instead of the record layer.

**Why GPT-4o specifically:** Same model, same provider, already used and proven for a closely related job — generating resume bullet points that must not fabricate facts (a prior, shipped project). Reusing it means reusing an engineering pattern that's already been built and validated once, applied to a new but structurally similar problem (constrain the model, then verify its output before trusting it).

---

## 7. Claim verification — literal check first, LLM entailment as fallback

**The problem this solves:** Even a *constrained* model (see #6) can still drift — subtly paraphrasing past what a source actually said, or implying a connection between two facts that wasn't really stated. So after the model generates an answer, a separate, independent check verifies that every specific claim in that answer is actually supported by the retrieved chunks — this step is what makes "constrained" a guarantee rather than just an instruction the model might not fully follow.

**What was chosen — a two-tier check, not a single method:**
1. **First tier: literal substring/keyword overlap (no LLM call).** Deterministic and free — check whether a claim's key facts and terms actually appear in the source chunk it's supposedly based on. This can't itself hallucinate a wrong "yes, verified" answer the way an LLM checker theoretically could.
2. **Second tier, only when tier one is inconclusive: sentence-level LLM entailment, via a smaller/cheaper model (`gpt-4o-mini`).** *Entailment* is a term from NLP meaning "does statement B logically follow from statement A." This tier catches cases where a generated sentence paraphrases a chunk closely enough that the exact words don't match, but the meaning genuinely is the same — literal overlap alone would wrongly flag that as unsupported.

**Why not just always use LLM entailment (the more "obvious" RAG pattern):** Cost and reliability. A deterministic check is cheaper, faster, and cannot itself be wrong the way a judgment call can — so the design uses it wherever it's sufficient, and reserves the more expensive, judgment-based check for the harder cases. This mirrors a pattern already proven in a related project: use code to check what code reliably can, and reach for a model only when the task genuinely requires judgment.

**Granularity — sentence-level, not finer:** A finer-grained check (breaking an answer into individual sub-claims and checking each) was considered and rejected as unnecessary precision for the value gained — it means more model calls, more cost, more opportunities for the checker itself to be wrong, without a clear benefit at this project's scale.

---

## 8. Partial verification handling — drop failed claims, then re-check whether the answer still holds up

**The scenario:** An answer has multiple claims; some pass verification (#7), some don't. What happens to the ones that fail?

**What was chosen:** Drop the specific claims that fail verification, keeping the ones that pass. Then check whether what remains still actually answers the original question. If it does, return the trimmed answer. If dropping the failed pieces leaves an answer that no longer meaningfully addresses the question, **abstain** — return "not enough evidence" rather than a hollowed-out partial answer.

**Why this won over the alternatives:**
- *Always abstain on any single failed claim* was rejected as too brittle — a four-sentence answer with one slightly overstated clause would be thrown away entirely, discarding three genuinely well-supported sentences along with the one flawed one.
- *Always fall back to showing the raw source chunk text instead of a failed claim* was rejected as the default (though kept as a fallback element) — doing this for every single failure would mean answers frequently become an awkward mix of polished prose and raw dumped text, undermining the value of generation.

This mirrors the same graceful-degradation pattern used throughout the project's design: prefer losing the smallest possible amount of trustworthy content over throwing everything away, but never let "gracefully degraded" quietly become "no longer actually answers the question."

---

## 9. CLI framework — Typer

**What it does:** Turns a plain Python function into a command-line tool (e.g., `decision-memory query "..."`), automatically generating the argument parsing, help text, etc.

**Alternatives considered:** Click (a more established, more configurable library that Typer is actually built on top of), and `argparse` (Python's built-in option, no extra dependency).

**Why Typer won:** This project's core is deliberately designed as one clean function — `query(question, filters) -> Answer(text, citations)` — kept separate from any interface-specific formatting. Typer's whole design premise is generating a CLI directly from a plain function's type hints, which reinforces that separation rather than requiring extra boilerplate to maintain it. `argparse`, while dependency-free, gets verbose quickly for a command with several optional filter flags.

---

## 10. Schema validation — Pydantic

**What it does:** Pydantic is a library for defining a data structure (like the canonical decision record) as a typed Python class, and automatically validating that any data loaded into it (e.g., from a parsed YAML file) actually matches the required shape and rules — catching malformed or incomplete data at the boundary where it enters the system, rather than letting it cause confusing errors later.

**Alternatives considered:** Python's built-in `dataclasses` plus hand-written validation checks, or the `attrs` + `cattrs` library pair (similar in spirit to Pydantic, smaller ecosystem).

**Why Pydantic won:** The validation rules this project needs aren't simple type-checking — they include conditional logic ("at least one of `why` or `rationale_summary` must be present"), and rules nested inside lists (every item in `alternatives` must have a `rejected_because`). Pydantic supports exactly this kind of rule directly and concisely; `dataclasses` would require writing and testing that logic entirely by hand.

---

## 11. Package layout — `src/` layout

**What it means:** This is about where the actual Python package code lives inside the project's folder structure. A "flat" layout puts the code directly in the project root; a "`src/` layout" nests it one level deeper, inside a `src/` folder.

**Why `src/` layout won:** It's not just convention — it prevents a specific, easy-to-hit bug. With a flat layout, tests can accidentally pass by finding your code in the current working directory, while the version that actually gets installed via `pip`/`uv` (which is what real users run) is broken — and you might not discover that until someone else installs it. Since this project is explicitly meant to ship as an installable CLI package, avoiding that failure mode from the start was worth the extra folder nesting. It's also the modern default that `uv` itself scaffolds automatically.

---

## 12. Data storage split — SQLite (authoritative) + Chroma (derived index)

**The question:** Chroma stores vector embeddings, but the full canonical decision records (with all their nested fields) and the text corpus that `rank_bm25` searches need to live somewhere too. Should that be Chroma's own metadata fields, or a separate database?

**What was chosen:** A separate SQLite database (a lightweight, file-based relational database, no separate server needed) holds the full canonical records, plus the text corpus `rank_bm25` searches over, plus the bookkeeping needed for incremental re-ingestion (see #14). Chroma holds *only* the vector embeddings, computed **from** the data in SQLite.

**Why this split, and why it's "authoritative vs. derived," not just "two databases":** SQLite is the source of truth. Chroma's vectors are a cache — something computed from SQLite's data, not a second independent copy of it. This has a real practical payoff: if the embedding model or a chunking parameter ever changes, Chroma's entire index can be deleted and rebuilt from scratch from SQLite, with zero data loss, because SQLite never depended on Chroma. If Chroma were the only store, changing the embedding model would risk losing canonical record data along with the vectors.

**Why not just use Chroma's built-in metadata fields for everything:** Those fields are designed for simple flat key-value tags (like `status` or `date`), not for a full nested record structure, and they can't serve as a search corpus for `rank_bm25` at all.

---

## 13. Observability — Python's standard `logging` module

**What it does:** Records what the program is doing and any problems it encounters, so they're visible rather than silently swallowed.

**Why this matters more than usual for this project, specifically:** The project's own "degradation policy" (see the MVP scope document) repeatedly says the system should "warn" when something goes wrong (a missing rationale, an alternative without a stated rejection reason, an unmapped field). Those warnings are a real, load-bearing part of the design — if logging isn't actually wired up, those promised warnings simply don't happen, silently undermining a design principle that was deliberately built in.

**What was chosen:** Standard library `logging` (no third-party tool like `structlog` — those solve problems this single-user local CLI doesn't have yet). Adapter and degradation-policy warnings are visible by default; a `--verbose` flag adds detail about the retrieval path itself (useful for debugging why a query returned "not enough evidence"). Using `logging` rather than scattered `print()` statements also matters for testing — logging output can be captured and checked in automated tests, confirming that a warning actually fired when it should have.

---

## 14. Testing framework — pytest

**Alternatives considered:** `unittest` (Python's built-in testing framework).

**Why pytest won:** A prior, already-shipped project used pytest-equivalent conventions extensively (350+ tests), so this reuses an already-familiar testing style rather than learning a second framework's conventions from scratch. Pytest's `parametrize` feature is also a strong fit for this project's evaluation harness — running the same check across several different questions/assertions — with noticeably less repeated code than `unittest` would require for the same coverage.

---

## 15. Test isolation strategy — mostly stubs, small marked subset hits the real API

**The problem:** Tests that call the real OpenAI API on every run are slow, cost money, and can occasionally fail for reasons that have nothing to do with a real bug (a network hiccup, a slightly different response) — this is called *flakiness*.

**Alternatives considered:** Record/replay "cassettes" (a tool like VCR.py records a real API response once, then replays it in future test runs without a real network call).

**What was chosen:** Hand-written stub/mock responses (fixed, fake, predictable stand-ins for what the API would return) for the large majority of tests — these check whether *your own code's logic* is correct, not whether OpenAI's API is behaving a certain way, so a real API call isn't needed. A small, explicitly marked subset of tests does hit the real API — specifically for things that genuinely can't be faked, like confirming the embedding model actually discriminates well between a chosen decision and its rejected alternatives.

**Why not cassettes:** Reasonable in general, but they add a dependency and an ongoing maintenance cost (re-recording them whenever a prompt changes) that a project at this scale doesn't clearly need. Hand-written stubs are more effort to write initially but don't silently go stale the way a recorded cassette can.

---

## 16. BM25 text normalization — lowercase, split on word boundaries, English stopword removal (no stemming)

**What "normalization" means here:** Before comparing words for keyword matching, text is processed to make matching more reliable — e.g., "Store" and "store" should count as the same word.

**Stopwords** are extremely common words (the, why, was, and, how) that carry little to no distinguishing meaning for search purposes — removing them stops these words from diluting a keyword match, since this project's real queries are full natural-language questions ("Why was the private beta access gate added?") full of such words.

**Stemming** (e.g., the Porter stemmer) reduces different forms of a word to a shared root (e.g., "storing," "stored," and "store" all become "stor"), so a search for one form can match documents using another form.

**Why stemming was left out for now:** Stemming helps most when vocabulary genuinely varies across documents, but this project's canonical schema uses fairly controlled, technical vocabulary. Stemming also has a real failure mode — aggressive stemmers can sometimes conflate unrelated words that happen to reduce to the same root, creating false matches. Since semantic search (via embeddings) already handles most wording/phrasing variation, adding stemming to the keyword-search half would mostly duplicate that coverage rather than add clear new value — worth adding later only if real evaluation shows specific word-form mismatches actually costing search accuracy.

---

## 17. Retrieval depth (top-k) and abstention threshold

**Top-k = 8** — the number of chunks retrieved per query. Chosen instead of a higher number (like 15) specifically because this project's chunks are already small and numerous (each field, each list item, is its own chunk) — pulling too many risks returning mostly fragments from a single record, diluting precision rather than adding genuinely new information.

**Abstention** (deciding to return "not enough evidence" rather than an answer) happens **before generation runs**, based on whether any retrieved chunk clears a minimum relevance floor — not a hardcoded number picked in advance. The actual numeric threshold is meant to be tuned later, once the evaluation harness (see the MVP scope document) is running against real data and can show what score distribution actually separates a genuinely relevant chunk from an irrelevant one.

**Why abstention is retrieval's decision, not generation's:** If retrieval found nothing meaningfully relevant, the system shouldn't let the language model attempt an answer anyway and hope its own claim-verification step (#7) catches the failure afterward — that wastes a paid generation call on bad input and puts the burden of catching "there's no real answer here" on the wrong, more expensive part of the pipeline.

---

## 18. Validation corpus — a real project's real specs (JobPilot), not synthetic or self-referential data

**What was chosen:** The system will initially be tested against a genuinely existing project's spec files (JobPilot, at `docs/specs/` in its repository), rather than decision-memory's own specs, and rather than made-up example data.

**Why not the project's own specs:** Two reasons. First, a bootstrapping problem — you'd need the parser working to accumulate specs, but need specs to test the parser. Second, and more important: specs written specifically to validate this tool would unconsciously be written in exactly the shape the tool expects, since the person writing them knows what the parser looks for — this would completely defeat the point of testing against realistically messy data.

**Why a real, independent project works:** It has genuine messiness a parser needs to survive — inconsistent formatting, missing sections, specs that were never formally finalized, decisions recorded across two separate files instead of one. This messiness was already confirmed directly, by manually mapping one real spec from that project into the canonical schema before this build began.

---

## 19. Packaging — pip/`uv`-installable CLI

**What was chosen:** The finished tool ships as a package installable via `pip` or `uv` (e.g., `uvx decision-memory query "..."`), rather than, say, a VS Code extension.

**Why:** This wasn't really a new decision — it falls directly out of choices already made (Python, a CLI interface, and a clean separation between the core logic and the interface). A future MCP server (making the tool queryable from inside a coding agent) or a web interface remain real possibilities, but they're later, separate decisions, not something to design prematurely now.

---

## Glossary — every technical term used above, in one place

| Term | Meaning |
|---|---|
| **Embedding / vector** | A list of numbers representing a piece of text's meaning, generated by an embedding model. Similar meanings produce similar vectors. |
| **Semantic search** | Finding text based on similarity of *meaning* (via embeddings), even without shared exact words. |
| **Lexical / keyword search** | Finding text based on shared literal words. |
| **Hybrid retrieval** | Combining semantic and keyword search so each covers the other's blind spots. |
| **BM25** | A well-established scoring algorithm for ranking documents by keyword relevance. |
| **TF-IDF** | An older keyword-weighting approach BM25 improves on; weights words by how distinctive they are to a document. |
| **Vector store / vector database** | A database optimized for storing embeddings and quickly finding the most similar ones to a query. |
| **Chunk / chunking** | Breaking a larger piece of text into smaller, individually retrievable pieces. |
| **Token** | Roughly a word or word-piece — the basic unit language models process text in; used to measure text length for chunking and cost purposes. |
| **Provenance** | The exact source (file, section) a piece of retrieved text came from — what makes a citation verifiable. |
| **Generation** | The step where a language model writes a readable answer, as opposed to just retrieving raw matching text. |
| **Constrained generation** | Generation where the model is restricted to using only specific provided material (here, retrieved chunks), not its own general knowledge. |
| **Fabrication / hallucination** | When a language model states something confidently that isn't actually true or supported by its source material. |
| **Claim verification** | Checking, after generation, whether each specific factual statement in an answer is actually supported by the source material it's based on. |
| **Entailment** | An NLP concept: whether one statement logically follows from another. Used here to judge if a generated sentence is truly supported by a source chunk, even when the wording differs. |
| **Abstention** | The system deliberately declining to answer ("not enough evidence") rather than guessing, when the evidence doesn't actually support a confident answer. |
| **Schema / canonical record** | The fixed, structured shape every decision record must follow (defined fields, defined rules), so records from different sources become uniformly usable. |
| **Adapter** | A piece of code that reads one project's specific file format and translates it into the canonical schema, without the rest of the system needing to know anything about that format. |
| **Validator** | Code that checks whether a given piece of data actually satisfies the schema's rules. |
| **Degradation policy** | A defined, deliberate response for each way real-world input can be messy or incomplete — rather than either crashing or silently guessing. |
| **Incremental ingestion / fingerprinting** | Re-processing only what's changed since the last run (tracked via a hash or modified-time per source file), instead of reprocessing everything every time. |
| **Corpus** | A collection of text used as the raw material for search — here, all the chunk text `rank_bm25` searches over. |
| **Stopwords** | Extremely common words (the, and, why) removed before keyword search since they carry little distinguishing meaning. |
| **Stemming** | Reducing different word forms (storing, stored, store) to a shared root, so a search matches across all of them. |
| **Relational database** | A database that organizes data into structured tables with defined relationships — SQLite is a lightweight, file-based example. |
| **Authoritative vs. derived data** | Authoritative data is the real source of truth; derived data is computed from it and can always be rebuilt if lost, without any actual data loss. |
| **Stub / mock** | A fixed, fake stand-in for a real dependency (like an API), used in tests so the test isn't dependent on that dependency actually being available or behaving predictably. |
| **Flaky test** | A test that sometimes fails for reasons unrelated to an actual bug (e.g., a network issue), making test results unreliable. |
| **`src/` layout** | A Python project structure where the actual package code lives inside a `src/` folder, rather than directly in the project root — helps ensure tests run against the real installed package. |
