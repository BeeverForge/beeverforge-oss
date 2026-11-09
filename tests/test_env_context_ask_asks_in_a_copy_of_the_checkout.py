"""`env context --ask` asks in a copy of the checkout, never in the checkout itself (#167).

WHAT WAS WRONG: `actions/catalog.py::_semantic_pass` asked the tech-lead harness with
`judging_worktree(project, root=checkout)` and `Workspace(path=checkout)`, where `checkout` is the
path the person typed or the project's `repo_path`: on a local deployment, the repository they
commit from. Kimi Code is read-only by instruction only, and one that disobeyed left its file in
their working tree for them to commit (`?? wrote.txt`, measured in the review of e2b57dd1).

WHAT IS HELD HERE (the Kimi row in
`tests/test_where_a_kimi_judging_role_runs_is_what_its_documents_say.py` holds the end to end):
  · the harness is asked in a directory that is not the checkout, and that directory is gone once
    the question is answered, and when it fails;
  · the copy is what the person sees: uncommitted edits and untracked files are in it; what git
    ignores, and the `.git` directory, are not;
  · a link is copied only when it stays inside the checkout: one with an absolute target, or one
    that climbs out, would reach the person's files from inside the copy (#467's review);
  · a checkout that is no git working tree, or a machine with no git, is copied whole but `.git`;
  · what can go wrong is said in one sentence naming the cause and the remedy: git too slow, a
    checkout over the size a copy may hold, a file that cannot be read;
  · a harness that cannot judge is still refused before anything is copied or asked.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

import beeverforge.actions.catalog as catalog
from beeverforge.actions.catalog import _copy_into, _semantic_pass, _what_to_copy
from beeverforge.onboarding import context as ctx


def _repo(root: Path) -> Path:
    root.mkdir()
    git = ["git", "-c", "init.defaultBranch=main", "-c", "commit.gpgSign=false",
           "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-C", str(root)]
    env = {**os.environ, "LC_ALL": "C"}
    subprocess.run([*git, "init", "-q"], check=True, env=env)
    (root / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("committed\n", encoding="utf-8")
    subprocess.run([*git, "add", "-A"], check=True, env=env)
    subprocess.run([*git, "commit", "-q", "-m", "base"], check=True, env=env)
    (root / "src" / "app.py").write_text("edited, not committed\n", encoding="utf-8")
    (root / "NOTES.md").write_text("untracked\n", encoding="utf-8")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "big.js").write_text("ignored\n", encoding="utf-8")
    return root


def _copy(checkout: Path, room: Path) -> Path:
    return _copy_into(checkout, _what_to_copy(checkout), room)


def test_the_copy_is_what_the_person_sees_and_not_what_git_ignores(tmp_path):
    room = _copy(_repo(tmp_path / "repo"), tmp_path / "copy")

    assert (room / "src" / "app.py").read_text(encoding="utf-8") == "edited, not committed\n"
    assert (room / "NOTES.md").read_text(encoding="utf-8") == "untracked\n"
    assert (room / ".gitignore").is_file()
    assert not (room / "node_modules").exists(), "an ignored directory was copied"
    assert not (room / ".git").exists(), "the repository's .git was copied"


def test_a_link_that_leaves_the_checkout_is_not_copied_and_one_inside_is(tmp_path):
    """#467's review: a link with an absolute target, or one that climbs out with `..`, would
    reach the person's real files from inside the copy, so a write through it lands in them."""
    checkout = _repo(tmp_path / "repo")
    (checkout / "to-root").symlink_to(checkout)                         # absolute, to itself
    (checkout / "src" / "out").symlink_to(Path("..") / ".." / "elsewhere")   # climbs out
    (checkout / "readme-link").symlink_to("NOTES.md")                   # stays inside

    room = _copy(checkout, tmp_path / "copy")

    assert not (room / "to-root").exists() and not (room / "to-root").is_symlink()
    assert not (room / "src" / "out").is_symlink()
    assert (room / "readme-link").is_symlink()
    assert (room / "readme-link").read_text(encoding="utf-8") == "untracked\n"


