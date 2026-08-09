# Portfolio roadmap strategy (v1 and v2)

_Reference artifact. Written 2026-08-09. The project started as a portfolio project while job hunting. This captures what to build for v1 and v2, balancing "working soon" against "quality", and where to stop so the project does not overcomplicate. Not in scope. Related: `importance-assessment.md`, `ingestion-paths.md` (in `docs/reference/artifact/`), `saas-angle.md` (in `docs/reference/business/`)._

## The portfolio reframe

For a job hunting portfolio, the evaluation is not "how ambitious is the vision". It is four things: does it work, is the code quality high, is the problem interesting, is it explained well. The project already has three of the four: a working CLI, Clean Architecture plus tests, and a genuinely interesting problem. The missing one, "does it work" in the demonstrative sense, is the gap. A tool that can adapt and validate but cannot answer a question is a well built foundation with no payoff, and that is a weak portfolio.

So: do not stop at the foundations, but do not gold plate either. The two instincts being weighed are both right, applied to different things.

## v1: working soon but quality

Keep v1 tight. The global vision (capture, generic parsing, SaaS, MCP) is not v1 work. It is README narrative and the reference docs already written. Nothing is lost by deferring it.

| Priority | Feature | Why |
|---|---|---|
| Must | 9 Core cited query | This is the demo. `decision-memory query "why is X built this way"` gives a cited answer or an honest "not enough evidence". The entire product in one command, and the moment an interviewer says "oh, that actually works". |
| Must | Finish 7 conformance and test adapter (already in progress) | Makes the anti fabrication guarantee checkable, the most defensible differentiator and a strong rigor signal. |
| Strong candidate | 11 evaluation harness, proven correctness | The sleeper portfolio win: an eval that proves citation accuracy and abstention behavior. Hard to fake rigor. Include if it does not blow the timeline; it can slip to v2. |
| Only as needed | 10 multi source retrieval | Add only what the demo needs to answer real queries well. Do not gold plate. |
| Not in v1 | MCP (14), capture, generic adapters, anything from the business folder | All deferred. |

The v1 exit criterion, so "working soon" is concrete: `query` returns cited answers and honest abstentions on a real corpus (JobPilot specs), tests are green, and the README has a working demo transcript. Then stop, polish, and ship.

## v2: deliberate growth, in this order

After v1 is shipped and demonstrable, grow in the order that most strengthens the portfolio and the product.

1. Feature 8 built in ADR adapters plus the generic markdown fallback. Proves "works on any project, not just my pipeline". Makes the demo relatable to any interviewer regardless of their stack.
2. Feature 11 evaluation harness if it did not make v1. The correctness proof.
3. Feature 14 MCP server. The capstone. Cheap to demo (an agent queries the decision memory) and the whole "agents consult the memory" story in one feature. High impact, low scope.
4. Features 13 and 12 (declarative adapters, flat file support). Only if they serve the story; they are polish, not priorities.

The SaaS angle stays in `docs/reference/business/`. It is the eventual monetization narrative, not portfolio work. Mention it in the README "where this is going" so the ambition is visible, but do not build it.

## On leaving it as is

The "do not overcomplicate" instinct is correct: do not add MCP, capture, SaaS, or global ambitions to v1. Every tempting idea from the strategy conversations is already captured in `docs/reference/`, so deferring costs nothing.

But leaving the project at its current state would be a mistake, because the current state is foundations without payoff. Feature 9 is not adding complication; it is completing the thing. That difference is the whole answer.

## The quality layer that does not require more features

Four things lift this more than any additional feature, for a portfolio.

1. A README that tells the story: problem, approach, the anti fabrication wedge, architecture diagram, a real demo transcript, and "where this is going" as one paragraph.
2. A recorded demo: 60 to 90 seconds, terminal run, doctor then adapt then query with a cited answer and one abstention. This is what gets sent with applications.
3. The existing spec trail: `docs/scope/`, `docs/specs/`, the reviews. Genuinely unusual and impressive. It shows process and engineering discipline. Surface it in the README.
4. Tests as the guarantee story: a strong unit suite plus the conformance suite (7) and the eval harness (11) make "it does not fabricate" a demonstrable claim, the line that makes the project memorable.

## Bottom line

Add one thing to v1: feature 9, the cited query, plus finishing feature 7, because without it there is no payoff to show. Defer everything else. For v2, add breadth (ADR and generic adapters) then the MCP capstone. Invest the remaining quality budget not in more features but in the story: README, demo recording, and surfacing the spec trail. That gives working soon, quality, and a project an interviewer remembers, without overcomplicating anything.

## Status

Not in scope. Strategy reference only. Revisit after feature 9 and feature 7 ship.
