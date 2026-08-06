# Scope: decision memory

A local, cited RAG system that makes software decision history queryable. Point it at a project's decision records and ask why something is built the way it is, and get an answer with citations back to the source, or an honest "not enough evidence here."

**Build approach:** Skateboard (ship the smallest usable whole first, a real person gets a real cited "why" answer, then grow it release by release).
**Workflow:** Beta (check verify, then test). The project's default rigor tier; a feature's own tier tag overrides it.

_You are in charge. Every box below is a suggestion, not a gate: run any, skip any, and mark a feature done when you decide it is. The workflow records what you actually did (including "skipped"), it never requires a step. The one thing it asks is that a load bearing decision be written down (a spec), not that any check be run._

## At a glance

| # | Feature | Phase | Status |
|---|---------|-------|--------|
| 1 | Stack & architecture | Foundation | in-progress |
| 2 | Coding standards & tooling | Foundation | planned |
| 3 | Canonical decision record schema & validator | Foundation | planned |
| 4 | jsmastery specs adapter | Foundation | planned |
| 5 | Core cited query | Slice 1 | planned |
| 6 | Reliable multi source retrieval | Slice 2 | planned |
| 7 | Proven correctness (evaluation harness) | Slice 3 | planned |

## Foundations

### 1. Stack & architecture
Decide the embedding model, vector store, chunking library, and the `uv` managed CLI package layout, then scaffold a runnable empty project.
**Done when:** the stack is recorded in a spec and the empty scaffold boots locally (`uvx decision-memory`) and passes build.
spec [0001](../specs/0001-stack-and-architecture.md)
- [x] Decide the stack (spec): `/architect stack & architecture`
- [ ] Scaffold from the decision: `/develop stack & architecture`

### 2. Coding standards & tooling
Capture conventions from the real scaffolded project into root `AGENTS.md`, then install lint, format, and pre commit enforcement.
**Done when:** root `AGENTS.md` reflects the real stack, and lint, format, and pre commit run clean.
- [ ] Capture conventions + tooling choices: `/audit`

### 3. Canonical decision record schema & validator · needs a decision
The YAML frontmatter plus markdown body schema (id, title, status, context, decision, why, rationale summary, consequences, evidence, tags, supersedes), and a validator that enforces the field rules: evidence must resolve, alternatives need a rejection reason, at least one of why or rationale summary is populated, and any field an adapter attempted and failed to populate is flagged rather than silently absent.
**Done when:** a hand written record that violates each rule above is rejected with a clear reason, and a valid record passes.
- [ ] Design it (spec): `/architect canonical decision record schema & validator`

### 4. jsmastery specs adapter · needs a decision
Reads `docs/specs/<n> <name>/index.md` (plus `rationale.md` where present) and implements discover, parse, and fingerprint, following the field mapping and degradation policy already defined (rationale as list only, prose only, both, or absent; a missing rejection reason; no Decision section means no record). The fingerprint covers every file that contributes to a record, not only the entry file.
**Done when:** run against JobPilot's real `docs/specs/`, the adapter produces valid canonical records for well formed specs and a clear warning, never a fabricated field, for each degraded case in the policy table.
- [ ] Design it (spec): `/architect jsmastery specs adapter`

## Slice 1: Core cited query

### 5. Core cited query · needs a decision
Ingest real specs (parse, chunk on canonical field boundaries, embed, index, with metadata kept as structured queryable fields), semantic only retrieval, and a CLI `query` command returning an answer plus citations through a clean function boundary, with an explicit "not enough evidence" path when nothing supports an answer. Incremental re ingestion via the adapter's fingerprint is built in here, not deferred, since retrofitting it later means re embedding everything.
**Done when:** a user runs the CLI against JobPilot's real specs and gets a cited answer, or an honest no evidence response, to query 1 (why was the private beta access gate added, and what was the alternative) end to end.
- [ ] Design it (spec): `/architect core cited query`

## Slice 2: Reliable multi source retrieval

### 6. Reliable multi source retrieval · needs a decision
Add structured metadata filtering and lexical retrieval alongside semantic retrieval, so a filter can constrain the candidate set before semantic similarity chooses among it, which is what keeps the tool from confidently citing the wrong document. Exact stage ordering and whether scores fuse or run as a pipeline is an `/architect` decision.
**Done when:** query 2 (what decisions affect resume generation) and query 4 (what was decided about separating server side and browser side database clients, and why) return correctly sourced answers, not merely plausible ones.
- [ ] Design it (spec): `/architect reliable multi source retrieval`

