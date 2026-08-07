# Session notes

In session residue that has not earned a place in scope, a spec, or AGENTS.md yet. `/checkpoint` owns the sections below; other skills own anything else.

## Open threads
- mypy is the installed strict type checker (tooling milestone); `AGENTS.md` records "mypy or pyright", so pyright stays a permitted alternative if a later session wants to swap.

## Ruled out
- Plain single command Typer app (one `@app.command` plus `no_args_is_help`) does not dispatch in Typer 0.27.1: it auto invokes the command and rejects the command name. The CLI uses a callback (`invoke_without_command`) plus commands instead.
