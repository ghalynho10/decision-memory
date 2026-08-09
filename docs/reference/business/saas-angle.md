# SaaS angle assessment

_Business reference artifact. Written 2026-08-09. Assesses whether decision memory has a viable SaaS angle, what it would be, who would pay, and when it becomes real. Not in scope. Complements `importance-assessment.md` and `ingestion-paths.md` under `docs/reference/artifact/`._

## The one angle that works: agent infrastructure, not documentation

Selling this as "hosted decision documentation" would be a mistake. Teams chronically under invest in docs and ADRs, so a docs adjacent SaaS is a historically hard sell. The angle that escapes that trap is reframing the category: decision memory as operational infrastructure for agentic development, the memory layer that agents consult, not docs that humans read. Companies are starting to budget for agent infrastructure; they do not budget for wikis.

That reframe changes the buyer (DevEx, platform, and agent infra teams rather than "someone should write better docs"), the value story (agents do not relitigate, onboard faster, stop re deciding), and willingness to pay.

## What the SaaS would concretely be

Open core, where the local CLI stays the free wedge:

- Local CLI (free): the adapter protocol, doctor, adapt, validate, local query. This is the adoption driver and the privacy story, "everything stays on your machine".
- Hosted tier (paid): the things that genuinely need a server.
  - Repo connected ingestion: a GitHub App or CI hook; connect a repo, adapters run server side, records build automatically on merge.
  - Team shared memory: the same corpus visible to the whole team, supersession history, and a "why is this the way it is" onboarding view for new developers.
  - A hosted MCP endpoint: any agent anywhere queries the team's decision memory over HTTP (dm query without running anything locally). This is the killer feature; it is how "agents consult your decisions" becomes true without per machine setup.
  - Analytics: unstable decisions, superseded chains, "what did we reject most" as an org signal.

## Who pays and why

- Most likely payers: teams already doing spec driven or agentic development, and companies with long lived codebases where institutional memory is genuinely lost. Both already feel the pain acutely.
- The weakest assumption is willingness to pay. Solo developers and vibe coders will not pay; the local tool covers them, which is fine, they are the growth and word of mouth, not the revenue. The SaaS is a team and enterprise story, and teams are slow to adopt new memory tooling. That slowness is the biggest risk.
- The counterweight: once agents depend on it, it stops being a nice to have and becomes load bearing, which is also the switching cost and the moat. The more decisions accumulate and the more agents consult them, the harder it is to leave.

## The moat

Three compounding assets:

1. The accumulated corpus per customer: more decisions, more value.
2. The adapter ecosystem: more formats supported, more reach, the "write an adapter not a fork" network effect.
3. Agent dependence: once an agent workflow consults the memory before building, it is infrastructure, not a tool.

## The honest gate: when this becomes real

Not now. The preconditions are the same ones from the broader strategy, and a SaaS does not shortcut any of them.

1. Ship the payoff loop (query, feature 9) and MCP (feature 14). You cannot sell hosted answers the local tool cannot even produce yet.
2. Get adopters on the local tool and prove the wedge: cited answers people actually trust, honest abstention.
3. Then the hosted layer is an extension, not a gamble: same product, same code, one more presentation layer. The SaaS is a layer on top of the globalized local product, not a substitute for building it.

## Bottom line

The angle exists and is defensible: hosted, team shared, agent consultable decision memory sold as agent infrastructure, open core around the free local CLI. But it is downstream. It only becomes real once the local product answers questions end to end, has real adopters, and has proven the cited honesty wedge. Build the globalized local tool first; the SaaS is how it would eventually be monetized, not how it would be built.

Likelihood: the product market need is genuinely there and growing with the agent era. The two things that will decide it are willingness to pay for memory (the riskiest assumption) and shipping the payoff loop (the only real blocker right now).

## Status

Not in scope. Business reference only. Revisit when feature 9 (query) and feature 14 (MCP) are shipped and the local tool has real adopters.
