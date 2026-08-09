"""Infrastructure: tiktoken based token counting (spec 0007 AC-4, AC-20).

The token counter is the one place tiktoken is imported. Application code
receives it as a narrow callable, so the pure chunker never depends on a third
party library. The encoding is fixed to ``cl100k_base`` and participates in
the pipeline signature, so a change forces an explicit rebuild.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache

import tiktoken

from decision_memory.application.pipeline import TIKTOKEN_ENCODING


@lru_cache(maxsize=1)
def _encoding() -> tiktoken.Encoding:
    """The cl100k_base encoding, cached; its data ships with the package."""
    return tiktoken.get_encoding(TIKTOKEN_ENCODING)


def tiktoken_count(text: str) -> int:
    """The number of cl100k_base tokens in ``text``."""
    return len(_encoding().encode(text))


TokenCounter = Callable[[str], int]
