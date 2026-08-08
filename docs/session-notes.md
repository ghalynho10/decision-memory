# Session notes

In session residue that has not earned a place in scope, a spec, or AGENTS.md yet. `/checkpoint` owns the sections below; other skills own anything else.

## Open threads
- mypy is the installed strict type checker (tooling milestone); `AGENTS.md` records "mypy or pyright", so pyright stays a permitted alternative if a later session wants to swap.
- Feature 3 failed `/check verify` on AC-16: a record with an unquoted `date: 2026-02-30` crashes the CLI with a traceback, because PyYAML builds it as a timestamp and raises a plain ValueError that the reader's `except yaml.YAMLError` misses. Fix pending: drop the timestamp implicit resolver from the reader loader and catch ValueError too, then re run `/check verify`. Unit tests stay green because they feed the string straight to the validator.
- Date handling gap: `/develop` added a Pydantic field validator to coerce an unquoted YAML date scalar (for example `date: 2026-08-07`) to its ISO string, because PyYAML parses it as a date object. Spec 0002 does not mention this; a candidate for a follow up line in the spec.
- Spec 0002 status reads `Accepted` even though feature 3 is not done, which `/check verify` flagged as unexpected at build start. Unresolved, worth a look before the feature ships.

## Ruled out
- Plain single command Typer app (one `@app.command` plus `no_args_is_help`) does not dispatch in Typer 0.27.1: it auto invokes the command and rejects the command name. The CLI uses a callback (`invoke_without_command`) plus commands instead.

## Standing instructions
- Commit messages in this project leave out the `Co-Authored-By: Claude` trailer. Asked for directly, so do not add it back on later commits.
