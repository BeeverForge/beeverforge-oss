"""A comment or close reason GitHub would accept reaches `gh` on stdin, whatever its bytes.

GITHUB COUNTS CHARACTERS; THE KERNEL COUNTS BYTES. The GitHub tracker's `comment` passed its text
to `gh` as one argv element (`--body body`), and `close_ticket` passed its reason the same way
(`--comment reason`). Linux refuses one argv element of `MAX_ARG_STRLEN` bytes or more (its NUL
counted) with `E2BIG`, raised by `subprocess.run` as `OSError` before `gh` starts, while GitHub
accepts 65,536 characters: a 3-byte script failed from about 43,690 characters.

`gh issue close` has no file form for `--comment`, so a close reason is now posted first as a
comment on stdin (`gh issue comment --body-file -`) and the issue closed with `--reason` alone.
Readers see the reason before the close, as they did. The forge's text rules (#127) hold for both
texts: a lone surrogate is marked U+FFFD, a NUL or other control character is sent as written, and
a text over GitHub's limit is refused by name before `gh` runs, never cut.

WHAT IS DRIVEN HERE IS THE PRODUCTION PATH: `comment` and `close_ticket`, through `_write` and
`_gh`, into `subprocess.run`, replaced by a fake that refuses an argv element the way the kernel
does and writes stdin with the strict UTF-8 encoder `text=True` uses. The fake never spawns `gh`.
Both bounds are read from the values the code exports.
"""

from __future__ import annotations

import errno
import os
import subprocess
import time

import pytest

from beeverforge.adapters.agent.base import MAX_ARG_STRLEN
from beeverforge.adapters.github_cli import BODY_LIMIT
from beeverforge.adapters.tracker.github import GitHubIssuesTracker

REPO = "someone/books"

#: A text GitHub accepts (under its character limit) that one argv element cannot carry.
LONG = "語" * 43_700

_REFUSAL = "HTTP 403: Resource not accessible by integration"


class KernelGH:
    """Stands in for `subprocess.run(["gh", ...])` as `execve` would see it, recording argv and
    stdin (`input=`) per call. An argument whose length with its NUL exceeds `MAX_ARG_STRLEN` is
    refused with `E2BIG` (`fs/exec.c::copy_strings`), before `gh` exists; an argument holding a NUL
    is refused by `subprocess` itself with `ValueError`, and a stdin text that is not valid UTF-8
    (a lone surrogate) raises `UnicodeEncodeError`, as `text=True`'s strict encoder does. A verb
    in `fails` (`"comment"`, `"close"`) exits 1 with a refusal carrying no rate-limit marker."""

    def __init__(self, *, fails: str = "") -> None:
        self.calls: list[list[str]] = []
        self.stdins: list[str | None] = []
        self.fails = fails

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
        if self.fails and argv[1:3] == ["issue", self.fails]:
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr=_REFUSAL)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    def verbs(self) -> list[str]:
        return [" ".join(argv[1:3]) for argv in self.calls]

    def writes(self, verb: str) -> list[tuple[list[str], str | None]]:
        return [(argv, stdin) for argv, stdin in zip(self.calls, self.stdins, strict=True)
                if argv[1:3] == ["issue", verb]]


class Board:
    """A board that records every move, so a close that did not happen is seen to move nothing."""

    def __init__(self) -> None:
        self.moves: list[dict] = []

    def set_status(self, **kw) -> None:
        self.moves.append(kw)


@pytest.fixture
def gh(monkeypatch):
    fake = KernelGH()
    monkeypatch.setattr(subprocess, "run", fake)
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    return fake


def _tracker() -> GitHubIssuesTracker:
    tracker = GitHubIssuesTracker(REPO)
    tracker.board = Board()
    return tracker


def _comment(tracker: GitHubIssuesTracker, text: str) -> None:
    tracker.comment("#12", text)


def _close(tracker: GitHubIssuesTracker, text: str) -> None:
    tracker.close_ticket("#12", text, delivered=False)


#: The two writes that carry a text, each driven through its public method.
SITES = {"comment": _comment, "close_ticket": _close}


def _posted(gh: KernelGH) -> str | None:
    """The one comment's stdin, after asserting it was sent on stdin and never in argv."""
    [(argv, stdin)] = gh.writes("comment")
    assert argv[-2:] == ["--body-file", "-"], argv[:6]
    assert "--body" not in argv
    assert max(len(arg) for arg in argv) < 40, "a text went into argv"
    return stdin


def test_a_long_comment_reaches_gh_on_stdin_byte_for_byte(gh):
    """About 43,700 three-byte characters, under GitHub's limit and over one argv element's bytes,
    reach `gh issue comment --body-file -` on stdin. On `main` the text is the `--body` element and
    the kernel refuses it, which `_write` raises as a failed call."""
    assert len(LONG) < BODY_LIMIT
    assert len(LONG.encode()) + 1 > MAX_ARG_STRLEN

    _tracker().comment("#12", LONG)

    assert gh.calls[0][:6] == ["gh", "issue", "comment", "12", "--repo", REPO]
    assert _posted(gh).encode() == LONG.encode()


