"""A worktree the box adds while a cache sync stages its snapshot keeps its `.git` (#91).

WHAT WAS MEASURED (review of #747). `RepoCache._needs_publish` reads the job marks and decides to
publish; `_publish` then hard-link-copies the master into `.staging` (`shutil.copytree`) and only
after that renames the served tree into `.trash`. `WorktreeSandbox.prepare` took no cache lock, so
a `worktree add` plus mark that landed in that window wrote the job's admin directory into the tree
about to be replaced, and the job failed with `fatal: not a git repository:
<root>/p/.git/worktrees/<name>` (`assert 128 == 0`) and lost its push. The window is the staging
time: 0.09 s for a 2,455-entry repository, growing with the file count.

THE INTERLEAVE IS DETERMINISTIC, NOT TIMED: a patched `copytree` runs the real `prepare` on the
served tree at the exact point in `_publish` the issue names, either before the real copy (the
window the lock closes) or after it, just before the rename (the window the re-check narrows).

RE-ENTRANCY DECIDES WHICH THREAD RUNS IT. The key's lock is re-entrant for the thread holding it
(`util/filelock.py`), and `sync` holds it around `_publish`. Run on the sync's own thread,
`prepare` passes the lock, so only the re-check before the rename can save the job: that is the
narrow test. Run on another thread, `prepare` waits on the lock until the publish is over: that is
the lock test. No wait in this file is bounded by time; the one deadline (on `join` and `wait`)
only fails the test when the code under test hangs.

The writers are the production ones (engineering lessons §1): the real `RepoCache` over a local
bare origin and the real `WorktreeSandbox.prepare`/`prepare_tip`/`publish_branch`.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from beeverforge.adapters.sandbox import worktree
from beeverforge.adapters.sandbox.worktree import WorktreeSandbox
from beeverforge.runtime import repo_cache
from beeverforge.runtime.repo_cache import RepoCache
from beeverforge.util.filelock import FileLock
from tests import the_git_bed

git_bed = the_git_bed.git_bed

BRANCH = "beeverforge/91"
REVIEWED = "beeverforge/91-review"
#: Only fails a test whose code under test hangs; nothing here is measured against it
HANG = 600


def _git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          check=True).stdout


def _git_dir(wt: Path) -> tuple[int, str]:
    """Whether the job's worktree still answers git: `rev-parse --git-dir`'s code and words."""
    done = subprocess.run(["git", "-C", str(wt), "rev-parse", "--git-dir"], capture_output=True,
                          text=True, env={**os.environ, "LC_ALL": "C"})
    return done.returncode, done.stdout + done.stderr


def _head(path: Path) -> str:
    return _git("rev-parse", "HEAD", cwd=path).strip()


class Origin:
    """A bare repository the cache clones and the job pushes to, and a clone that moves it."""

    def __init__(self, tmp: Path, bed, src: Path) -> None:
        self.work = the_git_bed.a_served_tree(bed, src, tmp / "origin-work")
        _git("config", "user.name", "someone", cwd=self.work)
        _git("config", "user.email", "someone@example.invalid", cwd=self.work)
        self.bare = tmp / "origin.git"
        _git("clone", "-q", "--bare", str(self.work), str(self.bare), cwd=tmp)
        _git("remote", "add", "origin", str(self.bare), cwd=self.work)
        self.url = str(self.bare)

    def advance(self, text: str = "x = 2\n") -> str:
        """Move `main` on the origin by one commit, and answer the new tip."""
        (self.work / "app.py").write_text(text)
        _git("commit", "-qam", "advance", cwd=self.work)
        _git("push", "-q", "origin", "main", cwd=self.work)
        return self.tip()

    def push_branch(self, branch: str) -> str:
        """Push a branch of one commit off `main` to the origin, and answer its tip."""
        _git("checkout", "-qb", branch, cwd=self.work)
        (self.work / "review.py").write_text("reviewed = True\n")
        _git("add", "-A", cwd=self.work)
        _git("commit", "-qm", "to review", cwd=self.work)
        _git("push", "-q", "origin", branch, cwd=self.work)
        tip = _head(self.work)
        _git("checkout", "-q", "main", cwd=self.work)
        return tip

    def tip(self, ref: str = "main") -> str:
        return _git("rev-parse", ref, cwd=self.bare).strip()


@pytest.fixture(scope="session")
def first_commit(tmp_path_factory) -> Path:
    """The files of the first commit, one directory for the session, so the bed builds it once."""
    src = tmp_path_factory.mktemp("issue-91-first-commit")
    (src / "app.py").write_text("x = 1\n")
    return src


@pytest.fixture
def origin(tmp_path, git_bed, first_commit) -> Origin:
    return Origin(tmp_path, git_bed, first_commit)


def _job(tmp_path: Path, served: Path, origin: Origin):
    """The box's own `prepare` over the served checkout, as for a project registered by clone URL:
    the job's remote is the forge, here the bare origin."""
    box = WorktreeSandbox(root=tmp_path / "jobs")
    ws = box.prepare(repo_path=served, base_branch="main", branch=BRANCH, remote_url=origin.url)
    return box, ws


