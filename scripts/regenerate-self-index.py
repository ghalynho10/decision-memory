#!/usr/bin/env python3
"""Rebuild the committed bundle of this repository's own decision records.

Spec 0014. The bundle at ``examples/self-index/`` lets a new reader ask a real
cited question with no corpus to prepare. This script is the only thing that
writes it.

Run it:

    uv run --env-file .env python scripts/regenerate-self-index.py

**When to run it.** Only when the pipeline signature changes or the corpus
changes materially (AC-15). Not on a schedule and not for a typo in a spec.
Every regeneration writes roughly 7MB of fresh embeddings into git history
permanently, and new embeddings do not delta compress, so the cost is paid in
full each time. Nothing in the test suite forces a rebuild: a bundle that is
behind the corpus is honest, it answers about the corpus at its freeze point.
The suite only fails when the bundle stops matching the pipeline that reads it.

**What it costs.** One embedding pass over the corpus plus ``--runs`` full
query executions per candidate question, each of which calls the provider
several times. At the default of ten runs and two questions that is twenty
full queries.

**What it guarantees.** The committed bundle is never left partially written
(AC-11). Everything is built in a scratch directory beside the bundle and
swapped in only after every check passes. The swap is two renames, because a
POSIX rename cannot replace a non empty directory: the old bundle moves aside,
the new one moves into place, the old one is deleted. A process killed between
those renames leaves the bundle briefly absent rather than corrupt, which
``git status`` shows plainly and rerunning this script repairs. The script
detects and finishes an interrupted swap on startup before doing anything else.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from decision_memory.application.adapter import adapt_corpus  # noqa: E402
from decision_memory.application.dto import (  # noqa: E402
    IngestRequest,
    QueryFilters,
    QueryRequest,
    QueryState,
)
from decision_memory.application.ingest import (  # noqa: E402
    IngestDependencies,
    ingest_records,
)
from decision_memory.application.pipeline import pipeline_signature  # noqa: E402
from decision_memory.application.query import (  # noqa: E402
    QueryDependencies,
    query_index,
)
from decision_memory.infrastructure.bm25 import bm25_lexical_scorer  # noqa: E402
from decision_memory.infrastructure.bundle_snapshot import (  # noqa: E402
    BundleSnapshot,
    DemoQuestion,
    write_snapshot,
)
from decision_memory.infrastructure.file_reader import (  # noqa: E402
    write_record_file,
)
from decision_memory.infrastructure.index_reader import (  # noqa: E402
    SqliteChromaIndexReader,
)
from decision_memory.infrastructure.index_store import (  # noqa: E402
    SqliteChromaIndexWriter,
)
from decision_memory.infrastructure.jsmastery_adapter import (  # noqa: E402
    JsmasteryAdapter,
)
from decision_memory.infrastructure.manifest_reader import (  # noqa: E402
    load_manifest,
    manifest_path,
    raw_manifest_digest,
    record_loader,
)
from decision_memory.infrastructure.openai_common import require_api_key  # noqa: E402
from decision_memory.infrastructure.openai_embeddings import embed_texts  # noqa: E402
from decision_memory.infrastructure.openai_generation import (  # noqa: E402
    coverage_verdict,
    decompose_sentence,
    entail_verdict,
    extract_facets,
    generate_answer,
)
from decision_memory.infrastructure.store import (  # noqa: E402
    generation_paths,
    read_active,
)
from decision_memory.infrastructure.store_resolution import (  # noqa: E402
    store_resolution,
)
from decision_memory.infrastructure.tokenization import tiktoken_count  # noqa: E402

DEFAULT_BUNDLE = Path("examples/self-index")
DEFAULT_RUNS = 10
RECORDS_DIRNAME = "records"
STORE_DIRNAME = "query-index"
# The bundle root sits one level under the clone root's ``examples/``, so the
# corpus the records cite is two levels up from the snapshot file.
CORPUS_ROOT_RELATIVE = "../.."


@dataclass(frozen=True)
class Candidate:
    """One question the bundle pins, and the disposition expected of it."""

    question: str
    expected: str


# The pinned demo questions. These are the exact strings the README shows, the
# snapshot records, and the integration smoke test asks, so the front page and
# the test cannot drift apart. Spec 0014's snapshot table refers to "the pinned
# questions, below" but never lists them; they are declared here until the spec
# records them. Both were measured before being pinned (docs/session-notes.md,
# "Measured flakiness for the smoke test's answering question"): the answering
# question abstained on 1 of 3 runs against a clean clone, which is why AC-13
# characterises it against the frozen index rather than trusting it.
CANDIDATE_QUESTIONS = (
    Candidate(
        question=(
            "why was the entry point discovery approach rejected for "
            "third party adapters?"
        ),
        expected="answered",
    ),
    Candidate(
        question="why is the subscription priced at nine dollars per month?",
        expected="abstained",
    ),
)


class RegenerationError(Exception):
    """A check failed, so the committed bundle was left untouched."""


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Rebuild the committed self index bundle. Run only when the "
            "pipeline signature changes or the corpus changes materially; "
            "every run adds roughly 7MB to git history permanently."
        )
    )
    parser.add_argument(
        "--bundle",
        type=Path,
        default=DEFAULT_BUNDLE,
        help=f"Bundle directory to rewrite (default {DEFAULT_BUNDLE})",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=DEFAULT_RUNS,
        help=(
            f"Characterisation runs per pinned question (default {DEFAULT_RUNS}). "
            "Every run is a full query and costs a provider call."
        ),
    )
    args = parser.parse_args()

    bundle = (REPO_ROOT / args.bundle).resolve()
    if args.runs < 1:
        print("--runs must be at least 1", file=sys.stderr)
        return 2

    try:
        recovered = recover_interrupted_swap(bundle)
        if recovered:
            print(f"recovered an interrupted swap: {recovered}")
        regenerate(bundle, args.runs)
    except RegenerationError as error:
        print(f"\nrefused to publish: {error}", file=sys.stderr)
        print("the committed bundle was not modified", file=sys.stderr)
        return 1
    return 0


def aside_path(bundle: Path) -> Path:
    """Where the old bundle is set aside during the two rename swap."""
    return bundle.with_name(bundle.name + ".old")


def recover_interrupted_swap(bundle: Path) -> str | None:
    """Finish or roll back a swap a previous run was killed partway through.

    The set aside directory only exists between the two renames. Finding one
    means a previous run died there, and there are exactly two states to
    repair: the new bundle already landed (so the leftover is garbage), or it
    never did (so the leftover is the only copy and must go back).
    """
    aside = aside_path(bundle)
    if not aside.exists():
        return None
    if bundle.exists():
        shutil.rmtree(aside)
        return f"removed a leftover {aside.name} (the new bundle had landed)"
    aside.rename(bundle)
    return f"restored {bundle.name} from {aside.name} (the new bundle never landed)"


def regenerate(bundle: Path, runs: int) -> None:
    """Build a fresh bundle in scratch space and swap it in once it checks out."""
    require_api_key()
    scratch = bundle.with_name(f".{bundle.name}.building")
    if scratch.exists():
        shutil.rmtree(scratch)
    # Scratch lives beside the bundle, not in the system temp directory, so the
    # final swap is a same filesystem rename and cannot fail partway across a
    # device boundary.
    scratch.mkdir(parents=True)
    try:
        records_dir = scratch / RECORDS_DIRNAME
        store_dir = scratch / STORE_DIRNAME

        record_count = build_records(records_dir)
        build_index(records_dir, store_dir)
        blank_store_paths(store_dir)

        snapshot = BundleSnapshot(
            schema_version=1,
            generated_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            commit=current_commit(),
            pipeline_signature=pipeline_signature(),
            records_dir=RECORDS_DIRNAME,
            store_dir=STORE_DIRNAME,
            corpus_root=CORPUS_ROOT_RELATIVE,
            records_indexed=record_count,
            specs_at_freeze=count_spec_directories(),
            demo_questions=(),
        )
        # Written before characterisation because the store's own path fields
        # are now empty: the queries below resolve through this file, which
        # means the characterisation exercises the exact path a reader takes.
        write_snapshot(scratch, snapshot)

        measured = characterise(scratch, store_dir, runs)
        write_snapshot(scratch, replace_questions(snapshot, measured))

        report_absent_specs(records_dir)
        publish(scratch, bundle)
        print(f"\npublished {bundle.relative_to(REPO_ROOT)}")
        print(f"  records indexed: {record_count}")
        print(f"  freeze commit:   {snapshot.commit}")
    finally:
        if scratch.exists():
            shutil.rmtree(scratch)


def build_records(records_dir: Path) -> int:
    """Adapt this repository's specs into canonical records (AC-14 input)."""
    print("adapting the corpus ...")
    outcome = adapt_corpus(
        REPO_ROOT,
        JsmasteryAdapter(),
        write_record_file,
        output=records_dir,
    )
    if outcome.exit_code != 0:
        raise RegenerationError(f"adapt failed with exit code {outcome.exit_code}")
    blank_manifest_source_root(records_dir)
    manifest = load_manifest(manifest_path(records_dir))
    print(f"  wrote {len(manifest.entries)} records")
    return len(manifest.entries)


