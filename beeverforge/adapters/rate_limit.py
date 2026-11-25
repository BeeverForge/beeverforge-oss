"""A forge's rate limit, read from what it answered and raised as itself (#698).

`gh` reports every failure the same way — an exit code and some text — so a rate limit that ran out
used to arrive as one more `RuntimeError`, and the caller could only give up. `RateLimited` is that
failure with the one fact a caller needs to do better: WHEN the limit resets (`reset_at`, epoch
seconds), read from the response's headers (`X-RateLimit-Reset`, `Retry-After`; `gh api --include`
prints them on stdout) or its body (GraphQL's `resetAt`). A limit that names no reset is read as
`DEFAULT_WAIT` from now — GitHub's secondary limits clear in about a minute, and a caller that waits
that long and finds the limit still up will ask again. A reset already in the past is not trusted.

The clock is a parameter, so nothing here reads the wall.
"""

from __future__ import annotations

import re
import subprocess
import time
from collections.abc import Callable
from datetime import datetime

#: What a rate limit that names no reset is read to mean, in seconds from now.
DEFAULT_WAIT = 60

#: GitHub's own words for it, over REST (`API rate limit exceeded`), GraphQL (`RATE_LIMITED`) and
#: the secondary limits (`abuse detection`, `submitted too quickly`).
_MARKERS = ("rate limit", "rate_limited", "abuse detection", "submitted too quickly")

_RESET_HEADER = re.compile(r"^\s*x-ratelimit-reset:\s*(\d+)\s*$", re.I | re.M)
_RETRY_AFTER = re.compile(r"^\s*retry-after:\s*(\d+)\s*$", re.I | re.M)
_RESET_AT = re.compile(r'"resetAt"\s*:\s*"([^"]+)"')


class RateLimited(RuntimeError):
    """The forge refused a call because its rate limit is spent; `reset_at` is when it refills."""

    def __init__(self, message: str, *, reset_at: float) -> None:
        super().__init__(message)
        self.reset_at = reset_at


def redact(text: str) -> str:
    """Strip any token embedded in an authenticated URL before it reaches a log or an error."""
    return re.sub(r"(https://)[^@/\s]+@", r"\1***@", text or "")


def _reset_of(text: str, now: float) -> float | None:
    found = _RESET_HEADER.search(text)
    if found:
        return float(found.group(1))
    found = _RETRY_AFTER.search(text)
    if found:
        return now + float(found.group(1))
    found = _RESET_AT.search(text)
    if found:
        try:
            return datetime.fromisoformat(found.group(1).replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def rate_limited(p: subprocess.CompletedProcess[str], message: str = "", *,
                 clock: Callable[[], float] = time.time) -> RateLimited | None:
    """The `RateLimited` a failed `gh` call is, or `None` when it failed for another reason.
    `message` is the call's own account of the failure, kept as the error's text when given."""
    if p.returncode == 0:
        return None
    text = f"{p.stderr or ''}\n{p.stdout or ''}"
    if not any(m in text.lower() for m in _MARKERS):
        return None
    now = clock()
    reset = _reset_of(text, now)
    if reset is None or reset <= now:
        reset = now + DEFAULT_WAIT
    said = message or f"the forge's rate limit is spent: {(p.stderr or p.stdout or '')[-300:]}"
    return RateLimited(redact(said), reset_at=reset)
