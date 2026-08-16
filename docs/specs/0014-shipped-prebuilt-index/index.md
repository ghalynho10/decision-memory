# 0014. Ship a prebuilt index of this repository's own decision records

**Date**: 2026-08-15
**Status**: Proposed

## Summary

Commit a ready built query index of this project's own decision records, so a new
reader asks a real cited question without adapting or ingesting anything first.
Today the shortest path to a first answer is clone, install, set a key, `adapt`,
`ingest`, `query`; this removes the two middle steps for everyone. The index is a
binary of roughly 7MB, committed deliberately, refreshed by a script rather than by
hand, and guarded by a test that fails when the committed artifact stops matching the
pipeline that reads it. Getting there needs one real fix underneath: a store today
records the absolute path of the machine that built it, so a shipped store must stop
doing that and must still resolve correctly on someone else's clone.

## Requirements

**User stories**:

- As someone evaluating this project, I want to ask it a real question about its own
  decisions with no corpus to prepare, so I can judge whether cited answers work before
  investing in setting up my own. (Deliberately not a wall clock promise; see the premise
  note in `rationale.md`.)
- As someone reading a cited answer from the shipped index, I want the citations to
  point at files in my own checkout, so I can open the source and check the claim.
- As the maintainer, I want the committed index to fail the build the moment it stops
  matching the current pipeline, so a stranger never meets a rotted artifact.
- As the maintainer, I want regenerating the index to be one command that cannot leave
  a half built store behind.

**Acceptance criteria** (the contract, each criterion is IDed and independently checkable):

*Resolution and portability*

- **AC-1**: When a store's `records_manifest_path` is empty or names a path that does
  not exist, resolution reads `snapshot.json` from the bundle root and derives the
  records directory and the corpus root from its relative fields, resolved against the
  snapshot file's own location. The resolved manifest path feeds the freshness
  computation **before** the `UNKNOWN` branch, so a shipped store is classified on its
  real manifest rather than on the absence of a stored path.
- **AC-1a**: The fallback lives inside `SqliteChromaIndexReader.manifest_metadata()`, so
  every caller of it gets resolved values without its own wiring.
  `query_index` reads that method directly rather than through an injectable closure
  (`query.py:294-296`), so resolution placed anywhere else would not reach the
  classification it must reach. The four stored path closures currently duplicated
  between `cli.py:766-783` and `evaluation_runner.py:160-179` are replaced by one shared
  helper reading the resolved values, so `query` and `evaluate` behave identically on a
  relocated or shipped store.
- **AC-1b**: A `snapshot.json` that is missing, unreadable, not valid JSON, carries an
  unrecognised `schema_version`, or fails structural validation of any required field is
  treated exactly as absent: resolution falls back to the convention and never raises
  into the query path. One rule, no partial acceptance.
- **AC-1c**: The corpus root has a convention fallback as well as a snapshot one. When
  neither a usable stored hint nor a snapshot is available, the corpus root resolves to
  `store_dir.parent.parent`, which is the real corpus root for the default
  `<root>/.decision-memory/query-index` layout. This makes citation resolution survive a
  relocated ordinary store, not only a shipped bundle.
- **AC-2**: A shipped bundle on a fresh clone at any absolute path reports freshness
  `CURRENT` and answers a question with no `--allow-stale` flag.
- **AC-3**: A store built normally and then copied to a different absolute path
  resolves its manifest and reports `CURRENT`.
- **AC-4**: A store copied to a location where a **different** corpus's manifest sits
  at the conventional place reports `DRIFT`, not `CURRENT`. Resolution must not turn a
  real mismatch into a pass.
- **AC-5**: Citations in an answer from the shipped bundle resolve to real files in the
  reader's own checkout (`ResolutionState.RESOLVED`), not `MISSING` and not
  `HINT_UNAVAILABLE`.

*The committed artifact*

- **AC-6**: The shipped store contains no absolute filesystem path.
  `records_manifest_path` and `source_root_hint` are written empty in the shipped
  store, and a test reads every column of the shipped store's `index_metadata` row and
  asserts each string value is empty or fails `Path(value).is_absolute()`, and
  additionally carries no leading `/` and no Windows drive prefix, so the check does not
  depend on the platform the test runs on.
- **AC-7**: The committed bundle is `examples/self-index/`, containing `records/` (the
  canonical records and `manifest.json`), `query-index/` (the index itself), and
  `snapshot.json` at the bundle root. `lock.sqlite3` is not committed.
