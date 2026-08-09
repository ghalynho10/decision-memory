# 0004. Doctor diagnostic

**Date**: 2026-08-08
**Status**: In Progress

_Decision history (context, options considered, rationale, references): [rationale.md](rationale.md)._

## Summary

The `doctor` command surveys an unfamiliar Markdown corpus without creating decision records or guessing what its headings mean. It reports coverage, common H2 headings, exact heading set groups, and every important exclusion or read failure. The implementation uses a small standard library scanner so its rules stay narrow, deterministic, and easy to test.

## Requirements

**User stories**:

- As a person evaluating an unfamiliar decision corpus, I want a structural survey so I can judge whether an adapter is likely to fit.
- As a maintainer, I want every excluded or unreadable path accounted for so partial coverage never looks complete.

**Acceptance criteria** (the contract, each criterion is IDed and independently checkable):

- **AC-1**: `decision-memory doctor DIRECTORY [--samples INTEGER]` accepts one directory. `--samples` is a nonnegative integer, defaults to `3`, controls samples for heading set groups and skip reasons, and suppresses sample fields when it is `0`. A negative value is a Typer `BadParameter`, returns exit code `2`, and prints no survey report.
- **AC-2**: The command recursively inspects regular files ending in `.md`, `.markdown`, or `.mdown` without regard to case. It excludes descendant directories whose name starts with `.`, but an explicitly supplied hidden root and a hidden Markdown file inside an inspected directory remain eligible. It resolves a symbolic link chain only when that chain is the root path explicitly supplied by the user, requires the resolved target to be a directory, and never opens or descends through a symbolic link found below that root. It may inspect only the target type of a descendant link so a directory target is reported as an unseen subtree. Displayed paths are relative to the resolved root, use POSIX separators, and use `.` for the root itself.
- **AC-3**: Traversal and every displayed collection are deterministic. Directory entries and corpus relative paths are sorted explicitly rather than relying on filesystem order. Heading groups sort by file count descending, then their sorted exact heading tuple. Headings inside a group sort by exact text. Skip reasons use the fixed order in `## Feature design`.
- **AC-4**: Markdown is read as strict UTF 8, with one leading UTF 8 BOM removed and CRLF or CR normalized to logical line breaks. H2 and fence recognition follow the complete grammar in `## Feature design`. A matching heading after an unmatched fence opener still counts, which intentionally matches the shipped adapter rather than full CommonMark fence behavior (basis: CommonMark ATX headings, CommonMark fenced code blocks, and spec 0003).
- **AC-5**: Each distinct H2 counts at most once per file. The common headings section lists every distinct H2 with its analyzed Markdown file count and percentage of all analyzed Markdown files, including analyzed files with no H2. Percentage is `100 × file count ÷ analyzed Markdown count`, rendered to one decimal place with decimal round half up. Rows sort by file count descending, then exact heading text. With zero analyzed Markdown files, there are no heading rows and the report states that no heading evidence was found.
- **AC-6**: Files are grouped by the exact set of their H2 text. Heading order and duplicate occurrences do not change group identity. An analyzed Markdown file with no H2 belongs to an explicit empty heading set group. Groups show their file count and up to the requested number of corpus relative sample paths.
- **AC-7**: The coverage summary reports analyzed Markdown files, regular non Markdown files ignored, and skipped totals by the closed reason set in `## Feature design`. Every path observed by traversal receives the first applicable classification exactly once. Each skip reason shows up to the requested number of sorted corpus relative sample paths. An unreadable directory is reported once with unknown contents, and the report never estimates what was below it.
- **AC-8**: Output follows the normative report contract in `## Feature design`, including exact section labels, row shapes, ordering, JSON style escaping, empty set rendering, and sample suppression. It prints no adapter verdict and makes no semantic inference from heading names.
- **AC-9**: An unreadable Markdown file, unreadable directory, strict UTF 8 decoding failure, or path that disappears after discovery is reported and does not stop the remaining survey. An unreadable resolved root produces one `unreadable directory` skip for `.`. A completed survey returns exit code `0` even when it reports skips. An empty corpus also returns `0` and states that no heading evidence was found.
- **AC-10**: A missing root, broken or cyclic root symbolic link chain, or resolved root that is not a directory returns exit code `3`. This reuses the unusable corpus convention from spec 0003 AC 21. Unexpected run failure returns `1`, while command syntax errors retain Typer's existing behavior.
- **AC-11**: The command performs no writes, produces no canonical decision records, opens or descends through no descendant symbolic links, uses no network access, and requires no environment variables.

## Decision

**Chosen option**: Option 1: Dedicated standard library scanner

Build a narrow read only scanner, a pure aggregation use case, and a Typer report formatter. Keep traversal and text decoding in infrastructure, exact grouping rules in the domain, orchestration in application, and formatting in the command line layer (basis: `AGENTS.md`, the Clean Architecture dependency rule).

## Feature design

**Data model sketch**:

No data is persisted. The feature uses immutable plain objects for one command run.

