# 0003. jsmastery specs adapter

**Date**: 2026-08-08
**Status**: In Progress

## Summary

This decision defines the adapter that reads a project's jsmastery style spec folders and turns each one into a canonical decision record, the format fixed by spec 0002. It settles which files feed a record, how every canonical field maps to a section of those files, and what happens when a source is degraded or unreadable. The adapter never invents a value: anything it tried to fill and could not is flagged as a warning, and anything it cannot map at all is skipped with a stated reason.

It also adds a command, `adapt`, that runs the conversion against a real corpus and writes the records to disk, so a person can see the result before any of it is embedded. A fingerprint per record makes a second run rewrite only what actually changed, which is what feature 5 needs to avoid re embedding a whole corpus on every edit.

## Requirements

**User stories**:
- As a person evaluating this tool, I want to run one command against a real project's specs and inspect the records it produces, so that I can judge the corpus before anything is embedded.
- As the ingestion slice, I want a stable fingerprint per record, so that I re embed only what changed.
- As a maintainer, I want every degraded or skipped source reported with a reason, so that gaps stay visible and no field is ever fabricated.

**Acceptance criteria** (the contract, each criterion is IDed and independently checkable):

- **AC-1**: `adapt` discovers every immediate child directory of the corpus's `docs/specs/` that contains an `index.md`, and produces one canonical record per adaptable spec. A directory with no `index.md` is reported as not a spec and does not fail the run.
- **AC-2**: A record's `id` is `DM-` followed by the leading digits of the spec directory name, so `0012-portfolio-private-access-gate` yields `DM-0012`. A directory name with no leading digits yields no derivable id and is skipped with that reason.
- **AC-3**: Every contributing file is cited on the record as `spec` evidence: `index.md` always, `rationale.md` when it exists.
- **AC-4**: Code paths are extracted from inline code spans, split into whitespace separated tokens, with a trailing `:NN` and a trailing `/` stripped, and with any token discarded that starts with `/`, starts with `@`, or contains `*`. Each surviving token is resolved against the corpus root, and those that resolve are added as `file` evidence.
- **AC-5**: Resolution is case sensitive. A token whose casing differs from the entry on disk does not resolve, including on a case insensitive filesystem such as macOS.
- **AC-6**: A token that does not resolve is dropped from evidence and never emitted. The warning counts only the dropped tokens that are shaped like a path. The shape is tested against the token as it stood **before** the trailing `/` was stripped, so a trailing slash is itself a path signal: the token contains a `/`, ends in a known file extension matched without regard to case, or starts with a `.`. A dropped token shaped like prose or an identifier is not counted. The count is of occurrences, not of distinct tokens, matching the `unresolved_mention_count` field it feeds. The count therefore means paths this spec names that are not in the corpus, which is a drift signal a person can act on.
- **AC-7**: `status` maps `Accepted` to `accepted`, `Proposed` to `proposed`, `Done` to `accepted`, and `In Progress` to `proposed`. The raw value is preserved as the tag `source-status:<raw>`. A value outside that set skips the spec with that reason.
- **AC-8**: Where both files carry the same section, `rationale.md` is used and `index.md` is the fallback. A fallback section whose whole body is a short pointer to the sibling file is treated as absent, falls through, and is discarded rather than joining the body.
- **AC-9**: The winning option is identified per decision unit by the ladder in `## Feature design`. A panel spec has one decision unit per panel; every other spec has one, the whole `## Options considered` section. A unit whose winner resolves contributes its non winning options to `decision.alternatives`; a unit whose winner does not resolve contributes nothing and causes `decision.alternatives` to be named in `attempted_fields`. An option is never emitted as an alternative on the strength of a unit whose winner is unknown.
- **AC-10**: Each non winning option becomes an alternative. In a panel spec the title is prefixed with its panel question; in a plain option spec it is not. The rejection reason is that option's Cons text, and an option with no Cons produces the existing `alternative.missing_rejection_reason` warning.
- **AC-11**: `body` holds every section that neither file's mapping consumed, with headings intact, including sections this format does not standardise.
- **AC-12**: `attempted_fields` names only fields that have a defined source section which turned out absent or empty. A canonical field with no source section in this format, such as `context.triggering_change`, is left unset and is not flagged.
- **AC-13**: A spec's fingerprint is a SHA-256 over each contributing file's corpus relative path and bytes, in a fixed order, combined with the adapter version string. Editing any contributing file changes it, and so does changing the adapter version.
- **AC-14**: A manifest is written to the output directory recording the adapter version, the run timestamp, and per record the id, fingerprint, contributing files, and record path, plus every skip and every collision from the run.
- **AC-15**: On a second run, a spec whose fingerprint matches the manifest is not rewritten, a spec whose fingerprint differs is rewritten, and the report gives both counts.
- **AC-16**: A record that fails validation is not written, and is reported as failed with its violations. No spec in the current corpus can reach this path, so it is exercised by a synthetic fixture only; see the note under `## Requirements`.
- **AC-17**: `--dry-run` performs the whole run and its full report, and writes no record file and no manifest.
- **AC-18**: `--output` overrides the default output directory, which is `.decision-memory/records/` inside the corpus.
- **AC-19**: An id derived from more than one source is reported as a collision naming every path found and the one used, and the run continues.
- **AC-20**: A directory holding an `index.md` that cannot be adapted, because it is unreadable, its frontmatter will not parse, or it has no `## Decision` section, is skipped with its path and the reason, and the run continues through the remaining specs.
- **AC-21**: `adapt` exits `0` when every discovered spec produced a valid record or was unchanged, `1` when at least one discovered spec failed to produce a valid record, and `3` when the corpus path does not exist or holds no `docs/specs/` directory. Warnings never change the exit code. Against the current corpus, exit `1` should never occur, so a non zero exit on a real run means something unexpected happened rather than routine partial failure, and is worth investigating rather than absorbing.
- **AC-22**: The `validate` command resolves evidence by checking each cited target directly rather than scanning the project root, and a target that names a directory resolves.
- **AC-23**: `ValidationContext` carries the unresolved mention count, and `validate` emits `evidence.mentions_unresolved` as a warning from it.
- **AC-24**: A written record file is the exact inverse of the read grammar spec 0002 fixed, so a record `adapt` writes parses back to an equal record. Its filename is the record id plus `.md`.
- **AC-25**: The manifest is written as `manifest.json` in the output directory, as JSON with two space indent and entries ordered by id.