- **AC-8**: Every file the bundle needs is tracked, and this is proved by a check rather
  than assumed. Three existing patterns collide with it and all three must be handled:
  `*.sqlite3` (line 93) catches `records.sqlite3` and `chroma.sqlite3`, and **`*.bin`
  (line 80) catches `data_level0.bin`, `header.bin`, `length.bin`, and `link_lists.bin`,
  which are the HNSW vector segments, meaning the actual vector index**. The negations
  must be **wildcarded across two randomly named directory levels**, the generation id
  and the Chroma collection id, both fresh UUIDs on every regeneration
  (`store.py:71-73`), so no negation may name a fixed generation path. The existing
  patterns keep applying everywhere outside the bundle, and
  `examples/self-index/query-index/lock.sqlite3` stays ignored so asking a question never
  dirties the working tree. A test asserts that the set of files the script produced and
  the set of files git tracks under the bundle are equal, except the lock database.

*The guard*

- **AC-9**: A test in the default (no API key) suite asserts that the committed store's
  stored pipeline signature equals `pipeline_signature()`, that its stored semantic
  manifest digest equals the digest computed from the committed `manifest.json`, and
  that `snapshot.json` parses and passes the same structural validation the reader
  applies. It runs on every push, so a pipeline change, a records and index pair that
  drifted apart, and a corrupted snapshot each fail the build rather than silently
  degrading a reader's answer. When the bundle is absent entirely, which is the case in
  a source tarball or a sparse checkout, the test skips with a stated reason rather than
  failing, because a missing bundle is not a broken one.
- **AC-10**: A test marked `integration` asks the pinned answered question against the
  committed bundle and asserts a cited answer whose citations resolve, and asks the
  pinned abstention question and asserts the honest no evidence response.

*Regeneration*

- **AC-11**: `scripts/regenerate-self-index.py` builds the new bundle in a temporary
  directory and swaps it into place only after every check passes. **The committed
  bundle is never left partially written.** The guarantee is stated precisely because a
  stronger one is not achievable: the target always exists and is not empty, and a POSIX
  rename cannot replace a non empty directory, so the swap is two renames (old aside,
  new into place, old deleted). A process killed between them leaves the bundle briefly
  absent rather than corrupt. That state is detectable, is repaired by rerunning the
  script, and `git status` makes it obvious. The script detects a leftover set aside
  directory on startup and completes or rolls back that interrupted swap before doing
  anything else.
- **AC-12**: The script writes `snapshot.json` with the fields in Feature design, every
  path field relative to the snapshot file's own directory, and no absolute path
  anywhere in the file.
- **AC-13**: The script runs each candidate question against the newly built index ten
  times and refuses to publish unless every run produced **the same disposition**, that
  is answered versus abstained, as the question's `expected` value. Disposition only:
  answer text and citation sets are expected to vary between runs and are never compared.
  The observed counts are recorded beside each question in `snapshot.json`, so a later
  flake reads as drift from a measured baseline rather than as a mystery.
- **AC-14**: The script reports how many spec directories under `docs/specs/` are absent
  from the shipped manifest, and reports rather than fails. Nothing in the test suite
  fails because the corpus moved on.
- **AC-15**: Regeneration happens only when the pipeline signature changes or the corpus
  changes materially. The policy is stated in the script's own help output and in
  `AGENTS.md`, and no automated check exists that would force a routine rebuild.

*Documentation*

- **AC-16**: The README opens its quickstart with the shipped bundle question, and the
  install and own corpus path follows it. The demo section states the snapshot's freeze
  point (commit and date) and that answers cover the corpus as of that point.

## Decision

**Chosen option**: Option 3: Commit the bundle at a distinct path, blank the absolute
fields, and resolve through a committed snapshot file.

Ship `examples/self-index/` as a committed bundle of records plus index plus a
`snapshot.json` that carries both the layout resolution needs and the freeze point the
documentation cites; write the store's two absolute fields empty so no machine path
leaves this machine; and resolve the manifest and corpus root at read time from the
snapshot, falling back to the existing convention when there is no snapshot.

**Implementation skills**: none; this decision rests on the project's own conventions
in `AGENTS.md` rather than on an installed community skill.

## Feature design

**Data model sketch**

The only new persisted artifact is the snapshot file. It is a plain JSON document at
the bundle root, and every path in it is relative to that file's own directory so the
bundle is position independent.

The bundle's real on disk shape matters for AC-8 and is not flat. Under
`query-index/` sit `ACTIVE`, `FORMAT`, and `generations/<generation-uuid>/` holding
`generation.json`, `records.sqlite3`, and `chroma/` which in turn holds
`chroma.sqlite3` plus `<collection-uuid>/` with the four `.bin` HNSW segments. Both
UUID levels are regenerated on every run, so nothing may be committed or ignored by a
fixed generation path.

