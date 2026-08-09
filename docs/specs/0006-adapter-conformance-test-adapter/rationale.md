# Rationale for 0006. Adapter conformance suite and `test-adapter`

## Context

> ⚠️ Premise note: A fixture suite cannot prove that an adapter never fabricates for every document it may ever read. It can prove exact behavior for declared cases and universal protocol properties. The right claim is strong repeatable conformance evidence, with required case categories that make an empty or convenient suite impossible, not formal correctness beyond the tested corpus.

The scope calls for a command any adapter author can run, a no confident record rule for malformed input, and the same suite for every built in adapter. (basis: `docs/scope/scope.md`, feature 7)

Spec 0003 made anti fabrication the governing adapter rule. A plausible record with one invented field is worse than no record because downstream retrieval presents it as evidence. Counts, record ids, and canonical validation do not detect that failure. An invented `rationale_summary` can preserve all three.

Spec 0005 exposed third party adapters through one trusted runtime loader and deliberately limited its contract check to metadata and callable presence. It left signatures, behavior, format drift, and anti fabrication evidence to this feature. The current `validate` command proves whether an adapter can process one supplied corpus without writes. It does not prove that the adapter behaves deterministically, fingerprints every contributing file, or refuses malformed grammar.

The hard constraint is that source grammar belongs to each adapter. A shared suite cannot know whether a changed heading is wrong. Inferring malformed input through scoring would recreate the rejected generic mapper from spec 0003, where a plausible score decides correctness. The suite can own only properties that remain true without grammar knowledge.

## Options considered

### Option 1: Declarative format cases plus closed universal corruption checks

Each adapter supplies strict YAML cases and complete expected records. The shared engine checks protocol behavior and adds only empty bytes and fixed invalid UTF8 for required text files. (basis: specs 0002, 0003, and 0005; golden record comparison; fail closed ingestion)

**Pros**:

1. Exact comparison catches fields that should be absent.
2. Authors define grammar truth without executable assertion hooks.
3. Closed corruption checks exercise unreadable required files without guessing headings.

**Cons**:

1. Authors must maintain full expected records and five case categories.
2. Coverage remains bounded by the declared fixtures.

### Option 2: Automatically mutate valid grammar fixtures

The shared suite would rename headings, remove sections, or truncate files and treat confident parsing as failure. (basis: mutation testing; spec 0003 rejected inference mapper)

**Pros**:

1. Authors write fewer negative fixtures.
2. The engine can generate many variants cheaply.

**Cons**:

1. The engine does not know whether a mutation remains valid for that format.
2. False failures punish an adapter for correct parsing and turn a scoring rule into the source of truth.

### Option 3: Let adapters supply Python assertions or a pytest plugin

Authors would write code that prepares fixtures and decides whether results pass. The CLI could delegate to those hooks or expose pytest integration. (basis: executable test extension patterns; spec 0005 trusted code boundary)

**Pros**:

1. Every format can express arbitrary checks.
2. Existing test tools provide rich failure output.

**Cons**:

1. A conformance case can assert nothing and still produce a passing report.
2. Reviewers cannot inspect a common declarative contract.
3. It couples the application surface to pytest or a second plugin protocol.

### Option 4: Check protocol shape and positive parsing only

The command would inspect signatures, call each method on one valid corpus, and accept any valid output. (basis: runtime structural contract checks; smallest implementation)

**Pros**:

1. It is quick to build and easy for adapter authors to satisfy.
2. It detects broken signatures earlier than the runtime loader.

**Cons**:

1. It cannot detect an invented field in an otherwise valid record.
2. It provides no evidence for grammar drift or unreadable files.

## Rationale

Option 1 is chosen because the user problem is trust, not merely call compatibility. Exact semantic record comparison is the only considered design that fails when an adapter invents a field while preserving the correct id and a valid record. Declarative expectations also make the claimed behavior inspectable and prevent author code from defining a hollow pass. (basis: spec 0003 anti fabrication rule; golden record comparison)

Grammar cases remain author supplied because the adapter owns the source language. The closed corruption list is intentionally smaller than general mutation testing. Empty bytes and invalid UTF8 are unambiguous for author marked required UTF8 text files. Mid document truncation is excluded because Markdown can remain valid at an arbitrary end of file. (basis: explicit grammar contracts; fail closed ingestion)

The application engine reuses `SourceAdapter` and the existing loader rather than creating a conformance plugin framework. Pydantic and safe YAML stay at the infrastructure boundary, while plain immutable objects and a fixture port keep the application independent of frameworks and concrete filesystem work. This is the smallest whole that fits the repository's current architecture. (basis: `AGENTS.md`, Clean Architecture and Skateboard approach; spec 0005 runtime boundary; `src/decision_memory/application/adapter.py`; `src/decision_memory/infrastructure/runtime_loader.py`)

The built in adapter selection currently lives in a private CLI helper while third party selection lives in infrastructure. Adding conformance without settling that split would create the second loading path the feature is meant to avoid. A public infrastructure selector now owns the built in id and delegates every third party value to the accepted loader, so all adapter commands share one composition boundary. (basis: spec 0005 explicit selector decision; `src/decision_memory/cli.py`; `src/decision_memory/infrastructure/runtime_loader.py`)

The starter adapter expands from flat discovery to recursive discovery because its original filename stem rule cannot create a collision inside one flat directory. Corpus relative POSIX lexical order is the selection rule because it is portable, visible, and already natural for deterministic traversal. Existing flat fixtures retain their ids and order. Spec 0005 remains an accurate record of the smaller teaching package it accepted, while this spec records the later expansion. (basis: spec 0005 AC-16; `examples/starter-adapter/`; deterministic lexical traversal)

Automatic preservation of failed copies is chosen over unconditional cleanup because corruption variants do not exist in the author's source tree. The exact bytes that failed are more useful than instructions to reconstruct them. Operating system temporary storage avoids writing beside an installed read only package, at the cost of one variable path in the report and eventual cleanup responsibility. (basis: failure artifact preservation; write free author feedback loops; `docs/adapter-author-guide.md`)

## References

**Project sources**:

1. `AGENTS.md`, Clean Architecture, strict types, existing dependencies, test split, and Skateboard delivery
2. `docs/scope/scope.md`, feature 7 intent and shared built in suite requirement
3. `docs/specs/0002-canonical-decision-record-schema.md`, canonical record and violation contracts
4. `docs/specs/0003-jsmastery-specs-adapter/index.md` and `rationale.md`, anti fabrication, attempted fields, fingerprint, and explicit mapping decisions
5. `docs/specs/0005-runtime-adapter-loading/index.md` and `rationale.md`, trusted loading, contract limits, exception outcomes, and conformance handoff
6. `src/decision_memory/application/adapter.py`, current `SourceAdapter` and result types
7. `src/decision_memory/infrastructure/runtime_loader.py`, selector and shared loading boundary
8. `src/decision_memory/cli.py`, current built in selection and command composition
9. `docs/adapter-author-guide.md` and `examples/starter-adapter/`, current third party author path

**Practices and standards**:

1. Golden record comparison for complete observable output
2. Fail closed ingestion when source meaning is uncertain
3. Strict versioned declarative configuration
4. Ports and adapters for filesystem isolation
5. Property testing of deterministic and content sensitive fingerprints
6. Failure artifact preservation for generated inputs