**A note on what the corpus can and cannot exercise.** Every field whose absence would fail validation is present in all 15 directory specs: a digit leading directory name, the H1 title, `**Date**`, `## Decision` with its `**Chosen option**` line, and `## Rationale` in `rationale.md`. Evidence is non empty by construction, since the contributing files are always cited. So a real spec cannot produce an invalid record, and the failure paths in **AC-16** and the exit `1` branch of **AC-21** are reachable only through synthetic fixtures. Build them as fixtures; do not expect a run against the real corpus to cover them.

## Decision

**Chosen option**: Option 1: A source adapter protocol in the application layer, with a jsmastery implementation in infrastructure and a section driven field mapping

The adapter is defined as a `SourceAdapter` protocol in the application layer exposing `discover`, `parse`, and `fingerprint`. The jsmastery implementation lives in infrastructure, where filesystem access belongs (basis: `AGENTS.md`, the dependency rule that infrastructure implements interfaces declared inward). Field mapping is driven by named sections of `index.md` and `rationale.md`, with `rationale.md` taking precedence and every unconsumed section falling through to the record body (basis: the corpus evidence in `rationale.md`, which shows the duplicated and stub sections this rule exists to handle).

## Feature design

**Data model sketch**:

The canonical record itself is unchanged; it is fixed by spec 0002. This feature adds the types around it.

