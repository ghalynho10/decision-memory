# 0004. Doctor diagnostic

The decision history for spec 0004: the problem, the options considered, the
rationale for the choice, and the references. The build spec lives in
[index.md](index.md).

## Context

An adapter can only work when a corpus has enough structural consistency for its field mapping. Today a person must inspect files by hand before deciding whether an existing adapter fits or whether a new adapter is needed. A structural survey gives that person evidence without claiming to understand the decisions inside the files.

Coverage is part of the answer. A report based on a small readable subset can create false confidence if excluded directories, symbolic links, or unreadable files disappear silently. The command must distinguish analyzed Markdown files, ignored non Markdown files, and skipped paths whose omission limits the survey (basis: scope feature 5, and the skip reporting discipline in spec 0003).

The project is a local Python command line tool with Clean Architecture boundaries. This feature needs no persistence, network call, secret, or new package. Its parsing grammar is deliberately narrower than full Markdown because the question is about exact H2 structure, not rendered document meaning (basis: `AGENTS.md`, the existing stack and dependency rule).

## Options considered

### Option 1: Dedicated standard library scanner

Add a small scanner for the agreed ATX H2 grammar, deterministic filesystem traversal, and structured coverage results. Keep full Markdown rendering out of scope (basis: `AGENTS.md`, CommonMark ATX heading rules, and Python `os.scandir` behavior).

**Pros**:

- Adds no dependency and implements only the grammar this diagnostic promises
- Makes every traversal, parsing, and skip rule directly testable
- Leaves the shipped adapter unchanged

**Cons**:

- Maintains another narrow Markdown scanner beside the adapter parser
- Deliberate departures from CommonMark must remain documented in tests

### Option 2: Generalize the adapter parser

Extract the private heading and fence helpers from the jsmastery adapter and make both features share them (basis: spec 0003 and `src/decision_memory/infrastructure/jsmastery_adapter.py`).

**Pros**:

- Reduces duplicate fence and heading logic
- Gives both features one future maintenance point

**Cons**:

- Couples a broad corpus survey to parser behavior that was calibrated for one adapter
- Risks changing accepted adapter behavior while building an independent diagnostic

### Option 3: Add a CommonMark parser

Add a third party Markdown parser, build a syntax tree, and filter it to H2 tokens (basis: CommonMark).

**Pros**:

- Delegates the wider Markdown grammar to a mature implementation
- Handles more Markdown constructs if the diagnostic later expands

**Cons**:

- Adds a dependency for a deliberately narrow rule set
- Full CommonMark treats an unmatched fence differently from the required adapter aligned behavior

## Rationale

The user needs trustworthy structural evidence, not a general Markdown engine. The dedicated scanner is the smallest implementation that can make coverage, exact comparison, and deterministic ordering explicit. It also avoids changing the accepted adapter while feature 5 is still only a reading aid.

The runner up is a shared parser extraction. That becomes worthwhile only after two shipped consumers need the same grammar. Today they do not: `doctor` trims headings for comparison, while the adapter maps named sections and already has accepted behavior. A new CommonMark dependency costs more and conflicts with the chosen unmatched fence rule.

## References

**Project sources**:

- `AGENTS.md`, stack, Clean Architecture rules, and Skateboard build approach
- `docs/scope/scope.md`, feature 5 intent and boundaries
- Spec 0002, exit code `3` for an unusable validation input
- Spec 0003, skip reporting discipline, exit code `3` for an unusable corpus, and unmatched fence behavior

**Practices & standards**:

- CommonMark ATX heading and fenced code block syntax
- Explicit sorting for deterministic filesystem reports
- Complete accounting for excluded and unreadable inputs

**Links**:

- CommonMark Spec 0.31.2: https://spec.commonmark.org/0.31.2/
- Python `os` documentation: https://docs.python.org/3/library/os.html
