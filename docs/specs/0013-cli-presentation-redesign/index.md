# 0013. CLI presentation redesign

**Date**: 2026-08-15
**Status**: Proposed

## Summary

The CLI prints plain `typer.echo` lines with no shared grammar: a reader cannot
tell at a glance what ran, what succeeded, and what to do next. This spec builds
the visual language from the design at
`docs/reference/artifact/decision-memory-cli-redesign.pdf` (aligned reports at
80 columns, one accent colour, status markers that carry a shape and a word, one
summary line paired with the exit code, and one `error` then `hint` then `exit`
grammar for failures), using a small rendering module rather than a new
dependency. Two surfaces are frozen: `query --debug` and `evaluate` keep byte
identical output when the stream is not a terminal, because committed
experiment instruments parse them. Nothing under the presentation layer changes:
same commands, same flags, same exit codes, same DTOs, and no printed value that
the pipeline does not already compute.

## Requirements

**User stories**:

- As someone running a command, I want to see at a glance what ran, what
  succeeded versus skipped versus failed, and what to do next, so I do not have
  to read a wall of undifferentiated lines.
- As someone hitting an error, I want the tool to name a fix and its exit code,
  so I know what to run next instead of only that something broke.
- As someone piping output into a script or an experiment, I want the bytes to
  stay stable and parseable, so an instrument does not silently stop matching.
- As a maintainer, I want one rendering module with a checked layer boundary, so
  the look stays consistent and cannot drift back into the use cases.

**Acceptance criteria**:

- **AC-1**: All eight commands (`version`, `validate`, `doctor`, `adapt`,
  `test-adapter`, `ingest`, `query`, `evaluate`) and their failure paths print
  through the shared renderer in the defined grammar: a `command — subject`
  header, one full width rule under the header and one above the summary,
  section labels in muted small letters with content indented 2 cells, and a
  final one line `summary  <counts> · exit <n>`.
- **AC-2**: No printed line exceeds 80 columns on any screen, including the
  widest real values (absolute store paths, long headings, long question text).
  A value too long for its column is wrapped or shortened within that column,
  never by pushing the line past 80. This is character level shortening inside a
  value that is already being printed; it never changes which values print, which
  is AC-7's subject.
- **AC-3**: Status is never carried by colour alone. Every state prints a shape
  plus a word (`+ ok`, `~ skip`, `! warn`, `x ERR`, `- info`), so the meaning
  survives `NO_COLOR`, a pipe, and a colourblind reader.
- **AC-4**: One shared capability predicate, evaluated per output stream,
  decides both colour and glyph set. Colour is emitted only when the stream is a
  terminal, `NO_COLOR` is unset, and `TERM` is not `dumb`. Unicode glyphs are
  emitted only when that same predicate passes and the stream encoding can
  represent them. A stream with no encoding attribute degrades to plain ASCII
  and never raises.
- **AC-5**: `query --debug` emits byte identical output to the committed pre
  change baseline whenever the stream is not a terminal. This covers the whole
  standard output of the command: the answer or abstention block, the trace
  sections, **and every failure path** of that invocation, not only the trace.
- **AC-6**: `evaluate` emits byte identical output to the committed pre change
  baseline whenever the stream is not a terminal, failure paths included.
- **AC-7**: Mode affects presentation only, never which data is present. No
  screen truncates, samples, hides, or adds a row based on terminal detection,
  colour support, or glyph support. Every row the command computes is printed in
  every mode, and no mode prints a row another mode does not.
- **AC-8**: Every printed value is derivable from what the pipeline already
  computes. No DTO field is added, removed, renamed, or retyped; no trace field
  is added; no retrieval, verification, or storage behaviour changes. A value
  from the design that is not derivable is not printed.
- **AC-9**: Every failure path prints the same three part grammar: an `error`
  line naming what happened, an indented `hint` line naming the fix as a real
  command or flag, and a final `exit <n>` line. This includes the usage errors
  Click raises before command code runs, rendered on the same stream Click uses
  today, and it is pinned by tests that assert the rendered bytes for a missing
  required argument and for an unknown flag. The hint text for every failure
  kind is fixed by the table in this spec, not authored during the build.
  **AC-5 and AC-6 take precedence over this criterion**: on the two frozen
  surfaces, a failure piped to something other than a terminal keeps today's
  bytes and does not gain the grammar.
