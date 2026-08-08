"""Command line interface for decision memory.

This is the single entry point named by the stack spec (0001): a Typer
application that will grow the ``query`` and ingest commands in later slices.
The scaffold ships a bare command shell plus a ``version`` command so the
package boots and builds.
"""

from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import typer

from decision_memory.application.validation_service import validate_file

app = typer.Typer(
    name="decision-memory",
    help=(
        "Answer why a project is built the way it is, with cited answers "
        "backed by its decision records."
    ),
)


@app.callback(invoke_without_command=True)
def _main(ctx: typer.Context) -> None:
    """decision-memory command line interface."""
    if ctx.invoked_subcommand is None:
        typer.echo(
            "decision-memory: answer 'why is this built this way' with "
            "cited answers backed by decision records."
        )
        typer.echo("Run 'decision-memory --help' to see available commands.")
        raise typer.Exit()


@app.command("version")
def version_command() -> None:
    """Print the installed version of decision-memory."""
    typer.echo(f"decision-memory {version('decision-memory')}")


@app.command("validate")
def validate_command(
    file: Annotated[
        Path, typer.Argument(help="Path to a canonical decision record file")
    ],
    project_root: Annotated[
        Path | None,
        typer.Option(help="Project root anchoring path and git checks"),
    ] = None,
) -> None:
    """Validate a canonical decision record file and print violations."""
    outcome = validate_file(file, project_root)
    for violation in outcome.violations:
        field = violation.field if violation.field else "(record)"
        typer.echo(
            f"{violation.severity.value} {violation.rule} {field}: {violation.reason}"
        )
    if not outcome.violations:
        typer.echo("valid record, no violations")
    raise typer.Exit(outcome.exit_code)


if __name__ == "__main__":
    app()
