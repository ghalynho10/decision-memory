"""decision-memory: answer why a project is built the way it is, with citations."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("decision-memory")
except PackageNotFoundError:  # pragma: no cover - loose/editable installs
    __version__ = "0.0.0"

__all__ = ["__version__"]