def _review(tmp_path: Path, served: Path, origin: Origin):
    box = WorktreeSandbox(root=tmp_path / "reviews")
    ws = box.prepare_tip(repo_path=served, base_branch="main", branch=REVIEWED,
                         remote_url=origin.url)
    return box, ws


def _pushes(box: WorktreeSandbox, ws, origin: Origin) -> None:
    """The job commits and the box pushes; the commit must be the branch on the bare origin."""
    (ws.path / "feature.py").write_text("done = True\n")
    _git("add", "-A", cwd=ws.path)
    _git("-c", "user.name=someone", "-c", "user.email=someone@example.invalid",
         "commit", "-qm", "the job's work", cwd=ws.path)
    work = _head(ws.path)
    try:
        box.publish_branch(workspace=ws, remote_url=origin.url)
    except RuntimeError as exc:
        pytest.fail(f"the job's finished work was not pushed: {exc}")
    assert origin.tip(BRANCH) == work


class _Interleave:
    """Runs `act` on another thread from inside `_publish`'s copy of the master, before the real
    copy, and lets the copy go on once that thread asked for the key's lock (or ended)."""

    def __init__(self, monkeypatch, cache: RepoCache, act) -> None:
        self.master = cache.root / repo_cache._MASTERS_DIRNAME / "p"
        self.lock_path = repo_cache._key_lock(cache.root, "p").path
        self.reached = threading.Event()
        self.result: list = []
        self.errors: list[BaseException] = []
        self.thread: threading.Thread | None = None
        self._act = act
        real_copy = shutil.copytree
        real_acquire = FileLock.acquire

        def acquire(lock, *, timeout):
            if lock.path == self.lock_path and threading.current_thread() is self.thread:
                self.reached.set()
            return real_acquire(lock, timeout=timeout)

        def copy(src, dst, *a, **kw):
            if Path(src) == self.master and self.thread is None:
                self.thread = threading.Thread(target=self._run, name="the-job", daemon=True)
                self.thread.start()
                assert self.reached.wait(HANG), "the job neither asked for the lock nor ended"
            return real_copy(src, dst, *a, **kw)

        monkeypatch.setattr(FileLock, "acquire", acquire)
        monkeypatch.setattr(repo_cache.shutil, "copytree", copy)

    def _run(self) -> None:
        try:
            self.result.append(self._act())
        except BaseException as exc:  # handed to the test thread by `done`
            self.errors.append(exc)
        finally:
            self.reached.set()       # the code without the lock never asks for it

    def done(self):
        assert self.thread is not None, "the sync never staged a snapshot"
        self.thread.join(HANG)
        assert not self.thread.is_alive(), "the job never got the key's lock"
        if self.errors:
            raise self.errors[0]
        return self.result[0]


