"""#317: `_worktree_at` reused a fixed path and never looked at what was there.

The measurement checkout of a ref lives at `default_root()/"worktrees"/<key>`. When that path was
a symbolic link, `dest.exists()` followed it, `git worktree remove --force <link>` removed the tree
the link named, and `git worktree add --detach <link>` then checked out THROUGH it into somebody
else's directory. The same block ran a blanket `git worktree prune`, which drops every other
registration whose directory is momentarily missing — other people's worktrees included.

What must be true: a symbolic link or a file at the path is refused in one sentence naming the path
and what is there, before git is asked to remove, prune or add anything, and the link's target is
untouched; `_worktree_at` never runs `git worktree prune`; a directory at the path is replaced by
the ref's tree as before.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from beeverforge import factory

_KEY = "acme@feat"


def _run(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def _repository(tmp_path: Path) -> Path:
    """A repository on `main`, and `feat` carrying `only-on-feat.txt` that `main` does not have."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["init", "-q", "."], repo)
    _run(["config", "user.email", "t@t"], repo)
    _run(["config", "user.name", "t"], repo)
    (repo / "README").write_text("main\n")
    _run(["add", "-A"], repo)
    _run(["commit", "-qm", "main"], repo)
    _run(["branch", "-M", "main"], repo)
    _run(["checkout", "-q", "-b", "feat"], repo)
    (repo / "only-on-feat.txt").write_text("feat\n")
    _run(["add", "-A"], repo)
    _run(["commit", "-qm", "feat"], repo)
    _run(["checkout", "-q", "main"], repo)
    return repo


def _here(tmp_path: Path, monkeypatch) -> Path:
    """The cache under the test's directory, and the path `_worktree_at` will use for `_KEY`."""
    cache = tmp_path / "cache"
    monkeypatch.setenv("BEEVERFORGE_REPO_CACHE", str(cache))
    from beeverforge.runtime.repo_cache import default_root

    dest = default_root() / "worktrees" / _KEY
    dest.parent.mkdir(parents=True, exist_ok=True)
    return dest


def _spy(monkeypatch) -> list[list[str]]:
    """Every git call `_worktree_at` makes, written down, then run for real."""
    from beeverforge.runtime import repo_cache

    calls: list[list[str]] = []
    real = repo_cache._git

    def recording(args, *a, **kw):
        calls.append(list(args))
        return real(args, *a, **kw)

    monkeypatch.setattr(repo_cache, "_git", recording)
    return calls


def _worktree_calls(calls: list[list[str]]) -> list[list[str]]:
    return [c for c in calls if "worktree" in c]


def test_a_symlink_at_the_checkout_path_is_refused_and_its_target_untouched(tmp_path,
                                                                            monkeypatch):
    repo = _repository(tmp_path)
    dest = _here(tmp_path, monkeypatch)
    target = tmp_path / "somebody-elses"
    target.mkdir()
    (target / "keep.txt").write_text("theirs")
    dest.symlink_to(target)
    calls = _spy(monkeypatch)

    with pytest.raises(RuntimeError) as refused:
        factory._worktree_at(repo, "feat", _KEY)

    said = str(refused.value)
    assert str(dest) in said and "symbolic link" in said, said
    assert "Nothing was changed" in said, said
    assert _worktree_calls(calls) == [], f"git was asked to change worktrees: {calls}"
    assert sorted(p.name for p in target.iterdir()) == ["keep.txt"]
    assert (target / "keep.txt").read_text() == "theirs"
    assert dest.is_symlink()


def test_a_symlink_to_an_empty_directory_is_not_checked_out_through(tmp_path, monkeypatch):
    """The git 2.53.0 case: `worktree add` through a link to an empty directory returned 0 and
    left `.git` in the target."""
    repo = _repository(tmp_path)
    dest = _here(tmp_path, monkeypatch)
    target = tmp_path / "empty"
    target.mkdir()
    dest.symlink_to(target)
    calls = _spy(monkeypatch)

    with pytest.raises(RuntimeError, match="symbolic link"):
        factory._worktree_at(repo, "feat", _KEY)

    assert list(target.iterdir()) == []
    assert _worktree_calls(calls) == []


def test_a_dangling_symlink_is_refused_and_left_as_it_is(tmp_path, monkeypatch):
    repo = _repository(tmp_path)
    dest = _here(tmp_path, monkeypatch)
    gone = tmp_path / "gone"
    dest.symlink_to(gone)
    calls = _spy(monkeypatch)

    with pytest.raises(RuntimeError, match="symbolic link"):
        factory._worktree_at(repo, "feat", _KEY)

    assert dest.is_symlink() and Path(dest.readlink()) == gone
    assert not gone.exists()
    assert _worktree_calls(calls) == []


def test_a_file_at_the_checkout_path_is_refused(tmp_path, monkeypatch):
    repo = _repository(tmp_path)
    dest = _here(tmp_path, monkeypatch)
    dest.write_text("a person's notes")
    calls = _spy(monkeypatch)

    with pytest.raises(RuntimeError) as refused:
        factory._worktree_at(repo, "feat", _KEY)

    said = str(refused.value)
    assert str(dest) in said and "a file" in said and "symbolic link" not in said, said
    assert "Nothing was changed" in said, said
    assert dest.read_text() == "a person's notes"
    assert _worktree_calls(calls) == []


def test_measuring_never_runs_git_worktree_prune(tmp_path, monkeypatch):
    repo = _repository(tmp_path)
    _here(tmp_path, monkeypatch)
    calls = _spy(monkeypatch)

    factory._worktree_at(repo, "feat", _KEY)
    factory._worktree_at(repo, "feat", _KEY)

    assert [c for c in calls if "prune" in c] == []


def test_measuring_leaves_another_persons_missing_worktree_listed(tmp_path, monkeypatch):
    """A blanket prune drops every registration whose directory is momentarily away — a worktree
    on an unmounted disk, another proof's tree mid-swap. Those are not this function's to drop."""
    repo = _repository(tmp_path)
    _here(tmp_path, monkeypatch)
    theirs = tmp_path / "theirs"
    assert _run(["worktree", "add", "--detach", str(theirs), "main"], repo).returncode == 0
    shutil.rmtree(theirs)

    factory._worktree_at(repo, "feat", _KEY)

    listed = _run(["worktree", "list", "--porcelain"], repo).stdout
    assert f"worktree {theirs}" in listed, listed


def test_a_registered_checkout_whose_directory_is_gone_is_checked_out_again(tmp_path,
                                                                           monkeypatch):
    """The cache wiped by hand leaves git's registration behind; `add` refuses a path it still
    believes in, so this path's own registration is cleared — and only that one."""
    repo = _repository(tmp_path)
    dest = _here(tmp_path, monkeypatch)
    factory._worktree_at(repo, "feat", _KEY)
    shutil.rmtree(dest)

    assert factory._worktree_at(repo, "feat", _KEY) == dest
    assert (dest / "only-on-feat.txt").read_text() == "feat\n"


def test_a_leftover_checkout_directory_is_replaced_by_the_ref(tmp_path, monkeypatch):
    repo = _repository(tmp_path)
    dest = _here(tmp_path, monkeypatch)
    factory._worktree_at(repo, "feat", _KEY)
    (dest / "sentinel").write_text("left over")

    assert factory._worktree_at(repo, "feat", _KEY) == dest
    assert not (dest / "sentinel").exists()
    assert (dest / "only-on-feat.txt").read_text() == "feat\n"