- **AC-10**: Help screens state the real interface. Root help lists all eight
  commands; each command's help lists every flag it really accepts and only the
  exit codes it can really return.
- **AC-11**: The renderer lives in a `presentation` package and imports nothing
  from `domain` or `infrastructure`. A layering test asserts the full dependency
  rule from `AGENTS.md`: `domain` imports nothing outward, `application` imports
  nothing from `infrastructure` or `presentation`, and no Typer, Pydantic,
  Chroma, or OpenAI import appears in `domain` or `application`. The one known
  violation is a named exemption in that test, not a weakened assertion.

## Decision

**Chosen option**: Option 3: an internal rendering module using semantic ANSI 16
colours, with the frozen piped surfaces as a byte invariant.

Build the design's visual language in one new `presentation/render.py` module
with no new runtime dependency, colouring with the sixteen named ANSI indices
chosen for what each token means rather than for an exact hex value, and freeze
`query --debug` and `evaluate` to today's exact bytes whenever the stream is not
a terminal.

## Rationale

Reasoning, the four options weighed, and the evidence this design was checked
against: see [rationale.md](rationale.md).

## Feature design

### The rendering module

`src/decision_memory/presentation/render.py`, a new package alongside
`cli.py`. `cli.py` stays where it is: it is the composition root, wiring
concrete adapters into use cases, which is a different job from rendering.

The module is pure presentation. It takes the DTOs the application already
returns and produces text. It reads no file, opens no store, and computes
nothing a use case owns.

**The capability predicate**, one function, evaluated per stream, used by both
colour and glyphs:

```text
styled(stream) = stream.isatty()
              and os.environ.get("NO_COLOR") is None
              and os.environ.get("TERM") != "dumb"

unicode_ok(stream) = styled(stream) and encoding_can_represent(stream, GLYPHS)
```

`encoding_can_represent` reads `getattr(stream, "encoding", None)`, returns
`False` when it is absent or `None`, and otherwise tests the glyph set with
`str.encode(errors="strict")` inside a `try`. It never raises.

**Palette**, semantic rather than decorative: each token names what it means, and
the terminal's own theme resolves it. This is why light and dark both work with
no theme detection, and why `is_light_term()` from the design sketch is not
built.

| Token | Meaning | SGR |
|---|---|---|
| accent | command word in the header, answer lead in | bold cyan (`1;36`) |
| ok | success, valid, written, added, grounded | green (`32`) |
| warn | skip, warning | yellow (`33`) |
| err | error, failure | red (`31`) |
| muted | section labels, keys, meta | bright black (`90`) |
| dim | rules, hints, arrows | faint (`2`) on the default foreground |

`muted` and `dim` are separated by the faint attribute, not by two grey indices,
because two greys read as one colour on many themes. The design's hex and ANSI
256 tables stay in the design document as documented intent, the record of what
each token means, and are not emitted as bytes.

**Markers**: ASCII is the contract, Unicode is the upgrade.

| Meaning | ASCII | Unicode | Summary token |
|---|---|---|---|
| ok, written, added | `+` | `✓` | `ok` |
| skipped | `~` | `≈` | `skip` |
| warning | `!` | `!` | `warn` |
| error | `x` | `✕` | `ERR` |
| info, meta | `-` | `·` | none |
| transform arrow | `->` | `→` | none |
| shortened value | `...` | `…` | none |

**The marker carries the outcome, the word carries the action.** This one rule
settles every per record state without a per screen lookup. A state that did
work successfully is `+ ok`; a state that deliberately did no work is `~ skip`;
a state that failed is `x ERR`. The word beside the marker is the real state
value, unchanged.

| Screen | State value | Marker |
|---|---|---|
| adapt | `written`, `rewritten` | `+ ok` |
| adapt | `unchanged` | `~ skip` |
| adapt | `failed` | `x ERR` |
| ingest | `added`, `updated`, `removed` | `+ ok` |
| ingest | `unchanged` | `~ skip` |
| ingest | `failed` | `x ERR` |
| validate, corpus | `ok` | `+ ok` |
| validate, corpus | a discovery skip | `~ skip` |
| validate, corpus | a collision | `! warn` |
| validate, corpus | `violation`, `exception` | `x ERR` |
| doctor | any of the six `SkipReason` values | `~ skip` |
| test-adapter | a passing check | `+ ok`, word `PASS` |
| test-adapter | a failing check | `x ERR`, word `FAIL` |