| Type | Layer | Fields |
|---|---|---|
| `SourceAdapter` (Protocol) | application | `discover(corpus_root: Path) -> DiscoveryResult` · `parse(spec: DiscoveredSpec) -> AdaptationResult` · `fingerprint(spec: DiscoveredSpec) -> str` |
| `DiscoveredSpec` | application | `id: str` (required) · `root: Path` (required) · `contributing_files: list[Path]` (required, non empty, fixed order: `index.md`, then `rationale.md` when present) |
| `SkippedSource` | application | `path: Path` (required) · `reason: str` (required) |
| `Collision` | application | `id: str` · `paths: list[Path]` (every source that derived this id) · `used: Path` |
| `DiscoveryResult` | application | `specs: list[DiscoveredSpec]` · `skipped: list[SkippedSource]` · `collisions: list[Collision]` |
| `AdaptationResult` | application | `record: CanonicalDecisionRecord \| None` · `violations: list[Violation]` · `attempted_fields: frozenset[str]` · `unresolved_mention_count: int` · `fingerprint: str` |
| `ManifestEntry` | application | `id: str` · `fingerprint: str` · `contributing_files: list[str]` (corpus relative POSIX) · `record_path: str` |
| `Manifest` | application | `adapter_version: str` · `generated_at: str` · `entries: list[ManifestEntry]` · `skipped: list[SkippedSource]` · `collisions: list[Collision]` |

One shipped domain type changes: `ValidationContext` gains `unresolved_mention_count: int = 0`. `existing_paths` keeps its name and its type, but its meaning narrows from every path under the project root to the cited targets that resolve, because resolution moves from a scan to a direct check (**AC-22**).

That direct check needs the target normalization that today lives as private helpers inside `domain/validation.py`, applied during validation after the set was already built. Building the set by checking each target means normalizing first, so the normalization is exported from the domain as a public function and both the adapter and the application call it. One implementation, rather than two that drift into disagreeing about whether a target resolves.

**Field mapping**:

Sources are `index.md` and `rationale.md`. Where both carry the same section, `rationale.md` wins and `index.md` is the fallback (**AC-8**).

| Canonical field | Source | Notes |
|---|---|---|
| `id` | the leading digits of the spec directory name, prefixed `DM-` | no leading digits means no derivable id, so the spec is skipped |
| `title` | `index.md` H1, leading `NNNN. ` stripped | `# 0012. Portfolio private access gate` gives `Portfolio private access gate` |
| `status` | `index.md` `**Status**` | mapped per **AC-7**, raw kept as a tag |
| `date` | `index.md` `**Date**` | already `YYYY-MM-DD` throughout the corpus |
| `body` | every section neither mapping consumed | headings kept intact |
| `context.problem` | `## Context` | `rationale.md` first, else `index.md` |
| `context.triggering_change` | no source in this format | left unset, not flagged |
| `decision.chosen` | `index.md` `## Decision`, the `**Chosen option**` value | present in every spec in the corpus |
| `decision.alternatives` | `## Options considered` | `rationale.md` first, else `index.md`; winner found by the ladder below |
| `why` | the bullet list inside the `## Rationale` of `rationale.md` | absent when that section has no bullets |
| `rationale_summary` | the paragraphs of that same section | `index.md`'s `## Rationale` is a pointer stub, so it is discarded, not used |
| `consequences.positive` / `.negative` | `index.md` `## Consequences` | its Positive and Negative lists |
| `evidence` | contributing files as `spec` kind, resolving code paths as `file` kind | per **AC-3** and **AC-4** |
| `tags` | `source-status:<raw>` | preserves the source status value losslessly |
| `supersedes` | a supersession line when present | absent throughout the current corpus |

**Parsing model**: a section is an H2 (`## `) block, running from its heading to the next H2 or end of file, and including any nested H3 headings. Content before the first H2, meaning the H1 title line and the `**Date**` and `**Status**` lines, is not a section; it is consumed by the field mapping and never reaches the body.

**Stub detection**: a section is a stub when its body, after markdown link syntax is reduced to its text and whitespace is collapsed, is a single line of at most 80 characters that names a sibling contributing file. Both real instances are ``See `rationale.md`.`` and `See [rationale.md](rationale.md).`. A stub is treated as absent everywhere: it never fills a field, it never joins the body, and it falls through to the next source in precedence order.

**Decision units**: the ladder below resolves one winner per decision unit, not one per spec. A panel spec has one unit per `### Panel N` block; every other spec has exactly one unit, the whole `## Options considered` section. Alternatives are pooled across units. A unit whose winner does not resolve contributes no alternatives and puts `decision.alternatives` into `attempted_fields`, while units that did resolve still contribute theirs (**AC-9**). `decision.chosen` is always the `**Chosen option**` value from `index.md` and is never derived from a unit.