def test_a_checkout_that_is_no_working_tree_is_copied_whole_but_its_git(tmp_path):
    plain = tmp_path / "plain"
    (plain / "docs").mkdir(parents=True)
    (plain / "docs" / "a.md").write_text("a\n", encoding="utf-8")
    (plain / ".git").mkdir()            # a directory named .git that is not a repository
    (plain / ".git" / "junk").write_text("x\n", encoding="utf-8")

    room = _copy(plain, tmp_path / "copy")

    assert (room / "docs" / "a.md").read_text(encoding="utf-8") == "a\n"
    assert not (room / ".git").exists()


def test_a_machine_with_no_git_copies_the_whole_tree_but_git(tmp_path, monkeypatch):
    checkout = _repo(tmp_path / "repo")

    def no_git(*_a, **_k):
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", no_git)

    room = _copy(checkout, tmp_path / "copy")

    assert (room / "src" / "app.py").is_file() and not (room / ".git").exists()


def test_git_that_does_not_answer_in_time_is_said(tmp_path, monkeypatch):
    checkout = _repo(tmp_path / "repo")

    def slow(argv, **_k):
        raise subprocess.TimeoutExpired(argv, 60)

    monkeypatch.setattr(subprocess, "run", slow)

    with pytest.raises(ValueError, match=r"did not list the files .* within 60 seconds.*without"):
        _what_to_copy(checkout)


def test_a_checkout_over_the_size_a_copy_may_hold_is_refused_before_it_is_copied(
        tmp_path, monkeypatch):
    checkout = _repo(tmp_path / "repo")
    monkeypatch.setattr(catalog, "_ASK_COPY_LIMIT", 10)

    with pytest.raises(ValueError, match=r"over the 0 MB a copy for `--ask` may hold.*\.gitignore"):
        _what_to_copy(checkout)


def test_a_file_that_cannot_be_read_is_said_by_name(tmp_path, monkeypatch):
    import shutil

    checkout = _repo(tmp_path / "repo")
    real = shutil.copy2

    def refused(source, target, **kw):
        if Path(source).name == "NOTES.md":
            raise PermissionError(13, "Permission denied")
        return real(source, target, **kw)

    monkeypatch.setattr(shutil, "copy2", refused)

    with pytest.raises(RuntimeError, match=r"NOTES\.md in .* could not be copied .*Permission "
                                           r"denied.*Make it readable"):
        _copy(checkout, tmp_path / "copy")


def _asked_in(monkeypatch, *, fails: bool) -> list[Path]:
    asked: list[Path] = []

    def bind(agent, *, sandbox, workspace, **_kw):
        def ask(prompt: str) -> str:
            room = Path(workspace.path)
            asked.append(room)
            (room / "wrote.txt").write_text("disobeyed\n", encoding="utf-8")
            if fails:
                raise RuntimeError("the harness crashed")
            return "done"
        return ask

    monkeypatch.setattr(ctx, "agent_ask", bind)
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")
    return asked


def test_the_harness_is_asked_in_the_copy_which_is_gone_after(tmp_path, monkeypatch):
    checkout = _repo(tmp_path / "repo")
    asked = _asked_in(monkeypatch, fails=False)

    answer = _semantic_pass(None, checkout, ctx)("What does this repository build?")

    assert answer == "done"
    assert asked and asked[0] != checkout and checkout not in asked[0].parents
    assert not asked[0].exists(), "the copy was left behind"
    assert not (checkout / "wrote.txt").exists(), "the write reached the person's checkout"


def test_the_copy_is_gone_when_the_question_fails_too(tmp_path, monkeypatch):
    checkout = _repo(tmp_path / "repo")
    asked = _asked_in(monkeypatch, fails=True)

    with pytest.raises(RuntimeError, match="the harness crashed"):
        _semantic_pass(None, checkout, ctx)("What does this repository build?")

    assert asked and not asked[0].exists(), "a failed question left its copy behind"
    assert not (checkout / "wrote.txt").exists()


def test_a_harness_that_cannot_judge_is_refused_before_anything_is_copied(tmp_path, monkeypatch):
    checkout = _repo(tmp_path / "repo")
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("beeverforge.adapters.agent.build_asker", lambda project: object())
    copied: list[Path] = []
    monkeypatch.setattr(catalog, "_copy_into",
                        lambda checkout, names, room: copied.append(room) or room)

    with pytest.raises(TypeError, match="no read-only `ask`"):
        _semantic_pass(None, checkout, ctx)

    assert copied == []
