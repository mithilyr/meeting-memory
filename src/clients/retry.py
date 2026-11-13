"""Retry with exponential backoff for rate-limited free-tier APIs.

Every provider we use is on a free tier, and free tiers rate-limit with HTTP 429.
The challenge appendix is explicit that systems without backoff "fail
unpredictably, including during your demo recording", so this is wired into every
API call from the first one rather than added after the first failure.

Deliberately dependency-free: no tenacity, no backoff library. This is thirty
lines of well-understood logic, and every team member has to be able to explain
any part of the system on demand.
"""

from __future__ import annotations

import random
import re
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

#: Substrings identifying a retryable failure. Matched against the exception
#: text because provider SDKs raise different exception types for the same
#: underlying condition, and we would rather over-match than crash a demo.
RETRYABLE_SIGNALS = (
    "429",
    "rate limit",
    "resource_exhausted",
    "resource exhausted",
    "quota",
    "500",
    "502",
    "503",
    "504",
    "timeout",
    "timed out",
    "connection reset",
    "temporarily unavailable",
)


#: Signals that a *daily* quota is gone. Backoff cannot recover from these -
#: waiting 8 seconds for a limit that resets tomorrow just burns attempts - so
#: they are raised immediately for the caller to handle (usually by switching to
#: a different model, which carries its own separate quota).
DAILY_QUOTA_SIGNALS = (
    "perday",
    "per day",
    "requestsperday",
    "generaterequestsperdayperprojectpermodel",
)

_RETRY_AFTER_RE = re.compile(
    r"(?:retry(?:delay|_delay)?[\"':\s]*|retry in\s*)(\d+(?:\.\d+)?)\s*s", re.I
)


class RetriesExhausted(RuntimeError):
    """Raised when every attempt failed, preserving the last error."""


class DailyQuotaExhausted(RuntimeError):
    """Raised when a provider reports the daily request quota is spent."""


def is_daily_quota_error(error: Exception) -> bool:
    """True if the provider says the *daily* allowance is gone.

    Distinguished from an ordinary 429 because the remedies differ completely:
    a per-minute limit wants a short wait, a daily limit wants a different model
    or tomorrow.
    """
    text = f"{type(error).__name__}: {error}".lower().replace("-", "")
    return any(signal in text for signal in DAILY_QUOTA_SIGNALS)


def retry_after_seconds(error: Exception) -> float | None:
    """Extract the provider's own retry hint, if it gave one.

    Google returns a RetryInfo with a concrete delay. Honouring it is both more
    polite and more effective than guessing with exponential backoff.
    """
    match = _RETRY_AFTER_RE.search(str(error))
    return float(match.group(1)) if match else None


def is_retryable(error: Exception) -> bool:
    """True if the error looks transient rather than a genuine bug.

    A 400 for a malformed request must fail immediately - retrying it just burns
    quota five times before reporting the same problem.
    """
    text = f"{type(error).__name__}: {error}".lower()
    return any(signal in text for signal in RETRYABLE_SIGNALS)


def with_retry(
    operation: Callable[[], T],
    *,
    attempts: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    description: str = "API call",
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Run an operation, retrying transient failures with exponential backoff.

    Delays follow 1s, 2s, 4s, 8s... with jitter. Jitter matters because four team
    members developing against per-account quotas produce synchronised retries
    otherwise, and synchronised retries re-trigger the same rate limit.

    Args:
        operation: Zero-argument callable performing the request.
        attempts: Total attempts including the first.
        base_delay: Delay before the second attempt, in seconds.
        max_delay: Ceiling on any single delay.
        description: Used in the error message so a failure says what failed.
        sleep: Injected for testing; defaults to time.sleep.

    Returns:
        Whatever the operation returns.

    Raises:
        RetriesExhausted: If every attempt failed with a retryable error.
        Exception: Immediately, unchanged, if the error is not retryable.
    """
    last_error: Exception | None = None

    for attempt in range(attempts):
        try:
            return operation()
        except Exception as error:  # noqa: BLE001 - classified below
            # A spent daily quota is not transient. Fail fast so the caller can
            # switch models rather than sleeping through attempts that cannot
            # succeed today.
            if is_daily_quota_error(error):
                raise DailyQuotaExhausted(f"{description}: {error}") from error
            if not is_retryable(error):
                raise
            last_error = error
            if attempt == attempts - 1:
                break

            # Prefer the provider's own hint over our guess.
            hinted = retry_after_seconds(error)
            delay = min(
                hinted if hinted is not None else base_delay * (2**attempt), max_delay
            )
            sleep(delay + random.uniform(0, delay * 0.1))

    raise RetriesExhausted(
        f"{description} failed after {attempts} attempts. Last error: {last_error}"
    ) from last_error