def blank_manifest_source_root(records_dir: Path) -> None:
    """Empty the manifest's absolute ``source_root_hint`` before ingest.

    ``adapt`` records the building machine's absolute corpus path here
    (``adapter.py:391``), and this manifest is committed as part of the bundle,
    so leaving it would publish a home directory in git history permanently.
    That is the disclosure class AC-6's security model exists to remove, and
    AC-6 names only the store's two columns.

    The order matters and is not interchangeable: ``source_root_hint`` is
    inside the semantic manifest digest (``adapter.py:505``), so this must
    happen **before** ingest. Blanking it afterwards would leave the stored
    digest computed over the old value, and every read of the shipped bundle
    would then report ``DRIFT`` against its own committed manifest.
    """
    path = manifest_path(records_dir)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["source_root_hint"] = ""
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def build_index(records_dir: Path, store_dir: Path) -> None:
    """Ingest the records into a fresh index inside the scratch bundle."""
    print("ingesting into a fresh index (this calls the embeddings API) ...")
    writer = SqliteChromaIndexWriter(store_dir)
    try:
        result = ingest_records(
            IngestRequest(
                records_dir=records_dir,
                store_dir=store_dir,
                rebuild=True,
                dry_run=False,
            ),
            IngestDependencies(
                load_manifest=lambda: load_manifest(manifest_path(records_dir)),
                read_record=record_loader(records_dir),
                count_tokens=tiktoken_count,
                embed=embed_texts,
                raw_manifest_digest=lambda: raw_manifest_digest(
                    manifest_path(records_dir)
                ),
                require_api_key=require_api_key,
                store=writer,
            ),
        )
    finally:
        writer.close()
    if result.exit_code != 0:
        failure = result.failure.message if result.failure else "unknown failure"
        raise RegenerationError(f"ingest failed: {failure}")


