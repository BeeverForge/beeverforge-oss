"""#276: a rebase before merge runs as the factory's bot, and a failure that is not a conflict
says what it was.

WHY. `rebase_onto_base` ran `git rebase` with whatever identity the host had: none, on a
deployment that sets none, and a rebase replays commits as their committer, so git refused
("Committer identity unknown") and the box reported "conflict". The job parked for a person on a
conflict that did not exist. And ANY nonzero exit was a conflict, so a held `index.lock` or a full
disk read the same.

THE RULE THIS FILE HOLDS:
  1. a host with no git identity rebases, as `bot_identity()`;
  2. a real textual conflict is still "conflict", and the tree is left clean;
  3. a failure with no unmerged path raises with git's own sentence, redacted.

Nothing here waits on real time: the lock is a file that is already there.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from beeverforge.adapters.sandbox.worktree import WorktreeSandbox
from tests import the_git_bed
from tests.the_git_bed import a_card_repository

REAL_RUN = subprocess.run
git_bed = the_git_bed.git_bed


def _git(*args: str, cwd: Path) -> str:
    return REAL_RUN(["git", "-c", "core.hooksPath=/dev/null", *args], cwd=cwd,
                    capture_output=True, text=True, check=True, timeout=60).stdout.strip()


@pytest.fixture
def cache(tmp_path, git_bed) -> Path:
    seed = a_card_repository(git_bed, tmp_path / "seed")
    _git("clone", "-q", "--bare", str(seed), str(tmp_path / "origin.git"), cwd=tmp_path)
    _git("clone", "-q", str(tmp_path / "origin.git"), str(tmp_path / "cache"), cwd=tmp_path)
    return tmp_path / "cache"


def _advance(tmp_path: Path, name: str, content: str = "x\n") -> None:
    other = tmp_path / f"other-{name}"
    _git("clone", "-q", str(tmp_path / "origin.git"), str(other), cwd=tmp_path)
    (other / f"{name}.txt").write_text(content)
    _git("add", "-A", cwd=other)
    _git("-c", "user.name=A Person", "-c", "user.email=a@example.invalid",
         "commit", "-qm", name, cwd=other)
    _git("push", "-q", "origin", "main", cwd=other)


def _commit(ws: Path, name: str, content: str = "y\n") -> None:
    (ws / name).write_text(content)
    _git("add", "-A", cwd=ws)
    _git("-c", "user.name=A Person", "-c", "user.email=a@example.invalid",
         "commit", "-qm", f"add {name}", "--no-verify", cwd=ws)


@pytest.fixture
def no_identity(tmp_path, monkeypatch):
    """A host where git knows nobody: no variable, no config file, and no guessing from the
    host's name (`useConfigOnly`), so the refusal does not depend on the machine."""
    for var in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME",
                "GIT_COMMITTER_EMAIL", "EMAIL"):
        monkeypatch.delenv(var, raising=False)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    count = int(os.environ.get("GIT_CONFIG_COUNT", "0"))
    monkeypatch.setenv(f"GIT_CONFIG_KEY_{count}", "user.useConfigOnly")
    monkeypatch.setenv(f"GIT_CONFIG_VALUE_{count}", "true")
    monkeypatch.setenv("GIT_CONFIG_COUNT", str(count + 1))


def test_a_host_with_no_git_identity_rebases(tmp_path, cache, no_identity, monkeypatch):
    monkeypatch.setenv("BEEVERFORGE_BOT_NAME", "The Bot")
    monkeypatch.setenv("BEEVERFORGE_BOT_EMAIL", "bot@example.invalid")
    box = WorktreeSandbox(root=tmp_path / "jobs")
    ws = box.prepare(repo_path=cache, base_branch="main", branch="job-1")
    _commit(ws.path, "job.py")
    _advance(tmp_path, "newer")

    assert box.rebase_onto_base(workspace=ws, base="main") == "rebased"
    assert _git("log", "-1", "--format=%cn <%ce>", cwd=ws.path) == "The Bot <bot@example.invalid>"


def test_a_real_conflict_is_still_a_conflict(tmp_path, cache):
    box = WorktreeSandbox(root=tmp_path / "jobs")
    ws = box.prepare(repo_path=cache, base_branch="main", branch="job-1")
    _commit(ws.path, "same.txt", "mine\n")
    _advance(tmp_path, "same", "theirs\n")

    assert box.rebase_onto_base(workspace=ws, base="main") == "conflict"
    assert _git("status", "--porcelain", cwd=ws.path) == ""


def test_a_held_index_lock_is_reported_by_its_cause(tmp_path, cache):
    box = WorktreeSandbox(root=tmp_path / "jobs")
    ws = box.prepare(repo_path=cache, base_branch="main", branch="job-1")
    _commit(ws.path, "job.py")
    _advance(tmp_path, "newer")
    git_dir = Path(_git("rev-parse", "--absolute-git-dir", cwd=ws.path))
    (git_dir / "index.lock").write_text("")

    with pytest.raises(RuntimeError, match=r"rebase failed: .*index\.lock"):
        box.rebase_onto_base(workspace=ws, base="main")


def test_the_cause_is_redacted(tmp_path, cache, monkeypatch):
    box = WorktreeSandbox(root=tmp_path / "jobs")
    ws = box.prepare(repo_path=cache, base_branch="main", branch="job-1")
    _commit(ws.path, "job.py")
    _advance(tmp_path, "newer")
    from beeverforge.adapters.sandbox import worktree
    real = worktree._run

    def run(cmd, **kw):
        if "rebase" in cmd and "--abort" not in cmd:
            return 128, "fatal: https://user:s3cret@host/x.git broke"
        return real(cmd, **kw)

    monkeypatch.setattr(worktree, "_run", run)
    with pytest.raises(RuntimeError) as err:
        box.rebase_onto_base(workspace=ws, base="main")
    assert "s3cret" not in str(err.value)