Doctor's six skip reasons keep the fixed display order spec 0004 AC-3 already
pins; this spec restyles those rows and never reorders them.

**Layout primitives**: `header(command, subject)`, `rule()`, `section(label)`,
`field(key, value)`, `row(marker, columns)`, `table(headers, rows, alignments)`,
`summary(counts, exit_code, note=None)`, and `failure(message, hint, exit_code)`.
Indent unit is 2 cells, nested blocks 4, column gutter exactly 2 cells, keys left
aligned with values aligned to one column, one blank line between sections.

**Column widths and overflow.** Per screen column widths are taken from the
design's own 80 column transcripts, which already fix them, including the two
line source row on page 17 where the relative path sits on its own continuation
line. Where a real value is wider than its column:

- Only the **last** column of a row may wrap. It continues on the next physical
  line, indented to its own column start, with every earlier column blank
  padded on the continuation lines.
- Every other column shortens at the tail with the shortened value glyph above,
  never at the head or middle, so the identifying prefix of a path or id stays
  readable.
- The shortened value glyph is part of the glyph set the capability predicate
  tests, so a stream that cannot encode `…` never receives it.

**Header subject** is the real thing the command acted on:

| Command | Subject |
|---|---|
| `version` | none; the header is the command word alone |
| `validate` | the record file path, or the corpus path plus `(corpus, write-free)` |
| `doctor` | the surveyed directory |
| `adapt` | `<corpus> → records` |
| `test-adapter` | the adapter selector |
| `ingest` | `records → query index` |
| `query` | the question text |
| `evaluate` | the corpus path |

When the effective value came from `.decision-memory.yml` rather than the
command line, the header prints the **resolved** value, because that is what the
run actually used.

**Summary line vocabulary.** The final line counts what the screen is about. A
screen with per record states rolls up using the marker vocabulary (`2 ok · 1
skip · 1 warn · 1 err`), so its counts and its rows use one set of words. A
screen with no per record states uses its own domain nouns (`14 analyzed · 1
ignored · 0 skipped`), exactly as the design draws each screen. Both forms end
in `· exit <n>`.

### Frozen surfaces

`query --debug` and `evaluate` are read by committed instruments
(`docs/experiments/data/jobpilot-abstention-cause.sh`,
`coverage-directness-extract.py`, `compare-retrieval.py`) and quoted in the
experiment writeups. The rule is an invariant, not a list of protected strings:

> When the stream is not a terminal, these two commands emit exactly the bytes
> the pre change build emits.

A list of anchors only ever protects the anchors somebody happened to find; the
six greps named at the start of this design turned out to be twelve regexes and
one more script. The invariant covers the instruments nobody has looked at yet,
including ones written after this ships. On a terminal these two surfaces gain
colour, and nothing else: no reordering, no re indenting, no renamed section, no
added or removed line.

Because `query --debug` prints the answer block and the trace to one stream, the
freeze covers the whole standard output of that invocation. This produces a
deliberate asymmetry, stated here so it does not read as a bug:

> `decision-memory query "..." --debug | cat` emits today's bytes exactly.
> `decision-memory query "..." | cat` emits the new layout.
> `--debug` is the machine surface; plain `query` is the human one.

**The frozen printers are not refactored on the way past.** `_print_query_debug`,
`_print_partial_query_debug`, and `_print_evaluation_report` stay untouched until
their own build task. While the other screens move to the new module those three
will look temptingly similar to the new primitives, and a shared helper extracted
in passing is exactly how a frozen surface drifts. The baseline diff catches it,
but the rule removes the ambiguity about whether it was allowed.

A sweep of `docs/experiments/data/`, `README.md`, and `docs/user-guide.md` found
no consumer of plain `query` output: every script that runs `query` passes
`--debug`. The README and user guide quote transcripts for humans, so they are
refreshed by this feature rather than protected by it.

### What the redesign cannot print (correction 3, resolved)

The scope guardrail holds with no exception: no DTO field changes. Each value
below is dropped or re sourced.