def blank_store_paths(store_dir: Path) -> None:
    """Write the store's two absolute path columns empty (AC-6).

    A store records where it was built. A shipped store must not, so both
    columns go out empty and the reader resolves them from the snapshot
    instead. This removes the disclosure class rather than one instance of it.
    """
    generation_id = read_active(store_dir)
    if generation_id is None:
        raise RegenerationError("the freshly built store has no active generation")
    database, _generation_json, _chroma = generation_paths(store_dir, generation_id)
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "UPDATE index_metadata SET records_manifest_path = '', "
            "source_root_hint = '' WHERE id = 1"
        )
        connection.commit()
    finally:
        connection.close()
    verify_no_absolute_paths(database)


def verify_no_absolute_paths(database: Path) -> None:
    """Fail before publishing if any metadata column still holds a path (AC-6)."""
    connection = sqlite3.connect(database)
    try:
        cursor = connection.execute("SELECT * FROM index_metadata WHERE id = 1")
        columns = [description[0] for description in cursor.description]
        row = cursor.fetchone()
    finally:
        connection.close()
    if row is None:
        raise RegenerationError("the freshly built store has no metadata row")
    for name, value in zip(columns, row, strict=True):
        if isinstance(value, str) and looks_absolute(value):
            raise RegenerationError(
                f"index_metadata.{name} still holds an absolute path: {value!r}"
            )


def looks_absolute(value: str) -> bool:
    """Whether a stored string names an absolute path on any platform.

    Checked without relying on the platform this runs on, so a POSIX build
    cannot ship a Windows drive path unnoticed and the reverse.
    """
    if not value:
        return False
    if value.startswith("/") or value.startswith("\\"):
        return True
    if len(value) >= 2 and value[1] == ":" and value[0].isalpha():
        return True
    return Path(value).is_absolute()


def characterise(
    bundle_root: Path, store_dir: Path, runs: int
) -> tuple[DemoQuestion, ...]:
    """Run each pinned question ``runs`` times and refuse on any wobble (AC-13).

    Disposition only: answered versus abstained. Answer text and citation sets
    vary between runs by design and are never compared. The counts are recorded
    in the snapshot so a later flake reads as drift from a measured baseline
    rather than as a mystery.
    """
    print(
        f"\ncharacterising {len(CANDIDATE_QUESTIONS)} questions, {runs} runs each ..."
    )
    measured: list[DemoQuestion] = []
    unstable: list[str] = []
    for candidate in CANDIDATE_QUESTIONS:
        stable = 0
        observed: list[str] = []
        for index in range(runs):
            disposition = run_once(bundle_root, store_dir, candidate.question)
            observed.append(disposition)
            if disposition == candidate.expected:
                stable += 1
            print(f"  [{index + 1}/{runs}] {candidate.question[:48]}... {disposition}")
        measured.append(
            DemoQuestion(
                question=candidate.question,
                expected=candidate.expected,
                runs=runs,
                stable=stable,
            )
        )
        print(f"  => {stable}/{runs} matched {candidate.expected!r}")
        if stable != runs:
            counts: dict[str, int] = {}
            for value in observed:
                counts[value] = counts.get(value, 0) + 1
            spread = ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
            unstable.append(
                f"{candidate.question!r} expected {candidate.expected} "
                f"but got {stable}/{runs} (observed: {spread})"
            )
    if unstable:
        raise RegenerationError(
            "a pinned question was not stable across the characterisation runs:\n  "
            + "\n  ".join(unstable)
        )
    return tuple(measured)