`examples/self-index/snapshot.json`

| Field | Type | Required | Meaning |
|---|---|---|---|
| `schema_version` | int | yes | Fixed at 1. A reader that does not recognise the value ignores the file and falls back to the convention. |
| `generated_at` | string (ISO 8601 UTC) | yes | When the script built this bundle. |
| `commit` | string | yes | The short commit the corpus was read at. The freeze point the README cites. |
| `pipeline_signature` | string | yes | The signature the index was built under. Informative; the guard reads the store, not this file. |
| `records_dir` | string (relative) | yes | Where the canonical records and their manifest live. `records`. |
| `store_dir` | string (relative) | yes | Where the index lives. `query-index`. |
| `corpus_root` | string (relative) | yes | The root the records' `contributing_files` are relative to. `../..`, the clone root. |
| `records_indexed` | int | yes | Count of manifest entries in the bundle. |
| `specs_at_freeze` | int | yes | Count of spec directories under `docs/specs/` at the freeze commit. Legitimately larger than `records_indexed`; see Key invariants. |
| `demo_questions` | array | yes | The pinned questions, below. |

Each `demo_questions` entry:

| Field | Type | Meaning |
|---|---|---|
| `question` | string | The exact question text the integration test asks. |
| `expected` | `"answered"` or `"abstained"` | The behaviour pinned for this question. |
| `runs` | int | How many characterisation runs were made. Ten. |
| `stable` | int | How many of those runs matched `expected`. Must equal `runs` to publish. |

**State transitions**

The bundle has three states and the script is the only thing that moves it between them.

`current` (the guard passes and the pipeline signature matches) → `incompatible` (the
pipeline changed underneath it; the unit guard fails the build and query refuses)
→ `current` again, only through a full regeneration. There is no in place repair and
no partial state, because AC-11 makes the swap atomic. A fourth state, `behind the
corpus` (specs exist that the bundle never saw), is deliberately **not** a failure: the
records and index are frozen together, so freshness still reads `CURRENT` and the
bundle honestly answers about the corpus at its freeze point.

**Interface surface**

There is no HTTP surface. The surfaces this feature adds or changes:

| Surface | Form | Key inputs | Key outputs | Key failures |
|---|---|---|---|---|
| `scripts/regenerate-self-index.py` | `uv run --env-file .env python scripts/regenerate-self-index.py` | optional `--bundle PATH` (default `examples/self-index`), optional `--runs N` (default 10) | rewritten bundle, printed report of records written, specs absent, and per question stability | no `OPENAI_API_KEY`; a candidate question unstable across runs; any check failing before the swap, all of which leave the bundle untouched |
| `snapshot_layout(bundle_root)` | new function, infrastructure | the bundle root path | resolved records dir, manifest path, corpus root | a missing, unreadable, or unrecognised `schema_version` file returns nothing and the caller falls back to the convention |
| the demo command | `uv run decision-memory query "<question>" --store examples/self-index/query-index` | existing flags only | existing query output | existing failures only; the missing key message is spec 0013's to fix |

No new CLI command is added. Spec 0013 freezes the command list at eight while feature
15 is mid build, and a maintainer tool has no reason to sit in a user facing CLI.

**Value sourcing**

| Action | Value produced or displayed | Source |
|---|---|---|
| regenerate | `commit` | `git rev-parse --short HEAD` at script run |
| regenerate | `generated_at` | the script's own UTC clock at run |
| regenerate | `pipeline_signature` | `pipeline_signature()` from `application/pipeline.py` |
| regenerate | `records_indexed` | count of `entries` in the freshly written `manifest.json` |
| regenerate | `specs_at_freeze` | count of directories under `docs/specs/` at run time |
| regenerate | `stable` and `runs` | measured, N executions of the query use case against the newly built index |
| regenerate | "specs absent from the bundle" report | the spec directory set minus the manifest's contributing file roots |
| query, shipped bundle | the records manifest path | `snapshot.records_dir` resolved against the snapshot file's directory, because the stored field is empty by AC-6 |
| query, shipped bundle | the corpus root for citation resolution | `snapshot.corpus_root` resolved against the snapshot file's directory, for the same reason |
| query, shipped bundle | the semantic manifest digest compared for freshness | computed from the committed `manifest.json` reached through the path above |
| query, any relocated store | the records manifest path | the stored absolute path when it exists, else the snapshot, else `store_dir.parent / "records" / "manifest.json"` |
| query, any relocated store | the corpus root for citation resolution | the stored hint when it exists, else the snapshot, else `store_dir.parent.parent` (AC-1c), which is the real corpus root for the default layout |
| any read | the bundle root the snapshot is looked for in | `store_dir.parent`, the directory holding both `records/` and `query-index/` |
| unit guard | the expected pipeline signature | `pipeline_signature()`, computed live, never a constant copied into the test |
| README demo section | the freeze point shown to a reader | `snapshot.commit` and `snapshot.generated_at` |

