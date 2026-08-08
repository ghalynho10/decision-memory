# Session notes

In session residue that has not earned a place in scope, a spec, or AGENTS.md yet. `/checkpoint` owns the sections below; other skills own anything else.

## Open threads
- mypy is the installed strict type checker (tooling milestone); `AGENTS.md` records "mypy or pyright", so pyright stays a permitted alternative if a later session wants to swap.
- Date handling gap: `/develop` added a Pydantic field validator to coerce an unquoted YAML date scalar (for example `date: 2026-08-07`) to its ISO string, because PyYAML parses it as a date object. Spec 0002 still does not mention this; a candidate for a follow up line in the spec.
- Feature 4 is shipped in PR #1, open and not merged yet. The code was written by DeepSeek V4 Flash, so the `/check review` should run on a Claude model for a true cross model read.
- After feature 4 merges, run `/sync`, then `/architect core cited query` for feature 5.

## Ruled out
- Plain single command Typer app (one `@app.command` plus `no_args_is_help`) does not dispatch in Typer 0.27.1: it auto invokes the command and rejects the command name. The CLI uses a callback (`invoke_without_command`) plus commands instead.

## Standing instructions
- Commit messages in this project leave out the `Co-Authored-By: Claude` trailer. Asked for directly, so do not add it back on later commits.