def run_once(bundle_root: Path, store_dir: Path, question: str) -> str:
    """One full query against the newly built index, as a bare disposition."""
    reader = SqliteChromaIndexReader(store_dir)
    resolution = store_resolution(reader.manifest_metadata)
    result = query_index(
        QueryRequest(
            question=question,
            store_dir=store_dir,
            allow_stale=False,
            filters=QueryFilters(),
        ),
        QueryDependencies(
            store=reader,
            count_tokens=tiktoken_count,
            embed=embed_texts,
            lexical_scorer=bm25_lexical_scorer,
            load_manifest=resolution.load_manifest,
            raw_manifest_digest=resolution.raw_manifest_digest,
            resolve_source=resolution.resolve_source,
            extract_facets=extract_facets,
            generate_answer=generate_answer,
            decompose=decompose_sentence,
            entail=entail_verdict,
            coverage=coverage_verdict,
        ),
    )
    if result.state == QueryState.ANSWERED:
        return "answered"
    if result.state == QueryState.ABSTAINED:
        return "abstained"
    # An error is neither disposition, and reporting it as an abstention would
    # let a broken build publish. Name it so the refusal message is legible.
    failure = result.failure.code if result.failure else "unknown"
    return f"error:{failure}"


def replace_questions(
    snapshot: BundleSnapshot, questions: tuple[DemoQuestion, ...]
) -> BundleSnapshot:
    """The same snapshot carrying the measured question stability."""
    return BundleSnapshot(
        schema_version=snapshot.schema_version,
        generated_at=snapshot.generated_at,
        commit=snapshot.commit,
        pipeline_signature=snapshot.pipeline_signature,
        records_dir=snapshot.records_dir,
        store_dir=snapshot.store_dir,
        corpus_root=snapshot.corpus_root,
        records_indexed=snapshot.records_indexed,
        specs_at_freeze=snapshot.specs_at_freeze,
        demo_questions=questions,
    )


def spec_directories() -> list[Path]:
    """Every spec directory under ``docs/specs/`` at run time."""
    specs_root = REPO_ROOT / "docs" / "specs"
    if not specs_root.is_dir():
        return []
    return sorted(path for path in specs_root.iterdir() if path.is_dir())


def count_spec_directories() -> int:
    return len(spec_directories())


def report_absent_specs(records_dir: Path) -> None:
    """Report which spec directories the bundle never saw (AC-14).

    Reports, never fails. A spec written after the freeze, or one the adapter
    cannot read yet, is an expected absence rather than a defect, and nothing
    in the suite should break because the corpus moved on. Printing the list is
    what lets a human tell an expected absence from a new one.
    """
    manifest = load_manifest(manifest_path(records_dir))
    covered: set[str] = set()
    for entry in manifest.entries:
        for contributing in entry.contributing_files:
            parts = Path(contributing).parts
            if len(parts) >= 3 and parts[0] == "docs" and parts[1] == "specs":
                covered.add(parts[2])
    absent = [path.name for path in spec_directories() if path.name not in covered]
    print(
        f"\nspec directories: {count_spec_directories()}, in the bundle: "
        f"{len(covered)}, absent: {len(absent)}"
    )
    for name in absent:
        print(f"  absent {name}")
    if absent:
        print(
            "  (absences are reported, not failed: a spec the adapter cannot "
            "read yet or one written after the freeze is expected)"
        )


def current_commit() -> str:
    """The short commit the corpus was read at."""
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise RegenerationError(f"cannot read the current commit: {error}") from error
    return completed.stdout.strip()


def publish(scratch: Path, bundle: Path) -> None:
    """Swap the scratch bundle into place with two renames (AC-11).

    A POSIX rename cannot replace a non empty directory, so a single atomic
    replacement is not available. The window between the two renames is the
    only failure state, it leaves the bundle briefly absent rather than
    corrupt, and ``recover_interrupted_swap`` repairs it on the next run.
    """
    aside = aside_path(bundle)
    if bundle.exists():
        bundle.rename(aside)
    try:
        scratch.rename(bundle)
    except OSError:
        if aside.exists() and not bundle.exists():
            aside.rename(bundle)
        raise
    if aside.exists():
        shutil.rmtree(aside)


if __name__ == "__main__":
    sys.exit(main())