**Identifying the winning option** within a unit, in order, first match wins, because no single marker is reliable across the corpus:

1. Panel unit: take the token immediately following `**Decision**:` and match its letter against that panel's `**Option B —**` entries. Only that first token counts; a later `Option X` mention in the same sentence is ignored. This matters: 0012's Panel 3 reads `**Decision**: Option B, revised after a cross check review ... Option A was chosen first`, so a rule that scans the sentence can pick the loser.
2. Decision line carrying an ordinal (`**Chosen option**: Option 1: ...`): match by ordinal.
3. Otherwise match the Decision line's text against option titles, after stripping trailing parentheticals and trailing punctuation from both sides of the comparison.
4. Otherwise, if exactly one option in the unit carries a `(chosen)` marker, take it. Panel entries carry this marker in practice (`**Option A — Synchronous request/response (chosen)**`), giving panel units a second independent signal; it is close to unused for plain option units, where steps 2 and 3 resolve first.
5. Otherwise the unit does not resolve.

**Alternative title**: the option's label with its `Option N:` or `Option A —` prefix removed, and a trailing `(chosen)` or `(recommended)` marker removed. Every other parenthetical is kept, so `The two agent routes only (the original proposal)` survives intact. The more aggressive stripping in ladder step 3 is for comparison only and never changes what is stored. In a panel unit the panel question is then prefixed (**AC-10**).

**Rejection reason**: the option's Cons block, running from its `**Cons**:` label to the next bold label, the next heading, or the end of that option's entry, whichever comes first.

**Record serialization** (**AC-24**): a written record is the exact inverse of the read grammar spec 0002 fixed. A `---` fence, the frontmatter written with `yaml.safe_dump` at `sort_keys=False` so field order follows the schema rather than alphabetical order, a closing `---`, one blank line, then the body verbatim. A key whose value is `None` or an empty list is omitted rather than written as null, so a record never asserts an empty field it simply does not have. The filename is the record id plus `.md`, giving `DM-0012.md`.

**Manifest serialization** (**AC-25**): `manifest.json` in the output directory, JSON with two space indent, entries ordered by id so a diff between runs is readable.

**Code path extraction**, applied to the text of both contributing files (**AC-4**):

1. Take every inline code span.
2. Split each span on whitespace, because some spans hold whole shell commands.
3. Strip a trailing `:NN` line number suffix, then a trailing `/`.
4. Discard a token that starts with `/` (a URL route), starts with `@` (a package name), or contains `*` (a glob).
5. Resolve each survivor against the corpus root. Existence is the disambiguator, so an identifier such as `agentRunsEnabled` falls out on its own without any identifier heuristic.
6. Resolution confirms the entry name appears exactly, character for character, in its parent directory's listing, which preserves the case sensitivity rule from spec 0002 on a case insensitive filesystem (**AC-5**).
7. Count a token that did not resolve only when it is shaped like a path (**AC-6**), counting occurrences rather than distinct tokens. Test the shape against the token as it stood after step 3 stripped a trailing `:NN` but **before** it stripped a trailing `/`, so a trailing slash counts as a path signal in its own right. A token is shaped like a path when it contains a `/`, ends in a known file extension compared without regard to case, or starts with a `.`. The known extensions are `.md`, `.py`, `.json`, `.ts`, `.tsx`, `.js`, `.jsx`, `.toml`, `.yaml`, `.yml`, `.txt`, `.lock`, `.cfg`, `.ini`, and `.sh`, held as a module constant in the jsmastery adapter beside `ADAPTER_VERSION`; the list is corpus calibration, not a principle, and extending it is expected.

The shape test in step 7 gates the warning only, never extraction. Steps 1 to 6 are unchanged, so existence remains the disambiguator for evidence and a bare directory reference such as `` `tests` `` or `` `lib/` `` still becomes evidence when it resolves. Putting the shape test upstream instead would drop those, because a bare directory name has no slash, no extension, and no leading dot. The two questions are genuinely different: what is evidence is settled by whether the thing exists, and what is worth warning about is settled by whether a missing thing looked like a path.

