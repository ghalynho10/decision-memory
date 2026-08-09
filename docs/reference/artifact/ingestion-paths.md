# Ingestion paths: eliminating adapter friction without losing the guarantee

_Reference artifact. Written 2026-08-09. Answers "could ingestion parse any harness output at the RAG level, so no adapter is needed", and lays out the four paths that remove adapter friction while preserving the anti fabrication guarantee. Not in scope; revisit against the roadmap. Related: `importance-assessment.md` and `step-7-proactive-wiring.md` in this folder._

## The core tension

"Parse any harness output at the RAG level" works technically (an LLM can parse anything) but the naive version destroys the product's value. Raw doc RAG is exactly what the README argues against: retrieval runs over structured records, not raw documentation, "which is what makes citations reliable instead of plausible." And LLM extraction is non deterministic and can hallucinate the fields that matter most (invented alternatives, fabricated evidence refs). The validator catches structural violations, not semantic fabrication.

So the real goal is not to remove adapters. It is to remove adapter friction, while keeping determinism and the degrade never guess guarantee.

## The four paths

They are a coverage ladder for different input shapes, not competing alternatives.

### Path 1 — Generic deterministic fallback

An adapter that targets no named format. It reuses the doctor structure detection to find decision shaped documents (recognizable headings like `## Context`, `## Decision`, `## Why`, a status or date line) and maps known sections to canonical fields. Everything else becomes attempted fields or skips. No LLM, fully deterministic.

- Pros: zero authoring for a large fraction of corpora; determinism and the no fabrication guarantee intact; reuses doctor, validation, fingerprint.
- Cons: only covers markdown with recognizable heading shapes. Needs a conservative "is this really a decision doc" gate to avoid thin records.
- Effort: moderate. A new adapter plus calibration plus conformance fixtures. The natural sibling of feature 8 (built in ADR adapters): ship `madr@1`, `adr@1`, and a `generic-markdown` fallback together.
- Risk: false positives. Mitigated by the conservative gate and the degrade rules.

### Path 2 — LLM assisted adapter authoring, LLM off the hot path

A one time dev tool: `generate-adapter --corpus ./x` feeds doctor output plus sample files to an LLM, which writes the deterministic adapter code (discover, parse, fingerprint) for that custom format. Review it, pass it through the conformance suite, then it runs forever with no LLM involved.

- Pros: custom formats get adapters in minutes; determinism preserved; the LLM is a code generator, not a runtime dependency; conformance (feature 7) is the trust gate.
- Cons: generated code can be subtly wrong, needs review and conformance; still requires a human to adopt.
- Effort: medium. A new CLI command, a prompt harness, conformance gating. Depends on feature 7.

### Path 3 — Confidence scored extraction, LLM in the parse path

A runtime LLM parser that extracts records with per field confidence. High confidence fields are promoted; uncertain ones become attempted fields; an overall low confidence document produces no record. Extracted records are marked proposed or inferred, never accepted.

- Pros: the only path that genuinely handles unstructured input: chat logs, prose with no headings, true "any harness output".
- Cons: non deterministic; cost and latency per ingest; a confident but wrong field can still slip through. It trades the core guarantee.
- Effort: high. New infrastructure, thresholds, calibration. Opt in and optional by design.

### Path 4 — Capture first, the schema becomes the contract upstream

Make the producing side write canonical records natively. Two parts: a remember or capture command plus an MCP write tool (`dm_capture`) so an agent records a decision at the moment it is made; and harnesses that emit the schema directly, so over time "speaks the schema" means no adapter needed. Extend the step 7 convention from consult only to record at decision time.

- Pros: strongest guarantees (records written deliberately, not parsed); fixes cold start; makes the tool load bearing.
- Cons: adoption dependent. Cannot force third party harnesses to emit the schema, and it does not backfill existing corpora (legacy artifacts still need adapters).
- Effort: medium high. Capture command, MCP write tool, agent skill, plus the hard part of getting producers to adopt.

## The coverage ladder

| Input shape | Path | Guarantee |
|---|---|---|
| Harness speaks the schema (new work) | 4 capture | strongest, deliberate records |
| Markdown with decision shaped headings | 1 generic deterministic | full, deterministic |
| Custom but structured format | 2 generated deterministic adapter | full, deterministic, LLM offline |
| Truly unstructured (chat, prose) | 3 confidence extraction | reduced, opt in |

Design principle: cover as much input space as possible with deterministic guarantees, in order of strength, and only fall to LLM extraction for what is left.

## Recommendation

A staged bundle, in this order, tied to the roadmap:

1. Path 1 first. Cheapest, highest coverage, guarantee preserving. Fold into feature 8 (ship `generic-markdown` beside `madr@1` and `adr@1`). Delivers "no adapter needed for the common case".
2. Path 2 second. The natural companion when the generic fallback misses a custom format. Gate behind feature 7 (conformance), needed anyway to trust both 1 and 2.
3. Path 4 as the parallel strategic track. Start the capture surface (remember command, `dm_capture` MCP tool, step 7 extension) early, paired with feature 14 (MCP). Do not gate on adoption; ship the capability so the corpus grows automatically for anyone who mounts it. The only path that eventually obviates adapters for new work.
4. Path 3 last and optional, or defer. The only path that trades away the guarantee. If built, make it opt in, mark every inferred record proposed never accepted, and keep it a secondary path. Never let it become the headline.

Sequencing: feature 7 (conformance) is the linchpin for paths 1 and 2; feature 9 (query) and feature 14 (MCP) unlock path 4's agent facing capture; path 3 waits.

Do not do: all four simultaneously (scope bloat, and 3 muddies 1), and do not build 3 as a headline feature. The order matters more than the set: the guarantee is the product, so deterministic coverage comes first and LLM extraction stays a guarded fallback.

## Status

Not in scope. Reference only. Related roadmap items: feature 7 (adapter conformance suite), feature 8 (built in ADR adapters), feature 9 (core cited query), feature 14 (MCP server interface) in `docs/scope/scope.md`.
