"""A relative `gitdir` under a symlinked cache root still holds the job's worktree (#115).

WHAT WAS MEASURED (from the issue). Git 2.48+ writes the admin directory's `gitdir` file relative
when `worktree.useRelativePaths=true`, computed from the REAL admin directory. With the cache root
a symlink deeper than its target (`deep/a/b/c/repos -> real-repos`), `gitdir` read
`../../../../../jobs/openfactory-1/.git`; `os.path.normpath(admin / gitdir)` applied the `..`
against the path as the cache spells it, named a directory that does not exist, the mark read as
gone (`live_job_marks(served).live == []`), and after the origin advanced the sync swapped the
served tree: `git -C <wt> status` exited 128, `fatal: not a git repository`.

TWO WRITERS OF THE RELATIVE `gitdir`:
  - git itself, through `worktree.useRelativePaths` (git 2.48 or newer; the module's other tests
    skip by name on an older git, which cannot write one);
  - this file, by hand, as git computes it — `os.path.relpath(<wt>/.git, <real admin>)` — so the
    reading is proven on every git, the worker image's 2.47.3 included.

The rest is the production path: the real `RepoCache` over a local bare origin and the real
`WorktreeSandbox.prepare` over the served checkout.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path

import pytest

from beeverforge.adapters import gitworktrees
from beeverforge.adapters.sandbox.worktree import WorktreeSandbox
from beeverforge.runtime.repo_cache import RepoCache

BRANCH = "beeverforge/115"


def _git_version() -> tuple[int, int] | None:
    done = subprocess.run(["git", "--version"], capture_output=True, text=True, check=False)
    found = re.search(r"(\d+)\.(\d+)", done.stdout or "")
    return (int(found.group(1)), int(found.group(2))) if found else None


GIT = _git_version()
#: The relative `gitdir` writer, `worktree.useRelativePaths`, arrived in git 2.48
WRITES_RELATIVE = GIT is not None and GIT >= (2, 48)
needs_relative_git = pytest.mark.skipif(
    not WRITES_RELATIVE,
    reason=f"git {'.'.join(map(str, GIT)) if GIT else 'unknown'} is older than 2.48 and cannot "
           f"write a relative gitdir (worktree.useRelativePaths)")


def _git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          check=True).stdout


def _answers(wt: Path) -> tuple[int, str]:
    """What `git status` in the job's worktree says: its exit code and its words."""
    done = subprocess.run(["git", "-C", str(wt), "status", "--porcelain"], capture_output=True,
                          text=True, env={**os.environ, "LC_ALL": "C"})
    return done.returncode, done.stdout + done.stderr


def _head(path: Path) -> str:
    return _git("rev-parse", "HEAD", cwd=path).strip()


class Origin:
    """A bare repository the cache clones and the job pushes to, and a clone that moves it."""

    def __init__(self, tmp: Path) -> None:
        self.work = tmp / "origin-work"
        self.work.mkdir()
        _git("init", "-q", "-b", "main", cwd=self.work)
        (self.work / "app.py").write_text("x = 1\n")
        _git("add", "-A", cwd=self.work)
        _git("commit", "-qm", "first", cwd=self.work)
        self.bare = tmp / "origin.git"
        _git("clone", "-q", "--bare", str(self.work), str(self.bare), cwd=tmp)
        _git("remote", "add", "origin", str(self.bare), cwd=self.work)
        self.url = str(self.bare)

    def advance(self, text: str = "x = 2\n") -> None:
        (self.work / "app.py").write_text(text)
        _git("commit", "-qam", "advance", cwd=self.work)
        _git("push", "-q", "origin", "main", cwd=self.work)


def _symlinked_cache(tmp: Path) -> RepoCache:
    """A cache whose root is a symlink deeper than its target: `deep/a/b/c/repos -> real-repos`."""
    (tmp / "real-repos").mkdir()
    (tmp / "deep" / "a" / "b" / "c").mkdir(parents=True)
    link = tmp / "deep" / "a" / "b" / "c" / "repos"
    link.symlink_to(tmp / "real-repos", target_is_directory=True)
    return RepoCache(root=link)


def _gitdir_file(served: Path) -> Path:
    (admin,) = [p for p in (served / ".git" / "worktrees").iterdir() if p.is_dir()]
    return admin / "gitdir"


@pytest.fixture(params=["written-by-git", "written-by-hand"])
def job(request, tmp_path, monkeypatch):
    """The served checkout under a symlinked cache root, a job's worktree added to it by the real
    box, and its admin directory's `gitdir` relative — written by git, or by hand as git does."""
    if request.param == "written-by-git":
        if not WRITES_RELATIVE:
            pytest.skip(needs_relative_git.kwargs["reason"])
        monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
        monkeypatch.setenv("GIT_CONFIG_KEY_0", "worktree.useRelativePaths")
        monkeypatch.setenv("GIT_CONFIG_VALUE_0", "true")
    origin = Origin(tmp_path)
    cache = _symlinked_cache(tmp_path)
    served = cache.sync("p", origin.url, "main")
    assert served is not None
    ws = WorktreeSandbox(root=tmp_path / "jobs").prepare(
        repo_path=served, base_branch="main", branch=BRANCH, remote_url=origin.url)
    gitdir = _gitdir_file(served)
    if request.param == "written-by-hand":
        real_admin = gitdir.parent.resolve()
        gitdir.write_text(os.path.relpath(ws.path.resolve() / ".git", real_admin) + "\n")
    written = gitdir.read_text().strip()
    assert not os.path.isabs(written), f"the case needs a relative gitdir, and it reads {written}"
    return cache, origin, served, ws


@needs_relative_git
def test_git_writes_a_relative_gitdir_under_worktree_use_relative_paths(tmp_path, monkeypatch):
    """The writer the issue names: the box's own add, under `worktree.useRelativePaths=true`."""
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "worktree.useRelativePaths")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "true")
    origin = Origin(tmp_path)
    served = _symlinked_cache(tmp_path).sync("p", origin.url, "main")
    assert served is not None
    WorktreeSandbox(root=tmp_path / "jobs").prepare(
        repo_path=served, base_branch="main", branch=BRANCH, remote_url=origin.url)
    assert not os.path.isabs(_gitdir_file(served).read_text().strip())


def test_a_relative_gitdir_under_a_symlinked_cache_root_is_read_as_a_live_mark(job):
    """Before the fix `live` was `[]`: `normpath` applied the `..` to the symlink's spelling."""
    _, _, served, ws = job
    marks = gitworktrees.live_job_marks(served)
    assert marks is not None
    assert [m.worktree for m in marks.live] == [str(ws.path.resolve())]


def test_a_relative_gitdir_under_a_symlinked_cache_root_holds_the_sync(job, caplog):
    """Before the fix the second sync swapped the served tree and `git status` exited 128."""
    cache, origin, served, ws = job
    served_head = _head(served)
    origin.advance()
    with caplog.at_level(logging.WARNING, logger="beeverforge.repo_cache"):
        assert cache.sync("p", origin.url, "main") == served
    rc, said = _answers(ws.path)
    assert rc == 0, f"the job's worktree lost its git directory to the sync: {said.strip()}"
    assert _head(served) == served_head
    assert any("BEEVERFORGE_CACHE_HELD" in r.getMessage() for r in caplog.records)
