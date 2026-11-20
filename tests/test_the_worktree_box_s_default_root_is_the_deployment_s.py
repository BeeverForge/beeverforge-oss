"""The worktree box's default root is the deployment's, not the directory the process started in.

`box prove` and `doctor` build the worktree box with no `root`. Its trees then belong beside the
repository cache (`default_root() / ".beeverforge-worktrees"`), the root a job's box gets from
`factory.py` for a project served from the cache, and never under whatever directory the command
was run from, which can be a person's checkout. Building a box writes nothing (`prepare` makes the
root), so these tests touch no disk.
"""

from pathlib import Path

from beeverforge.adapters.sandbox.registry import build_sandbox
from beeverforge.runtime.repo_cache import RepoCache

SUBDIR = ".beeverforge-worktrees"


def _box_built_in(monkeypatch, where: Path):
    where.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(where)
    return build_sandbox("worktree")


def test_two_working_directories_get_one_root_beside_the_cache(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    monkeypatch.setenv("BEEVERFORGE_REPO_CACHE", str(cache))
    here, there = tmp_path / "here", tmp_path / "there"

    first = _box_built_in(monkeypatch, here)
    second = _box_built_in(monkeypatch, there)

    assert first.root == second.root, (
        f"a box built in {here} has its root at {first.root} and one built in {there} at "
        f"{second.root}: the default root follows the working directory, so a later command run "
        f"elsewhere does not find the trees; build it from the repository cache's root")
    assert first.root == cache / SUBDIR, (
        f"the default root is {first.root}, not {cache / SUBDIR}: the box does not put its trees "
        f"beside the repository cache where a job looks; compose `default_root() / {SUBDIR!r}`")
    for cwd in (here, there):
        assert not first.root.resolve().is_relative_to(cwd.resolve()), (
            f"the default root {first.root} is under the working directory {cwd}: a proof run "
            f"from a person's checkout writes into it; take the root from the repository cache")


def test_a_cache_changed_after_import_is_the_one_used(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for name in ("first", "second"):
        cache = tmp_path / name
        monkeypatch.setenv("BEEVERFORGE_REPO_CACHE", str(cache))
        root = build_sandbox("worktree").root
        assert root == cache / SUBDIR, (
            f"with BEEVERFORGE_REPO_CACHE={cache} the box's default root is {root}, not "
            f"{cache / SUBDIR}: the cache root was read once and kept; ask `default_root()` "
            f"each time the box is built, never at import")


def test_a_given_root_is_used_as_given(tmp_path, monkeypatch):
    monkeypatch.setenv("BEEVERFORGE_REPO_CACHE", str(tmp_path / "cache"))
    explicit = tmp_path / "explicit"
    for given in (explicit, str(explicit)):
        root = build_sandbox("worktree", root=given).root
        assert root == explicit, (
            f"the box was given root={given!r} and took {root}: a caller's root (a job's, from "
            f"`factory.py`) is overridden by the default; use the given root when there is one")


def test_the_default_root_is_the_one_a_job_served_from_the_cache_gets(tmp_path, monkeypatch):
    monkeypatch.setenv("BEEVERFORGE_REPO_CACHE", str(tmp_path / "cache"))
    monkeypatch.chdir(tmp_path)
    served = RepoCache().root / "demo"
    job_root = served.parent / SUBDIR  # the composition `factory.py` hands a job's box

    root = build_sandbox("worktree").root
    assert root == job_root, (
        f"a box built with no root uses {root}, a job's box for a project served from the cache "
        f"uses {job_root}: a tree a proof leaves is not where a job looks; make the default "
        f"`default_root() / {SUBDIR!r}`, the same name `factory.py` uses")
