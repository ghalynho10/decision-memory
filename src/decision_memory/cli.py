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
    Manifest,
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
from decision_memory.application.dto import (
    FreshnessState,
    IngestRequest,
    IngestResult,
    QueryRequest,
    QueryResult,
    QueryState,
)
from decision_memory.application.ingest import IngestDependencies, ingest_records
from decision_memory.application.query import QueryDependencies, query_index
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
from decision_memory.infrastructure.index_lock import LockError, store_lock
from decision_memory.infrastructure.index_reader import SqliteChromaIndexReader
from decision_memory.infrastructure.index_store import SqliteChromaIndexWriter
from decision_memory.infrastructure.manifest_reader import (
    load_manifest,
    manifest_path,
    raw_manifest_digest,
    record_loader,
)
from decision_memory.infrastructure.openai_embeddings import embed_texts
from decision_memory.infrastructure.openai_generation import (
    coverage_verdict,
    entail_verdict,
    extract_facets,
    generate_answer,
)
from decision_memory.infrastructure.path_resolution import resolve_cited_paths
from decision_memory.infrastructure.project_config import (
    ProjectConfig,
    ProjectConfigError,
    load_project_config,
)
from decision_memory.infrastructure.runtime_loader import LoadFailure, select_adapter
from decision_memory.infrastructure.tokenization import tiktoken_count

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


# ---------------------------------------------------------------------------
# Ingest and query commands (spec 0007)
# ---------------------------------------------------------------------------


