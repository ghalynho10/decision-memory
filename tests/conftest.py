"""Shared test setup.

Makes the bundled starter adapter importable as an installed package, so the
unit tests can call its methods directly and the integration tests can load it
through the real runtime loader by its selector. The package lives in the
``src/`` layout that uv_build expects, so that directory goes on the path.
"""

from __future__ import annotations

import sys
from pathlib import Path

_EXAMPLES_SRC = (
    Path(__file__).resolve().parent.parent / "examples" / "starter-adapter" / "src"
)
if str(_EXAMPLES_SRC) not in sys.path:
    sys.path.insert(0, str(_EXAMPLES_SRC))
