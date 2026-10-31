"""A symbolic link or a regular file at the box's path is refused by name even when the
working-tree list cannot be read (#124); only the checks that need the list wait for it.

THE DEFECT. `prepare` asked `_what_is_at` only when the list was read, so with `_working_trees`
answering `None` the symlink and file checks were skipped too. A symlink to an EMPTY directory
was then accepted by git (rc 0) and the card was checked out through the link: the directory a
person owns held `.git` and `README.md` (git 2.50.1, by hand). A file at the path got git's
`worktree add failed: ... already exists` after `branch -D` had run. Neither check depends on the
list: what is AT the path is a link or a file whatever the list says.

A DIRECTORY STILL GOES TO GIT on an unread list (the reverse guard below): whether it is this
repository's own tree is what the list decides, and unread, git judges as before.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from beeverforge.adapters.sandbox import worktree as worktree_box
from beeverforge.adapters.sandbox.base import BranchHeldElsewhere
from beeverforge.adapters.sandbox.worktree import WorktreeSandbox, path_taken

BRANCH = "beeverforge/28"
DOORS = ["fresh", "local-keep", "hosted-resume"]


def _git(cwd: Path, *args: str) -> str:
    p = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, f"git {' '.join(args)}: {p.stderr}"
    return p.stdout.strip()


def _commit(repo: Path, name: str, text: str, message: str) -> None:
    (repo / name).write_text(text)
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgSign=false",
         "commit", "-q", "-m", message)


def _sha(repo: Path, ref: str) -> str:
    p = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", ref],
                       capture_output=True, text=True)
    return p.stdout.strip()


def _repository(where: Path) -> Path:
    """`main`, and the card's branch carrying the job's committed work."""
    subprocess.run(["git", "init", "-q", "-b", "main", str(where)], capture_output=True, check=True)
    _commit(where, "README.md", "# app\n", "base")
    _git(where, "switch", "-q", "-c", BRANCH)
    _commit(where, "work.py", "WORK = True\n", "the job's work")
    _git(where, "switch", "-q", "main")
    return where


class Door:
    """One way into `prepare`: the repository the box is handed, and the call."""

    def __init__(self, name: str, repo: Path, remote: str | None, box: WorktreeSandbox):
        self.name, self.repo, self.remote, self.box = name, repo, remote, box

    def prepare(self):
        if self.name == "fresh":
            return self.box.prepare(repo_path=self.repo, base_branch="main", branch=BRANCH)
        return self.box.prepare(repo_path=self.repo, base_branch="main", branch=BRANCH,
                                checkout_existing=True, remote_url=self.remote)


def _door(name: str, tmp_path: Path, root: Path) -> Door:
    box = WorktreeSandbox(root=root)
    if name == "fresh":
        return Door(name, _repository(tmp_path / "myapp"), None, box)
    if name == "local-keep":
        repo = _repository(tmp_path / "myapp")
        return Door(name, repo, str(repo), box)
    # a hosted forge: a bare origin holds the card's branch, the clone's tracking ref is behind it
    origin = tmp_path / "forge.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)],
                   capture_output=True, check=True)
    seed = _repository(tmp_path / "seed")
    _git(seed, "push", "-q", str(origin), "main", BRANCH)
    clone = tmp_path / "myapp"
    subprocess.run(["git", "clone", "-q", str(origin), str(clone)], capture_output=True,
                   check=True)
    _git(seed, "switch", "-q", BRANCH)
    _commit(seed, "work.py", "WORK = 2\n", "the factory's second pass")
    _git(seed, "push", "-q", str(origin), BRANCH)
    return Door(name, clone, f"file://{origin}", box)


@pytest.fixture(params=["boxes", "my boxes"], ids=["plain-root", "root-with-a-space"])
def root(tmp_path, request):
    return tmp_path / request.param


@pytest.fixture
def unread(monkeypatch):
    """The working-tree list cannot be read."""
    monkeypatch.setattr(worktree_box, "_working_trees", lambda repo_path: None)


def _refs(door: Door) -> tuple[str, str]:
    return _sha(door.repo, BRANCH), _sha(door.repo, f"refs/remotes/origin/{BRANCH}")


@pytest.mark.parametrize("door_name", DOORS)
def test_a_symbolic_link_at_the_box_s_path_is_refused_when_the_list_cannot_be_read(
        tmp_path, root, unread, door_name):
    """The criterion. Red before the fix: git accepted the add (rc 0) and wrote the card's tree
    into the empty directory the link names."""
    door = _door(door_name, tmp_path, root)
    wt = root / BRANCH.replace("/", "-")
    wt.parent.mkdir(parents=True, exist_ok=True)
    target = tmp_path / "their empty directory"
    target.mkdir()
    os.symlink(target, wt)
    refs = _refs(door)

    with pytest.raises(RuntimeError) as raised:
        door.prepare()

    assert not isinstance(raised.value, BranchHeldElsewhere)
    assert str(raised.value) == path_taken(BRANCH, str(worktree_box._where(wt)),
                                           repo=str(door.repo), what="symlink")
    assert os.listdir(target) == []
    assert wt.is_symlink() and os.readlink(wt) == str(target)
    assert _refs(door) == refs


def test_a_regular_file_at_the_box_s_path_is_refused_when_the_list_cannot_be_read(
        tmp_path, root, unread):
    """Red before the fix: git's `worktree add failed: ... already exists`, after `branch -D`."""
    door = _door("fresh", tmp_path, root)
    wt = root / BRANCH.replace("/", "-")
    wt.parent.mkdir(parents=True, exist_ok=True)
    wt.write_bytes(b"a file, where the box would put a directory\n")
    refs = _refs(door)

    with pytest.raises(RuntimeError) as raised:
        door.prepare()

    assert str(raised.value) == path_taken(BRANCH, str(worktree_box._where(wt)),
                                           repo=str(door.repo), what="file")
    assert wt.read_bytes() == b"a file, where the box would put a directory\n"
    assert _refs(door) == refs


def test_a_directory_at_the_box_s_path_still_goes_to_git_when_the_list_cannot_be_read(
        tmp_path, root, unread):
    """REVERSE GUARD: green before the fix, and it stays green. Unread, the list cannot say
    whether a directory is this repository's own tree, so git judges it as before."""
    door = _door("fresh", tmp_path, root)
    wt = root / BRANCH.replace("/", "-")
    wt.mkdir(parents=True)
    (wt / "notes.txt").write_text("a person's notes\n")

    with pytest.raises(RuntimeError) as raised:
        door.prepare()

    assert "worktree add failed" in str(raised.value)
    assert "a directory that is not a working tree" not in str(raised.value)
    assert sorted(os.listdir(wt)) == ["notes.txt"]
    assert (wt / "notes.txt").read_text() == "a person's notes\n"
