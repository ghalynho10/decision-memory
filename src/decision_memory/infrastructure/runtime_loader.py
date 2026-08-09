"""Infrastructure: strict adapter selector parsing and runtime loading.

Spec 0005 AC-2 and AC-3: a third party adapter is selected by an absolute
selector ``package.module:attribute``, imported with importlib, and the named
attribute is read as an already created instance. The loader performs a
shallow contract check (both metadata values are nonempty strings and
``discover``, ``parse``, and ``fingerprint`` are callable) before any corpus
access; it does not claim to validate method signatures or behavior.

The loader never modifies ``sys.path``, never adds the config directory or
corpus root, and never loads direct files (AC-14): the module must be
importable on the existing Python path, and an imported adapter is trusted
Python code that executes with the CLI process permissions. No sandbox is
provided.
"""

from __future__ import annotations

import importlib
import inspect
from dataclasses import dataclass
from typing import cast

from decision_memory.application.adapter import BUILTIN_ADAPTER_ID, SourceAdapter
from decision_memory.infrastructure.jsmastery_adapter import JsmasteryAdapter


@dataclass(frozen=True)
class Selector:
    """A parsed absolute selector: an absolute dotted module and one attribute."""

    module: str
    attribute: str


@dataclass(frozen=True)
class LoadFailure:
    """Why the loader could not produce an adapter instance.

    ``phase`` is one of ``selector``, ``import``, ``attribute``, or
    ``contract``. A selector failure is a usage error (exit 2); the remaining
    phases are runtime failures (exit 1) per AC-9.
    """

    phase: str
    exception_type: str
    message: str


def parse_selector(selector: str) -> Selector | LoadFailure:
    """Parse ``package.module:attribute`` strictly (AC-2).

    The module is an absolute dotted Python name and the attribute is one
    Python identifier. Relative modules, missing colons, empty parts, dotted
    attribute traversal, direct file paths, and invalid identifiers are
    rejected. The built in name contains a hyphen and therefore cannot collide
    with a valid Python module name.
    """
    if ":" not in selector:
        return LoadFailure(
            "selector", "", "selector must be shaped as package.module:attribute"
        )
    module_part, _, attribute_part = selector.partition(":")
    module = module_part.strip()
    attribute = attribute_part.strip()
    if not module:
        return LoadFailure("selector", "", "empty module name")
    if not attribute:
        return LoadFailure("selector", "", "empty attribute name")
    if module.startswith("."):
        return LoadFailure("selector", "", "module name must be absolute, not relative")
    if "/" in module or "\\" in module:
        return LoadFailure(
            "selector",
            "",
            "module name must be a dotted Python name, not a file path",
        )
    if "." in attribute:
        return LoadFailure(
            "selector", "", "attribute must be a single identifier, not dotted"
        )
    if not attribute.isidentifier():
        return LoadFailure(
            "selector",
            "",
            f"{attribute!r} is not a valid Python identifier",
        )
    if not all(part.isidentifier() for part in module.split(".")):
        return LoadFailure(
            "selector",
            "",
            "module name contains a part that is not a valid Python identifier",
        )
    return Selector(module=module, attribute=attribute)


def select_adapter(selector: str) -> SourceAdapter | LoadFailure:
    """Resolve one adapter by built in id or third party selector (spec 0006 AC-1).

    The exact built in id returns a fresh ``JsmasteryAdapter``; every other
    value delegates unchanged to ``load_adapter``. Metadata access inside
    loading catches ``Exception`` and returns a contract ``LoadFailure``, so
    a broken property never escapes the load boundary.
    """
    if selector == BUILTIN_ADAPTER_ID:
        try:
            candidate = JsmasteryAdapter()
        except Exception as exc:  # noqa: BLE001 - built in construction failure
            message = str(exc) if str(exc) else type(exc).__name__
            return LoadFailure("contract", type(exc).__name__, message)
        error = _contract_error(candidate)
        if error is not None:
            return LoadFailure("contract", "", error)
        return cast(SourceAdapter, candidate)
    return load_adapter(selector)


def load_adapter(selector: str) -> SourceAdapter | LoadFailure:
    """Load one adapter instance from an absolute selector (AC-3).

    Imports the module with ``importlib.import_module``, reads the named
    attribute as an already created instance (never calls it), and checks the
    contract before any corpus access: both metadata values are nonempty
    strings and ``discover``, ``parse``, and ``fingerprint`` are present and
    callable. A class (an uncreated definition) and a factory (a callable with
    no adapter metadata) are both rejected. The check does not validate method
    signatures or behavior.
    """
    parsed = parse_selector(selector)
    if isinstance(parsed, LoadFailure):
        return parsed
    try:
        module = importlib.import_module(parsed.module)
    except Exception as exc:  # noqa: BLE001 - import failure (AC-9)
        message = str(exc) if str(exc) else type(exc).__name__
        return LoadFailure("import", type(exc).__name__, message)
    try:
        candidate = getattr(module, parsed.attribute)
    except AttributeError as exc:
        message = str(exc) if str(exc) else type(exc).__name__
        return LoadFailure("attribute", type(exc).__name__, message)
    if inspect.isclass(candidate):
        return LoadFailure(
            "contract",
            "",
            f"{parsed.attribute!r} is a class, expected an already created instance",
        )
    error = _contract_error(candidate)
    if error is not None:
        return LoadFailure("contract", "", error)
    return cast(SourceAdapter, candidate)


def _contract_error(candidate: object) -> str | None:
    """A message naming the first contract violation, else None.

    Metadata and method access is wrapped so a raising property or descriptor
    is treated as a contract violation, not a crash inside loading (spec 0006
    AC-1 metadata access).
    """
    for field in ("adapter_id", "adapter_version"):
        try:
            value = getattr(candidate, field, None)
        except Exception:  # noqa: BLE001 - property access failure
            return f"adapter.{field} must be a nonempty string (access raised)"
        if not isinstance(value, str) or not value:
            return f"adapter.{field} must be a nonempty string"
    for method in ("discover", "parse", "fingerprint"):
        try:
            value = getattr(candidate, method, None)
        except Exception:  # noqa: BLE001 - descriptor access failure
            return f"adapter.{method} must be callable (access raised)"
        if not callable(value):
            return f"adapter.{method} must be callable"
    return None
