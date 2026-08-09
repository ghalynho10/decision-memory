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

from decision_memory.application.adapter import (
    BUILTIN_ADAPTER_ID,
    AdaptOutcome,
    SourceAdapter,
    adapt_corpus,
)
from decision_memory.application.conformance import (
    CheckResult,
    ConformanceCase,
    ConformanceManifest,
    ConformanceOutcome,
    run_adapter_conformance,
)
from decision_memory.application.corpus_validation import (
    CorpusValidationOutcome,
    validate_corpus,
)
from decision_memory.application.doctor_service import (
    EXIT_ERROR,
    DoctorOutcome,
    DoctorRequest,
    run_doctor,
)
from decision_memory.application.settings import SettingsError, resolve_runtime_settings
from decision_memory.application.validation_service import validate_file
from decision_memory.infrastructure.conformance_fixtures import conformance_fixture_port
from decision_memory.infrastructure.conformance_manifest import (
    ConformanceManifestError,
    load_conformance_manifest,
)
from decision_memory.infrastructure.doctor_scanner import scan_corpus
from decision_memory.infrastructure.file_reader import (
    parse_record_file,
    write_record_file,
)
from decision_memory.infrastructure.path_resolution import resolve_cited_paths
from decision_memory.infrastructure.project_config import (
    ProjectConfig,
    ProjectConfigError,
    load_project_config,
)
from decision_memory.infrastructure.runtime_loader import LoadFailure, select_adapter

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
        Path | None,
        typer.Argument(
            help="A canonical record file, or a corpus directory for write free "
            "corpus validation; omit it to use the configured corpus root"
        ),
    ] = None,
    project_root: Annotated[
        Path | None,
        typer.Option(help="Project root anchoring path and git checks"),
    ] = None,
    adapter: Annotated[
        str | None,
        typer.Option(
            "--adapter",
            help="Adapter for corpus validation: the built in jsmastery-specs "
            "or package.module:attribute for an installed third party adapter",
        ),
    ] = None,
) -> None:
    """Validate a canonical record file, or run write free corpus validation.

    A file argument validates one canonical record (unchanged from spec 0002).
    A directory argument runs corpus validation: it checks whether the selected
    adapter can turn the corpus into valid records, writing nothing.
    """
    if file is not None:
        # A directory, or a path that does not exist, is a corpus argument; a
        # path that exists and is not a directory is a record file argument.
        if file.is_dir() or not file.exists():
            _validate_corpus_cli(file, adapter)
            return
        if adapter is not None:
            # AC-5: passing --adapter with a record file is a usage error.
            typer.echo("--adapter requires a corpus directory, not a record file")
            raise typer.Exit(2)
        outcome = validate_file(
            file, project_root, reader=parse_record_file, resolver=resolve_cited_paths
        )
        for violation in outcome.violations:
            field = violation.field if violation.field else "(record)"
            typer.echo(
                f"{violation.severity.value} {violation.rule} {field}: "
                f"{violation.reason}"
            )
        if not outcome.violations:
            typer.echo("valid record, no violations")
        raise typer.Exit(outcome.exit_code)
    # No argument: corpus validation from the configured corpus root (AC-5).
    _validate_corpus_cli(None, adapter)


def _validate_corpus_cli(corpus_root: Path | None, adapter: str | None) -> None:
    """Run write free corpus validation and print its report."""
    settings = resolve_runtime_settings(
        cli_corpus=corpus_root,
        cli_adapter=adapter,
        cli_output=None,
        config=_project_config(),
    )
    if isinstance(settings, SettingsError):
        typer.echo(settings.message)
        raise typer.Exit(2)
    loaded, exit_code, error = _load_adapter(settings.adapter)
    if loaded is None:
        typer.echo(error)
        raise typer.Exit(exit_code or 1)
    outcome = validate_corpus(settings.corpus_root, loaded)
    _print_corpus_validation_report(outcome)
    raise typer.Exit(outcome.exit_code)