## Slice 3: Proven correctness (evaluation harness)

### 7. Proven correctness (evaluation harness)
The five defining queries as fixtures with known correct sources, plus two further assertions: one whose correct answer requires the rationale summary specifically and cannot be answered from the why list alone, and one that edits a `rationale.md`, re ingests, and confirms the record's chunks updated. The questions and assertions are already fully specified; this feature builds the harness, it does not design one.
**Done when:** query 3 (which decisions are still provisional rather than ratified), query 5 (what changed the original approach to storing uploaded files, expected to return no evidence in v1), and both extra assertions pass or fail legibly against JobPilot's real corpus.
- [ ] Build it: `/develop proven correctness (evaluation harness)`

## Deferred
Out of scope for the current build pass, kept so the plan stays honest.
- **Capture**: interview based record creation for projects with no existing decision shaped artifacts · needs a decision
- **MCP server interface**: exposes the query function as an MCP tool inside a coding agent · needs a decision
- **Web UI**: a frontend over a thin HTTP layer on the core · needs a decision
- **History reconstruction**: recovering decisions from a codebase that never recorded them
- **Multi project or cross repo querying**
- **Auto generating records without human review**
- **Corpus backfill from git history**: padding the JobPilot corpus from commit history if it proves too thin to evaluate hybrid versus semantic only retrieval; a conscious later choice, not assumed now

## Legend

**The decision box.** Every feature carries at most one, the sub task whose label ends with `(spec)`. Its wording varies (`Design it (spec)` normally, `Decide the stack (spec)` on Stack & architecture), so skills locate it by that `(spec)` suffix, never by an exact label. Every other box is an execution box and `/architect` never ticks one.

**Feature lifecycle**: the scope updates as a feature moves; each row is what it shows and who sets it:

| State | Set by | The feature shows |
|---|---|---|
| `planned` · needs a decision | `/scope` | one box: `Design it (spec): /architect <feature>` |
| `in-progress` (designed) | `/architect` at spec capture | `Design it` ticked; spec linked; `Build it: /develop <feature>` plus 2 to 5 milestones; the tier's closing boxes (`Verify it` at Alpha and above, `Test it` at Beta and above, `Review it` plus `Document it` at GA); any surfaced follow up enrolled |
| `in-progress` (building) | `/develop` | milestone sub boxes tick one by one; code pointer filled |
| `in-progress` (verified) | `/check verify` | `Build it` plus milestones ticked; `Verify it` ticked |
| `done` | you, when you decide it is (any skill sets it when you say so); `/sync` reconciles | the boxes you ran are ticked, the ones you skipped are recorded as skipped; the tier's last stage (Prototype after `/develop`, Alpha after `/check verify`, Beta or GA after `/test`) is the suggested point to call it done, never a gate; `/sync` captures conventions |

- **Next step** = the first unticked box (always a command or a tracked milestone).
- **needs a decision** = run `/architect` first; otherwise straight to `/develop` (or `/audit` for standards and tooling). The tag drops once the spec is captured.
- **Atomic build tasks live in the spec's `## Build plan`, not here**: the scope carries only the milestone rollup.
- **Status** `planned` then `in-progress` then `done`, plus `existing` (pre workflow) and `dropped` (de scoped, kept for history).
- **Approach tag** beside a heading overrides the project default for that feature; no tag means it inherits.
- **Workflow tier tag** beside a heading (for example `· GA`, `· Prototype`) overrides the project default `**Workflow:**` tier for that one feature; no tag means it inherits. The effective tier (tag if set, else default) is the recommended verification depth; every skill reads it the same way to suggest the next step and shape the closing boxes. Those boxes are suggestions you run or skip; skipping never blocks `done`.
- **Workflow** (header line) is the project default tier, the stages each feature suggests running after `/develop`: Prototype means nothing beyond `/develop`'s own build time self check; Alpha means `/check verify`; Beta means `/check verify` then `/test`; GA adds a fresh model `/check review` then `/document`. `done` is your call, not gated on these; a skipped stage is recorded as skipped. An Assumed spec is flagged on the feature (its decision still owes ratification) but does not block you from marking `done`; `/architect` still records any load bearing decision, the one thing the workflow asks. A feature's own tier tag overrides the default.
- **Pointer line** (`spec <n> · code in <path>`): the spec link added by `/architect`, the code path by `/develop`.
