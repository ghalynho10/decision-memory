# 0013. CLI presentation redesign, reasoning

Reasoning, options, and the evidence behind
[index.md](index.md). Not read during a build.

## Context

The CLI prints with bare `typer.echo` calls scattered through `cli.py`. Each
command grew its own shape as it was built, so there is no shared grammar: no
consistent header, no section labels, no aligned columns, no summary line, and
no standard failure format. A reader cannot answer the three questions a report
should answer at a glance, which are what command ran, what succeeded versus
skipped versus failed, and what to do next. Errors print a bare sentence with no
fix and no exit code, and Typer's own usage errors look different again.

A full external design already exists at
`docs/reference/artifact/decision-memory-cli-redesign.pdf`: 25 pages of 80
column transcripts, before and after, for every command, plus error screens and
edge cases. It is good, and the task is to build from it rather than redesign
it. But it was drawn against an idea of the tool rather than against the tool,
so parts of it describe a program that does not exist. Three kinds of drift
matter here: an invented statement about the tool's own providers, an
implementation sketch built on a library the project does not depend on, and
numbers on several screens whose source was never checked against the pipeline.

Two constraints bound the work hard. First, scope feature 15's guardrail:
presentation only, with no new command, no new or renamed flag, no changed exit
code, no changed DTO field, and no retrieval or storage change. Second, and
discovered during this design, parts of the CLI's output are not human facing
prose at all. They are a machine interface that committed experiment
instruments parse, and those instruments fail quiet: a changed line prefix makes
a grep return nothing, which the next reader interprets as "no cause found"
rather than as a broken tool. The abstention attributions in experiments 0009
and 0012 were produced that way.

The cost of not deciding is that the design gets built literally, printing a
false statement about which models the tool uses, silently breaking the
instruments that several experiments depend on, and adding a dependency by
default rather than by decision.

## Options considered

### Option 1: build the design's sketch on Rich

Take pages 21 and 22 as written: `rich.theme.Theme` for the dark and light
palettes, `Console(theme=..., width=80)`, and `rich.table.Table` for the ranked
and grouped tables.

**Pros**:

- Least code to write; the sketch is already drawn against this API.
- Detection of a stream that is not a terminal, and the styling strip that
  follows, comes free.
- Exact hex colours render on any terminal with truecolor support, so the
  design's palette ships as specified.

**Cons**:

- A new runtime dependency, and its `pygments` and `markdown-it-py` chain, for a
  tool whose output is deliberately plain.
- The design's own "deliberately not done" list rules out every Rich feature
  that would justify it: no live regions, no spinners, no panels, no boxes.
- `Table`'s value is dynamic width computation, and this design fixes every
  width at 80 columns, so the main feature is the one already declined.
- A stack change in `AGENTS.md` for capability the project does not use.

### Option 2: internal renderer reproducing the exact palettes

Write the module by hand, but emit the design's exact hex or ANSI 256 values,
with a `is_light_term()` implementation to choose between the dark and light
tables.

**Pros**:

- No dependency, and the designer's palette ships byte for byte.
- Full control over every escape sequence.

**Cons**:

- Light terminal detection is not reliably possible. `COLORFGBG` is set by rxvt,
  Konsole, and a few others, and is not set by Terminal.app, iTerm2, the VS Code
  terminal, Windows Terminal, kitty, or Alacritty. On the terminals this tool's
  readers actually use, the heuristic does not fire.
- So it degrades to "dark by default" plus a detection path that rarely runs,
  plus an environment variable escape hatch nobody discovers. That is the worst
  shape of the three: paying for a heuristic that is absent on the common case.
- More code to test, in the part most likely to be wrong.

### Option 3: internal renderer with semantic ANSI 16 colours (chosen)

Write the module by hand and colour with the sixteen named ANSI indices, chosen
for what each token means. The terminal resolves them against its own theme.

**Pros**:

- No dependency, no detection code, and both light and dark look native, because
  the decision is handed to the only component that knows the answer.
- What `gh`, `git`, `cargo`, and `ripgrep` do.
- `is_light_term()` never needs to exist, so neither does a test for it, and no
  new flag or environment variable is added.

**Cons**:

- The exact hex and ANSI 256 values are not emitted; two readers on different
  themes see different shades of the same meaning.
- The two greys collapse: `muted` and `dim` both tend toward bright black.
- About 200 lines to write, whose real cost is the degradation paths.

### Option 4: a development only formatter

Use Rich in tests or tooling to check alignment while shipping plain ANSI.

**Pros**:

- Alignment gets an independent check.

**Cons**:

- Two rendering paths that must agree, with nothing forcing them to. This
  project already refused that shape once, when spec 0010 made
  `classify_decomposition` a derivation of `classify_decomposition_detail`
  rather than a parallel implementation, so the disposition and its
  observational detail can never disagree. A formatter that must match the
  shipped one has exactly that defect.

## Rationale

**On the renderer.** Rich earns its keep through dynamic layout: computed column
widths, live regions, panels, spinners. This design fixes every width at 80
columns and its own "not done" list declines the rest, so option 1 buys a
`Table` class whose main feature the design has already decided not to use, at
the price of a dependency chain. Option 2 fails on a fact about terminals rather
than on taste: the detection it needs does not work where it would matter, so it
collapses into a dark default wearing a heuristic. Option 4 is refused on this
project's own precedent. Option 3 remains, and the loss it takes is smaller than
it looks, because the palette is semantic: `ok` is green because it means ok, not
because green is `#57c785`. That framing is what makes the choice coherent
rather than a downgrade, and it is the rule that stops a later contributor
reintroducing exact colours one token at a time. The one genuine loss, the two
greys, is repaired with the faint attribute rather than by picking two indices
that read alike on half of all themes.

**On the frozen surfaces.** The first instinct was to name the strings the
instruments depend on and hold those byte identical. That was rejected by
evidence gathered while checking it: a list of six greps in one script turned out
to be twelve anchored regexes in a second script, plus a third reading a section
prefix, on a surface believed to be already checked. A list of anchors protects
what somebody happened to find and fails quiet for everything else, which is the
worst failure mode available here. One invariant, stated over the mode rather
than over the content, covers the instruments nobody has looked at yet. It also
changes the verification from a partial check to a total one: diffing piped
output against a committed baseline proves the whole surface survived, where
grepping six strings only ever proves those six did.

The invariant also dissolves what looked like a tradeoff. The human report and
the machine trace no longer compete: the trace gets colour where a human reads
it, and exact bytes where a script reads it, and neither is compromised for the
other.

A stricter variant was weighed and declined: freeze the two surfaces completely,
so they never gain colour even on a terminal. It is genuinely simpler, since the
highest risk task in the plan is the one that touches the very surface the
feature exists to protect, and it would remove the precedence question between
the freeze and the error grammar by removing one side of it. It was declined
because a person does read the debug trace on a terminal, often while debugging
an abstention, and leaving one surface in the old language there is the seam this
feature exists to close. The precedence question is answered explicitly instead,
in AC-9, and the risk is bounded by doing that work last against a baseline
captured first.

**On the guardrail.** Correction 3's findings could each be repaired by a small
additive DTO field, and that was the tempting path. It was refused because a
changed DTO field means the affected tests move, and a presentation task must
not be able to invalidate a measurement. Deciding it per screen was refused for a
different reason: eight individual rulings are eight chances to say yes to the
one that turns out to matter, and that is how a guardrail becomes negotiable.
Where a screen is genuinely worse for lacking a value, it is recorded in Follow
up as a candidate for its own decision rather than smuggled in here.

**On truncation.** The design elides long lists. Dropping the elision follows
from the mode rule already adopted for the debug trace: mode may change style
and must never change content. Allowing truncation on a terminal only would mean
mode changes style in one place and hides data in another, which is two rules
wearing one principle, and the next screen would have no way to tell which
applies. There is also a plain usability problem, since no `--full` flag may
exist: a reader who sees "20 more rows" would have no way to see them except by
discovering that piping to `cat` changes the output, which nobody guesses.

**On the layering test.** `AGENTS.md` has claimed four layers with a dependency
rule since the beginning, and nothing has ever verified it. The test is written
to the whole stated rule rather than to the renderer alone, and it is known to
find one violation on arrival, in code this feature may not touch. Naming that
violation as a single exemption with a follow up attached is honest; narrowing
the assertion until it passes would produce a guardrail that certifies whatever
it finds.

## Evidence: the design checked against the code

Read on 2026-08-15 against the working tree at commit `94b731e`.

### Correction 1, providers

`openai_generation.py` sets `MODEL_FACETS_AND_ANSWER = "gpt-4o"` (line 35) and
`MODEL_ENTAILMENT_COVERAGE = "gpt-4o-mini"` (line 36). The call sites are what
decide, and they are:

| Concern | Model | Line |
|---|---|---|
| facets | `gpt-4o` | 634 |
| answer | `gpt-4o` | 698 |
| entailment | `gpt-4o-mini` | 750 |
| **coverage** | **`gpt-4o`** | **799** |
| decompose | `gpt-4o-mini` | 855 |
| embedding | `text-embedding-3-small` | `pipeline.py:19` |

Coverage uses `gpt-4o`, contradicting both the module docstring at lines 10 to
12 and the constant's own name. The one other place in the repository that
records this mapping, the `CONCERN_MODEL` table in
`docs/experiments/data/coverage-directness-extract.py`, agrees with the call
sites. So the correction that the design's providers line is invented is right,
and the replacement text that circulated with it inherited the docstring's
error.

### Correction 2, Rich

`pyproject.toml` dependencies are `chromadb`, `openai`, `pydantic`, `pyyaml`,
`rank_bm25`, `tiktoken`, and `typer`. No `rich`, in runtime or dev. Every line
the CLI prints today goes through `typer.echo`, and `cli.py` never writes to
standard error.

### Correction 3, value by value

Confirmed derivable, no plumbing needed:

- `grounded in N of M consulted records` and `M minus N records offered no
  supporting evidence`. `FusedCandidate` carries `record_id`, and
  `DiversityTrace.accepted_chunk_ids` names the accepted set, so both counts
  come from a join inside the trace the result already carries.
- Every doctor field, every validate and adapt discovery total, every
  test-adapter coordinate, every ingest action and chunk count, and every
  citation column.
- The per source path column on the corpus validation screen, by joining the
  result id to `DiscoveredSpec.root`.
- The adapter identity row `jsmastery-specs 5`, which is `adapter_id` plus
  `adapter_version` and is already what the code prints.

Confirmed not derivable, listed with the reason in
[index.md](index.md): record titles in the query trace, the index build
timestamp, per record ingest stage flags, and the record identity on a single
record validation. One design value describes something that cannot happen: a
per record "provider lock held" row, when a lock aborts the entire command at
`cli.py:707`. One names a state that does not exist: `dropped (low)`, when
`relevance_floor` is hardcoded `None` at `query.py:1282` and the real
dispositions are `ranked`, `outside_top_24`, `accepted`, and `outside_top_8`.

### The interface the design does not know about

- `evaluate` is a real eighth command (`cli.py:1203`), documented in `README.md`
  beside `ingest` and `query`. Root help in the design lists seven.
- `query` accepts `--record-id`, `--status`, `--tag`, and `--value-path`. The
  design's help screen shows none of the four.
- `doctor` can exit 2, because `_validate_samples` raises `typer.BadParameter`
  on a negative value. Its table lists 0, 1, and 3.

### The instruments that read CLI output

| Instrument | Reads | How |
|---|---|---|
| `jobpilot-abstention-cause.sh` | `query --debug` | greps six tokens including `reason=no emitted answer sentence`, `uncovered F`, `dropped_sentence`, `state:`, `abstention_stage:` |
| `coverage-directness-extract.py` | `query --debug` | twelve anchored regexes, including exact 2 and 4 cell indents such as `^  (F\d+) covered=...` and `^    contained=...` |
| `compare-retrieval.py` | `query --debug` | the `  accepted: ` prefix from the Diversity section |

All three capture redirected output, never a terminal, which is why the mode
based invariant covers them by construction. Two of the extractor's regexes are
already stale: they expect lowercase `c1` citation ids while `query.py:1154`
allocates `C1`. They have never fired, because every transcript captured in that
run abstained and produced no citations. That is a pre existing defect this
feature does not cause and does not fix.

A sweep for consumers of plain `query` output (without `--debug`) across
`docs/experiments/data/`, `README.md`, and `docs/user-guide.md` found none:
every script passes `--debug`. The README and user guide quote transcripts for
human readers, so they are refreshed rather than frozen.

### The layer rule as it stands today

Checked across `src/decision_memory/`:

- `domain` imports nothing outward. Clean.
- `application` imports from `infrastructure` in exactly one place:
  `application/settings.py:22`, `from
  decision_memory.infrastructure.project_config import ProjectConfig`, at module
  level, not under `TYPE_CHECKING`.
- No Typer, Pydantic, Chroma, or OpenAI import appears anywhere in `domain` or
  `application`. Clean, and worth locking before it stops being true.

### Test surface

120 assertions on standard output across 13 test files, importing `app` and
three private print helpers (`_print_query_debug`, `_print_adapt_report`,
`_print_query_report`) from `decision_memory.cli`. Keeping `cli.py` where it is
avoids a re export shim whose only job would be to keep those imports working.