**Key invariants**

- The shipped store holds no absolute path. Anything a reader needs about location comes
  from the snapshot, relative to itself.
- The records and the index in a bundle are always written by the same script run, so
  their digests agree by construction rather than by discipline.
- Resolution never converts a mismatch into a pass: a manifest found by fallback is
  digest compared exactly as a manifest found by the stored path is (AC-4).
- `records_indexed` may be smaller than `specs_at_freeze` and that is not a defect. As
  of this spec a fresh adapt over this repository writes 10 records from 13 specs:
  0001 and 0002 are flat single file specs the adapter does not read yet (scope feature
  12 owns that), and 0009 has no `index.md` at all. The script reports the gap so a
  human can tell an expected absence from a new one.
- The bundle answers about the corpus as of its freeze commit, not as of the reader's
  checkout. Nothing in the code hides this, so the documentation must state it.

**Security model**

No authentication or authorization surface: the bundle is public, read only in normal
use, and holds only content already public in this repository. The one real concern is
information disclosure, and it is the reason for AC-6: a store built today records the
building machine's absolute paths, including a home directory, and committing that
would publish it permanently in git history. Writing both fields empty removes the
class rather than the instance. No regulated data is involved, so no compliance scope
applies and no audit logging is warranted.

**Configuration required**

No new environment variables. `OPENAI_API_KEY` is already required and is needed twice
here: by the regeneration script (embedding the corpus, then the characterisation runs)
and by anyone asking the demo question, since query embeds the question. There is no
key free path and this spec does not attempt to invent one.

**Critical test scenarios**

- Happy path: a clone at an arbitrary absolute path queries the committed bundle with no
  flags beyond `--store` and receives a cited answer whose citations resolve to files in
  that clone, verifies **AC-2**, **AC-5**.
- Guard: mutating any pipeline constant makes the default suite fail on the committed
  bundle, with no API key present, verifies **AC-9**.
- Failure case: a store copied next to a different corpus's manifest reports `DRIFT`
  rather than passing, verifies **AC-4**.
- Failure case: killing the regeneration script partway leaves the committed bundle byte
  identical, verifies **AC-11**.
- Failure case: a candidate question that behaves inconsistently across the ten
  characterisation runs stops the script from publishing, verifies **AC-13**.
- Failure case: a `snapshot.json` that is valid JSON and version 1 but missing a required
  field is treated as absent by the reader, and fails the unit guard rather than silently
  degrading citations, verifies **AC-1b**, **AC-9**.
- Consistency: `evaluate` and `query` resolve the same relocated store identically, so
  the shared helper cannot drift back into two behaviours, verifies **AC-1a**.
- Packaging: the set of files the script produced under the bundle equals the set git
  tracks there, except the lock database, which catches a missed `.bin` or a negation
  written against a stale generation id, verifies **AC-8**.
- Disclosure: the committed store's metadata row contains no absolute path, verifies
  **AC-6**.
- Honest miss: the pinned out of corpus question abstains rather than inventing an
  answer, verifies **AC-10**.

## Build plan

Skateboard, so the ordering delivers the thinnest thing a person can actually use, then
hardens it. The read side fix comes first because nothing else works without it, and the
script comes before the committed artifact so the bundle in git is the script's output
rather than something handmade that the script might not reproduce.

1. Add `snapshot.json` reading: the schema, `snapshot_layout(bundle_root)`, its strict
   validate or treat as absent rule, and the fallback order (stored path when it exists,
   then snapshot, then convention). Unit tested against fixtures with no store involved,
   satisfies **AC-1**, **AC-1b**, **AC-12**.
2. Move the fallback inside `SqliteChromaIndexReader.manifest_metadata()` so the resolved
   manifest path and corpus root reach the freshness classification that reads it
   directly, and add the corpus root convention fallback. Replace the four duplicated
   stored path closures in `cli.py` and `evaluation_runner.py` with one shared helper, so
   `query` and `evaluate` cannot diverge. Cover the relocation and the wrong corpus
   cases, satisfies **AC-1**, **AC-1a**, **AC-1c**, **AC-3**, **AC-4**, **AC-5**.
3. Write `scripts/regenerate-self-index.py`: adapt, ingest, blank the two absolute
   fields, write the snapshot, build in a temporary directory, recover any interrupted
   previous swap on startup, and swap only at the end, satisfies **AC-6**, **AC-11**,
   **AC-12**.
