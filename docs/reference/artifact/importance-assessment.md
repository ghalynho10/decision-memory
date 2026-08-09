# Importance assessment: could decision-memory be a genuinely important tool?

_Reference artifact. Written 2026-08-09 as a strategic assessment of whether decision-memory could become a genuinely important tool for developers and non technical "vibe coders" worldwide, and what blocks it. Not in scope; revisit against the roadmap._

## The case for

The core problem is universal and getting worse. Every developer has hit "why is this built this way" with no answer. The agent era makes it acute: reasoning now lives in chat sessions that vanish, and a vibe coder has effectively no memory at all — no ADRs, no specs, no PR culture, just a pile of agent decisions that evaporate when the tab closes.

The wedge is genuinely differentiated:

- **Cited answers plus honest abstention.** Most RAG tools confidently hallucinate. "Not enough evidence here" as a first class, schema enforced outcome is a feature most competitors do not have — the difference between a tool you trust and a tool you must double-check.
- **Decision specific schema, not generic RAG.** "What did we reject, and why?" is a query most retrieval cannot answer because the data is not captured in a shape that supports it.
- **It is infrastructure, not a notes app.** Harness agnostic memory service (MCP spine, adapters, "write an adapter not a fork") positions it to be mounted rather than adopted, which is how tools become ecosystem level rather than niche.

## The four hard limitations today

### 1. The capture problem (the biggest one, especially for vibe coders)

The tool's value depends on decision records existing.

- Developers: most teams do not maintain ADRs or specs. An empty corpus means nothing to answer. The built in adapters only cover jsmastery specs plus (planned) MADR and plain ADR.
- Vibe coders: they almost certainly do not write specs at all. Their decisions live in chat. And the tool is read only — adapters read artifacts, they never capture. So the audience with the worst memory problem gets the least from it. "Capture" is planned (v2) but does not exist yet.

### 2. The payoff loop is not shipped

Today you can `doctor`, `validate`, and `adapt`, but you cannot ask. The entire value proposition ("ask why, get a cited answer") is feature 9 (`query`, Slice 1), not in the CLI. MCP is feature 14. Until those ship, it is a tool that indexes but does not answer.

### 3. Friction: keys, a separate CLI, nothing ambient

It is local but Slice 1 needs an OpenAI key and Chroma. It is a CLI you must remember to run. The proactive wiring (step 7) is a doc, not a product. Vibe coders live inside Cursor, Claude Code, and VS Code and will never open a terminal to survey a corpus. A tool that is not ambient does not get used by anyone, and definitely not by non technical people.

### 4. Trust and capture discipline

Even with records, records are only as good as what got written. The schema enforces honesty (rejected alternatives need a reason) but cannot enforce that people record anything. There is real competition — agent memory tools, RAG tools, ADR tools — so it needs the wedge finished and discoverable, not just designed.

## What would solve these, in priority order

| Limitation | Fix |
|---|---|
| No payoff loop | Ship feature 9 (`query`) then feature 14 (MCP). The single highest leverage item; nothing else matters until "ask why" works |
| Capture cold start | Make capture first class and near zero friction: a `remember` command, plus an MCP tool or agent skill so an agent writes a decision record at the moment a decision is made ("the agent just chose X because"). Fixes both audiences at once |
| Vibe coder mismatch | Ambient integration: MCP server plus the step 7 convention as a shipped artifact, and the VS Code plugin as a client. The tool should be consulted and written to by the agent, not by the human |
| Friction (keys, setup) | Provider agnostic, offline capable embeddings (optional local model, bring your own key) so "local" is actually local and does not gate on OpenAI |
| Adapter reach | More built in adapters plus a generic fallback: an "any markdown with Decision headings" heuristic adapter so adoption never requires writing one; also auto derive records from commits and PRs so the corpus grows without new discipline |
| Ecosystem | Close the loop: the harness produces decisions, memory stores them, agents consult before building, more decisions get recorded. When the corpus grows automatically, cold start disappears and the tool becomes load bearing rather than optional |

## Bottom line

The hardest barrier is not technical — it is getting the first record written and getting the tool to be ambient. The design already makes the right calls (adapters not forks, anti fabrication, harness agnostic MCP spine); what is missing is the loop: capture when you decide, consult before you build, both happening inside the agent where the work happens.

The one thing that determines whether this becomes genuinely important: capture first, integrated into the agent loop, with the query payoff shipped. Right now it is "read the records you were already disciplined enough to write." The version that matters is "remember this for me, and tell me why before I relitigate it" — which is a tool both a senior engineer and a vibe coder would rely on daily. That version is buildable and mostly already on the roadmap; it is just not shipped yet.

## Status

Not in scope. Reference only. Related artifacts: `step-7-proactive-wiring.md` in this folder covers the proactive consultation layer; feature 9 (query) and feature 14 (MCP) in `docs/scope/scope.md` are the roadmap items this assessment depends on.