def test_a_long_close_reason_reaches_gh_on_stdin_byte_for_byte(gh):
    """The same text as a close reason is posted as a comment on stdin, and the issue then closed.
    On `main` it is the close's `--comment` element and the kernel refuses it."""
    tracker = _tracker()

    tracker.close_ticket("#12", LONG, delivered=True)

    assert _posted(gh).encode() == LONG.encode()
    assert gh.verbs() == ["issue comment", "issue close"]
    assert len(tracker.board.moves) == 1


@pytest.mark.parametrize(("delivered", "why"), [(True, "completed"), (False, "not planned")])
def test_the_reason_is_posted_before_a_close_that_carries_no_comment(gh, delivered, why):
    """Readers see the reason before the close, as they did: the comment, then a bare close whose
    `--reason` says how it ended. On `main` there is one call, the close, carrying `--comment`."""
    tracker = _tracker()

    tracker.close_ticket("#12", "folded into #288", delivered=delivered)

    assert gh.verbs() == ["issue comment", "issue close"]
    assert gh.stdins[0] == "folded into #288"
    [(close, stdin)] = gh.writes("close")
    assert close == ["gh", "issue", "close", "12", "--repo", REPO, "--reason", why]
    assert stdin is None
    assert "--comment" not in close


def test_a_refused_comment_leaves_the_issue_open(gh):
    """A comment `gh` refuses raises, as the tracker's contract asks, and nothing is closed or
    moved: an issue closed without its reason is a close nobody can read."""
    gh.fails = "comment"
    tracker = _tracker()

    with pytest.raises(RuntimeError, match="403"):
        tracker.comment("#12", "a note")
    with pytest.raises(RuntimeError, match="403"):
        tracker.close_ticket("#12", "folded into #288", delivered=False)

    assert gh.verbs() == ["issue comment", "issue comment"]
    assert gh.stdins == ["a note", "folded into #288"]
    assert tracker.board.moves == []


def test_a_refused_close_after_the_comment_says_the_reason_was_posted_and_the_issue_is_open(gh):
    """The comment is on the issue and the close was refused: the raise says both, with `gh`'s own
    error and the remedy, and the card's column does not move."""
    gh.fails = "close"
    tracker = _tracker()

    with pytest.raises(RuntimeError) as raised:
        tracker.close_ticket("#12", "folded into #288", delivered=False)

    said = str(raised.value)
    assert "posted" in said and "still open" in said, said
    assert _REFUSAL in said
    assert "close" in said and "by hand" in said
    assert "12" not in said, "an issue number is in the sentence"
    assert isinstance(raised.value.__cause__, RuntimeError)
    assert gh.verbs() == ["issue comment", "issue close"]
    assert tracker.board.moves == []


def test_a_refused_close_with_no_reason_never_says_a_reason_was_posted(gh):
    """With nothing posted, a refused close raises `gh`'s own error, unchanged: a sentence about a
    comment that was never written would send a person looking for it."""
    gh.fails = "close"
    tracker = _tracker()

    with pytest.raises(RuntimeError) as raised:
        tracker.close_ticket("#12", "", delivered=True)

    assert "posted" not in str(raised.value)
    assert _REFUSAL in str(raised.value)
    assert gh.verbs() == ["issue close"]
    assert tracker.board.moves == []


@pytest.mark.parametrize("site", list(SITES))
def test_a_lone_surrogate_is_replaced_before_stdin(gh, site):
    """A byte that was not UTF-8, read with `surrogateescape`, is sent as U+FFFD and the rest
    unchanged. Compared as encoded bytes, so a failure prints valid UTF-8."""
    SITES[site](_tracker(), "before \udcff after")

    assert _posted(gh).encode() == "before \ufffd after".encode()


@pytest.mark.parametrize("site", list(SITES))
def test_a_control_character_reaches_stdin_unchanged(gh, site):
    """A NUL and a bell reach stdin as written: stdin carries any byte, and no argv carries the
    text. On `main` the NUL in argv is refused by `subprocess` before `gh` starts."""
    text = "a\x00b\x07c"

    SITES[site](_tracker(), text)

    assert _posted(gh) == text


@pytest.mark.parametrize("site", list(SITES))
def test_a_text_over_the_limit_is_refused_before_any_gh_call(gh, site):
    """A text over GitHub's limit is refused by name, with the remedy, before `gh` runs, and is
    never cut to fit; a text of exactly the limit is sent whole."""
    tracker = _tracker()

    with pytest.raises(RuntimeError) as raised:
        SITES[site](tracker, "x" * (BODY_LIMIT + 1))

    said = str(raised.value)
    assert f"{BODY_LIMIT:,}" in said and f"{BODY_LIMIT + 1:,}" in said, said
    assert "shorten" in said, said
    assert gh.calls == []
    assert tracker.board.moves == []

    SITES[site](tracker, "x" * BODY_LIMIT)

    assert _posted(gh) == "x" * BODY_LIMIT


@pytest.mark.parametrize("reason", ["", "  \n"])
def test_an_empty_or_blank_reason_closes_with_no_comment(gh, reason):
    """A reason with nothing in it is not posted: one call, the bare close."""
    tracker = _tracker()

    tracker.close_ticket("#12", reason, delivered=True)

    assert gh.calls == [["gh", "issue", "close", "12", "--repo", REPO, "--reason", "completed"]]
    assert len(tracker.board.moves) == 1
