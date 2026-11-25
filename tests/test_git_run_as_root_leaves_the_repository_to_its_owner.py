"""What only real ownership can show: a platform run as root leaves a repository of another user's
with nothing of root's in it, and its owner can go on working there.

Every call the change touches is made for real, as root, on a repository chowned to a user that is
not root, with the machine's own `setpriv`. The calls are the ones
`test_git_runs_as_the_repositorys_owner.py` makes through injected ownership; here the setup they
do in the repository runs as the owner, as a person's would.

These need root, and are skipped with a reason otherwise. They start no container.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from tests import test_git_runs_as_the_repositorys_owner as made
from tests import the_git_bed

pytestmark = pytest.mark.skipif(
    os.geteuid() != 0, reason="needs root: only root can give a repository to another user")

git_bed = the_git_bed.git_bed

#: A user with no entry in any passwd file: the platform must need none.
UID, GID = 4242, 4343
CARD, JOB = made.CARD, made.JOB


def _as_the_owner(*argv, cwd="/", check: bool = True) -> subprocess.CompletedProcess:
    done = subprocess.run(
        list(argv), user=UID, group=GID, extra_groups=[], cwd=str(cwd), capture_output=True,
        text=True, check=False, env={"PATH": os.environ["PATH"], "HOME": "/nonexistent",
                                     "GIT_CONFIG_NOSYSTEM": "1", "LC_ALL": "C.UTF-8"})
    if check:
        assert done.returncode == 0, f"the owner's {argv}: {done.stdout}{done.stderr}"
    return done


def _owners_git(where, *args) -> str:
    return _as_the_owner("git", "-c", "core.hooksPath=/dev/null", "-c", "user.name=someone",
                         "-c", "user.email=someone@example.invalid", "-C", str(where), *args,
                         ).stdout.strip()


def _give(where: Path) -> None:
    for path in (where, *where.rglob("*")):
        os.chown(path, UID, GID, follow_symlinks=False)


def _roots(where: Path) -> list[str]:
    return sorted(str(p.relative_to(where)) for p in (where, *where.rglob("*"))
                  if p.lstat().st_uid == 0)


@pytest.fixture
def open_root():
    """A directory anybody may enter: pytest's own is the runner's alone."""
    root = Path(tempfile.mkdtemp(prefix="beeverforge-owned-"))
    root.chmod(0o755)
    yield root
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
def scene(monkeypatch, git_bed, open_root):
    """The other file's scene, its repositories the owner's, and what a call does there as setup
    done by the owner."""
    root = open_root
    tmp = root / "tmp"
    tmp.mkdir()
    tmp.chmod(0o755)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp))
    monkeypatch.setenv("BEEVERFORGE_BOARD_DB", str(root / "board.db"))
    monkeypatch.setenv("WORKER_SECRET", "planted")
    scene = made.Scene(root, git_bed)
    plain_ok, plain_commit = made._ok, made._commit

    def owned(where) -> bool:
        return any(Path(where).is_relative_to(d) for d in scene.owned)

    def ok(where, *args):
        return _owners_git(where, *args) if owned(where) else plain_ok(where, *args)

    def commit(where, name, text):
        if not owned(where):
            return plain_commit(where, name, text)
        _as_the_owner("sh", "-c", 'printf %s "$1" > "$2"', "sh", text, name, cwd=where)
        ok(where, "add", "-A")
        ok(where, "commit", "-qm", name)
        return ok(where, "rev-parse", "HEAD")

    monkeypatch.setattr(made, "_ok", ok)
    monkeypatch.setattr(made, "_commit", commit)
    monkeypatch.setattr(made.Scene, "the_job_commits", _a_workspace_of_the_jobs)
    _give(scene.repo)
    _give(scene.bare)
    return scene


def _a_workspace_of_the_jobs(scene, branch: str = JOB) -> str:
    """The job's clone, root's, made from root's own copy of the same commits."""
    subprocess.run(["git", "clone", "-q", "--no-local", str(scene.cache), str(scene.ws)],
                   check=True, capture_output=True)
    made._ok(scene.ws, "checkout", "-q", "-B", branch)
    return made._commit(scene.ws, "job.py", "JOB = True\n")


