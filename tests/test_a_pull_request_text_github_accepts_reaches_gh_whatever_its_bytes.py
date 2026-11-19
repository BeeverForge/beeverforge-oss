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
    refused with `E2BIG` (`fs/exec.c::copy_strings`), before `gh` exists; an argument holding a NUL
    is refused by `subprocess` itself with `ValueError`, and a stdin text that is not valid UTF-8
    (a lone surrogate) raises `UnicodeEncodeError`, as `text=True`'s strict encoder does."""

    def __init__(self, *, open_pr: str = "") -> None:
        self.calls: list[list[str]] = []
        self.stdins: list[str | None] = []
        self._open_pr = open_pr

    def __call__(self, argv, **kw):
        for arg in argv:
            if "\x00" in arg:  # `subprocess` refuses it before `execve`
                raise ValueError("embedded null byte")
            if len(os.fsencode(arg)) + 1 > MAX_ARG_STRLEN:
                raise OSError(errno.E2BIG, os.strerror(errno.E2BIG), argv[0])
        if kw.get("input") is not None:
            kw["input"].encode("utf-8")  # strict, as `text=True` writes stdin
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


# ---- what GitHub would not take is refused by name before `gh` runs; what is not UTF-8 is marked

#: A text as `surrogateescape` decodes bytes that are not UTF-8: it holds a lone surrogate.
UNDECODED = "before \udcff after"

#: The same text as UTF-8 once its undecodable byte is marked with U+FFFD.
MARKED = b"before \xef\xbf\xbd after"


def _shown(text: str | None) -> bytes:
    """`text` as UTF-8 with a lone surrogate written out as its escape, so a failed comparison
    prints nothing that is not UTF-8."""
    return (text or "").encode("utf-8", "backslashreplace")


def _open_with(forge: GitHubForge, *, title: str = "t", body: str = "b") -> str:
    return forge.open_pr(head="h", base="main", title=title, body=body)


def _title_too_long() -> str:
    from beeverforge.adapters.github_cli import TITLE_LIMIT

    return "t" * (TITLE_LIMIT + 1)


#: A title GitHub would not take: how it is made, and a word its refusal must say.
BAD_TITLES = {
    "nul": (lambda: "a\x00b", "NUL"),
    "too_long": (_title_too_long, "characters"),
}


@pytest.mark.parametrize("bad", list(BAD_TITLES))
def test_a_title_github_would_not_take_fails_the_create_by_name(monkeypatch, bad):
    """A NUL in the title ended `open_pr` in `ValueError: embedded null byte`, and a title over
    GitHub's limit was sent as is. Both are refused before `gh pr create` runs, as the
    `RuntimeError` a failed create raises, with the cause and the remedy."""
    make, says = BAD_TITLES[bad]
    gh = KernelGH()
    monkeypatch.setattr(subprocess, "run", gh)

    with pytest.raises(RuntimeError) as caught:
        _open_with(GitHubForge("o/r"), title=make())

    assert says in str(caught.value) and "title" in str(caught.value), str(caught.value)
    assert gh.writes("create") == [], "the create ran with a title GitHub would not take"


@pytest.mark.parametrize("bad", list(BAD_TITLES))
def test_a_title_github_would_not_take_leaves_the_open_pr_as_it_was_by_name(
        monkeypatch, caplog, bad):
    """Bringing an open pull request up to date with such a title is refused before `gh pr edit`
    runs, logged as the refused update it is, and the open pull request is still answered."""
    make, says = BAD_TITLES[bad]
    gh = KernelGH(open_pr=_URL + "\n")
    monkeypatch.setattr(subprocess, "run", gh)

    with caplog.at_level(logging.WARNING, logger="beeverforge.forge.github"):
        assert _open_with(GitHubForge("o/r"), title=make()) == _URL

    assert "BEEVERFORGE_PR_BODY_REFUSED" in caplog.text
    assert says in caplog.text, caplog.text
    assert gh.writes("edit") == [], "the edit ran with a title GitHub would not take"


def _refused_create(forge: GitHubForge, body: str) -> str:
    with pytest.raises(RuntimeError) as caught:
        _open_with(forge, body=body)
    return str(caught.value)