Testing the shape before the trailing slash is stripped matters for one case that is easy to miss. A renamed single segment directory, written `` `oldlib/` ``, arrives at step 7 as `oldlib` once the slash is gone: no slash, no extension, no leading dot, so it would go uncounted even though it is exactly the drift the warning exists to report. Multi segment paths keep an internal slash and are caught either way. The current corpus contains no such case, so no measurement distinguishes the two orderings; the rule is written this way on reasoning, not on evidence.

**State transitions**: none. Records have a `status` field carried from the source, and this feature enforces no transitions between values.

**API surface**:

| Surface | Kind | Key inputs | Key outputs | Auth | Key errors |
|---|---|---|---|---|---|
| `SourceAdapter.discover(corpus_root)` | protocol method | corpus root path | `DiscoveryResult` | none | none, unadaptable sources come back as `SkippedSource` |
| `SourceAdapter.parse(spec)` | protocol method | `DiscoveredSpec` | `AdaptationResult` | none | none, failures come back as violations with no record |
| `SourceAdapter.fingerprint(spec)` | protocol method | `DiscoveredSpec` | fingerprint string | none | none |
| `decision-memory adapt CORPUS_PATH [--output PATH] [--dry-run]` | CLI command | corpus root, optional output dir, optional dry run | written records, a manifest, a printed report, an exit code | none | see the exit code table |

**Exit codes** for `adapt`, chosen to match the vocabulary spec 0002 fixed for `validate`:

| Code | Meaning |
|---|---|
| `0` | every discovered spec produced a valid record or was unchanged; warnings may be present |
| `1` | at least one discovered spec failed to produce a valid record |
| `2` | usage error, reserved by Click, not produced by this command directly |
| `3` | the corpus path does not exist, or holds no `docs/specs/` directory |

A directory with no `index.md` is reported as not a spec and does not affect the exit code, because a corpus legitimately contains folders that were never specs.

**Value sourcing** (every value each action produces names where it comes from):

| Action | Value produced / displayed | Source |
|---|---|---|
| `discover` | spec id | the leading digits of the directory name, prefixed `DM-` |
| `discover` | contributing files | `index.md` in the directory, plus `rationale.md` when it exists |
| `discover` | skip reason | the failing condition: no `index.md`, no leading digits, unreadable, unparseable frontmatter, no `## Decision`, unmapped status |
| `discover` | collision entry | two or more sources deriving the same id, and the one discovery ordered first |
| `parse` | every canonical field | the field mapping table, under the precedence and stub rules |
| `parse` | `spec` evidence targets | the contributing file paths, corpus relative POSIX |
| `parse` | `file` evidence targets | extracted tokens that resolve, corpus relative POSIX |
| `parse` | unresolved mention count | extracted tokens that did not resolve |
| `parse` | `attempted_fields` | fields whose defined source section was absent or empty |
| `parse` | violations | the adapter emitted rules, plus what `validate` returns for the built record |
| `fingerprint` | fingerprint string | SHA-256 over contributing file paths and bytes in fixed order, plus the adapter version |
| `fingerprint` | adapter version | `ADAPTER_VERSION`, a module constant in the jsmastery adapter, initial value `"1"`, bumped by hand when the mapping changes |
| `unresolved_mention_count` | the known file extensions | `_KNOWN_PATH_EXTENSIONS`, a module constant in the jsmastery adapter beside `ADAPTER_VERSION`, holding the 15 extensions listed in step 7, compared without regard to case and extended by hand when a corpus needs it (**AC-6**) |
| `parse` | alternative title | the option label, prefix and trailing chosen marker removed, panel question prefixed in a panel unit |
| `parse` | rejection reason | the option's Cons block, bounded as defined above |
| CLI `adapt` | record filename | the record id plus `.md` |
| CLI `adapt` | manifest filename | `manifest.json` in the output directory |
| CLI `adapt` | output directory | `--output`, else `.decision-memory/records/` inside the corpus root |
| CLI `adapt` | which records are rewritten | the fingerprint compared against the manifest entry for that id |
| CLI `adapt` | manifest `generated_at` | the run's start time, ISO 8601 |
| CLI `adapt` | report lines | the discovery result, the per spec adaptation result, and the write outcome |
| CLI `adapt` | exit code | the exit code table |
| `validate` | `existing_paths` | each target the record cites, checked directly, replacing the project root scan |
| `validate` | `evidence.mentions_unresolved` | `ValidationContext.unresolved_mention_count` |

