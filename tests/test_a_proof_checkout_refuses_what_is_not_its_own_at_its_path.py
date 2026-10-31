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


# THE WINDOW (#317 review, the shape #124 / PR #312 settled). The guard reads the path once; git
# creates it only at the `add`. Whatever appears in between must be refused by name, not written
# through. The last git call before the add is this path's own `worktree remove`, so the spy plants
# there, right after it ran — the latest point a test can reach before the function makes the path.


def _plant_after_the_remove(monkeypatch, plant) -> list[list[str]]:
    from beeverforge.runtime import repo_cache

    calls: list[list[str]] = []
    real = repo_cache._git

    def planting(args, *a, **kw):
        calls.append(list(args))
        result = real(args, *a, **kw)
        if "worktree" in args and "remove" in args:
            plant()
        return result

    monkeypatch.setattr(repo_cache, "_git", planting)
    return calls


def _adds(calls: list[list[str]]) -> list[list[str]]:
    return [c for c in calls if "worktree" in c and "add" in c]


@pytest.mark.parametrize("leftover", [False, True], ids=["fresh", "leftover-checkout"])
def test_a_symlink_planted_after_the_check_is_refused_not_written_through(tmp_path, monkeypatch,
                                                                          leftover):
    repo = _repository(tmp_path)
    dest = _here(tmp_path, monkeypatch)
    if leftover:
        factory._worktree_at(repo, "feat", _KEY)
    target = tmp_path / "empty"
    target.mkdir()
    calls = _plant_after_the_remove(monkeypatch, lambda: dest.symlink_to(target))

    with pytest.raises(RuntimeError) as refused:
        factory._worktree_at(repo, "feat", _KEY)

    said = str(refused.value)
    assert str(dest) in said and "symbolic link" in said, said
    assert list(target.iterdir()) == [], "git checked out through the link"
    assert _adds(calls) == [], f"git was asked to add: {calls}"
    assert dest.is_symlink() and Path(dest.readlink()) == target


def test_a_file_planted_after_the_check_is_refused_by_name(tmp_path, monkeypatch):
    repo = _repository(tmp_path)
    dest = _here(tmp_path, monkeypatch)
    calls = _plant_after_the_remove(monkeypatch, lambda: dest.write_text("a person's notes"))

    with pytest.raises(RuntimeError) as refused:
        factory._worktree_at(repo, "feat", _KEY)

    said = str(refused.value)
    assert str(dest) in said and "a file" in said and "symbolic link" not in said, said
    assert dest.read_text() == "a person's notes"
    assert _adds(calls) == []


def test_a_path_that_cannot_be_made_is_refused_in_one_sentence(tmp_path, monkeypatch):
    repo = _repository(tmp_path)
    dest = _here(tmp_path, monkeypatch)
    real_mkdir = factory.os.mkdir

    def refusing(path, *a, **kw):
        if Path(path) == dest:
            raise PermissionError(13, "Permission denied", str(path))
        return real_mkdir(path, *a, **kw)

    monkeypatch.setattr(factory.os, "mkdir", refusing)
    calls = _spy(monkeypatch)

    with pytest.raises(RuntimeError) as refused:
        factory._worktree_at(repo, "feat", _KEY)

    said = str(refused.value)
    assert str(dest) in said and "Permission denied" in said and "run again" in said, said
    assert _adds(calls) == []


def _failing_add(monkeypatch, before=lambda: None) -> None:
    from beeverforge.runtime import repo_cache

    real = repo_cache._git

    def failing(args, *a, **kw):
        if "worktree" in args and "add" in args:
            before()
            return 128, "fatal: simulated"
        return real(args, *a, **kw)

    monkeypatch.setattr(repo_cache, "_git", failing)


def test_a_failed_add_removes_only_the_empty_directory_it_made(tmp_path, monkeypatch):
    repo = _repository(tmp_path)
    dest = _here(tmp_path, monkeypatch)
    seen: list[bool] = []
    _failing_add(monkeypatch, lambda: seen.append(dest.is_dir() and not dest.is_symlink()))

    with pytest.raises(RuntimeError, match="could not check"):
        factory._worktree_at(repo, "feat", _KEY)

    assert seen == [True], "the path was not made before the add"
    assert not dest.exists() and not dest.is_symlink()


def test_a_failed_add_leaves_what_is_inside_the_directory(tmp_path, monkeypatch):
    repo = _repository(tmp_path)
    dest = _here(tmp_path, monkeypatch)
    _failing_add(monkeypatch, lambda: (dest / "theirs.txt").write_text("keep"))

    with pytest.raises(RuntimeError, match="could not check"):
        factory._worktree_at(repo, "feat", _KEY)

    assert (dest / "theirs.txt").read_text() == "keep"


def test_a_failed_add_leaves_a_link_now_at_the_path_alone(tmp_path, monkeypatch):
    repo = _repository(tmp_path)
    dest = _here(tmp_path, monkeypatch)
    target = tmp_path / "somebody-elses"
    target.mkdir()
    (target / "keep.txt").write_text("theirs")

    def swap():
        dest.rmdir()
        dest.symlink_to(target)

    _failing_add(monkeypatch, swap)

    with pytest.raises(RuntimeError, match="could not check"):
        factory._worktree_at(repo, "feat", _KEY)

    assert dest.is_symlink() and Path(dest.readlink()) == target
    assert (target / "keep.txt").read_text() == "theirs"


def test_a_leftover_directory_that_cannot_be_removed_is_refused_by_name(tmp_path, monkeypatch):
    """`rmtree(..., ignore_errors=True)` says nothing when it fails; what is still there is looked
    at before anything else runs."""
    repo = _repository(tmp_path)
    dest = _here(tmp_path, monkeypatch)
    dest.mkdir()
    (dest / "theirs.txt").write_text("keep")
    monkeypatch.setattr(factory.shutil, "rmtree", lambda *a, **kw: None)
    calls = _spy(monkeypatch)

    with pytest.raises(RuntimeError) as refused:
        factory._worktree_at(repo, "feat", _KEY)

    said = str(refused.value)
    assert str(dest) in said and "could not be removed" in said and "a directory" in said, said
    assert (dest / "theirs.txt").read_text() == "keep"
    assert _adds(calls) == []
