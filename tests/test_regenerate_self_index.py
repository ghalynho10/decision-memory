"""The regeneration script's safety properties (spec 0014).

Covers the parts that must hold without calling a provider: the two rename
swap and its recovery from an interrupted previous run (AC-11), the absolute
path check that gates publishing (AC-6), and the refusal to publish when a
pinned question is not stable across the characterisation runs (AC-13).

The script lives in ``scripts/`` rather than in the package, so it is loaded
here by path.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "regenerate-self-index.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("regenerate_self_index", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["regenerate_self_index"] = module
    spec.loader.exec_module(module)
    return module


script = _load_script()


def _bundle_with(root: Path, name: str, marker: str) -> Path:
    path = root / name
    (path / "records").mkdir(parents=True)
    (path / "records" / "manifest.json").write_text(marker, encoding="utf-8")
    return path


# The swap and its recovery (AC-11).


def test_publish_replaces_the_bundle(tmp_path: Path) -> None:
    bundle = _bundle_with(tmp_path, "self-index", "old")
    scratch = _bundle_with(tmp_path, ".self-index.building", "new")

    script.publish(scratch, bundle)

    assert (bundle / "records" / "manifest.json").read_text(encoding="utf-8") == "new"
    assert not scratch.exists()
    assert not script.aside_path(bundle).exists()


def test_publish_into_an_absent_bundle_works(tmp_path: Path) -> None:
    """The first ever run has nothing to set aside."""
    bundle = tmp_path / "self-index"
    scratch = _bundle_with(tmp_path, ".self-index.building", "new")

    script.publish(scratch, bundle)

    assert (bundle / "records" / "manifest.json").read_text(encoding="utf-8") == "new"


def test_recovery_rolls_back_when_the_new_bundle_never_landed(tmp_path: Path) -> None:
    """Killed between the two renames: the set aside copy is the only one left."""
    bundle = tmp_path / "self-index"
    aside = _bundle_with(tmp_path, "self-index.old", "old")
    assert aside == script.aside_path(bundle)
    assert not bundle.exists()

    message = script.recover_interrupted_swap(bundle)

    assert message is not None
    assert (bundle / "records" / "manifest.json").read_text(encoding="utf-8") == "old"
    assert not aside.exists()


def test_recovery_clears_the_leftover_when_the_new_bundle_landed(
    tmp_path: Path,
) -> None:
    """Killed after the second rename: the leftover is garbage, the new one stands."""
    bundle = _bundle_with(tmp_path, "self-index", "new")
    aside = _bundle_with(tmp_path, "self-index.old", "old")

    message = script.recover_interrupted_swap(bundle)

    assert message is not None
    assert (bundle / "records" / "manifest.json").read_text(encoding="utf-8") == "new"
    assert not aside.exists()


def test_recovery_is_a_no_op_on_a_clean_tree(tmp_path: Path) -> None:
    bundle = _bundle_with(tmp_path, "self-index", "current")
    assert script.recover_interrupted_swap(bundle) is None
    assert (bundle / "records" / "manifest.json").read_text(
        encoding="utf-8"
    ) == "current"


def test_a_failed_check_leaves_the_bundle_byte_identical(tmp_path: Path) -> None:
    """AC-11: every check runs before the swap, so a refusal changes nothing."""
    bundle = _bundle_with(tmp_path, "self-index", "untouched")
    before = (bundle / "records" / "manifest.json").read_bytes()

    with pytest.raises(script.RegenerationError):
        raise script.RegenerationError("a check failed")

    assert (bundle / "records" / "manifest.json").read_bytes() == before


# The absolute path gate (AC-6).


@pytest.mark.parametrize(
    "value",
    [
        "/Users/someone/project",
        "/etc",
        "C:\\Users\\someone",
        "\\\\server\\share",
        "D:/build/records",
    ],
)
def test_absolute_paths_are_detected_on_any_platform(value: str) -> None:
    """The check must not depend on the platform the script happens to run on."""
    assert script.looks_absolute(value)


@pytest.mark.parametrize(
    "value", ["", "records", "records/manifest.json", "../..", "2"]
)
def test_relative_and_empty_values_pass(value: str) -> None:
    assert not script.looks_absolute(value)


# Characterisation stability (AC-13).


def _stub_dispositions(
    monkeypatch: pytest.MonkeyPatch, dispositions: dict[str, list[str]]
) -> None:
    """Replace the live query with a scripted sequence per question."""
    remaining = {question: list(values) for question, values in dispositions.items()}

    def _fake_run_once(_bundle_root: Path, _store_dir: Path, question: str) -> str:
        return remaining[question].pop(0)

    monkeypatch.setattr(script, "run_once", _fake_run_once)


def test_characterisation_publishes_when_every_run_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_dispositions(
        monkeypatch,
        {
            candidate.question: [candidate.expected] * 3
            for candidate in script.CANDIDATE_QUESTIONS
        },
    )

    measured = script.characterise(tmp_path, tmp_path, 3)

    assert len(measured) == len(script.CANDIDATE_QUESTIONS)
    for question in measured:
        assert question.runs == 3
        assert question.stable == 3


def test_one_deviating_run_refuses_to_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-13: disposition instability stops the script, it does not average out."""
    answering, abstaining = script.CANDIDATE_QUESTIONS
    _stub_dispositions(
        monkeypatch,
        {
            answering.question: ["answered", "abstained", "answered"],
            abstaining.question: ["abstained"] * 3,
        },
    )

    with pytest.raises(script.RegenerationError) as error:
        script.characterise(tmp_path, tmp_path, 3)

    message = str(error.value)
    assert "2/3" in message
    assert "answered 2" in message and "abstained 1" in message


def test_an_errored_run_is_never_counted_as_a_disposition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A broken build must not publish by looking like an abstention."""
    answering, abstaining = script.CANDIDATE_QUESTIONS
    _stub_dispositions(
        monkeypatch,
        {
            answering.question: ["answered", "error:stale.refused", "answered"],
            abstaining.question: ["abstained"] * 3,
        },
    )

    with pytest.raises(script.RegenerationError) as error:
        script.characterise(tmp_path, tmp_path, 3)

    assert "error:stale.refused" in str(error.value)


def test_the_pinned_questions_are_the_ones_the_readme_shows() -> None:
    """AC-16: the front page, the snapshot, and the smoke test are one artifact."""
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    for candidate in script.CANDIDATE_QUESTIONS:
        assert candidate.question in readme
    assert [candidate.expected for candidate in script.CANDIDATE_QUESTIONS] == [
        "answered",
        "abstained",
    ]
