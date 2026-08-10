"""Infrastructure: the shared OpenAI client, key check, and retry policy.

Spec 0007 AC-16 and AC-20: provider calls have a 60 second whole request
timeout; connection errors, timeouts, HTTP 408, 409, 429, and 500 through 599
receive up to three retries after 0.5, 1.0, then 2.0 seconds with no jitter
(four attempts at most); authentication, permission, not found, invalid
request, and other 400 responses do not retry. The application records only
the sanitized class and status. This module configures the client and applies
the policy; the two concern modules are the only places that call the SDK.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any, TypeVar

from decision_memory.application.dto import ProviderAttempt, ProviderOutcome

TIMEOUT_SECONDS = 60
RETRY_DELAYS = (0.5, 1.0, 2.0)
MAX_ATTEMPTS = 4

_MODEL_KEY = "OPENAI_API_KEY"

T = TypeVar("T")


class OpenAIClientError(Exception):
    """A fatal provider failure: API key missing or a non retryable error."""


def api_key_present() -> bool:
    """Whether OPENAI_API_KEY is set (spec 0007 AC-20)."""
    return bool(os.environ.get(_MODEL_KEY, "").strip())


def require_api_key() -> None:
    """Raise when OPENAI_API_KEY is absent; validated before store mutation."""
    if not api_key_present():
        raise OpenAIClientError("OPENAI_API_KEY is not set")


def _client() -> Any:
    """The lazily created OpenAI client."""
    from openai import OpenAI

    return OpenAI(timeout=TIMEOUT_SECONDS)


def _retryable(error: BaseException) -> bool:
    """Whether a provider error should be retried per the AC-16 policy."""
    message = f"{type(error).__name__}: {error}"
    lower = message.lower()
    if isinstance(error, TimeoutError):
        return True
    if "connection" in lower or "timeout" in lower:
        return True
    status = getattr(error, "status_code", None)
    if not isinstance(status, int):
        return False
    if status in (408, 409, 429):
        return True
    return 500 <= status <= 599


def _sanitized_detail(error: BaseException) -> str:
    """The sanitized failure detail: class and status, never the SDK message."""
    status = getattr(error, "status_code", None)
    if status is not None:
        return f"{type(error).__name__} status {status}"
    return type(error).__name__


def run_with_retries(
    operation: str,
    call: Callable[[], T],
    attempts: list[ProviderAttempt] | None = None,
) -> T:
    """Run ``call`` under the AC-16 retry policy, recording every attempt.

    Raises ``OpenAIClientError`` on a non retryable or final failure. When
    ``attempts`` is given it collects one ``ProviderAttempt`` per try, so the
    trace keeps provider attempts even after a fatal failure.
    """
    last_error: BaseException | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        started = time.monotonic()
        try:
            result = call()
        except Exception as exc:  # noqa: BLE001 - provider boundary
            elapsed = int((time.monotonic() - started) * 1000)
            last_error = exc
            if attempts is not None:
                outcome = (
                    ProviderOutcome.RETRYABLE_FAILURE
                    if _retryable(exc)
                    else ProviderOutcome.FINAL_FAILURE
                )
                attempts.append(
                    ProviderAttempt(
                        concern=operation,
                        attempt_number=attempt,
                        elapsed_ms=elapsed,
                        outcome=outcome,
                    )
                )
            if not _retryable(exc):
                break
            if attempt < MAX_ATTEMPTS:
                time.sleep(RETRY_DELAYS[attempt - 1])
            continue
        elapsed = int((time.monotonic() - started) * 1000)
        if attempts is not None:
            attempts.append(
                ProviderAttempt(
                    concern=operation,
                    attempt_number=attempt,
                    elapsed_ms=elapsed,
                    outcome=ProviderOutcome.SUCCESS,
                )
            )
        return result
    assert last_error is not None
    raise OpenAIClientError(
        f"{operation}: {_sanitized_detail(last_error)}"
    ) from last_error
