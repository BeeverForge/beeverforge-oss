"""A `git rev-parse` that times out while marking the worktree does not fail the job (#117).

WHY. `gitworktrees.mark_as_job` asks `git -C <wt> rev-parse --absolute-git-dir` with
`timeout=60`. On expiry Python raises `subprocess.TimeoutExpired`, a `SubprocessError` and not an
`OSError`, while `prepare` catches only `OSError` around the marker: a hung `rev-parse` failed the
job after its worktree was added, although a marker that cannot be written is meant to be said
and let the job start. `mark_as_job` now raises `OSError` for it, as its docstring says.

The timeout is forced by a patched `subprocess.run` that raises at once for that one command and
delegates every other git call to the real one: no sleep, nothing bounded by elapsed time.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import pytest

from beeverforge.adapters import gitworktrees
from beeverforge.adapters.sandbox.worktree import WorktreeSandbox

#: The marker's name, as the #747 contract states it
MARKER = "beeverforge-job"
BRANCH = "beeverforge/117"


def _git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          check=True).stdout


@pytest.fixture
def repo(tmp_path) -> Path:
    """A person's repository with one commit on `main`."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    (repo / "app.py").write_text("x = 1\n")
    _git("add", "-A", cwd=repo)
    _git("commit", "-qm", "first", cwd=repo)
    return repo


@pytest.fixture
def rev_parse_hangs(monkeypatch):
    """`git rev-parse --absolute-git-dir` times out; every other command runs for real."""
    real_run = subprocess.run

    def run(cmd, *args, **kwargs):
        if "--absolute-git-dir" in list(cmd):
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout") or 60)
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(gitworktrees.subprocess, "run", run)


def test_a_rev_parse_that_times_out_still_starts_the_job_and_says_the_marker_was_not_written(
        tmp_path, repo, rev_parse_hangs, caplog):
    """Before the fix `prepare` raised `subprocess.TimeoutExpired` after the worktree was added."""
    with caplog.at_level(logging.WARNING, logger="beeverforge.sandbox.worktree"):
        ws = WorktreeSandbox(root=tmp_path / "jobs").prepare(
            repo_path=repo, base_branch="main", branch=BRANCH)

    assert _git("rev-parse", "--abbrev-ref", "HEAD", cwd=ws.path).strip() == BRANCH
    said = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any(str(ws.path) in line and "could not mark" in line for line in said), (
        f"the unwritten marker was not said: {said}")
    assert list((repo / ".git" / "worktrees").glob(f"*/{MARKER}")) == []


def test_mark_as_job_raises_oserror_when_rev_parse_times_out(tmp_path, repo, rev_parse_hangs):
    """The docstring's contract: git that cannot answer is an `OSError`, the timeout its cause."""
    wt = tmp_path / "wt"
    _git("worktree", "add", "-q", "-b", BRANCH, str(wt), "main", cwd=repo)

    with pytest.raises(OSError) as excinfo:
        gitworktrees.mark_as_job(wt)

    assert isinstance(excinfo.value.__cause__, subprocess.TimeoutExpired)
    assert str(wt) in str(excinfo.value)
