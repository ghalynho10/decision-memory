"""Runtime loader tests (spec 0005 AC-2, AC-3, AC-9, AC-14).

The strict selector parser and the importlib loader, exercised against real
temporary modules so the import and contract failure table runs against actual
import machinery rather than stubs.
"""

from __future__ import annotations

import sys
from pathlib import Path

from typer.testing import CliRunner

from decision_memory.application.adapter import BUILTIN_ADAPTER_ID
from decision_memory.cli import app
from decision_memory.infrastructure.runtime_loader import (
    LoadFailure,
    Selector,
    load_adapter,
    parse_selector,
)

runner = CliRunner()

# A valid adapter module: metadata as class attributes and the three methods.
VALID_MODULE = """\
class Adapter:
    adapter_id = "vendor"
    adapter_version = "2"
    def discover(self, corpus_root):
        return None
    def parse(self, spec):
        return None
    def fingerprint(self, spec):
        return "fp"

adapter = Adapter()
"""

EMPTY_METADATA_MODULE = """\
class Adapter:
    adapter_id = ""
    adapter_version = "2"
    def discover(self, corpus_root):
        return None
    def parse(self, spec):
        return None
    def fingerprint(self, spec):
        return "fp"

adapter = Adapter()
"""

MISSING_METHOD_MODULE = """\
class Adapter:
    adapter_id = "vendor"
    adapter_version = "2"
    def discover(self, corpus_root):
        return None
    def parse(self, spec):
        return None

adapter = Adapter()
"""

NONCALLABLE_METHOD_MODULE = """\
class Adapter:
    adapter_id = "vendor"
    adapter_version = "2"
    def discover(self, corpus_root):
        return None
    def parse(self, spec):
        return None
    fingerprint = "not callable"

adapter = Adapter()
"""

CLASS_MODULE = """\
class Adapter:
    adapter_id = "vendor"
    adapter_version = "2"
    def discover(self, corpus_root):
        return None
    def parse(self, spec):
        return None
    def fingerprint(self, spec):
        return "fp"

adapter = Adapter
"""

FACTORY_MODULE = """\
class Adapter:
    adapter_id = "vendor"
    adapter_version = "2"

def adapter():
    return Adapter()
"""


def _install(monkeypatch, tmp_path: Path, body: str, name: str = "vendor") -> None:
    """Write a temp package named ``name`` with runtime.py and put it on path."""
    package = tmp_path / name
    package.mkdir()
    (package / "runtime.py").write_text(body, encoding="utf-8")
    # A prior test may have imported the same module name; drop the cached
    # module so this test's file is the one importlib actually loads.
    sys.modules.pop(name, None)
    sys.modules.pop(f"{name}.runtime", None)
    monkeypatch.syspath_prepend(str(tmp_path))


class TestParseSelector:
    def test_accepts_absolute_module_and_single_attribute(self) -> None:
        result = parse_selector("vendor_adapter.runtime:adapter")
        assert result == Selector(module="vendor_adapter.runtime", attribute="adapter")

    def test_accepts_a_top_level_module(self) -> None:
        result = parse_selector("adapter_pkg:adapter")
        assert result == Selector(module="adapter_pkg", attribute="adapter")

    def test_missing_colon_is_rejected(self) -> None:
        result = parse_selector("vendor.runtime.adapter")
        assert isinstance(result, LoadFailure)
        assert result.phase == "selector"

    def test_empty_module_is_rejected(self) -> None:
        result = parse_selector(":adapter")
        assert isinstance(result, LoadFailure)
        assert "empty module" in result.message

    def test_empty_attribute_is_rejected(self) -> None:
        result = parse_selector("vendor.runtime:")
        assert isinstance(result, LoadFailure)
        assert "empty attribute" in result.message

    def test_relative_module_is_rejected(self) -> None:
        result = parse_selector(".vendor.runtime:adapter")
        assert isinstance(result, LoadFailure)
        assert "absolute" in result.message

    def test_file_path_is_rejected(self) -> None:
        result = parse_selector("/abs/path/adapter.py:adapter")
        assert isinstance(result, LoadFailure)
        assert "file path" in result.message

    def test_dotted_attribute_is_rejected(self) -> None:
        result = parse_selector("vendor.runtime:nested.adapter")
        assert isinstance(result, LoadFailure)
        assert "single identifier" in result.message

    def test_non_identifier_attribute_is_rejected(self) -> None:
        result = parse_selector("vendor.runtime:adapter-instance")
        assert isinstance(result, LoadFailure)
        assert "not a valid Python identifier" in result.message

    def test_non_identifier_module_part_is_rejected(self) -> None:
        result = parse_selector("vendor-memory.runtime:adapter")
        assert isinstance(result, LoadFailure)
        assert "not a valid Python identifier" in result.message

    def test_whitespace_around_parts_is_trimmed(self) -> None:
        result = parse_selector("  vendor.runtime : adapter  ")
        assert result == Selector(module="vendor.runtime", attribute="adapter")


