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

from decision_memory.application.adapter import AdaptOutcome, adapt_corpus
from decision_memory.application.validation_service import validate_file
from decision_memory.infrastructure.jsmastery_adapter import (
    ADAPTER_VERSION,
    JsmasteryAdapter,
)

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


@app.command("adapt")
def adapt_command(
    corpus_path: Annotated[
        Path, typer.Argument(help="Path to the corpus, a project holding docs/specs/")
    ],
    output: Annotated[
        Path | None,
        typer.Option(help="Output directory for records and the manifest"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Run and report without writing anything"),
    ] = False,
) -> None:
    """Adapt a project's jsmastery specs into canonical decision records."""
    outcome = adapt_corpus(
        corpus_path,
        JsmasteryAdapter(),
        ADAPTER_VERSION,
        output=output,
        dry_run=dry_run,
    )
    _print_adapt_report(outcome)
    raise typer.Exit(outcome.exit_code)


def _print_adapt_report(outcome: AdaptOutcome) -> None:
    """Print the adapt run's report: discovery, per record, and summary."""
    discovery = outcome.discovered
    typer.echo(
        f"discovered {len(discovery.specs)} specs, skipped {len(discovery.skipped)}"
    )
    for skipped in discovery.skipped:
        typer.echo(f"  skipped {skipped.path}: {skipped.reason}")
    for collision in discovery.collisions:
        typer.echo(
            f"  collision {collision.id}: "
            f"{', '.join(str(path) for path in collision.paths)} "
            f"(using {collision.used})"
        )
    for record in outcome.records:
        if record.state == "failed":
            reasons = "; ".join(v.reason for v in record.violations)
            typer.echo(f"  failed {record.id}: {reasons}")
        else:
            typer.echo(f"  {record.state} {record.id}")
    counts: dict[str, int] = {}
    for record in outcome.records:
        counts[record.state] = counts.get(record.state, 0) + 1
    summary = ", ".join(f"{state} {count}" for state, count in counts.items())
    typer.echo(f"result: {summary}")
    if outcome.exit_code == 3:
        typer.echo("corpus path does not exist or holds no docs/specs/ directory")
    suffix = " (dry run, nothing written)" if outcome.dry_run else ""
    typer.echo(f"output: {outcome.output_dir}{suffix}")


if __name__ == "__main__":
    app()
