"""Built in manifest runs in the fast unit suite (spec 0006 AC-20).

The committed strict manifest for ``jsmastery-specs`` must load and pass the
same public engine the CLI uses, with no adapter import tricks and no git
dependency.
"""

from __future__ import annotations

from pathlib import Path

from decision_memory.application.conformance import run_adapter_conformance
from decision_memory.infrastructure.conformance_fixtures import WorkspaceFixture
from decision_memory.infrastructure.conformance_manifest import (
    load_conformance_manifest,
)
from decision_memory.infrastructure.jsmastery_adapter import JsmasteryAdapter

_BUILTIN_MANIFEST = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "adapter_conformance"
    / "jsmastery_specs"
    / "adapter-conformance.yml"
)


def test_builtin_manifest_passes_the_engine() -> None:
    manifest = load_conformance_manifest(_BUILTIN_MANIFEST)
    outcome = run_adapter_conformance(JsmasteryAdapter(), manifest, WorkspaceFixture())
    assert outcome.failed == 0
    assert outcome.exit_code == 0
    assert outcome.passed > 0


def test_builtin_manifest_has_all_five_categories() -> None:
    manifest = load_conformance_manifest(_BUILTIN_MANIFEST)
    categories = {case.category.value for case in manifest.cases}
    assert categories == {
        "valid",
        "skip",
        "wrong_heading",
        "missing_required_field",
        "collision",
    }