**Key invariants**:
- No canonical field is ever populated with a value not present in the source. A field that cannot be filled is left unset and flagged, never guessed.
- Every record carries at least one evidence entry, because its contributing files are always cited.
- An evidence target is only emitted after it resolves, so a written record never fails on `evidence.path_unresolved`.
- Only records that pass validation are written, so the output directory holds valid records exclusively.
- A record's `id` is stable across a rename of its spec directory, because it derives from the number, not the slug.
- One spec directory produces at most one record.
- The fingerprint changes when any contributing file changes, and when the adapter version changes.
- The adapter reads the corpus and writes only inside the output directory; it modifies no source file.
- A single unadaptable source never stops the run.

**Security model**: none in the access control sense; this is a local command line tool with no users and no regulated data. Three notes on reading and writing another project's repository. YAML is loaded with the safe loader, inherited from feature 3, so a source file cannot construct arbitrary Python objects. Extracted tokens are rejected before resolution when absolute or containing a glob, so a spec cannot direct a filesystem check outside the corpus root. Writing defaults to a dot directory inside the corpus, and `--output` exists so the tool can be pointed elsewhere when writing into the source repository is not wanted.

**Configuration required**: none. No new runtime dependency, no environment variable, no credential. Fingerprinting uses `hashlib` and the protocol uses `typing.Protocol`, both standard library.

**Critical test scenarios** (each maps to an acceptance criterion in `## Requirements`):
- Happy path: `adapt` against the real corpus produces one valid written record per adaptable spec directory plus a manifest, and exits `0`, verifies **AC-1**, **AC-14**, **AC-21**
- Edge case: `0012-portfolio-private-access-gate` yields id `DM-0012`, verifies **AC-2**
- Edge case: a record cites both `index.md` and `rationale.md` as `spec` evidence, verifies **AC-3**
- Edge case: a span holding a shell command yields its path token; `/dashboard`, `@insforge/cli`, and `app/api/**/route.ts` are all discarded; `app/dashboard/page.tsx:67` and `lib/` resolve after stripping, verifies **AC-4**
- Failure case: a token differing only in casing from the real entry does not resolve on macOS, verifies **AC-5**
- Edge case: a spec naming a since renamed file drops it and reports the count as a warning, verifies **AC-6**, **AC-23**
- Edge case: a span holding quoted prose such as `` `read only` `` adds nothing to the count, while a bare directory reference such as `` `tests` `` still resolves as evidence, verifies **AC-6**
- Failure case: a dotted field name such as `` `decision.chosen` `` is not counted, because `.chosen` is not a known file extension, verifies **AC-6**
- Failure case: a renamed single segment directory written `` `oldlib/` `` is counted, because the shape test sees the trailing slash before it is stripped, verifies **AC-6**
- Edge case: a token ending `.MD` is counted the same as one ending `.md`, since the extension comparison ignores case, verifies **AC-6**
- Edge case: an `In Progress` spec maps to `proposed` and carries the tag `source-status:In Progress`, verifies **AC-7**
- Edge case: 0005, whose `index.md` has a real `## Context` and a stub `## Options considered`, uses `rationale.md` for both, and the stub reaches neither a field nor the body, verifies **AC-8**, **AC-11**
- Edge case: 0001, 0011, and 0013 resolve their winner by ordinal; 0006, whose heading says `(recommended)` and whose Decision line drops the ordinal, resolves by title match; 0009 and 0012 resolve per panel by letter, verifies **AC-9**
- Failure case: 0012's Panel 3, whose Decision line names Option B first and then discusses Option A, resolves to Option B, and Option A appears among the alternatives, verifies **AC-9**
- Edge case: a spec with one unresolvable unit and two resolvable ones still contributes the two units' alternatives and names `decision.alternatives` in `attempted_fields`, verifies **AC-9**
- Edge case: a written record parses back through `parse_record_file` to a record equal to the one written, and its filename is `DM-0012.md`, verifies **AC-24**
- Edge case: the manifest is valid JSON at `manifest.json` with entries in id order, verifies **AC-25**
- Edge case: a panel spec's alternatives carry the panel question prefix, a plain option spec's do not, verifies **AC-10**
- Edge case: `context.triggering_change` appears in no record's `attempted_fields`, while a spec with no `## Context` at all does list `context.problem`, verifies **AC-12**
- Edge case: editing `rationale.md` changes the fingerprint, and so does bumping the adapter version with both files untouched, verifies **AC-13**
- Edge case: a second run with no source change rewrites nothing and reports every record unchanged; touching one spec rewrites exactly that record, verifies **AC-15**
- Failure case, synthetic fixture only: a hand written spec directory whose `rationale.md` has no `## Rationale` section produces a record that fails validation, is not written, and is reported with its violations. No spec in the real corpus reaches this path, verifies **AC-16**
- Edge case: `--dry-run` produces the identical report and writes nothing. On a first run the output directory is never created; on a later run every existing record file and the manifest are left byte for byte unchanged, verifies **AC-17**
- Edge case: `--output` writes elsewhere and the records still validate when given the corpus as project root, verifies **AC-18**
- Edge case: id `DM-0019`, derived from both the directory and, in a later slice, the flat file, is reported as a collision naming both paths and the one used, verifies **AC-19**
- Failure case: a directory with an `index.md` but no `## Decision` section is skipped with that reason and the run completes the other specs, verifies **AC-20**
- Failure case: a corpus path with no `docs/specs/` exits `3`, verifies **AC-21**
- Edge case: `validate` on a record citing a directory target resolves it, and completes without walking the corpus root, verifies **AC-22**