| Screen | Design showed | Resolution |
|---|---|---|
| query, abstained | `refs DM-0002 "Retry policy"` | **Re sourced.** No record title reaches the trace. Print record id plus relative path, taken from the fused candidate's `provenance[].path`. |
| query, abstained | `next` naming `docs/notes/retry.md` | **Replaced.** No per question path exists. Print a static true hint naming the real commands with no invented path. |
| query, debug | `index built 2026-08-09 09:12` | **Dropped.** Not in `FreshnessTrace`, and the surface is frozen. |
| query, debug | `disposition dropped (low)` | **Dropped.** No such disposition exists: `relevance_floor` is hardcoded `None`. The frozen surface prints today's real enum values. |
| query, debug | `providers embed local-fp16 · answer rule-based assembly` | **Not built.** See below. |
| query, debug | `facets  status=accepted applied` | **Not built.** That is the filter stage, not facets, and the surface is frozen. |
| ingest, debug | `· embedded · indexed` | **Dropped.** No per record stage flags exist on `RecordIngestResult`. |
| ingest, debug | `x ERR DM-0005 embed failed: provider lock held` | **Replaced.** A lock aborts the whole run, so it can never be a per record row. Print the real `failure_code` on the row, and render the lock failure through the `error` then `hint` then `exit` grammar. |
| validate, one record | `record DM-0002 canonical-...-schema` | **Re sourced.** `ValidationOutcome` carries only violations and an exit code. Print the file path being validated. |
| validate, corpus | per source path column | **Kept.** Join the result id to `DiscoveredSpec.root` and render it relative to the corpus root. |
| doctor, adapt | `... 20 more rows`, `... 13 more` | **Dropped.** Every row prints (AC-7). Truncation would change a normative report and strand rows behind a flag that the scope guardrail forbids. |

**On the providers line, and correction 1.** The design's line is invented: the
real providers are OpenAI with `text-embedding-3-small` for embedding, `gpt-4o`
for facets, answer, and coverage, and `gpt-4o-mini` for entailment and
decomposition. That mapping is recorded here so nobody reintroduces a guess. It
is not printed, because the only screen it appears on is frozen, and adding a
line on a terminal only would break AC-7. The tool therefore never makes a false
statement about itself, by never making the statement.

Note the true mapping differs from what this module's own docstring claims:
`coverage_verdict` calls `MODEL_FACETS_AND_ANSWER` (`gpt-4o`) at
`openai_generation.py:799`, while the docstring and the constant name
`MODEL_ENTAILMENT_COVERAGE` both imply `gpt-4o-mini`. The misleading name is a
follow up, not this feature's work.

### Failure kinds and their hints

Fixed here so the wording is reviewed once rather than invented fifteen times
during the build. Every hint names a real command or flag. The two frozen
surfaces are absent from this table on purpose: `query --debug` and `evaluate`
keep today's failure lines when piped, per AC-9's precedence rule.

| Command | Failure | Exit | Hint |
|---|---|---|---|
| any | unknown flag or missing argument (Click) | 2 | the command's own usage line, then `<command> --help` |
| any | `.decision-memory.yml` unreadable or invalid | 1 | fix the key the message names in `.decision-memory.yml` |
| any | malformed adapter selector | 2 | use `jsmastery-specs`, or `package.module:attribute` |
| any | adapter import or contract failure | 1 | install the adapter, or use the built in `jsmastery-specs` |
| any | no corpus root after precedence | 2 | pass a corpus path, or set `corpus_root` in `.decision-memory.yml` |
| `validate` | `--adapter` given with a record file | 2 | drop `--adapter`; it applies to a corpus directory |
| `validate` | record has violations | 1 | fix the field named on each violation row, then run `validate` again |
| `validate` | corpus path missing | 3 | point at a real corpus directory, or run `adapt` first |
| `doctor` | directory missing or not a directory | 3 | point at a real corpus directory |
| `doctor` | `--samples` negative | 2 | `--samples` takes 0 or more |
| `doctor` | scan failed unexpectedly | 1 | check the path is readable, then run `doctor` again |
| `adapt` | corpus lacks the adapter's layout | 3 | the message names the missing structure; run `doctor <dir>` to survey it |
| `adapt` | adapter raised during discover or parse | 1 | run `test-adapter <selector> --cases <manifest>` to find the failing contract |
| `adapt` | write failure | 1 | check the `--output` directory is writable |
| `test-adapter` | manifest unreadable or invalid | 1 | check the manifest against the conformance schema |
| `test-adapter` | a check failed | 1 | the failing rule names the contract; fix the adapter, then run it again |
| `ingest` | no records directory resolved | 2 | pass a records directory, or set `output` in `.decision-memory.yml` |
| `ingest` | records directory missing | 3 | run `adapt` first to write records |
| `ingest` | store locked | 1 | wait for the running ingest or query to finish, then run it again |
| `ingest` | partial ingest | 1 | run `ingest` again to retry the records that failed |
| `ingest` | no API key | 1 | set `OPENAI_API_KEY`, embedding needs a provider call |
| `query` | store path missing | 3 | run `ingest` first, or pass `--store <path>` |
| `query` | bad filter value | 2 | the message names the bad value; see `query --help` for accepted filters |
| `query` | index stale, `--allow-stale` absent | 1 | run `ingest --rebuild`, or pass `--allow-stale` to answer anyway |
| `query` | store locked | 1 | wait for the running ingest to finish, then ask again |
| `query` | retrieval integrity failure | 1 | run the same query with `--debug` to see the stage that failed |
| `query` | provider failure | 1 | check `OPENAI_API_KEY` and the network, then ask again |

