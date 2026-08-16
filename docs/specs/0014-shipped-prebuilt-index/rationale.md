# 0014. Rationale: ship a prebuilt index of this repository's own decision records

Reasoning, options, and the measurements behind [index.md](index.md).

## Context

> ⚠️ Premise note: the goal is written as "a first question in about two minutes", and
> this feature does not control most of those two minutes. It removes `adapt` and
> `ingest`, which together take seconds and a fraction of a cent. What remains before a
> reader's first answer is `git clone`, `uv sync` (which resolves and downloads chromadb,
> openai, and tiktoken), setting a key, and one query that makes several provider calls.
> The dependency install dominates and this spec cannot shorten it. The claim the feature
> can actually keep is **no corpus setup**: a real cited answer with nothing to prepare,
> whatever the reader's own project looks like. The documentation in AC-16 should promise
> that, not a stopwatch figure, because a wall clock claim is the kind that quietly
> becomes false on a slow network and makes a reader distrust the rest of the page.

The project's front door asks a reader to do work before it shows them anything. The
README's quickstart points the tool at the reader's own project, and the adapter reads
one specific directory shape, so the most common outcome for a new reader is `doctor`
reporting that their corpus does not fit. That is a dead end at step two, and it happens
before the reader has seen a single cited answer. The thing the project is trying to
demonstrate, that decision history can be queried and the answer checked against its
source, never gets demonstrated.

This repository is itself a corpus. Its decisions live in `docs/specs/` in exactly the
shape the built in adapter reads, so it can answer questions about its own construction.
Making that available without setup turns the front door into a demonstration rather than
a form to fill in. It also serves a reader who never intends to use the tool on their own
project and only wants to judge whether the idea works.

Three forces constrain how this can be done. The index is a binary of roughly 7MB and
regenerating it produces an entirely fresh binary, so anything committed is paid for
permanently in git history. The pipeline signature is hashed into the store and compared
before any question is embedded, so an index built under different chunking or embedding
settings is refused rather than silently misread; that protects a reader but it also means
a shipped index rots the moment the pipeline changes. And a store built today records the
absolute paths of the machine that built it, which is fine for a local artifact and is not
fine for one that ships.

That last force turned out to be the load bearing one, and it was not visible from the
scope row. The index stores `records_manifest_path`, and query loads the manifest back
from that stored path to compare digests (`cli.py:766-774`, `query.py:1360-1374`). The
value in this repository's store is
`/Users/ghaly/Documents/Work/Personal/decision-memory/.decision-memory/records/manifest.json`.
On anyone else's clone that path does not exist, so `load_manifest` raises,
`_manifest_freshness` returns `UNKNOWN`, and `query.py:319` refuses the question with
`stale.refused` unless the reader passes `--allow-stale`. A committed index with no other
change gives every new reader a staleness error about an index that is perfectly fresh.
The same field's neighbour, `source_root_hint`, drives citation source resolution
(`source_resolver.py:43-60`), so a stale value there degrades every citation to `MISSING`
and an empty one degrades them to `HINT_UNAVAILABLE`. Both fields also publish the
author's home directory path inside a binary going to strangers.

## Options considered

### Option 1: Commit the index at the default path and document `--allow-stale`

Un ignore `.decision-memory/`, commit what is already there, and tell readers in the
README to pass `--allow-stale` on their first question.

**Pros**

- Almost no code. The artifact already exists on disk in the right shape.
- Query finds it with no flag, since `.decision-memory/query-index` is the default store
  location resolved from the git root.

**Cons**

- Every reader's first interaction is an error message that is not true, followed by
  instructions to override a safety check. That is the opposite of the impression the
  feature exists to make.
- It teaches `--allow-stale` as a normal flag, which weakens a guard that exists for a
  real reason.
- The committed artifact sits at the same path a contributor's own `ingest` writes to, so
  ordinary use overwrites it and leaves a 7MB unintended diff.
- The author's absolute paths ship inside the binary and stay in history.

### Option 2: Make the store self describing (a format change)

Change ingest to record the manifest path and corpus root relative to the store, bump the
store format, and resolve them on read.