def _print_corpus_validation_report(outcome: CorpusValidationOutcome) -> None:
    """Print the write free corpus validation report (spec 0005 AC-6).

    The report includes adapter identity, discovery totals, every skip and
    collision, every source result, violations with stable rule ids, and a
    final summary. It never prints a projected write state or output path.
    """
    typer.echo(f"adapter: {outcome.adapter_id} {outcome.adapter_version}")
    if outcome.exit_code == 3:
        typer.echo(
            outcome.corpus_error or "corpus path does not exist or is not a directory"
        )
        return
    if outcome.discovery_failure is not None:
        failure = outcome.discovery_failure
        typer.echo(
            f"adapter failed during {failure.operation}: "
            f"{failure.exception_type}: {failure.message}"
        )
        return
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
    for result in outcome.results:
        if result.kind == "ok":
            typer.echo(f"  ok {result.id}")
        elif result.kind == "violation":
            for violation in result.violations:
                field = violation.field if violation.field else "(record)"
                typer.echo(
                    f"  violation {result.id}: {violation.rule} {field}: "
                    f"{violation.reason}"
                )
        else:
            source_failure = result.failure
            if source_failure is not None:
                typer.echo(
                    f"  exception {result.id}: {source_failure.operation} "
                    f"{source_failure.exception_type}: {source_failure.message}"
                )
    failed = sum(1 for result in outcome.results if result.kind != "ok")
    typer.echo(f"result: {len(outcome.results) - failed} ok, {failed} failed")


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


def _project_config() -> ProjectConfig | None:
    """Load project config, exiting 1 on a config file error (AC-13)."""
    try:
        found = load_project_config(Path.cwd())
    except ProjectConfigError as exc:
        typer.echo(f"config error: {exc}")
        raise typer.Exit(1) from None
    if found is None:
        return None
    return found[1]


def _load_adapter(
    selector: str | None,
) -> tuple[SourceAdapter | None, int | None, str | None]:
    """Resolve and load an adapter, returning (adapter, exit_code, error).

    A ``None`` selector or the built in name selects ``jsmastery-specs``. A
    malformed selector is a usage error (exit 2); import, attribute, and
    contract failures are runtime errors (exit 1). The returned error message
    names the selector, the failed phase, and the original exception type and
    message, without a traceback (AC-9).
    """
    name = selector or BUILTIN_ADAPTER_ID
    loaded = select_adapter(name)
    if isinstance(loaded, LoadFailure):
        if loaded.exception_type:
            detail = f"{loaded.phase} {loaded.exception_type}: {loaded.message}"
        else:
            detail = f"{loaded.phase}: {loaded.message}"
        message = f"failed to load adapter {name!r}: {detail}"
        exit_code = 2 if loaded.phase == "selector" else 1
        return None, exit_code, message
    return loaded, None, None


@app.command("adapt")
def adapt_command(
    corpus_path: Annotated[
        Path | None,
        typer.Argument(
            help="Path to the corpus; defaults to the configured corpus_root"
        ),
    ] = None,
    adapter: Annotated[
        str | None,
        typer.Option(
            "--adapter",
            help="Adapter to use: the built in jsmastery-specs or "
            "package.module:attribute for an installed third party adapter",
        ),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option(help="Output directory for records and the manifest"),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Run and report without writing anything"),
    ] = False,
) -> None:
    """Adapt a project's specs into canonical decision records."""
    settings = resolve_runtime_settings(
        cli_corpus=corpus_path,
        cli_adapter=adapter,
        cli_output=output,
        config=_project_config(),
    )
    if isinstance(settings, SettingsError):
        typer.echo(settings.message)
        raise typer.Exit(2)
    loaded, exit_code, error = _load_adapter(settings.adapter)
    if loaded is None:
        typer.echo(error)
        raise typer.Exit(exit_code or 1)
    outcome = adapt_corpus(
        settings.corpus_root,
        loaded,
        write_record_file,
        output=settings.output,
        dry_run=dry_run,
    )
    _print_adapt_report(outcome)
    raise typer.Exit(outcome.exit_code)


def _print_adapt_report(outcome: AdaptOutcome) -> None:
    """Print the adapt run's report: identity, discovery, per record, summary."""
    typer.echo(f"adapter: {outcome.adapter_id} {outcome.adapter_version}")
    if outcome.exit_code == 3:
        # Lead with the most important message, so an invalid corpus is the
        # first thing an operator sees rather than the last. The message
        # comes from the adapter's corpus error, so each adapter names its
        # own missing structure (AC-20).
        typer.echo(
            outcome.corpus_error or "corpus path does not exist or is not a directory"
        )
    if outcome.failure is not None:
        typer.echo(
            f"adapter failed during {outcome.failure.operation}: "
            f"{outcome.failure.exception_type}: {outcome.failure.message}"
        )
    if outcome.manifest_warning is not None:
        typer.echo(f"warning: {outcome.manifest_warning}")
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