### Value sourcing

Every value each screen displays, and where it comes from. Nothing here needs
plumbing that does not exist.

| Screen | Value displayed | Source |
|---|---|---|
| all | header subject | the command's own argument (path, selector, question) |
| all | `exit <n>` | the outcome's `exit_code`, unchanged |
| doctor | analyzed, ignored, skipped | `DoctorOutcome.markdown_analyzed`, `.non_markdown_ignored`, sum of `.skips[].count` |
| doctor | ranked headings, files, pct | `DoctorOutcome.headings[].heading`, `.file_count`, `.percentage` |
| doctor | heading sets, samples | `.heading_groups[].headings`, `.file_count`, `.sample_paths` |
| doctor | skips | `.skips[].reason`, `.count`, `.unseen_subtrees`, `.sample_paths` |
| validate, one record | record path | the `file` argument |
| validate, one record | violations | `ValidationOutcome.violations[].severity`, `.rule`, `.field`, `.reason` |
| validate, corpus | adapter identity | `CorpusValidationOutcome.adapter_id`, `.adapter_version` |
| validate, corpus | discovered, skipped, collisions | `.discovered.specs`, `.skipped[].path/.reason`, `.collisions[].id/.paths/.used` |
| validate, corpus | per source id, state, path | `.results[].id`, `.kind`, joined to `.discovered.specs[].root` |
| validate, corpus | summary counts | counted from `.results[].kind` and `.discovered` |
| adapt | mode row | the `--dry-run` flag, via `AdaptOutcome.dry_run` |
| adapt | per record id and state | `AdaptOutcome.records[].id`, `.state`, `.violations[].reason` |
| adapt | output path | `AdaptOutcome.output_dir` |
| test-adapter | manifest, cases, checks | the `--cases` path, `len(manifest.cases)`, `len(outcome.checks)` |
| test-adapter | case header | `ConformanceCase.id`, `.category`, `.subject_path`, `.target_fields` |
| test-adapter | check rows | `CheckResult.status`, `.rule`, `.case_id`, `.source_id`, `.path`, `.operation`, `.variant`, `.detail` |
| test-adapter | result, final | `outcome.passed`, `.failed` |
| ingest | records, store, mode | the request paths, `IngestResult.store_path`, the `--dry-run` flag |
| ingest | per record action, chunk count | `records[].action`, `len(records[].chunks)` |
| ingest | unchanged reason | `records[].desired_fingerprint` equals `.active_fingerprint` |
| ingest | failed row | `records[].failure_code` |
| ingest | summary state | counts by `action`, plus `IngestResult.state` for the note |
| query, answered | answer text and markers | `QueryResult.sentences[].text`, `.citation_ids` (real ids are `C1`, `C2`, uppercase) |
| query, answered | source rows | `citations[].citation_id`, `.record_id`, `.chunk_id`, `.value_path`, `.relative_path`, `.section` |
| query, answered | grounded count | distinct `record_id` across `citations` |
| query, answered | consulted count | distinct `record_id` of `trace.retrieval.diversity.accepted_chunk_ids`, resolved through `trace.retrieval.fusion.candidates` |
| query, answered | records with no supporting evidence | consulted minus grounded, from the two rows above |
| query, abstained | the verbatim string | `not enough evidence here`, unchanged |
| query, abstained | consulted, supporting | the same two counts; supporting is 0 because an abstention carries no citations |
| query, abstained | refs rows | record id plus `provenance[].path` of the accepted chunks |
| query, both | stale marker | `trace.freshness.state` and `.stale_reasons` |
| errors | message, hint, code | the outcome's failure text, an authored hint per failure kind, the real exit code |