class TestLoadAdapter:
    def test_loads_a_valid_module_attribute(self, tmp_path, monkeypatch) -> None:
        _install(monkeypatch, tmp_path, VALID_MODULE)
        adapter = load_adapter("vendor.runtime:adapter")
        assert not isinstance(adapter, LoadFailure)
        assert adapter.adapter_id == "vendor"
        assert adapter.adapter_version == "2"

    def test_missing_module_is_an_import_failure(self) -> None:
        result = load_adapter("no_such_pkg.runtime:adapter")
        assert isinstance(result, LoadFailure)
        assert result.phase == "import"
        assert result.exception_type == "ModuleNotFoundError"

    def test_import_time_exception_names_the_type(self, tmp_path, monkeypatch) -> None:
        _install(monkeypatch, tmp_path, "raise RuntimeError('boom')\n")
        result = load_adapter("vendor.runtime:adapter")
        assert isinstance(result, LoadFailure)
        assert result.phase == "import"
        assert result.exception_type == "RuntimeError"
        assert "boom" in result.message

    def test_missing_attribute_is_an_attribute_failure(
        self, tmp_path, monkeypatch
    ) -> None:
        _install(monkeypatch, tmp_path, "value = 1\n")
        result = load_adapter("vendor.runtime:adapter")
        assert isinstance(result, LoadFailure)
        assert result.phase == "attribute"

    def test_empty_metadata_is_a_contract_failure(self, tmp_path, monkeypatch) -> None:
        _install(monkeypatch, tmp_path, EMPTY_METADATA_MODULE)
        result = load_adapter("vendor.runtime:adapter")
        assert isinstance(result, LoadFailure)
        assert result.phase == "contract"
        assert "adapter_id" in result.message

    def test_missing_method_is_a_contract_failure(self, tmp_path, monkeypatch) -> None:
        _install(monkeypatch, tmp_path, MISSING_METHOD_MODULE)
        result = load_adapter("vendor.runtime:adapter")
        assert isinstance(result, LoadFailure)
        assert result.phase == "contract"
        assert "fingerprint" in result.message

    def test_noncallable_method_is_a_contract_failure(
        self, tmp_path, monkeypatch
    ) -> None:
        _install(monkeypatch, tmp_path, NONCALLABLE_METHOD_MODULE)
        result = load_adapter("vendor.runtime:adapter")
        assert isinstance(result, LoadFailure)
        assert result.phase == "contract"
        assert "fingerprint" in result.message

    def test_class_is_rejected(self, tmp_path, monkeypatch) -> None:
        _install(monkeypatch, tmp_path, CLASS_MODULE)
        result = load_adapter("vendor.runtime:adapter")
        assert isinstance(result, LoadFailure)
        assert result.phase == "contract"
        assert "class" in result.message

    def test_factory_function_is_rejected(self, tmp_path, monkeypatch) -> None:
        _install(monkeypatch, tmp_path, FACTORY_MODULE)
        result = load_adapter("vendor.runtime:adapter")
        assert isinstance(result, LoadFailure)
        assert result.phase == "contract"

    def test_loader_never_modifies_sys_path(self, tmp_path, monkeypatch) -> None:
        _install(monkeypatch, tmp_path, VALID_MODULE)
        before = list(sys.path)
        load_adapter("vendor.runtime:adapter")
        assert sys.path == before


class TestCliAdapterFlag:
    def test_built_in_name_is_accepted_without_import(self, tmp_path) -> None:
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        result = runner.invoke(
            app, ["adapt", str(corpus), "--adapter", BUILTIN_ADAPTER_ID]
        )
        assert result.exit_code == 3  # corpus invalid, but the adapter loaded

    def test_malformed_selector_exits_two(self, tmp_path) -> None:
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        result = runner.invoke(
            app, ["adapt", str(corpus), "--adapter", "not-a-selector"]
        )
        assert result.exit_code == 2
        assert "selector" in result.stdout

    def test_unknown_module_exits_one_and_names_the_failure(self, tmp_path) -> None:
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        result = runner.invoke(
            app, ["adapt", str(corpus), "--adapter", "no_such_pkg.runtime:adapter"]
        )
        assert result.exit_code == 1
        assert "import" in result.stdout
        assert "ModuleNotFoundError" in result.stdout
