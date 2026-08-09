"""Command line interface for decision memory.

This is the single entry point named by the stack spec (0001): a Typer
application that will grow the ``query`` and ingest commands in later slices.
The scaffold ships a bare command shell plus a ``version`` command so the
package boots and builds.
"""

import json
from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import typer

from decision_memory.application.adapter import AdaptOutcome, adapt_corpus
from decision_memory.application.doctor_service import (
    EXIT_ERROR,
    DoctorOutcome,
    DoctorRequest,
    run_doctor,
)
from decision_memory.application.validation_service import validate_file
from decision_memory.infrastructure.doctor_scanner import scan_corpus
from decision_memory.infrastructure.file_reader import (
    parse_record_file,
    write_record_file,
)
from decision_memory.infrastructure.jsmastery_adapter import (
    ADAPTER_VERSION,
    JsmasteryAdapter,
)
from decision_memory.infrastructure.path_resolution import resolve_cited_paths

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
    outcome = validate_file(
        file, project_root, reader=parse_record_file, resolver=resolve_cited_paths
    )
    for violation in outcome.violations:
        field = violation.field if violation.field else "(record)"
        typer.echo(
            f"{violation.severity.value} {violation.rule} {field}: {violation.reason}"
        )
    if not outcome.violations:
        typer.echo("valid record, no violations")
    raise typer.Exit(outcome.exit_code)


def _validate_samples(value: int) -> int:
    """A nonnegative sample count; a negative one is a Typer bad parameter."""
    if value < 0:
        raise typer.BadParameter("samples must be a nonnegative integer")
    return value


@app.command("doctor")
def doctor_command(
    directory: Annotated[
        Path,
        typer.Argument(
            help="Path to the corpus to survey",
            # readable=False: an unreadable root must reach the survey, which
            # reports it as one '.' unreadable directory skip (AC-9), rather
            # than being rejected as a bad argument.
            readable=False,
        ),
    ],
    samples: Annotated[
        int,
        typer.Option(
            help="Number of sample paths per heading set group and skip reason",
            callback=_validate_samples,
        ),
    ] = 3,
) -> None:
    """Survey a corpus of Markdown files and report its H2 structure."""
    try:
        outcome = run_doctor(
            DoctorRequest(root=directory, samples=samples), scan_corpus
        )
    except Exception:
        typer.echo("doctor failed unexpectedly")
        raise typer.Exit(EXIT_ERROR) from None
    if outcome.exit_code != 0:
        typer.echo("corpus path does not exist or is not a directory")
        raise typer.Exit(outcome.exit_code)
    _print_doctor_report(outcome)
    raise typer.Exit(outcome.exit_code)


def _print_doctor_report(outcome: DoctorOutcome) -> None:
    """Print the normative report contract from spec 0004 (AC-8)."""
    skipped_total = sum(summary.count for summary in outcome.skips)
    typer.echo("coverage")
    typer.echo(f"  markdown analyzed: {outcome.markdown_analyzed}")
    typer.echo(f"  non markdown ignored: {outcome.non_markdown_ignored}")
    typer.echo(f"  skipped: {skipped_total}")

    typer.echo("common H2 headings")
    if outcome.markdown_analyzed == 0:
        typer.echo("  no heading evidence found")
    else:
        for frequency in outcome.headings:
            heading = _json(frequency.heading)
            percentage = f"{frequency.percentage:f}"
            typer.echo(
                f"  {heading} | files: {frequency.file_count} | percent: {percentage}%"
            )

    typer.echo("exact H2 heading sets")
    if outcome.markdown_analyzed == 0:
        typer.echo("  no heading sets found")
    else:
        for group in outcome.heading_groups:
            typer.echo(f"  {_json(list(group.headings))} | files: {group.file_count}")
            if group.sample_paths:
                typer.echo(f"    samples: {_json(list(group.sample_paths))}")

    typer.echo("skipped")
    if not outcome.skips:
        typer.echo("  none")
    else:
        for summary in outcome.skips:
            typer.echo(
                f"  {summary.reason} | count: {summary.count} | "
                f"unseen subtrees: {summary.unseen_subtrees}"
            )
            if summary.sample_paths:
                typer.echo(f"    samples: {_json(list(summary.sample_paths))}")


def _json(value: object) -> str:
    """JSON serialization that preserves Unicode while escaping quotes."""
    return json.dumps(value, ensure_ascii=False)


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
        write_record_file,
        output=output,
        dry_run=dry_run,
    )
    _print_adapt_report(outcome)
    raise typer.Exit(outcome.exit_code)


def _print_adapt_report(outcome: AdaptOutcome) -> None:
    """Print the adapt run's report: discovery, per record, and summary."""
    if outcome.exit_code == 3:
        # Lead with the most important message, so an invalid corpus is the
        # first thing an operator sees rather than the last.
        typer.echo("corpus path does not exist or holds no docs/specs/ directory")
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
    suffix = " (dry run, nothing written)" if outcome.dry_run else ""
    typer.echo(f"output: {outcome.output_dir}{suffix}")


if __name__ == "__main__":
    app()