### Help screens

Help states the real interface (AC-10). Corrections against the design:

- Root help lists **eight** commands. `evaluate` is real and documented in the
  README, and omitting it is a false statement about the interface.
- `query` help lists `--record-id`, `--status`, `--tag`, and `--value-path`
  alongside `--store`, `--allow-stale`, and `--debug`. The design shows three of
  the seven.
- `doctor` help lists exit code 2. A negative `--samples` raises
  `typer.BadParameter`, which exits 2. The design lists only 0, 1, and 3.
- Exit code 2 belongs on every command's table, `version` included, because
  Click raises it for an unknown flag on any command.

Verified real per command: `validate` 0/1/2/3 · `doctor` 0/1/2/3 · `adapt`
0/1/2/3 · `test-adapter` 0/1/2 · `ingest` 0/1/2/3 · `query` 0/1/2/3 ·
`evaluate` 0/1/2/3 · `version` 0/2.

### Key invariants

- Mode affects presentation only, never which data is present. This one sentence
  governs colour, glyphs, truncation, and every screen added later.
- The answer paragraph on the plain `query` screen wraps at 72 columns, not at
  the 78 the indent arithmetic would give. That is deliberate and taken from the
  design: running prose reads better on a shorter measure than aligned tables do,
  and it is the only place the tool prints a paragraph. It satisfies AC-2 with
  room to spare rather than sitting at the limit.
- Colour and glyphs come from one shared predicate per stream, never two parallel
  checks that can drift into colour without glyphs or the reverse.
- Rendering never reads a store, a file, or an environment value other than the
  capability variables named above.
- No value is printed that the pipeline does not already compute.

### Critical test scenarios

- Every command renders its happy path in the new grammar, verifies **AC-1**,
  **AC-2**, **AC-3**.
- `NO_COLOR=1`, output to a pipe, output to a file, `TERM=dumb`, and a stream
  whose `encoding` is `None`: each asserts exact bytes, not absence of a crash,
  verifies **AC-4**.
- `query --debug` rendered with a stream that is not a terminal, diffed whole
  against the committed baseline, verifies **AC-5**.
- `evaluate` rendered the same way against its baseline, verifies **AC-6**.
- A corpus large enough that a screen would have truncated: every row is present
  in both modes, verifies **AC-7**.
- A missing required argument and an unknown flag: assert the rendered bytes and
  the stream each is written to, verifies **AC-9**.
- The layering test over the whole source tree, with the single named exemption,
  verifies **AC-11**.

## Build plan

Skateboard: the instrument first, then the thinnest whole screen, then the rest.

1. Capture the two frozen baselines from the **current** build, before any
   rendering change lands, and commit them under
   `docs/experiments/data/cli-baseline/`: a real `query --debug` transcript and
   an `evaluate` report, both captured redirected. A baseline captured after the
   change would certify the change against itself. Satisfies **AC-5**, **AC-6**.
2. Add the layering test asserting the full `AGENTS.md` dependency rule, with
   `application/settings.py:22` as a single named exemption carrying a comment
   that points at the follow up. Satisfies **AC-11**.
3. Build `presentation/render.py`: the capability predicate, the semantic
   palette, the marker sets, and the layout primitives, with unit tests
   asserting exact bytes for every degradation path. Satisfies **AC-3**,
   **AC-4**.
4. Render `doctor` end to end through the module, the first whole screen in the
   new language: header, coverage fields, two aligned tables, skip rows,
   summary. **Update that screen's existing stdout assertions in the same task.**
   Satisfies **AC-1**, **AC-2**, **AC-7**.
5. Render `validate` (both the one record and the corpus screens) and `adapt`,
   including the re sourced path column and the dropped record identity row,
   with their assertions updated in this task. Satisfies **AC-1**, **AC-8**.
6. Render `test-adapter` and `ingest`, including the real `failure_code` row and
   the removal of the invented per record stage words, with their assertions
   updated in this task. Satisfies **AC-1**, **AC-8**.
7. Render plain `query`: the answer block wrapped at 72 columns, the chunk scoped
   source rows, the grounded and consulted counts, and the abstention screen with
   its re sourced refs and static hint, with its assertions updated in this task.
   Satisfies **AC-1**, **AC-8**.