@app.command("test-adapter")
def test_adapter_command(
    selector: Annotated[
        str,
        typer.Argument(
            help="Adapter to test: the built in jsmastery-specs or "
            "package.module:attribute for an installed third party adapter"
        ),
    ],
    cases: Annotated[
        Path,
        typer.Option(
            "--cases",
            help="Path to the adapter conformance manifest (a strict YAML file)",
        ),
    ],
) -> None:
    """Run the conformance suite against one adapter and its manifest.

    Every reachable independent protocol, behavior, and anti fabrication check
    runs and reports one line each. Exit 0 means every executed check passed;
    exit 1 covers loading, manifest, fixture, execution, and conformance
    failures; exit 2 is reserved for a malformed selector on the command line
    (spec 0006 AC-16).
    """
    try:
        manifest = load_conformance_manifest(cases)
    except ConformanceManifestError as exc:
        typer.echo(f"manifest: {cases.name}")
        typer.echo(f"FAIL {exc.rule}: {exc.detail}")
        typer.echo("result: 0 passed, 1 failed")
        typer.echo("final: failed")
        raise typer.Exit(1) from None
    loaded = select_adapter(selector)
    if isinstance(loaded, LoadFailure):
        if loaded.exception_type:
            detail = f"{loaded.phase} {loaded.exception_type}: {loaded.message}"
        else:
            detail = f"{loaded.phase}: {loaded.message}"
        typer.echo(f"FAIL adapter.load: {detail}")
        typer.echo("result: 0 passed, 1 failed")
        typer.echo("final: failed")
        raise typer.Exit(2 if loaded.phase == "selector" else 1)
    outcome = run_adapter_conformance(loaded, manifest, conformance_fixture_port())
    _print_conformance_report(outcome, manifest, cases.name)
    raise typer.Exit(outcome.exit_code)


def _print_conformance_report(
    outcome: ConformanceOutcome, manifest: ConformanceManifest, manifest_name: str
) -> None:
    """Print the deterministic conformance report (spec 0006 AC-15).

    Order is fixed by phase, manifest case order, then declared source and
    path order. Case headers print before the first check of each case.
    """
    typer.echo(f"adapter: {outcome.adapter_id} {outcome.adapter_version}")
    typer.echo(f"manifest: {manifest_name}")
    case_index = 0
    for check in outcome.checks:
        if (
            check.case_id is not None
            and case_index < len(manifest.cases)
            and manifest.cases[case_index].id == check.case_id
        ):
            _print_conformance_case_header(manifest.cases[case_index])
            case_index += 1
        _print_conformance_check(check)
    typer.echo(f"result: {outcome.passed} passed, {outcome.failed} failed")
    final = "passed" if outcome.failed == 0 else "failed"
    typer.echo(f"final: {final}")


def _print_conformance_case_header(case: ConformanceCase) -> None:
    line = f"case: {case.id} category={case.category.value}"
    if case.subject_path is not None:
        line += f" subject={case.subject_path.as_posix()}"
    if case.target_fields:
        line += f" target_fields={_json(sorted(case.target_fields))}"
    typer.echo(line)


def _print_conformance_check(check: CheckResult) -> None:
    status = "PASS" if check.status else "FAIL"
    line = f"{status} {check.rule}"
    coordinates: list[str] = []
    if check.case_id is not None:
        coordinates.append(f"case={check.case_id}")
    if check.source_id is not None:
        coordinates.append(f"source={check.source_id}")
    if check.path is not None:
        coordinates.append(f"path={check.path.as_posix()}")
    if check.operation is not None:
        coordinates.append(f"operation={check.operation}")
    if check.variant is not None:
        coordinates.append(f"variant={check.variant.value}")
    if coordinates:
        line += " " + " ".join(coordinates)
    if check.detail:
        line += f": {check.detail}"
    typer.echo(line)
    if check.artifact_path is not None:
        typer.echo(f"artifact: {check.artifact_path}")


if __name__ == "__main__":
    app()
