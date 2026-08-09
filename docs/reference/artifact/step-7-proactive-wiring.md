# Step 7: Optional proactive wiring

_Step 7 of the third party mounting walk. Status: design note, not yet in scope. Exported from a design conversation on 2026-08-09; `docs/scope/scope.md` has no row for this yet._

## What this step is

The piece that moves agents from *only querying when told* to *consulting decision-memory by default*. It is a small, plain set of instructions — either a paragraph in `AGENTS.md` or a proper `SKILL.md` — that tells an agent **when** to run `dm_query`, and **what to do with the answer**.

That is the whole thing: no code, no fork dependency, no new interface. It works because decision-memory's real interface (the MCP server / CLI) is already harness neutral; this step is just the trigger that makes agents *use* it.

It is optional. It comes after the core mounting steps (install, `doctor`, adapter, `adapt`, `query`, MCP registration) and adds the habit layer on top.

## Goal

Turn decision-memory from "a tool I run" into "memory the pipeline consults." A third party that does only steps 1 through 6 can query on demand. Adding step 7 means their agents pause and check the recorded decision history before relitigating a decision or making a decision shaped call — without any change to decision-memory itself.

## The two shapes

| Shape | What it is | Pros | Cons |
|---|---|---|---|
| **Note** (a `decision-memory.md` referenced from `AGENTS.md`) | A few lines of convention | Zero dependency, any repo can drop it in | Passive: the agent only reads it if it reads `AGENTS.md` |
| **Skill** (a `SKILL.md` in `.agents/skills/`) | A first class Agent Skills entry with frontmatter | Discoverable, nameable, surfaced in the client UI, works on any Agent Skills client | One more file to install |

For a third party, the note is the honest minimum and the skill is the nice default. Both are harness agnostic: neither references `/architect` or `/develop`. If the third party happens to use the jsmastery style skills pipeline, its skills can reference the same convention; the coupling lives in *their* choice, never in decision-memory.

## What the content says

Three rules do almost all the work.

### 1. When to query (the triggers)

Keep it cheap: do not query for every micro task. Query when a decision shaped question is on the table:

- Before choosing something that smells settled: a stack, a data model, an API shape, a provider, an alternative about to be relitigated.
- When the task is "why is this built this way."
- At the start of work in an area that likely has recorded decisions.
- When a plan or spec proposes something that might contradict an existing record.

### 2. What to call

`dm_query "<the question>"` — or `dm_search_records` / `dm_get_record` when the agent needs raw detail.

### 3. What to do with the answer (the protocol)

- **A cited answer**: surface the citation, do not silently absorb it. If it contradicts the plan, pause and surface the conflict to the human. The agent neither complies blindly nor ignores it silently.
- **"Not enough evidence"**: treat as genuinely unknown. The agent says so instead of inventing a justification — the exact failure mode decision-memory exists to prevent.
- **Superseded record**: report it as superseded, never present it as current ("confident and wrong at the same time" otherwise).

## Etiquette that makes it safe

- **Advisory, not a gate.** A `dm_query` result is a reason to pause, never a hard block. The human overrides; the record is memory, not law.
- **Stay read only.** The convention only ever triggers queries. It never prompts an agent to write to decision-memory; adapters and capture own that and are separate.
- **Abstention is first class.** The convention tells the agent what to do when there is no evidence, rather than letting it fall back to guessing.

## The thin version (example)

```markdown
# decision-memory.md

Before relitigating a decision or proposing a new stack, schema, or API
shape, run `dm_query "<the question>"` against the project's decision memory.

- Cited answer: use it, preserve the citation, and if it contradicts the
  plan, stop and raise the conflict rather than ignoring it.
- "Not enough evidence": say so; do not invent a rationale.
- Superseded decision: report it as superseded, never as current.

This file is a convention. It is not a gate: a human can override any
recorded decision. It is read only: never write to decision memory.
```

The `SKILL.md` version is the same body with frontmatter on top (`name`, `description`, `allowed-tools: Bash, Read`) so it is a discoverable, installable skill.

## Where it fits

Step 7 is what turns decision-memory from "a tool I run" into "memory the pipeline consults." It is the same move the skills fork makes with its added skills, but inverted: instead of a harness's skills being the interface, the convention is a thin plug any harness can attach.

For the decision-memory project itself, this is the natural future companion to the MCP server (feature 14): the MCP server gives third parties the *capability*; step 7 gives them the *habit*.

## Status

Not in scope. `docs/scope/scope.md` has no row for third party proactive wiring. If pursued, it should be enrolled as a feature via `/scope` and designed via `/architect` before any implementation.