8. Install the `error` then `hint` then `exit` grammar across the six restyled
   commands using the hint table above, including the Click usage error
   override, with tests pinning the rendered bytes and the stream for a missing
   required argument and an unknown flag. Satisfies **AC-9**.
9. Rewrite the help screens for all eight commands with the real flags and the
   real exit codes. Satisfies **AC-10**.
10. Only now, add colour to the two frozen surfaces, and wire the baseline diff
    tests that render each with a stream that is not a terminal and compare whole
    against task 1's files. Until this task the three frozen printers are not
    edited at all. Satisfies **AC-5**, **AC-6**.
11. Refresh the transcripts in `README.md` and `docs/user-guide.md`, add the
    `presentation` layer and the composition root note to `AGENTS.md`, and update
    scope feature 15's "done when" from seven commands to eight.

Each screen's assertions move in the task that changes that screen, rather than
in one sweep at the end. A single trailing task would leave the unit suite red
across seven milestones, which the project's per milestone commit policy and its
push time CI both make expensive.

## Consequences

**Positive**:

- One grammar across every command: a reader learns it once and every screen,
  including failures, reads the same way.
- Every failure names a fix and its exit code, instead of only reporting that
  something broke.
- The instruments keep working by construction rather than by a protected string
  list, so an experiment script written next year is safe too.
- The human report and the machine trace stop being a tradeoff: nobody has to
  choose between a readable trace and a parseable one.
- `AGENTS.md` has claimed a four layer dependency rule since the first commit and
  nothing has ever checked it. After this, the suite does, and one real
  violation becomes visible and counted instead of invisible.
- No new runtime dependency, and no new flag or environment variable.

**Negative / tradeoffs**:

- About 200 lines of hand written rendering, whose real cost is the degradation
  paths (`NO_COLOR`, piped, not a terminal, ASCII fallback), each needing its own
  byte exact test. That is where a hand rolled renderer actually fails and where
  Rich would have earned its keep.
- Overriding Click's error rendering touches framework internals, so a Typer or
  Click upgrade can silently revert those screens to default styling. The pinning
  tests in task 10 are what make that fail loudly, and without them this decision
  should be reversed to leaving usage errors alone.
- The exact hex and ANSI 256 palettes from the design are not emitted. Colours
  are the terminal's, so two readers on different themes see different shades of
  the same meaning.
- Two surfaces are frozen, so `query --debug` and `evaluate` stay in the old
  layout on a pipe forever, or until a separate decision unfreezes them.
- `query --debug | cat` and `query | cat` render the answer differently. That is
  coherent only because this spec states it.
- On a large corpus, `doctor` and `adapt` print long output with no truncation.
  Acceptable because both are occasional diagnostics rather than loops, and
  terminals have scrollback. If compactness genuinely bites later, the answer is
  an explicit `--limit` with a stated default, decided then against a real corpus
  size, not hidden rows now.
- 120 existing stdout assertions move, which is real review surface even though
  each change is small.

**Neutral**:

- A new `presentation` package appears beside `cli.py`. `cli.py` stays outside it
  on purpose, as the composition root; this is stated in `AGENTS.md` so a later
  reader does not "finish" the move.
- The design document keeps its hex tables as documented intent for anyone
  porting this language to another surface.
- Scope feature 15's acceptance list grows from seven commands to eight.

## Follow-up

- [ ] Invert the `application/settings.py` dependency on
      `infrastructure.project_config`: a port in `application`, the concrete
      reader wired at the composition root, the same shape already applied to
      `adapt_corpus` and `validate_file`. Then remove the exemption from the
      layering test.
- [ ] Rename `MODEL_ENTAILMENT_COVERAGE` and fix the `openai_generation` module
      docstring: coverage uses `gpt-4o`, not `gpt-4o-mini`. The name and the
      docstring both say otherwise, and the docstring is what led the design to
      state the wrong mapping.
- [ ] Repair or delete the two stale regexes in
      `docs/experiments/data/coverage-directness-extract.py` that expect
      lowercase `c1` citation ids while the code emits `C1`. They have never
      fired, because every captured transcript in that run abstained.
- [ ] Decide whether a true providers and models line belongs in the debug
      trace. It cannot be added under this spec's frozen surface rule, and it
      would need its own decision about unfreezing or about a new surface.
- [ ] Decide whether `query --debug` should stay frozen permanently. The freeze
      buys instrument safety and costs the trace ever getting the new language on
      a pipe; revisit once the experiment programme settles.
