"""Parse tests for the jsmastery adapter (spec 0003).

Covers the field mapping, precedence and stub rules, the winner ladder,
attempted fields, code path extraction, and the AC-16 failure path.
"""

from __future__ import annotations

from pathlib import Path

from spec_factory import INDEX, RATIONALE, make_corpus, write_spec

from decision_memory.domain.records import EvidenceKind, Status
from decision_memory.infrastructure.jsmastery_adapter import JsmasteryAdapter


def _adapt(corpus: Path) -> object:
    discovery = JsmasteryAdapter().discover(corpus)
    assert len(discovery.specs) == 1
    return JsmasteryAdapter().parse(discovery.specs[0])


STUB_INDEX = """\
# 0005. Stub options

**Date**: 2026-08-07
**Status**: Accepted

## Summary

The stub sections must fall through to rationale.md.

## Context

Real context lives in index.md here, but rationale.md wins.

## Decision

**Chosen option**: Option 1: Build an internal state machine

## Options considered

See [rationale.md](rationale.md).

## Consequences

**Positive**:
- Good.

## Rationale

See [rationale.md](rationale.md).
"""

STUB_RATIONALE = """\
# 0005. Stub options

## Context

The full rationale context for the stub spec.

## Options considered

**Option 1:** Build an internal state machine
**Pros**: Full control.
**Cons**: More code.

**Option 2:** Use a hosted provider
**Pros**: Less code.
**Cons**: Cost.

## Rationale

The internal state machine is the chosen approach.
"""

TITLE_MATCH_INDEX = """\
# 0006. Background jobs

**Date**: 2026-08-07
**Status**: Proposed

## Decision

**Chosen option**: Background job via BullMQ

## Rationale

See [rationale.md](rationale.md).
"""

TITLE_MATCH_RATIONALE = """\
# 0006. Background jobs

## Options considered

**Option 1:** Background job via BullMQ (recommended)
**Pros**: Reliable.
**Cons**: Needs a worker.

**Option 2:** Inline processing
**Pros**: Simple.
**Cons**: Blocks the request.

## Rationale

- BullMQ is the established queue in the stack.
- Workers already exist for other jobs.
"""

PANEL_INDEX = """\
# 0012. Portfolio private access gate

**Date**: 2026-08-07
**Status**: Accepted

## Summary

The gate before private portfolio pages.

## Decision

**Chosen option**: Option B, revised. Option A was picked first, then dropped.

## Options considered

See [rationale.md](rationale.md).

## Consequences

**Positive**:
- Private pages are protected.

**Negative**:
- More code.

## Rationale

See [rationale.md](rationale.md).
"""

PANEL_RATIONALE = """\
# 0012. Portfolio private access gate

## Context

The portfolio is public today; private pages need a gate.

## Options considered

### Panel 1
**Question**: Should the gate be synchronous?
**Decision**: Option A, chosen for simplicity.
**Option A —** Synchronous request/response (chosen)
**Pros**: Simple to reason about.
**Cons**: Blocks the request.

**Option B —** Async worker
**Pros**: Non blocking.
**Cons**: More moving parts.

### Panel 2
**Question**: Where should state live?
**Decision**: Option A, client side.
**Option A —** Client side state (chosen)
**Pros**: No server round trip.
**Cons**: Can go stale.

**Option B —** Server side state
**Pros**: Always current.
**Cons**: More server work.

### Panel 3
**Question**: Which provider?
**Decision**: Option B, revised. Option A was picked first, then dropped.
**Option A —** Hosted provider (chosen)
**Pros**: Little code.
**Cons**: Cost.

**Option B —** Internal service
**Pros**: No recurring cost.
**Cons**: More work.

## Rationale

The gate is served by the chosen options.
"""

UNRESOLVED_RATIONALE = """\
# 0012. Portfolio private access gate

## Context

The portfolio is public today.

## Options considered

### Panel 1
**Question**: Which provider?
**Option A —** Hosted provider
**Pros**: Little code.
**Cons**: Cost.

**Option B —** Internal service
**Pros**: No recurring cost.
**Cons**: More work.

## Rationale

The gate is served by an option.
"""