4. Add characterisation and reporting to the script: N runs per candidate question,
   refuse to publish on any instability, report specs absent from the bundle, satisfies
   **AC-13**, **AC-14**.
5. Run the script, add the `.gitignore` negations, and commit the bundle at
   `examples/self-index/`, satisfies **AC-2**, **AC-7**, **AC-8**.
6. Add the unit guard over the committed bundle to the default suite, satisfies **AC-9**.
7. Add the integration smoke test using the pinned questions from the snapshot, including
   the clean checkout case that asks with no `--allow-stale`, satisfies **AC-2**,
   **AC-10**.
8. Rewrite the README quickstart to lead with the demo, state the freeze point, and keep
   the install and own corpus path directly after it; record the regeneration policy in
   `AGENTS.md` and the script's help, satisfies **AC-15**, **AC-16**.

## Consequences

**Positive**

- The shortest path to a real cited answer stops depending on the reader having a corpus
  in the supported format, which most readers do not.
- The portability fix is not demo only. Any store that is moved, copied, or restored from
  a backup resolves afterwards, both its freshness and its citations, which was broken
  before and silently so. Freshness is fixed by the manifest fallback and citations by the
  corpus root fallback in AC-1c; without that second half a relocated store would have
  reported `CURRENT` while every citation degraded to `MISSING`, which is the more
  dangerous of the two failures because it looks like success.
- `query` and `evaluate` stop being able to diverge on store resolution, since the two
  copies of the same four closures collapse into one helper.
- A class of information disclosure goes away: no store this project ships can carry a
  machine path.
- The measured stability of the pinned questions is recorded in a file rather than in
  someone's memory, so a later flake is answerable in one command.

**Negative and tradeoffs**

- Git history grows by roughly 7MB per regeneration, permanently. New embeddings are a
  fresh binary and do not delta compress, so this cost is paid in full each time. It is
  accepted on the basis that the pipeline signature makes regeneration deliberate and
  rare, and AC-15 forbids routine rebuilds.
- The bundle is a second copy of decisions that already live in `docs/specs/`, and it
  goes out of date by design. Anyone asking about a spec written after the freeze gets
  nothing, which is why AC-16 makes the freeze point visible where the question is asked.
- Reading location from a companion file is weaker than a store that describes itself.
  This is a deliberate deferral, not an oversight: making it a store property is a format
  change, and feature 15 is mid build.
- The regeneration script costs real money and real time each run: one embedding pass over
  the corpus plus twenty full query executions for characterisation, each of which calls
  the provider several times.
- The demo's most likely first failure, a missing API key, is not fixed here. Spec 0013
  owns that message and its hint. Until feature 15 lands, a reader without a key sees
  `error embedding provider.embedding: OpenAIClientError`, which does not name the key.

**Neutral**

- `examples/` gains a second entry beside `starter-adapter/`, consistent with it: both
  exist to be shown rather than run.
- `scripts/` is a new directory. It is deliberately not `docs/experiments/data/`, which
  holds measurement instruments tied to numbered experiments; a regeneration tool is
  maintainer tooling and not a measurement, and mixing the two would blur what that
  directory means.
- Contributors who run `adapt` and `ingest` in a clone still write to `.decision-memory/`
  as before. The bundle is untouched by ordinary use, which is why it is not at the
  default path.

## Follow-up

- [ ] A `store` key in `.decision-memory.yml`. The config accepts `adapter`,
      `corpus_root`, and `output` only, so nothing can point `query` at a bundle without
      a flag. The README's own corpus path already repeats `--store` across two commands,
      so the value is not specific to this feature. Its own small decision.
- [ ] Spec 0009 has no `index.md`, only `verify.md`, so the evaluation harness decision is
      absent from the corpus entirely and the shipped bundle cannot answer about it. Worth
      fixing at the source rather than working around here.
- [ ] Consider promoting the snapshot's layout fields into the store itself once the
      format is free to change, which would make every store self describing and retire
      the fallback chain. Bound to the next store format change that happens for an
      independent reason.
- [ ] Both stored path fields become empty for shipped stores under AC-6, and neither
      says so where it is defined. `source_root_hint` is documented as absolute at
      `adapter.py:161`; `records_manifest_path` has no such docstring and is simply
      written absolute at `ingest.py:226` via `.resolve()`, declared at `dto.py:453` and
      `sqlite_store.py:34`. Both should state the empty case, and a later change may want
      a proper nullable type rather than an empty string sentinel.

## Rationale

Reasoning, the options weighed, and the measurements behind them: see
[rationale.md](rationale.md).