**Pros**

- Fixes the defect at its source for every store, not only shipped ones. No companion file
  and no fallback chain.
- The cleanest end state: a store that can be moved anywhere and still explains itself.

**Cons**

- It is a store format change, and every existing local index must be rebuilt to gain it,
  including the ones the evaluation baselines were measured against.
- It lands while feature 15 is mid build against the current shapes.
- It is a large blast radius for what is, in this feature, a packaging problem.

### Option 3: Distinct path, blanked absolute fields, resolution through a committed snapshot

Commit the bundle at `examples/self-index/`; have the regeneration script write both
absolute fields empty; and resolve the records directory and corpus root at read time from
a `snapshot.json` in the bundle, falling back to the existing convention when no snapshot
is present.

**Pros**

- Nothing absolute ships, so the disclosure problem is removed by construction rather than
  patched.
- The read time fallback fixes the general moved or copied store case for everyone, not
  only for the demo.
- The snapshot file answers a second question the feature needs anyway: where the corpus
  was frozen, which the README and a later MCP tool description must state.
- The bundle sits away from `.decision-memory/`, so a contributor's own `adapt` and
  `ingest` never touch it.
- No store format change, so no existing index is invalidated and feature 15 is undisturbed.

**Cons**

- Location lives in a companion file rather than in the store, which is a weaker property
  than option 2 offers.
- It introduces a new small file format that has to be versioned and read defensively.
- Blanking `records_manifest_path` is only safe **because** the snapshot resolves it. Blank
  without resolution reproduces option 1's failure by a different route.

### Option 4: Publish the index as a release asset and fetch it on demand

Keep git history clean by attaching the bundle to a GitHub release and adding a fetch step.

**Pros**

- No binary in the repository at all, so history never grows and the index can be replaced
  without a commit.
- Allows shipping a much larger corpus later without a repository cost.

**Cons**

- Adds a network dependency and a download code path to the very flow this feature exists
  to shorten.
- A reader offline, behind a proxy, or on a fork without the release gets a failure that
  has nothing to do with the product.
- More surface to build and test than the whole rest of this feature.

## Rationale

Option 3 is chosen because the two problems that actually block a shipped index, the baked
absolute paths and the collision with a contributor's own store, are both solved by it
without touching anything feature 15 depends on. Option 2 solves the first problem more
elegantly and was rejected on blast radius: rebuilding every existing store, including the
evaluation baselines, to fix a path portability defect is disproportionate, and doing it
during another feature's build is worse. The promotion path stays open and is recorded as a
follow up bound to the next format change that happens for its own reasons.

Option 1 was rejected on the first impression, which is the entire point of the feature. A
reader who is told to pass `--allow-stale` before their first question has learned that the
tool's freshness reporting cannot be trusted, which is a strange lesson from a project whose
pitch is honest answers. Option 4 was rejected because it reintroduces a step into the flow
being shortened, and because a network failure would be indistinguishable, to a new reader,
from the product not working.

Two choices inside option 3 deserve their reasons recorded. **Blanking rather than
relativising** the two fields: an empty value is checkable and already has defined behaviour
(`source_root_hint` defaults to empty at `adapter.py:169`), whereas a relative string in a
field documented as absolute produces a subtly wrong path in any reader that does not know
about the convention, and wrong is worse than absent. **Sealing was rejected outright**: a
marker that tells freshness to skip the manifest comparison would make the demo work by
switching off the one guard protecting a stranger's first query, and this project has
repeatedly refused to weaken a check to obtain a green result.

The integration smoke test was argued for on this project's own history rather than on
principle. The unit guard proves the artifact's metadata agrees with itself, and
`docs/session-notes.md` records a store that reached exactly that state while being broken:
the writer reported the records fine and the reader rejected their digests, unrecoverable by
any documented remedy and fixed only by deleting the store. Metadata agreement is precisely
what was intact in that incident, so a committed binary going to strangers is the last place
to treat signature plus digest as proof that it answers.