| Type | Layer | Required fields and rules |
|---|---|---|
| `DoctorRequest` | application | `root: Path`, `samples: int` where samples is at least zero |
| `SurveyedDocument` | domain | `relative_path: str`, `h2_headings: frozenset[str]` |
| `SkippedPath` | domain | `relative_path: str`, `reason: SkipReason`, `unseen_contents: bool`; reason comes from the closed ordered set below |
| `ScanResult` | application boundary | surveyed documents, ignored non Markdown count, skipped paths |
| `HeadingFrequency` | domain | exact heading, file count, percentage |
| `HeadingSetGroup` | domain | sorted heading tuple, file count, sorted sample paths |
| `DoctorOutcome` | application DTO | coverage totals, heading frequencies, heading set groups, skip summaries, exit code |

There are no identifiers, foreign keys, relationships, stored lifecycle states, or migrations.

**API surface**:

| Endpoint | Method | Key inputs | Key outputs | Auth | Key errors |
|---|---|---|---|---|---|
| `decision-memory doctor DIRECTORY [--samples INTEGER]` | CLI | directory path, samples integer optional | coverage, common headings, exact groups, skips, exit code | local user | `3` missing or non directory root, Typer syntax error, `1` unexpected failure |

**Parser grammar**:

| Construct | Exact rule |
|---|---|
| Text decoding | Decode strict UTF 8, remove one leading UTF 8 BOM, then normalize CRLF and CR to LF |
| H2 opener | Zero through three ASCII spaces, exactly `##`, at least one ASCII space or tab, then heading text. A bare `##` at end of line is not a heading. `## ` is an empty heading |
| H2 text | Strip leading and trailing ASCII spaces and tabs. Then remove an unescaped closing `#` run only when whitespace precedes it and only ASCII spaces or tabs follow it. Strip surrounding ASCII spaces and tabs again. Preserve all remaining case, punctuation, links, inline markup, and Unicode code points |
| Fence opener | Zero through three ASCII spaces, then at least three backticks or at least three tildes. A backtick opener's remaining text cannot contain a backtick |
| Fence closer | Zero through three ASCII spaces, the same marker character repeated at least as many times as the opener, then only ASCII spaces or tabs |
| Closed fence interval | The opener, its contents, and its first valid closer are excluded from heading recognition. An opener with no valid closer creates no excluded interval, so later H2 lines remain eligible |

The scanner establishes closed fence intervals before it classifies headings. A one pass state machine that treats every opener as closed until end of file would violate the unmatched fence rule.

**Path classification**:

For each observed descendant path, use the first matching row. A metadata call that says the path no longer exists uses `disappeared`. Other metadata failures use `unsupported entry` with the operating system reason.

| Order | Classification | Result |
|---|---|---|
| 1 | Path disappeared | skip reason `disappeared` |
| 2 | Symbolic link | skip reason `descendant symbolic link`, regardless of its name or target. Query only whether its target is a directory, never open or descend through it. A directory target sets `unseen_contents` true. A broken, cyclic, or unreadable target leaves it false |
| 3 | Directory whose name starts with `.` | skip reason `hidden directory`, do not inspect contents, set `unseen_contents` true |
| 4 | Other directory | inspect it; an access failure becomes skip reason `unreadable directory` with unknown contents |
| 5 | Regular file with an eligible Markdown suffix | read it; access or strict decoding failure becomes skip reason `unreadable Markdown file`, otherwise analyze it |
| 6 | Other regular file | increment ignored non Markdown count |
| 7 | Any other entry or metadata failure | skip reason `unsupported entry` |

Skip reasons display in this fixed order: `disappeared`, `descendant symbolic link`, `hidden directory`, `unreadable directory`, `unreadable Markdown file`, `unsupported entry`. Every displayed skip row always reports `unseen subtrees`, including `unseen subtrees: 0`, using the count of its `SkippedPath` values whose `unseen_contents` is true. An unreadable directory always sets it true.

**Report contract**:

All headings and paths use `json.dumps(value, ensure_ascii=False)` serialization. This preserves Unicode while escaping quotes, backslashes, and control characters. Heading sets use JSON array syntax, so the empty set is `[]`. When samples is zero, every `samples` line is omitted. This fixture fixes labels and row shapes. Ellipses stand only for repeated rows of the same fixed shape.

```text
coverage
  markdown analyzed: 3
  non markdown ignored: 2
  skipped: 1
common H2 headings
  "Context" | files: 2 | percent: 66.7%
  ...
exact H2 heading sets
  ["Context", "Decision"] | files: 2
    samples: ["adr/0001.md", "adr/0002.md"]
  [] | files: 1
    samples: ["notes.md"]
skipped
  descendant symbolic link | count: 1 | unseen subtrees: 1
    samples: ["linked.md"]
```

Individual zero count skip reasons are omitted. When every skip reason has count zero, the `skipped` section contains the literal line `none`. Exact heading set groups use the order in **AC-3**. Skip rows use the fixed reason order above. This second normative fixture defines the zero case.