CODE_INDEX = """\
# 0013. Code paths

**Date**: 2026-08-07
**Status**: Accepted

## Decision

**Chosen option**: Option 1: Wire the page

## Options considered

**Option 1:** Wire the page
**Cons**: Work.

## Rationale

See [rationale.md](rationale.md).

## Build plan

- Touch `app/dashboard/page.tsx:67`.
- Use `lib/` for shared helpers.
- Never route through `/dashboard`.
- Package `@insforge/cli`.
- Glob `app/api/**/route.ts`.
- Run `uv run decision-memory`.
- The typo `App/Dashboard/Page.Tsx` must not resolve.
"""

CODE_RATIONALE = """\
# 0013. Code paths

## Rationale

Wiring the page keeps the change small.
"""


def test_maps_title_stripping_number_prefix(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    write_spec(corpus, "0012-portfolio-private-access-gate")
    result = _adapt(corpus)
    assert result.record is not None
    assert result.record.id == "DM-0012"
    assert result.record.title == "Portfolio private access gate"


def test_status_maps_with_raw_preserved_as_tag(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    write_spec(corpus, "0001-first")
    result = _adapt(corpus)
    assert result.record.status == Status.ACCEPTED
    assert result.record.tags == ["source-status:Accepted"]


def test_in_progress_status_maps_to_proposed_with_tag(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    index = INDEX.replace("**Status**: Accepted", "**Status**: In Progress")
    write_spec(corpus, "0001-first", index=index)
    result = _adapt(corpus)
    assert result.record.status == Status.PROPOSED
    assert result.record.tags == ["source-status:In Progress"]


def test_rationale_context_wins_over_index(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    write_spec(corpus, "0001-first")
    result = _adapt(corpus)
    assert "The full context lives here" in result.record.context.problem


def test_alternatives_pool_non_winning_options_with_cons(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    write_spec(corpus, "0001-first")
    result = _adapt(corpus)
    assert result.record.decision.chosen == "Option 1: Build an internal state machine"
    alternatives = result.record.decision.alternatives
    assert len(alternatives) == 1
    assert alternatives[0].title == "Use a hosted provider"
    assert "Cost and a third party" in alternatives[0].rejection_reason
    assert result.attempted_fields == frozenset()


def test_winner_resolves_by_title_match_when_ordinal_dropped(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    write_spec(
        corpus, "0006-bg", index=TITLE_MATCH_INDEX, rationale=TITLE_MATCH_RATIONALE
    )
    result = _adapt(corpus)
    assert result.record.decision.chosen == "Background job via BullMQ"
    alternatives = result.record.decision.alternatives
    assert [alternative.title for alternative in alternatives] == ["Inline processing"]
    assert "Blocks the request" in alternatives[0].rejection_reason
    assert result.record.why == [
        "BullMQ is the established queue in the stack.",
        "Workers already exist for other jobs.",
    ]


def test_stub_sections_fall_through_to_rationale(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    write_spec(corpus, "0005-stub", index=STUB_INDEX, rationale=STUB_RATIONALE)
    result = _adapt(corpus)
    assert "The full rationale context" in result.record.context.problem
    assert result.record.decision.alternatives
    assert (
        result.record.rationale_summary
        == "The internal state machine is the chosen approach."
    )
    assert "## Options considered" not in result.record.body


def test_body_holds_unconsumed_sections_only(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    write_spec(corpus, "0001-first")
    result = _adapt(corpus)
    body = result.record.body
    assert "## Summary" in body
    assert "Adds a gate before the private portfolio pages." in body
    assert "## Decision" not in body
    assert "## Rationale" not in body
    assert "## Options considered" not in body
    assert "## Context" not in body


def test_panel_units_resolve_by_decision_letter(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    write_spec(corpus, "0012-portfolio", index=PANEL_INDEX, rationale=PANEL_RATIONALE)
    result = _adapt(corpus)
    titles = [alternative.title for alternative in result.record.decision.alternatives]
    assert titles == [
        "Should the gate be synchronous?: Async worker",
        "Where should state live?: Server side state",
        "Which provider?: Hosted provider",
    ]
    # Panel 3's decision names Option B first; Option A is the alternative.
    assert "Which provider?: Hosted provider" in titles
    assert "Which provider?: Internal service" not in titles
    assert result.attempted_fields == frozenset()


def test_unit_with_unknown_winner_emits_no_alternatives(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    index = PANEL_INDEX.replace(
        "Option B, revised. Option A was picked first, then dropped.",
        "Option A, the hosted provider",
    )
    write_spec(corpus, "0012-portfolio", index=index, rationale=UNRESOLVED_RATIONALE)
    result = _adapt(corpus)
    assert result.record.decision.alternatives == []
    assert "decision.alternatives" in result.attempted_fields


def test_code_paths_extract_resolve_and_count_unresolved(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    (corpus / "app" / "dashboard").mkdir(parents=True)
    (corpus / "app" / "dashboard" / "page.tsx").write_text("x", encoding="utf-8")
    (corpus / "lib").mkdir()
    write_spec(corpus, "0013-code-paths", index=CODE_INDEX, rationale=CODE_RATIONALE)
    result = _adapt(corpus)
    spec_targets = {
        entry.target
        for entry in result.record.evidence
        if entry.kind == EvidenceKind.SPEC
    }
    assert spec_targets == {
        "docs/specs/0013-code-paths/index.md",
        "docs/specs/0013-code-paths/rationale.md",
    }
    file_targets = {
        entry.target
        for entry in result.record.evidence
        if entry.kind == EvidenceKind.FILE
    }
    assert file_targets == {"app/dashboard/page.tsx", "lib"}
    # uv run decision-memory and the shell tokens are not path shaped (AC-6);
    # only the wrong case typo counts, because it contains a slash.
    assert result.unresolved_mention_count == 1
    rules = {violation.rule for violation in result.violations}
    assert "evidence.mentions_unresolved" in rules


def test_wrong_case_token_does_not_resolve(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    (corpus / "app" / "dashboard").mkdir(parents=True)
    (corpus / "app" / "dashboard" / "page.tsx").write_text("x", encoding="utf-8")
    index = (
        "# 0013. Code paths\n\n"
        "**Date**: 2026-08-07\n"
        "**Status**: Accepted\n\n"
        "## Decision\n\n"
        "**Chosen option**: Option 1: Wire the page\n\n"
        "## Rationale\n\n"
        "See [rationale.md](rationale.md).\n\n"
        "## Build plan\n\n"
        "- The typo `App/Dashboard/Page.Tsx` must not resolve.\n"
    )
    write_spec(corpus, "0013-code-paths", index=index, rationale=CODE_RATIONALE)
    result = _adapt(corpus)
    file_targets = {
        entry.target
        for entry in result.record.evidence
        if entry.kind == EvidenceKind.FILE
    }
    assert file_targets == set()
    assert result.unresolved_mention_count == 1


def test_non_path_tokens_do_not_count_as_unresolved(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    index = (
        "# 0013. Code paths\n\n"
        "**Date**: 2026-08-07\n"
        "**Status**: Accepted\n\n"
        "## Decision\n\n"
        "**Chosen option**: Option 1: Wire the page\n\n"
        "## Rationale\n\n"
        "See [rationale.md](rationale.md).\n\n"
        "## Build plan\n\n"
        "- A quoted span such as `read only` adds nothing.\n"
        "- A dotted field name `decision.chosen` is not a path.\n"
    )
    write_spec(corpus, "0013-code-paths", index=index, rationale=CODE_RATIONALE)
    result = _adapt(corpus)
    assert result.unresolved_mention_count == 0


def test_renamed_single_segment_dir_counts_via_pre_strip_slash(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    index = (
        "# 0013. Code paths\n\n"
        "**Date**: 2026-08-07\n"
        "**Status**: Accepted\n\n"
        "## Decision\n\n"
        "**Chosen option**: Option 1: Wire the page\n\n"
        "## Rationale\n\n"
        "See [rationale.md](rationale.md).\n\n"
        "## Build plan\n\n"
        "- A renamed directory `oldlib/` still counts.\n"
    )
    write_spec(corpus, "0013-code-paths", index=index, rationale=CODE_RATIONALE)
    result = _adapt(corpus)
    assert result.unresolved_mention_count == 1


def test_extension_comparison_ignores_case(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    index = (
        "# 0013. Code paths\n\n"
        "**Date**: 2026-08-07\n"
        "**Status**: Accepted\n\n"
        "## Decision\n\n"
        "**Chosen option**: Option 1: Wire the page\n\n"
        "## Rationale\n\n"
        "See [rationale.md](rationale.md).\n\n"
        "## Build plan\n\n"
        "- A missing file `missing.MD` counts as an unresolved path.\n"
    )
    write_spec(corpus, "0013-code-paths", index=index, rationale=CODE_RATIONALE)
    result = _adapt(corpus)
    # `.MD` matches the known `.md` extension without regard to case, so the
    # missing file is still a path shaped mention even though the casing differs.
    assert result.unresolved_mention_count == 1


def test_no_context_anywhere_flags_context_problem(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    index = INDEX.replace(
        "## Context\n\n"
        "The portfolio is public today; private projects need a gate "
        "before they can be shown.\n\n",
        "",
    )
    rationale = RATIONALE.replace(
        "## Context\n\nThe full context lives here, and it wins over "
        "index.md when both files carry one.\n\n",
        "",
    )
    write_spec(corpus, "0001-first", index=index, rationale=rationale)
    result = _adapt(corpus)
    assert result.record.context is None
    assert "context.problem" in result.attempted_fields
    assert "context.triggering_change" not in result.attempted_fields


def test_triggering_change_is_never_flagged(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    write_spec(corpus, "0001-first")
    result = _adapt(corpus)
    assert "context.triggering_change" not in result.attempted_fields


def test_spec_without_rationale_section_fails_validation(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    rationale = RATIONALE.split("## Rationale")[0]
    write_spec(corpus, "0001-first", rationale=rationale)
    result = _adapt(corpus)
    assert result.record is not None
    rules = {violation.rule for violation in result.violations}
    assert "rationale.missing" in rules
    assert "why" in result.attempted_fields
    assert "rationale_summary" in result.attempted_fields


REAL_OPTION_INDEX = """\
# 0006. Adzuna job discovery

**Date**: 2026-08-01
**Status**: Accepted

## Context

Jobs are fetched from Adzuna.

## Decision

**Chosen option**: One request, then a client side refetch

## Consequences

**Positive**:
- Fast first paint.

**Negative**:
- Slight delay.

## Rationale

See [rationale.md](rationale.md).
"""

REAL_OPTION_RATIONALE = """\
# 0006. Adzuna job discovery

## Options considered

### Option 1: One request, then a client side refetch (recommended)

**Pros**:
- Single round trip.

**Cons**:
- Jobs appear with a delay.

### Option 2: One request, jobs included in the response

**Pros**:
- Everything at once.

**Cons**:
- Bigger payload.

### Option 3: Poll for job completion

**Pros**:
- Always fresh.

**Cons**:
- More requests.

## Rationale

The client side refetch keeps the first paint fast.
"""

REAL_PANEL_INDEX = """\
# 0012. Portfolio private access gate

**Date**: 2026-08-01
**Status**: Accepted

## Decision

**Chosen option**: A dedicated read only user_access table

## Options considered

See [rationale.md](rationale.md).

## Consequences

**Positive**:
- Pages are protected.

**Negative**:
- More code.

## Rationale

See [rationale.md](rationale.md).
"""

REAL_PANEL_RATIONALE = """\
# 0012. Portfolio private access gate

## Context

The portfolio is public today.

## Options considered

### Panel 1: Which routes the gate covers

**Option A — The two agent routes only (the original proposal)**: gate two routes.

- **Pros**: Smallest diff.
- **Cons**: Leaves two call sites open.

**Option B — All four paid routes (chosen)**: gate all four.

- **Pros**: Closes the whole surface.
- **Cons**: Two more files to touch.

**Decision**: Option B.

### Panel 2: Where approval state lives

**Option A — A dedicated user_access table (chosen)**: one row per user.

- **Pros**: RLS select own row.
- **Cons**: A new table.

**Option B — An is_approved column on profiles**: no new table.

- **Pros**: One boolean.
- **Cons**: A self approval hole.

**Decision**: Option A.

## Rationale

The server route is the boundary.
"""


def test_real_style_heading_options_resolve_and_carry_cons(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    write_spec(
        corpus, "0006-adzuna", index=REAL_OPTION_INDEX, rationale=REAL_OPTION_RATIONALE
    )
    result = _adapt(corpus)
    assert result.record.decision.chosen == "One request, then a client side refetch"
    alternatives = result.record.decision.alternatives
    assert [alternative.title for alternative in alternatives] == [
        "One request, jobs included in the response",
        "Poll for job completion",
    ]
    assert "Bigger payload" in alternatives[0].rejection_reason
    assert result.attempted_fields == frozenset()


def test_real_style_panel_options_with_heading_questions(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    write_spec(
        corpus, "0012-portfolio", index=REAL_PANEL_INDEX, rationale=REAL_PANEL_RATIONALE
    )
    result = _adapt(corpus)
    titles = [alternative.title for alternative in result.record.decision.alternatives]
    assert titles == [
        "Which routes the gate covers: "
        "The two agent routes only (the original proposal)",
        "Where approval state lives: An is_approved column on profiles",
    ]
    assert (
        "Leaves two call sites open"
        in result.record.decision.alternatives[0].rejection_reason
    )
    assert result.attempted_fields == frozenset()


REAL_QUALIFIED_NEGATIVE_INDEX = """\
# 0019. Resume generation quality

**Date**: 2026-08-01
**Status**: Accepted

## Context

Generated resumes need to read as if a person wrote them.

## Decision

**Chosen option**: A single prompt with a style guide

## Consequences

**Positive**:
- Consistent tone across resumes.

**Negative / tradeoffs**:
- Longer prompts cost more per generation.
- **Style drift**: a style guide update needs a re-run to take effect everywhere.
- Harder to test than a template based approach.

## Rationale

See [rationale.md](rationale.md).
"""

REAL_QUALIFIED_NEGATIVE_RATIONALE = """\
# 0019. Resume generation quality

## Rationale

A single prompt keeps voice consistent across every resume.
"""


def test_qualified_negative_label_and_bold_bullet_are_not_dropped(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    write_spec(
        corpus,
        "0019-resume-quality",
        index=REAL_QUALIFIED_NEGATIVE_INDEX,
        rationale=REAL_QUALIFIED_NEGATIVE_RATIONALE,
    )
    result = _adapt(corpus)
    assert result.record.consequences.positive == ["Consistent tone across resumes."]
    assert result.record.consequences.negative == [
        "Longer prompts cost more per generation.",
        "**Style drift**: a style guide update needs a re-run to take effect "
        "everywhere.",
        "Harder to test than a template based approach.",
    ]
    assert "consequences.positive" not in result.attempted_fields
    assert "consequences.negative" not in result.attempted_fields


FENCED_HEADING_INDEX = """\
# 0021. Something fenced

**Date**: 2026-08-01
**Status**: Accepted

## Context

Some context here.

## Decision

**Chosen option**: Ship it

## Consequences

**Positive**:
- Good.

## Notes

Example command:

```bash
## this looks like a heading but is inside a fence
echo hi
```

The paragraph after the fence stays in this section.

## Rationale

See [rationale.md](rationale.md).
"""

FENCED_HEADING_RATIONALE = """\
# 0021. Something fenced

## Rationale

Shipping it is the simplest option available.
"""


def test_heading_like_line_inside_a_fence_is_not_a_section_break(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    write_spec(
        corpus,
        "0021-fenced",
        index=FENCED_HEADING_INDEX,
        rationale=FENCED_HEADING_RATIONALE,
    )
    result = _adapt(corpus)
    body = result.record.body
    # The fenced line stays fenced (one occurrence, inside the code block)
    # rather than also being split out as its own "## <heading>" section.
    assert body.count("## this looks like a heading but is inside a fence") == 1
    assert (
        "```bash\n"
        "## this looks like a heading but is inside a fence\n"
        "echo hi\n"
        "```" in body
    )
    assert body.count("## Notes") == 1
    assert "The paragraph after the fence stays in this section." in body


UNKNOWN_CONSEQUENCE_LABELS_INDEX = """\
# 0030. Odd consequence labels

**Date**: 2026-08-01
**Status**: Accepted

## Context

Some context.

## Decision

**Chosen option**: Ship it

## Consequences

**Upsides**:
- Faster to run.

**Downsides**:
- Costs more per call.

## Rationale

See [rationale.md](rationale.md).
"""

UNKNOWN_CONSEQUENCE_LABELS_RATIONALE = """\
# 0030. Odd consequence labels

## Rationale

Shipping it is the simplest option.
"""


def test_unrecognized_consequence_labels_are_flagged_and_kept(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    write_spec(
        corpus,
        "0030-odd-labels",
        index=UNKNOWN_CONSEQUENCE_LABELS_INDEX,
        rationale=UNKNOWN_CONSEQUENCE_LABELS_RATIONALE,
    )
    result = _adapt(corpus)
    # Neither list maps, so the field stays empty, but the failure is
    # reported rather than silent, and the prose survives in the body.
    assert result.record.consequences is None
    assert "consequences.positive" in result.attempted_fields
    assert "consequences.negative" in result.attempted_fields
    assert "## Consequences" in result.record.body
    assert "Faster to run." in result.record.body
    assert "Costs more per call." in result.record.body


UNCLOSED_FENCE_INDEX = """\
# 0031. Unclosed fence

**Date**: 2026-08-01
**Status**: Accepted

## Context

Some context.

## Decision

**Chosen option**: Ship it

## Notes

```bash
echo "this fence is never closed"

## Consequences

**Positive**:
- Still found.

## Rationale

See [rationale.md](rationale.md).
"""

UNCLOSED_FENCE_RATIONALE = """\
# 0031. Unclosed fence

## Rationale

Shipping it is the simplest option.
"""


def test_a_fence_that_never_closes_does_not_swallow_later_sections(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    write_spec(
        corpus,
        "0031-unclosed",
        index=UNCLOSED_FENCE_INDEX,
        rationale=UNCLOSED_FENCE_RATIONALE,
    )
    result = _adapt(corpus)
    # One stray delimiter must not delete the rest of the document.
    assert result.record.consequences is not None
    assert result.record.consequences.positive == ["Still found."]
    assert result.record.decision.chosen == "Ship it"


MIXED_FENCE_INDEX = """\
# 0032. Mixed fence markers

**Date**: 2026-08-01
**Status**: Accepted

## Context

Some context.

## Decision

**Chosen option**: Ship it

## Notes

```markdown
~~~
## not a real heading, it is inside the backtick fence
```

After the fence.

## Consequences

**Positive**:
- Real one.

## Rationale

See [rationale.md](rationale.md).
"""

MIXED_FENCE_RATIONALE = """\
# 0032. Mixed fence markers

## Rationale

Shipping it is the simplest option.
"""


def test_a_different_delimiter_inside_a_fence_does_not_close_it(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    write_spec(
        corpus,
        "0032-mixed-fence",
        index=MIXED_FENCE_INDEX,
        rationale=MIXED_FENCE_RATIONALE,
    )
    result = _adapt(corpus)
    body = result.record.body
    # The tilde line does not end the backtick fence, so the heading-looking
    # line inside it never becomes a section of its own.
    assert "## not a real heading" in body
    assert body.count("## Notes") == 1
    assert result.record.consequences.positive == ["Real one."]


def test_recognized_consequences_stay_out_of_the_body(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    write_spec(corpus, "0001-first")
    result = _adapt(corpus)
    assert result.record.consequences.positive
    assert "consequences.positive" not in result.attempted_fields
    assert "## Consequences" not in result.record.body