def test_a_worktree_added_just_before_the_rename_keeps_its_git_and_its_push(
        tmp_path, origin, monkeypatch, caplog):
    """The narrow check. The job's add and mark land after the copy, just before the served tree is
    renamed into the trash, on the sync's own thread (which the re-entrant lock lets through).
    Before the fix the rename took the job's admin directory with it: `rev-parse` exited 128."""
    cache = RepoCache(root=tmp_path / "cache")
    served = cache.sync("p", origin.url, "main")
    assert served is not None
    before = _head(served)
    origin.advance()
    master = cache.root / repo_cache._MASTERS_DIRNAME / "p"
    real_copy = shutil.copytree
    jobs: list = []

    def copy_then_add(src, dst, *a, **kw):
        copied = real_copy(src, dst, *a, **kw)
        if Path(src) == master and not jobs:
            jobs.append(_job(tmp_path, served, origin))
        return copied

    monkeypatch.setattr(repo_cache.shutil, "copytree", copy_then_add)
    with caplog.at_level(logging.INFO, logger="beeverforge.repo_cache"):
        assert cache.sync("p", origin.url, "main") == served
    monkeypatch.undo()

    assert jobs, "the sync never staged a snapshot"
    box, ws = jobs[0]
    rc, said = _git_dir(ws.path)
    assert rc == 0, f"the job's worktree lost its git directory to the swap: {said.strip()}"
    assert _head(served) == before, "the served tree was swapped while a job stood on it"
    assert cache.held is True
    assert list((cache.root / repo_cache._STAGING_DIRNAME).iterdir()) == []
    held = [r.getMessage() for r in caplog.records if "BEEVERFORGE_CACHE_HELD" in r.getMessage()]
    assert len(held) == 1, f"a held sync must say so exactly once: {held}"
    _pushes(box, ws, origin)


def test_a_worktree_added_while_the_snapshot_is_staged_keeps_its_git_and_its_push(
        tmp_path, origin, monkeypatch):
    """The lock. The job's `prepare` starts on another thread while `_publish` is about to copy the
    master. It waits for the key's lock, the publish ends, and the worktree is added to the NEW
    served tree. Before the fix the add and mark landed in the tree about to be replaced."""
    cache = RepoCache(root=tmp_path / "cache")
    served = cache.sync("p", origin.url, "main")
    assert served is not None
    tip = origin.advance()
    interleave = _Interleave(monkeypatch, cache, lambda: _job(tmp_path, served, origin))

    assert cache.sync("p", origin.url, "main") == served
    box, ws = interleave.done()
    monkeypatch.undo()

    rc, said = _git_dir(ws.path)
    assert rc == 0, f"the job's worktree lost its git directory to the swap: {said.strip()}"
    assert _head(served) == tip, "the job's add did not wait for the publish it raced"
    assert cache.held is False
    _pushes(box, ws, origin)


def test_a_review_tree_added_while_the_snapshot_is_staged_keeps_its_git(
        tmp_path, origin, monkeypatch):
    """The sibling door: `prepare_tip` adds a detached review tree to the served checkout, and
    takes the same lock around its fetch, add and mark."""
    cache = RepoCache(root=tmp_path / "cache")
    served = cache.sync("p", origin.url, "main")
    assert served is not None
    reviewed = origin.push_branch(REVIEWED)
    tip = origin.advance()
    interleave = _Interleave(monkeypatch, cache, lambda: _review(tmp_path, served, origin))

    assert cache.sync("p", origin.url, "main") == served
    _, ws = interleave.done()
    monkeypatch.undo()

    rc, said = _git_dir(ws.path)
    assert rc == 0, f"the review tree lost its git directory to the swap: {said.strip()}"
    assert _head(ws.path) == reviewed
    assert _head(served) == tip, "the review's add did not wait for the publish it raced"