The characterisation requirement (AC-13) exists because a naive smoke test here would be
flaky and then muted. Measured on a clean clone, the same question answered in two runs of
three and abstained in the third. What makes a pinned assertion tractable is that the shipped
index is frozen, so a question's behaviour against it can be measured once and held, which is
not true of the live corpus. Recording the observed counts turns a future flake into drift
from a baseline rather than an open investigation, a distinction that has repeatedly been the
difference between a one command answer and several rounds of digging on this project.

Finally, the regeneration policy (AC-15) is stated as a criterion rather than left to habit
because the cost structure invites the wrong habit. A rebuild is cheap in money and slow in
history: roughly 7MB added permanently, every time. Without a stated policy, "regenerate the
demo index" becomes a reflex attached to unrelated commits and the repository grows for
nothing. The corresponding decision not to automate drift detection follows from the same
place: a test that failed whenever a spec was added would force a rebuild on every
`/architect` run, which is exactly the routine regeneration the policy forbids.

## Measurements taken while designing this

All figures were taken from this repository on 2026-08-15 rather than estimated.

| Fact | Value | How it was obtained |
|---|---|---|
| Store size | 7.1MB total: 6.7MB index (4.7MB Chroma, 2.0MB records database), 404K records | `du -sh` on `.decision-memory/` |
| Stored manifest path | `/Users/ghaly/Documents/.../records/manifest.json` | direct query of `index_metadata` in the store |
| Stored source root hint | the same absolute repository root | same query |
| Absolute paths inside the Chroma database | none found | string scan of `chroma.sqlite3` |
| Records a fresh adapt writes | 10, from 13 spec directories | `adapt` run to a scratch directory |
| Specs absent and why | 0001 and 0002 are flat files the adapter does not read; 0009 contains only `verify.md` | the same run, plus listing `docs/specs/0009-*/` |
| Query exit code with no API key | 1, correct | running query with the key unset |
| Query message with no API key | `error embedding provider.embedding: OpenAIClientError`, does not name the key | same run |
| Lock database creation | bootstrapped on first use inside the store directory | `index_lock.py:30-49` |
| `.gitignore` patterns blocking the bundle | `*.sqlite3` (line 93) and `*.bin` (line 80) | `git check-ignore -v` against every real file the store produces |
| Files a bundle actually contains | `ACTIVE`, `FORMAT`, `generations/<uuid>/{generation.json, records.sqlite3, chroma/chroma.sqlite3, chroma/<uuid>/{data_level0,header,length,link_lists}.bin}` | listing the real store |
| Directory names that change every run | two: the generation id and the Chroma collection id, both fresh UUIDs | `store.py:71-73` and the listing above |

The last three rows are why AC-8 exists, and an earlier draft of this table got them
wrong in a way worth recording. `*.sqlite3` ignores both the Chroma database and the
records database wherever they sit, and **`*.bin`, which sits under a "Local model
weights" heading and looks irrelevant, ignores the four HNSW segment files that are the
vector index itself**. A negation set written from the obvious pattern alone would commit
a bundle that looks complete, passes a signature check, and cannot load its vectors.

The earlier draft also named a bare `index/` (line 73) as a blocking pattern. That is
wrong: gitignore matches whole path components, so `index/` matches a directory named
exactly `index` and does not match `query-index`. The mistake came from probing with a
candidate path that happened to contain a literal `index` component, which matched for a
reason that would not apply to the chosen layout. Recorded rather than quietly corrected,
because the general lesson is the durable part: a `git check-ignore` probe proves
something only about the exact path probed.

## References

**Project sources**

- `AGENTS.md`, the Clean Architecture layering rules and the Skateboard build approach
- Spec 0007, the pipeline signature and its immutability contract
- Spec 0013, the frozen eight command CLI surface and the hint table owning the missing key
  message
- `docs/session-notes.md`, the 2026-08-12 store incident where writer and reader disagreed
  about the same records
- Scope feature 22 and its Slice 4 placement note

**Practices and standards**

- Atomic publish through build then swap, so a failed run cannot leave a partially written
  artifact in place
- Characterising a nondeterministic assertion before pinning it, rather than muting it after
  it flakes
- Removing a class of disclosure at the write side rather than filtering it at the read side