## Build plan

Ordered for the Skateboard approach: the thinnest thing a person can actually run first, then each step thickens the mapping. A real record exists on disk from step 2 onward, so every later step is checkable end to end rather than only in tests.

1. Build discovery and the `adapt` command shell: walk `docs/specs/`, derive ids, collect contributing files, report skips and not a spec directories, and implement `--dry-run` so the first run writes nothing, satisfies **AC-1**, **AC-2**, **AC-17**, **AC-20**
2. Map the required fields only (title, status with its tag, date, `decision.chosen`, rationale, and evidence from the contributing files), define the section parsing model, write the record with the serialization above, validate before writing, and set the exit code, satisfies **AC-3**, **AC-7**, **AC-16**, **AC-18**, **AC-21**, **AC-24**
3. Change the shipped validation path: add `unresolved_mention_count` to `ValidationContext`, add the `evidence.mentions_unresolved` rule, export target normalization from the domain as a public function, and replace the project root scan with a direct check per cited target that also resolves directories, satisfies **AC-22**, **AC-23**
4. Add code path extraction, case sensitive resolution, and the unresolved mention warning, satisfies **AC-4**, **AC-5**, **AC-6**
5. Add section precedence, stub detection, the residue body, and `attempted_fields`, satisfies **AC-8**, **AC-11**, **AC-12**
6. Add alternatives: the winner ladder across both source shapes, panel prefixing, and rejection reasons from Cons, satisfies **AC-9**, **AC-10**
7. Add the fingerprint, the manifest, incremental rewriting, and collision reporting, satisfies **AC-13**, **AC-14**, **AC-15**, **AC-19**, **AC-25**
8. Complete the test suite across every acceptance criterion, including a round trip test that parses a written record back to an equal record, run it against the real corpus, and run ruff and mypy clean, satisfies **AC-1** through **AC-25**

Step 3 sits where it does deliberately. It changes code that shipped in feature 3, and putting it before extraction means every later step resolves evidence through one mechanism rather than two.

## Consequences