```text
coverage
  markdown analyzed: 0
  non markdown ignored: 0
  skipped: 0
common H2 headings
  no heading evidence found
exact H2 heading sets
  no heading sets found
skipped
  none
```

**Value sourcing**:

| Action | Value produced or displayed | Source |
|---|---|---|
| Traverse corpus | analyzed Markdown count | Eligible Markdown paths that were read and decoded successfully |
| Traverse corpus | ignored non Markdown count | Regular files whose suffix is not one of the three eligible suffixes |
| Traverse corpus | skipped totals, unseen subtree counts, and samples | One `SkippedPath` per explicit exclusion or filesystem failure, grouped by reason; unseen subtree count is the sum of true `unseen_contents` values |
| Analyze headings | heading file count | Membership of the exact heading in each document's unique H2 set |
| Analyze headings | heading percentage | `100 × heading file count ÷ analyzed Markdown count`, rendered with `Decimal` round half up to one decimal place; no row when the denominator is zero |
| Group documents | exact heading set group count | Equality of each document's H2 set, including the empty set |
| Group documents | sample paths | Corpus relative paths in the group, sorted and limited by `DoctorRequest.samples` |
| Format report | labels, row shapes, escaping, empty set form, and section order | The normative fixture and serialization rules in **AC-8** |
| Complete command | exit code | Root validation, completed survey status, or unexpected failure per **AC-9** and **AC-10** |

**Key invariants**:

- Every analyzed Markdown path contributes to exactly one heading set group.
- Every path observed by traversal receives exactly one classification: analyzed Markdown, ignored non Markdown, or one skip reason.
- An unreadable directory is counted once with `unseen_contents` true. The report never claims to know how many files were below it.
- Heading frequencies use file presence, never occurrence count.
- Sorting is explicit at every output boundary.
- Sample limits change examples only, never totals or grouping.
- The scanner never opens or descends through a descendant symbolic link. It may query only whether the target is a directory to set `unseen_contents`.

**Security model**:

The command reads files available to the local operating system user and writes nothing. It resolves an explicitly supplied root symbolic link once. For descendant links it may query whether the target is a directory only to report an unseen subtree, but it never opens the target or descends through it. Sample paths are corpus relative, so the report does not expose unrelated absolute paths. No regulated data, remote service, authentication, or authorization model applies.

**Critical test scenarios**:

- Happy path: a mixed nested corpus produces stable coverage, heading frequencies, exact groups, and limited samples, verifies **AC-1**, **AC-2**, **AC-3**, **AC-5**, **AC-6**, and **AC-8**.
- Parsing case: table driven fixtures cover decoding, BOM, line endings, whitespace, empty headings, closing hashes, both fence markers, closer lengths, closed fences, and an unmatched fence, verifies **AC-4** and **AC-5**. One shared fixture, an unmatched fence opener followed by an H2, is asserted through both the new doctor scanner and the shipped adapter scanner so their agreed behavior cannot drift.
- Coverage case: hidden directories, hidden Markdown files, mixed suffix casing, descendant file and directory links, unreadable entries, and a disappearing file are all classified without stopping the run. A directory link reports one unseen subtree without traversal, verifies **AC-2**, **AC-7**, **AC-9**, and **AC-11**.
- Input case: empty, missing, file, hidden root, unreadable root, negative samples, and root symbolic link chain inputs produce the fixed reports and exit codes, verifies **AC-1**, **AC-9**, and **AC-10**.

## Build plan

1. Ship the thinnest usable whole: add the request and outcome DTOs, the pure heading aggregation rules, a readable tree scanner, the `doctor` command, and the four report sections for a normal corpus, satisfies **AC-1**, **AC-5**, **AC-6**, and **AC-8**.
2. Make parsing exact: implement and test the ATX H2 and fence grammar without changing the adapter parser. Add one shared unmatched fence fixture and assert its later H2 through both scanners, satisfies **AC-4**.
3. Make coverage honest: add hidden path, suffix, symbolic link, unreadable entry, unsupported entry, and transient disappearance accounting with deterministic samples, satisfies **AC-2**, **AC-3**, **AC-7**, **AC-9**, and **AC-11**.
4. Fix the command boundary: enforce sample validation, root symbolic link behavior, empty corpus output, and the established exit code contract, then cover the full Typer flow, satisfies **AC-1**, **AC-9**, and **AC-10**.

## Consequences

**Positive**:

- A user can inspect corpus shape before trusting an adapter.
- Complete coverage accounting makes partial surveys visible.
- Exact rules and stable sorting make reports reproducible and tests durable.
- The feature adds no package, persistence, or network requirement.

**Negative / tradeoffs**:

- The project owns a second narrow Markdown scanner.
- Exact text comparison treats case, punctuation, inline markup, and Unicode representation differences as different headings.
- Exit code `0` can still mean partial coverage, so automation must inspect the coverage section rather than treating success as completeness.
- Following an explicit root symbolic link means the user can intentionally survey outside the link's parent tree.

**Neutral**:

- `doctor` describes structure and does not recommend an adapter.
- Unseen files below an unreadable directory cannot be included in totals, so the report names that uncertainty instead.
