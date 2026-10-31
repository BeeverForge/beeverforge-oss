"""An argument list too long is a named failure of the GitHub tracker, not a raw `OSError` (#130).

Linux refuses one argv element longer than `MAX_ARG_STRLEN` (131,072 bytes, its terminating NUL
counted) with `E2BIG`, and `subprocess.run` raises it as
`OSError: [Errno 7] Argument list too long: 'gh'` before `gh` starts. `GitHubIssuesTracker._gh`
caught only `FileNotFoundError`, so a long text on a call site that still builds it into argv
(`comment`'s `--body`, `close_ticket`'s `--comment`) reached the caller as a traceback. It is now a
failed call, answered as `refused()` answers one, whose one sentence names the cause and the
remedy for that command (a comment's text goes on stdin with `--body-file -`; a close reason,
since `gh issue close` has no `--body-file`, is posted as a comment on stdin before a bare
close), and the bound is logged.

`subprocess.run` is replaced by a fake that applies the kernel's rule; `gh` is never spawned. The
bound is read from `MAX_ARG_STRLEN`, never typed here.
"""

from __future__ import annotations

import errno
import logging
import os
import subprocess
import time

import pytest

from beeverforge.adapters.agent.base import MAX_ARG_STRLEN
from beeverforge.adapters.tracker.github import GitHubIssuesTracker

#: Over `MAX_ARG_STRLEN` in UTF-8 bytes (3 bytes a character), under GitHub's 65,536 characters.
BIG = "語" * 50_000

_SECONDARY = "You have exceeded a secondary rate limit. Please wait a few minutes before you try again."


class KernelGH:
    """`subprocess.run(["gh", ...])` as `execve` sees it: an argument whose length with its NUL
    exceeds `MAX_ARG_STRLEN` is refused with `E2BIG` (`fs/exec.c::copy_strings`). The first
    `rate_limited` calls that pass the rule answer with a secondary rate limit."""

    def __init__(self, *, rate_limited: int = 0, oversize_from: int = 0) -> None:
        self.calls: list[list[str]] = []
        self._rate_limited = rate_limited
        self._oversize_from = oversize_from  # the rule applies from this call on (0: always)
        self._n = 0

    def __call__(self, argv, **kw):
        n = self._n
        self._n += 1
        if n >= self._oversize_from:
            for arg in argv:
                if len(os.fsencode(arg)) + 1 > MAX_ARG_STRLEN:
                    raise OSError(errno.E2BIG, os.strerror(errno.E2BIG), argv[0])
        self.calls.append(list(argv))
        if self._rate_limited:
            self._rate_limited -= 1
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr=_SECONDARY)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")


@pytest.fixture
def kernel(monkeypatch):
    fake = KernelGH()
    monkeypatch.setattr(subprocess, "run", fake)
    return fake


def _comment_args() -> list[str]:
    return ["issue", "comment", "1", "--repo", "o/r", "--body", BIG]


def test_the_text_is_over_the_ceiling_in_bytes():
    assert len(BIG) < GitHubIssuesTracker.body_limit
    assert len(BIG.encode()) + 1 > MAX_ARG_STRLEN


def test_an_argv_element_over_the_ceiling_is_a_failed_call_naming_the_remedy(kernel):
    p = GitHubIssuesTracker("o/r")._gh(_comment_args())
    assert isinstance(p, subprocess.CompletedProcess)
    assert p.returncode != 0
    assert f"{MAX_ARG_STRLEN:,}" in p.stderr
    assert "--body-file -" in p.stderr
    assert "stdin" in p.stderr
    assert "E2BIG" in p.stderr
    assert kernel.calls == []


def test_the_ceiling_is_logged_when_hit(kernel, caplog):
    with caplog.at_level(logging.WARNING, logger="beeverforge.tracker.github"):
        GitHubIssuesTracker("o/r")._gh(_comment_args())
    hits = [r.getMessage() for r in caplog.records
            if "BEEVERFORGE_GH_ARGV_TOO_LONG" in r.getMessage()]
    assert len(hits) == 1
    assert f"{MAX_ARG_STRLEN:,}" in hits[0]


def test_a_long_comment_fails_by_name_not_as_oserror(kernel):
    with pytest.raises(RuntimeError) as caught:
        GitHubIssuesTracker("o/r").comment("#1", BIG)
    assert not isinstance(caught.value, OSError)
    message = str(caught.value)
    assert "`gh issue comment`" in message
    assert "must go to `gh` on stdin with `--body-file -`" in message
    assert "without `--comment`" not in message
    assert f"{MAX_ARG_STRLEN:,}" in message


def test_a_long_close_reason_fails_by_name_not_as_oserror(kernel):
    # `gh issue close` has no `--body-file`: its remedy is the comment on stdin, then a bare close
    with pytest.raises(RuntimeError) as caught:
        GitHubIssuesTracker("o/r").close_ticket("#1", BIG)
    assert not isinstance(caught.value, OSError)
    message = str(caught.value)
    assert "`gh issue close`" in message
    assert "posted first as a comment on stdin" in message
    assert "closed without `--comment`" in message
    assert "must go to `gh` on stdin with `--body-file -`" not in message
    assert f"{MAX_ARG_STRLEN:,}" in message


def test_the_retry_run_is_caught_too(monkeypatch):
    # the first run is answered with a secondary rate limit; the retry meets the kernel's rule
    fake = KernelGH(rate_limited=1, oversize_from=1)
    monkeypatch.setattr(subprocess, "run", fake)
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    p = GitHubIssuesTracker("o/r")._gh(_comment_args())
    assert len(fake.calls) == 1  # the first run happened, the retry was refused by the kernel
    assert p.returncode != 0
    assert "--body-file -" in p.stderr
    assert f"{MAX_ARG_STRLEN:,}" in p.stderr


def test_another_oserror_still_raises(monkeypatch):
    def denied(argv, **kw):
        raise OSError(errno.EACCES, os.strerror(errno.EACCES), argv[0])

    monkeypatch.setattr(subprocess, "run", denied)
    with pytest.raises(OSError) as caught:
        GitHubIssuesTracker("o/r")._gh(["issue", "view", "1", "--repo", "o/r"])
    assert caught.value.errno == errno.EACCES


def test_a_missing_gh_keeps_its_own_remedy(monkeypatch):
    def missing(argv, **kw):
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), argv[0])

    monkeypatch.setattr(subprocess, "run", missing)
    with pytest.raises(RuntimeError, match="is not installed"):
        GitHubIssuesTracker("o/r")._gh(["issue", "view", "1", "--repo", "o/r"])