**Positive**:
- A real corpus becomes inspectable before anything is embedded, which is the first point this project produces something a person can judge.
- Only valid records reach the output directory, so feature 5 can ingest the whole directory without revalidating each file.
- Incremental re ingestion is proven in this slice rather than written and left untested until feature 5 needs it.
- Ids survive a spec being renamed, so citations stay valid across normal repository maintenance.
- Replacing the project root scan with direct checks removes a cost that would have grown with every corpus, and it closes a follow up spec 0002 already carried.
- Nothing in the mapping fabricates a value, so a degraded source produces a smaller record rather than a wrong one.

**Negative / tradeoffs**:
- The mapping is tuned to one project's spec conventions. A second jsmastery style project with different heading habits will need work, and the winner ladder is the most likely thing to break.
- The tool writes into a repository it was only asked to read. `--output` mitigates it, the default does not.
- This feature reaches into shipped feature 3 code twice, for the directory resolution change and for the new context field, so feature 3's tests move with it.
- Rejection reasons are inferred from Cons prose. That is what the text means, but it is an interpretation, and a Cons list written as caveats rather than reasons will read oddly in a record.
- `why` populates in exactly 1 of the 15 directory specs, because only 0006 writes its Rationale with bullets. The field is close to vestigial against this corpus, and the evaluation harness assertion that needs the rationale summary specifically has almost nothing to contrast against.
- Ladder step 4 does real work only for panel units, where entries carry their own `(chosen)` marker. For plain option specs steps 2 and 3 always resolve first, so step 4 is untested by anything in the current corpus.
- `DM-<number>` is not corpus scoped, so a second corpus collides on ids and will force a migration of stored citations.
- Flat single file specs stay unreadable this slice, which leaves a quarter of the corpus, including its most recent entries, out of the evaluation harness in feature 7.
- The step 7 shape test is calibrated to one corpus's backtick habits and is now on its third calibration. It will need retuning against a second corpus, and a project that writes bare filenames without extensions, or quotes prose that happens to contain a slash, will read differently.
- The known extension list is a maintained list, so a corpus using a file type outside it undercounts real misses until someone extends it. That was the deliberate trade against overcounting every dotted identifier.
- A file with no extension at all, such as `Makefile`, `Dockerfile`, or `LICENSE`, is invisible to the warning once it is renamed, because it has no slash, no extension, and no leading dot. Nothing in the current corpus names one, so this is untested rather than known good.
- A corpus that quotes prose containing a slash undercuts the whole filter: `` `and/or` ``, `` `Settings/Profile` ``, and a quoted URL path all read as path shaped and would be counted. This corpus's habit is backticked prose without slashes, which is why the slash rule is safe here and may not be elsewhere.
- Evidence and the warning now answer two different questions with two different tests, which is one more thing to hold in mind when reading the extraction code than a single filter would be.

**Neutral**:
- Establishes the adapter protocol that a second source format implements later.
- The adapter version string is bumped by hand, which is one more thing to remember when the mapping changes.
- `existing_paths` keeps its name while its meaning narrows, which is worth a comment at its definition.

## Follow-up

- [ ] Add flat single file spec support in a later slice. Note that doing so makes `DM-0019` a genuine duplicate rather than a reported collision, so the id scheme needs a tiebreak before that slice ships
- [ ] Update spec 0002 to record the `ValidationContext` change, the `evidence.mentions_unresolved` rule id, and the narrowed meaning of `existing_paths`
- [ ] Recalibrate the step 7 shape test against the second corpus when one exists, and record what changed. Treat the current rule as calibration, not a principle; it has already been retuned twice
- [ ] Close spec 0002's follow up about bounding the project root scan; step 3 removes the scan rather than bounding it
- [ ] Update `AGENTS.md` and spec 0001 if the layer list changes as the adapter lands
- [ ] Decide a corpus scoped id scheme before multi project querying leaves the deferred list, since changing ids later invalidates stored citations and embeddings
- [ ] Revisit the winner ladder and the panel prefix convention when a second corpus exists; both are shaped by one project's habits
- [ ] Consider whether `adapt` should accept a single spec directory rather than a whole corpus, for a fast edit and check loop

## Rationale

Reasoning, options considered, and the corpus evidence behind every mapping rule: see [rationale.md](rationale.md).