def _refused_update(forge: GitHubForge, body: str) -> str:
    assert _open_with(forge, body=body) == _URL
    return ""


def _refused_review(forge: GitHubForge, body: str) -> str:
    forge.review_pr(pr="7", event="comment", body=body)
    return ""


def _refused_set_body(forge: GitHubForge, body: str) -> str:
    assert forge.set_pr_body(pr="7", body=body) is False
    return ""


#: One row per write: what `pr list` answers, the write expecting a refusal, and its `gh pr` verb.
REFUSED = {
    "create": ("", _refused_create, "create"),
    "bring_up_to_date": (_URL + "\n", _refused_update, "edit"),
    "review": ("", _refused_review, "review"),
    "set_body": ("", _refused_set_body, "edit"),
}


@pytest.mark.parametrize("row", list(REFUSED))
def test_a_text_over_githubs_limit_is_refused_by_name_before_gh_runs(monkeypatch, caplog, row):
    """A text over GitHub's 65,536 characters was sent, and only GitHub refused it. Each write now
    refuses it before `gh` runs, never cut, through its own failure path, and the refusal names
    the limit and the remedy."""
    open_pr, write, verb = REFUSED[row]
    gh = KernelGH(open_pr=open_pr)
    monkeypatch.setattr(subprocess, "run", gh)

    with caplog.at_level(logging.WARNING, logger="beeverforge.forge.github"):
        raised = write(GitHubForge("o/r"), "x" * (GitHubIssuesTracker.body_limit + 1))

    said = raised + caplog.text
    assert f"{GitHubIssuesTracker.body_limit:,}" in said and "shorten" in said, said
    assert gh.writes(verb) == [], "the text was sent over GitHub's limit"


def _write_text(forge: GitHubForge, row: str, *, title: str = "t", body: str = "b") -> None:
    if row == "review":
        forge.review_pr(pr="7", event="comment", body=body)
    elif row == "set_body":
        assert forge.set_pr_body(pr="7", body=body) is True
    else:
        assert _open_with(forge, title=title, body=body) == _URL


@pytest.mark.parametrize("row", list(ROWS))
def test_a_text_that_is_not_utf8_reaches_gh_with_its_undecodable_bytes_marked(monkeypatch, row):
    """A lone surrogate in the text raised `UnicodeEncodeError` inside `subprocess.run`, a raw
    traceback. Each is replaced by U+FFFD before the text goes on stdin, so the write is still
    made and only the bytes that could not be decoded are marked."""
    open_pr, _, verb = ROWS[row]
    gh = KernelGH(open_pr=open_pr)
    monkeypatch.setattr(subprocess, "run", gh)

    _write_text(GitHubForge("o/r"), row, body=UNDECODED)

    [(_, stdin)] = gh.writes(verb)
    assert _shown(stdin) == MARKED


@pytest.mark.parametrize("row", ["create", "bring_up_to_date"])
def test_a_title_that_is_not_utf8_reaches_gh_with_its_undecodable_bytes_marked(monkeypatch, row):
    """The title follows the text's rule: a lone surrogate is replaced by U+FFFD, so `gh` is never
    handed bytes that are not UTF-8 to send to GitHub."""
    open_pr, _, verb = ROWS[row]
    gh = KernelGH(open_pr=open_pr)
    monkeypatch.setattr(subprocess, "run", gh)

    _write_text(GitHubForge("o/r"), row, title=UNDECODED)

    [(argv, _)] = gh.writes(verb)
    assert _shown(argv[argv.index("--title") + 1]) == MARKED


@pytest.mark.parametrize("row", list(ROWS))
def test_a_control_character_in_the_text_reaches_gh_on_stdin_unchanged(monkeypatch, row):
    """THE DELIBERATE CHOICE: a NUL or another control character in the TEXT is neither refused nor
    rewritten. Stdin carries any byte, so it reaches `gh` as it was written."""
    open_pr, _, verb = ROWS[row]
    gh = KernelGH(open_pr=open_pr)
    monkeypatch.setattr(subprocess, "run", gh)
    body = "a\x00b\x07c\x1bd"

    _write_text(GitHubForge("o/r"), row, body=body)

    [(_, stdin)] = gh.writes(verb)
    assert stdin == body