def _git_root(start: Path) -> Path | None:
    """The nearest Git root above ``start``, or None."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    root = result.stdout.strip()
    return Path(root) if root else None


def _resolve_records_dir(
    cli_records: Path | None, config: ProjectConfig | None
) -> Path | None:
    """Records directory precedence: CLI, config output, config corpus root."""
    if cli_records is not None:
        return cli_records
    if config is not None and config.output is not None:
        return config.output
    if config is not None and config.corpus_root is not None:
        return config.corpus_root / ".decision-memory" / "records"
    return None


def _resolve_store_dir(cli_store: Path | None, config: ProjectConfig | None) -> Path:
    """Store directory precedence: CLI, config corpus root, Git root, cwd."""
    if cli_store is not None:
        return cli_store
    if config is not None and config.corpus_root is not None:
        return config.corpus_root / ".decision-memory" / "query-index"
    root = _git_root(Path.cwd())
    if root is not None:
        return root / ".decision-memory" / "query-index"
    return Path.cwd() / ".decision-memory" / "query-index"


@app.command("ingest")
def ingest_command(
    records_dir: Annotated[
        Path | None,
        typer.Argument(
            help="Records directory; defaults to the configured output or corpus root"
        ),
    ] = None,
    store: Annotated[
        Path | None,
        typer.Option("--store", help="Index store path"),
    ] = None,
    rebuild: Annotated[
        bool,
        typer.Option("--rebuild", help="Force an explicit rebuild"),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Preview spend without provider calls or writes",
        ),
    ] = False,
    debug: Annotated[
        bool,
        typer.Option("--debug", help="Print the complete chunk plan"),
    ] = False,
) -> None:
    """Ingest canonical records into the versioned query index."""
    config = _project_config()
    resolved = _resolve_records_dir(records_dir, config)
    if resolved is None:
        typer.echo(
            "no records directory resolved; pass RECORDS_DIR or set config output"
        )
        raise typer.Exit(2)
    if not resolved.is_dir():
        typer.echo(f"records directory does not exist: {resolved}")
        raise typer.Exit(3)
    store_dir = _resolve_store_dir(store, config)
    writer = SqliteChromaIndexWriter(store_dir)

    def _run() -> IngestResult:
        return ingest_records(
            IngestRequest(
                records_dir=resolved,
                store_dir=store_dir,
                rebuild=rebuild,
                dry_run=dry_run,
            ),
            IngestDependencies(
                load_manifest=lambda: load_manifest(manifest_path(resolved)),
                read_record=record_loader(resolved),
                count_tokens=tiktoken_count,
                embed=embed_texts,
                raw_manifest_digest=lambda: raw_manifest_digest(
                    manifest_path(resolved)
                ),
                store=writer,
            ),
        )

    try:
        if dry_run:
            outcome = _run()
        else:
            with store_lock(store_dir, exclusive=True):
                outcome = _run()
    except LockError:
        typer.echo("store is locked by another ingest or query")
        raise typer.Exit(1) from None
    finally:
        writer.close()
    _print_ingest_report(outcome, debug, dry_run)
    raise typer.Exit(outcome.exit_code)


@app.command("query")
def query_command(
    question: Annotated[str, typer.Argument(help="The question to answer")],
    store: Annotated[
        Path | None,
        typer.Option("--store", help="Index store path"),
    ] = None,
    allow_stale: Annotated[
        bool,
        typer.Option("--allow-stale", help="Allow a stale index manifest"),
    ] = False,
    debug: Annotated[
        bool,
        typer.Option("--debug", help="Print the full query trace"),
    ] = False,
) -> None:
    """Ask a question and get a cited answer from the index."""
    config = _project_config()
    store_dir = _resolve_store_dir(store, config)
    if not store_dir.exists():
        typer.echo(f"store directory does not exist: {store_dir}")
        raise typer.Exit(3)
    reader = SqliteChromaIndexReader(store_dir)

    def _stored_manifest_path() -> Path | None:
        stored = reader.manifest_metadata()[0]
        return Path(stored) if stored else None

    def _load_stored_manifest() -> Manifest:
        path = _stored_manifest_path()
        if path is None:
            raise FileNotFoundError("no stored manifest path")
        return load_manifest(path)

    def _stored_manifest_raw_digest() -> str:
        path = _stored_manifest_path()
        if path is None:
            raise FileNotFoundError("no stored manifest path")
        return raw_manifest_digest(path)

    try:
        with store_lock(store_dir, exclusive=False):
            outcome = query_index(
                QueryRequest(
                    question=question,
                    store_dir=store_dir,
                    allow_stale=allow_stale,
                ),
                QueryDependencies(
                    store=reader,
                    count_tokens=tiktoken_count,
                    embed=embed_texts,
                    load_manifest=_load_stored_manifest,
                    raw_manifest_digest=_stored_manifest_raw_digest,
                    extract_facets=extract_facets,
                    generate_answer=generate_answer,
                    entail=entail_verdict,
                    coverage=coverage_verdict,
                ),
            )
    except LockError:
        typer.echo("store is locked by an ingest")
        raise typer.Exit(1) from None
    _print_query_report(outcome, debug)
    raise typer.Exit(outcome.exit_code)


def _print_ingest_report(outcome: IngestResult, debug: bool, dry_run: bool) -> None:
    """Print the fixed ingest report (spec 0007 AC-10)."""
    counts: dict[str, int] = {}
    for record in outcome.records:
        counts[record.action.value] = counts.get(record.action.value, 0) + 1
    typer.echo(
        "plan: "
        f"added {counts.get('added', 0)}, updated {counts.get('updated', 0)}, "
        f"unchanged {counts.get('unchanged', 0)}, "
        f"removed {counts.get('removed', 0)}, failed {counts.get('failed', 0)}"
    )
    for record in sorted(outcome.records, key=lambda item: item.record_id):
        if record.action.value == "failed":
            typer.echo(f"failed {record.record_id}: {record.failure_code}")
        else:
            typer.echo(f"{record.action.value} {record.record_id}")
        if debug:
            for chunk in record.chunks:
                typer.echo(
                    f"  chunk {chunk.chunk_id} {chunk.value_path} "
                    f"ordinal={chunk.ordinal} "
                    f"evidence_tokens={chunk.evidence_token_count} "
                    f"embedding_tokens={chunk.embedding_input_token_count}"
                )
    typer.echo(f"result: {outcome.state.value}")
    typer.echo(f"output: {outcome.store_path}")
    if dry_run:
        typer.echo("dry run, no provider calls or writes")


def _print_query_report(outcome: QueryResult, debug: bool) -> None:
    """Print the fixed query report (spec 0007 AC-10, AC-13)."""
    if outcome.state == QueryState.FAILED and outcome.failure is not None:
        typer.echo(
            f"error {outcome.failure.stage} {outcome.failure.code}: "
            f"{outcome.failure.detail}"
        )
        return
    if outcome.state == QueryState.ABSTAINED:
        typer.echo("not enough evidence here")
        return
    for sentence in outcome.sentences:
        markers = ",".join(sentence.citation_ids)
        typer.echo(f"{sentence.text} [{markers}]")
    typer.echo("Sources")
    for citation in outcome.citations:
        chunk = citation.chunk_id or "-"
        typer.echo(
            f"{citation.citation_id} {citation.record_id} {chunk} "
            f"{citation.value_path} {citation.relative_path} {citation.section}"
        )
    stale_reasons = outcome.trace.freshness.stale_reasons
    if (
        outcome.trace.freshness.state
        in (
            FreshnessState.DRIFT,
            FreshnessState.UNKNOWN,
        )
        or stale_reasons
    ):
        labels = ", ".join(reason.value for reason in stale_reasons)
        typer.echo(f"WARNING: stale index{f' ({labels})' if labels else ''}")
    if debug:
        _print_query_debug(outcome)


def _print_query_debug(result: QueryResult) -> None:
    """Print the fixed debug sections in order (spec 0007 AC-13)."""
    trace = result.trace
    typer.echo("Freshness")
    typer.echo(f"  state: {trace.freshness.state.value}")
    stored = trace.freshness.stored_pipeline_signature
    running = trace.freshness.running_pipeline_signature
    typer.echo(f"  stored_pipeline_signature: {stored}")
    typer.echo(f"  running_pipeline_signature: {running}")
    typer.echo(f"  records_manifest_path: {trace.freshness.records_manifest_path}")
    typer.echo(f"  manifest_available: {trace.freshness.manifest_available}")
    typer.echo(f"  start_semantic_digest: {trace.freshness.start_semantic_digest}")
    typer.echo(f"  end_semantic_digest: {trace.freshness.end_semantic_digest}")
    typer.echo(f"  start_raw_digest: {trace.freshness.start_raw_digest}")
    typer.echo(f"  end_raw_digest: {trace.freshness.end_raw_digest}")
    if trace.freshness.stale_reasons:
        labels = ", ".join(reason.value for reason in trace.freshness.stale_reasons)
        typer.echo(f"  stale_reasons: {labels}")
    typer.echo("Retrieval")
    typer.echo(f"  question: {trace.retrieval.question}")
    typer.echo(f"  filters: {','.join(trace.retrieval.filters)}")
    typer.echo(f"  candidate_limit: {trace.retrieval.candidate_limit}")
    typer.echo(f"  accepted_limit: {trace.retrieval.accepted_limit}")
    typer.echo(f"  relevance_floor: {trace.retrieval.relevance_floor}")
    for candidate in trace.retrieval.candidates:
        typer.echo(
            f"  candidate {candidate.chunk_id} {candidate.record_id} "
            f"distance={candidate.distance:.6f} similarity={candidate.similarity:.6f} "
            f"rank={candidate.rank} disposition={candidate.disposition.value}"
        )
        typer.echo("  chunk text begin")
        typer.echo(candidate.text)
        typer.echo("  chunk text end")
    typer.echo("Facets")
    for facet in trace.generation.facets:
        typer.echo(f"  {facet.facet_id}: {facet.text}")
    typer.echo("Draft")
    for sentence in trace.generation.draft_sentences:
        markers = ",".join(sentence.chunk_ids)
        typer.echo(f"  {sentence.sentence_id}: {sentence.text} [{markers}]")
    typer.echo("Verification")
    for sentence_id, contained in trace.verification.containment:
        typer.echo(f"  {sentence_id} containment={contained}")
    for sentence_id, verdict, reason in trace.verification.entailment:
        typer.echo(f"  {sentence_id} entailment={verdict} reason={reason}")
    for removed_id in trace.verification.removed_sentences:
        typer.echo(f"  removed {removed_id}")
    for row in trace.verification.coverage:
        markers = ",".join(row.sentence_ids)
        typer.echo(f"  {row.facet_id} covered={row.covered} [{markers}]")
    for facet in trace.verification.uncovered_facets:
        typer.echo(f"  uncovered {facet.facet_id}: {facet.text}")
    typer.echo("Providers")
    for attempt in trace.providers:
        typer.echo(
            f"  {attempt.concern} attempt={attempt.attempt_number} "
            f"elapsed_ms={attempt.elapsed_ms} outcome={attempt.outcome.value}"
        )
    typer.echo("Citations")
    for citation in result.citations:
        typer.echo(f"  {citation.citation_id} {citation.record_id} {citation.chunk_id}")
    typer.echo("Result")
    typer.echo(f"  state: {result.state.value}")
    if result.abstention_stage is not None:
        typer.echo(f"  abstention_stage: {result.abstention_stage.value}")
    typer.echo(f"  freshness: {result.freshness.value}")


if __name__ == "__main__":
    app()
