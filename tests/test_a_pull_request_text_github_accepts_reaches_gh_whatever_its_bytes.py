"""A pull-request text GitHub would accept reaches `gh` on stdin, whatever its bytes.

GITHUB COUNTS CHARACTERS; THE KERNEL COUNTS BYTES. The GitHub forge passed every pull-request text
to `gh` as one argv element (`--body body`): `gh pr create`, the `gh pr edit` that brings an open
pull request up to date, `gh pr review` and `set_pr_body`'s `gh pr edit`. Linux refuses one argv
element of `MAX_ARG_STRLEN` bytes or more (its NUL counted) with `E2BIG`, raised by
`subprocess.run` as `OSError` before `gh` starts, while GitHub's limit is 65,536 characters. A
3-byte script crosses the byte ceiling at about 43,690 characters.

WHAT IS DRIVEN HERE IS THE PRODUCTION PATH: each forge write, through `_gh`, into
`subprocess.run`, replaced by a fake that refuses an argv element the way the kernel does. The fake
never spawns `gh`. Both numbers are read from the values the code exports.
"""

from __future__ import annotations

import errno
import logging
import os
import subprocess

import pytest

from beeverforge.adapters.agent.base import MAX_ARG_STRLEN
from beeverforge.adapters.forge.github import GitHubForge
from beeverforge.adapters.tracker.github import GitHubIssuesTracker

_URL = "https://github.com/o/r/pull/7"

#: A text GitHub accepts (under its character limit) that one argv element cannot carry.
BODY = "語" * 43_700


class KernelGH:
    """Stands in for `subprocess.run(["gh", ...])` as `execve` would see it, recording argv and
    stdin (`input=`) per call. An argument whose length with its NUL exceeds `MAX_ARG_STRLEN` is
    refused with `E2BIG` (`fs/exec.c::copy_strings`), before `gh` exists."""

    def __init__(self, *, open_pr: str = "") -> None:
        self.calls: list[list[str]] = []
        self.stdins: list[str | None] = []
        self._open_pr = open_pr

    def __call__(self, argv, **kw):
        for arg in argv:
            if len(os.fsencode(arg)) + 1 > MAX_ARG_STRLEN:
                raise OSError(errno.E2BIG, os.strerror(errno.E2BIG), argv[0])
        self.calls.append(list(argv))
        self.stdins.append(kw.get("input"))
        if argv[1:3] == ["pr", "list"]:
            return subprocess.CompletedProcess(argv, 0, stdout=self._open_pr, stderr="")
        if argv[1:3] == ["pr", "create"]:
            return subprocess.CompletedProcess(argv, 0, stdout=_URL + "\n", stderr="")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    def writes(self, verb: str) -> list[tuple[list[str], str | None]]:
        return [(argv, stdin) for argv, stdin in zip(self.calls, self.stdins, strict=True)
                if argv[1:3] == ["pr", verb]]


def _short(argv: list[str]) -> list[str]:
    return [a if len(a) <= 40 else f"<{len(a)} characters>" for a in argv]


def _create(forge: GitHubForge) -> None:
    assert forge.open_pr(head="h", base="main", title="t", body=BODY) == _URL


def _bring_up_to_date(forge: GitHubForge) -> None:
    assert forge.open_pr(head="h", base="main", title="t", body=BODY) == _URL


def _review(forge: GitHubForge) -> None:
    forge.review_pr(pr="7", event="comment", body=BODY)


def _set_body(forge: GitHubForge) -> None:
    assert forge.set_pr_body(pr="7", body=BODY) is True


#: One row per call site: what the fake's `pr list` answers, the write, and the `gh pr` verb of
#: the write's own call.
ROWS = {
    "create": ("", _create, "create"),
    "bring_up_to_date": (_URL + "\n", _bring_up_to_date, "edit"),
    "review": ("", _review, "review"),
    "set_body": ("", _set_body, "edit"),
}


def test_the_forges_gh_hands_its_stdin_to_gh_as_input(monkeypatch):
    """`GitHubForge._gh(..., stdin=)` reaches `subprocess.run` as `input=`, as the tracker's does.
    On `main` `_gh` takes no `stdin` and raises `TypeError`."""
    gh = KernelGH()
    monkeypatch.setattr(subprocess, "run", gh)

    done = GitHubForge("o/r")._gh(["pr", "view", "1", "--repo", "o/r"], stdin="x")

    assert done.returncode == 0
    assert gh.stdins == ["x"]


@pytest.mark.parametrize("row", list(ROWS))
def test_a_pull_request_text_reaches_gh_on_stdin(monkeypatch, caplog, row):
    """Each forge write with a text under GitHub's 65,536 characters and over one argv element's
    bytes succeeds, with the text on stdin and never in argv. On `main` the create and the review
    raise `OSError [Errno 7]`, `set_pr_body` answers False, and the bring-up-to-date edit is logged
    as refused without ever reaching `gh`."""
    assert len(BODY) < GitHubIssuesTracker.body_limit
    assert len(BODY.encode()) + 1 > MAX_ARG_STRLEN
    open_pr, write, verb = ROWS[row]
    gh = KernelGH(open_pr=open_pr)
    monkeypatch.setattr(subprocess, "run", gh)

    with caplog.at_level(logging.WARNING, logger="beeverforge.forge.github"):
        write(GitHubForge("o/r"))

    assert "BEEVERFORGE_PR_BODY_REFUSED" not in caplog.text
    [(argv, stdin)] = gh.writes(verb)
    assert "--body" not in argv, _short(argv)
    assert "--body-file" in argv and argv[argv.index("--body-file") + 1] == "-", _short(argv)
    assert not any(BODY in arg for arg in argv), "the text is still an argv element"
    assert stdin == BODY, "the text did not reach gh on stdin"


def test_a_kernel_refusal_reaching_the_forge_is_a_named_failed_call(monkeypatch, caplog):
    """An argv the kernel still refuses is answered as a failed call that names the cause and the
    remedy, logged by name on the forge's own logger, never a raw `OSError`."""
    monkeypatch.setattr(subprocess, "run", KernelGH())

    with caplog.at_level(logging.WARNING, logger="beeverforge.forge.github"):
        done = GitHubForge("o/r")._gh(["pr", "edit", "1", "--repo", "o/r", "--body", BODY])

    assert done.returncode != 0
    assert "E2BIG" in done.stderr
    assert f"{MAX_ARG_STRLEN:,}" in done.stderr
    assert "--body-file -" in done.stderr
    assert any("BEEVERFORGE_GH_ARGV_TOO_LONG" in r.getMessage() for r in caplog.records
               if r.name == "beeverforge.forge.github"), caplog.text


@pytest.mark.parametrize("raised", [
    OSError(errno.EACCES, os.strerror(errno.EACCES), "gh"),
    FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), "gh"),
], ids=["eacces", "enoent"])
def test_any_other_oserror_reaching_the_forge_is_raised_unchanged(monkeypatch, raised):
    """Only `E2BIG` is answered as a failed call: any other `OSError`, a missing `gh` included,
    still reaches the caller as the same object."""
    def run(argv, **kw):
        raise raised

    monkeypatch.setattr(subprocess, "run", run)

    with pytest.raises(OSError) as caught:
        GitHubForge("o/r")._gh(["pr", "view", "1", "--repo", "o/r"])

    assert caught.value is raised