def test_a_repository_registered_by_path_takes_no_cache_lock(
        tmp_path, monkeypatch, git_bed, first_commit):
    """A repository that is not a cache checkout has no key lock beside it: `prepare` behaves as
    before, asks for no lock and leaves no `.locks` directory next to the person's repository."""
    repo = the_git_bed.a_served_tree(git_bed, first_commit, tmp_path / "projects" / "mine")
    asked: list[str] = []
    real_acquire = FileLock.acquire

    def acquire(lock, *, timeout):
        asked.append(lock.path)
        return real_acquire(lock, timeout=timeout)

    monkeypatch.setattr(FileLock, "acquire", acquire)
    ws = WorktreeSandbox(root=tmp_path / "jobs").prepare(
        repo_path=repo, base_branch="main", branch=BRANCH)

    assert _git_dir(ws.path)[0] == 0
    assert asked == [], f"a repository registered by path asked for {asked}"
    assert not (repo.parent / repo_cache._LOCKS_DIRNAME).exists()


def test_a_lock_that_cannot_be_checked_refuses_the_add_rather_than_run_it_unlocked(
        tmp_path, origin, monkeypatch):
    """Absent is not unreadable (review of #456): a served checkout whose key lock this process
    cannot stat — a `.locks` it may not search, on a volume the panel and the worker share — is
    refused by name, with the lock's path and the permission to give, and nothing is added. It is
    never taken for a repository registered by path and added unlocked."""
    cache = RepoCache(root=tmp_path / "cache")
    served = cache.sync("p", origin.url, "main")
    assert served is not None
    lock_path = str(repo_cache._key_lock(served.parent, served.name).path)
    assert os.path.isfile(lock_path), "the setup is a served checkout with its key lock"
    real_stat = os.stat

    def stat(path, *args, **kwargs):
        if os.fspath(path) == lock_path:
            raise PermissionError(13, "Permission denied", lock_path)
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(worktree.os, "stat", stat)
    with pytest.raises(RuntimeError) as refused:
        WorktreeSandbox(root=tmp_path / "jobs").prepare(
            repo_path=served, base_branch="main", branch=BRANCH)
    said = str(refused.value)
    assert lock_path in said and "permission" in said.lower(), said
    assert not (served / ".git" / "worktrees").exists() or not any(
        (served / ".git" / "worktrees").iterdir()), "a worktree was added unlocked"


def test_a_cache_key_held_past_the_wait_refuses_the_add_and_says_why(
        tmp_path, origin, monkeypatch):
    """No deadlock and no silent unlocked add: a key lock somebody else holds past the wait refuses
    the job by name, with the cause (a sync of that key holds it) and the remedy (retry once it
    ends, or look for a hung sync), and nothing is added to the served tree."""
    cache = RepoCache(root=tmp_path / "cache")
    served = cache.sync("p", origin.url, "main")
    assert served is not None
    lock = repo_cache._key_lock(cache.root, "p")
    holding, letgo = threading.Event(), threading.Event()

    def hold() -> None:
        with lock.held(timeout=0):
            holding.set()
            letgo.wait(HANG)

    holder = threading.Thread(target=hold, name="a-sync", daemon=True)
    holder.start()
    try:
        assert holding.wait(HANG), "the helper never took the key's lock"
        monkeypatch.setattr(worktree, "_CACHE_LOCK_WAIT_SECONDS", 0)
        with pytest.raises(RuntimeError) as refused:
            _job(tmp_path, served, origin)
    finally:
        letgo.set()
        holder.join(HANG)
    said = str(refused.value)
    assert str(served) in said and lock.path in said, said
    assert "cache sync" in said and "Retry" in said and "hung" in said, said
    listed = _git("worktree", "list", "--porcelain", cwd=served)
    assert str((tmp_path / "jobs").resolve()) not in listed, listed