@made.every_call
def test_nothing_in_the_repository_is_roots_after_a_call(scene, call):
    call(scene)

    assert _roots(scene.repo) == [] and _roots(scene.bare) == []
    assert [p.name for p in (scene.root / "tmp").iterdir()] == []


def test_the_owner_goes_on_working_after_a_push_and_a_merge(scene):
    made._the_jobs_push(scene)
    made._the_merge(scene)
    repo = scene.repo

    _as_the_owner("sh", "-c", "echo edited >> work.py", cwd=repo)
    _owners_git(repo, "commit", "-qam", "the owner's edit of a merged file")
    _owners_git(repo, "branch", "-D", JOB)
    _owners_git(repo, "branch", "beeverforge/10")
    for n in range(40):
        _owners_git(repo, "commit", "-q", "--allow-empty", "-m", f"the owner's {n}")
    _owners_git(repo, "gc", "-q")

    assert _roots(repo) == []


@pytest.mark.parametrize("call", [made._the_jobs_push, made._the_merge,
                                  made._the_merge_with_the_base_not_out],
                         ids=lambda f: f.__name__.strip("_"))
def test_a_hook_runs_as_the_owner(scene, call):
    seen = scene.root / "hook.log"
    seen.touch()
    os.chown(seen, UID, GID)
    hooks = scene.repo / ".git" / "hooks"
    hooks.mkdir(exist_ok=True)
    for name in ("reference-transaction", "pre-receive", "post-merge"):
        (hooks / name).write_text(f"#!/bin/sh\n{{ echo who $(id -u) $(id -g) $(id -G); env; }} "
                                  f">> '{seen}'\n")
        (hooks / name).chmod(0o755)
    _give(hooks)

    call(scene)

    lines = seen.read_text().splitlines()
    assert {line for line in lines if line.startswith("who ")} == {f"who {UID} {GID} {GID}"}
    assert not [line for line in lines if line.startswith("WORKER_SECRET")]


@pytest.mark.parametrize("place", [made._the_boxs_clone, made._the_jobs_push,
                                   made._the_caches_clone, made._list_branches],
                         ids=lambda f: f.__name__.strip("_"))
@pytest.mark.parametrize("cause", ["two owners", "a closed parent", "no setpriv"])
def test_each_refusal_comes_before_anything_is_written(scene, monkeypatch, caplog, place, cause):
    from beeverforge import gitowner

    if cause == "two owners":
        os.chown(scene.repo / ".git", 0, 0)
        reason, remedy = f"two owners: work tree uid {UID}, git directory uid 0", "chown -R"
    elif cause == "a closed parent":
        shut = scene.root / "shut"
        shut.mkdir(mode=0o700)
        scene.repo = scene.repo.rename(shut / "myapp")
        reason, remedy = f"uid {UID}, cannot enter {shut}", f"chmod o+x {shut}"
    else:
        monkeypatch.setattr(gitowner, "_setpriv", lambda: None)
        reason, remedy = "`setpriv` is missing", "util-linux"
    before = made._tree(scene.repo)

    if (cause, place) == ("no setpriv", made._list_branches):
        place(scene)  # started by Python, which needs none
        return
    with pytest.raises((RuntimeError, AssertionError)) as refused:
        place(scene)

    said = f"{refused.value}{caplog.text}"
    assert reason in said and remedy in said, said
    assert made._tree(scene.repo) == before


def test_a_directory_is_tried_as_the_user_itself(scene):
    """Root may enter any directory, so an attempt made as root would answer yes to both."""
    from beeverforge import gitowner

    shut = scene.root / "shut"
    shut.mkdir(mode=0o700)
    assert gitowner._can_enter(gitowner.Owner(UID, GID), shut) is False
    shut.chmod(0o701)
    assert gitowner._tried_and_entered(gitowner.Owner(UID, GID), shut) is True
