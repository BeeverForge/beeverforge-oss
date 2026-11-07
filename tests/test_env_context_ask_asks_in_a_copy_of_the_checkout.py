"""`env context --ask` asks in a copy of the checkout, never in the checkout itself (#167).

WHAT WAS WRONG: `actions/catalog.py::_semantic_pass` asked the tech-lead harness with
`judging_worktree(project, root=checkout)` and `Workspace(path=checkout)`, where `checkout` is the
path the person typed or the project's `repo_path`: on a local deployment, the repository they
commit from. Kimi Code is read-only by instruction only, and one that disobeyed left its file in
their working tree for them to commit (`?? wrote.txt`, measured in the review of e2b57dd1).

WHAT IS HELD HERE (the Kimi row in
`tests/test_where_a_kimi_judging_role_runs_is_what_its_documents_say.py` holds the end to end):
  · the harness is asked in a directory that is not the checkout, and that directory is gone once
    the question is answered;
  · the copy is what the person sees: uncommitted edits and untracked files are in it; what git
    ignores, and the `.git` directory, are not;
  · a checkout that is no git working tree is copied whole but its `.git`;
  · a harness that cannot judge is still refused before anything is copied or asked.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from beeverforge.actions.catalog import _a_copy_of, _semantic_pass
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


def test_the_copy_is_what_the_person_sees_and_not_what_git_ignores(tmp_path):
    room = _a_copy_of(_repo(tmp_path / "repo"), tmp_path / "copy")

    assert (room / "src" / "app.py").read_text(encoding="utf-8") == "edited, not committed\n"
    assert (room / "NOTES.md").read_text(encoding="utf-8") == "untracked\n"
    assert (room / ".gitignore").is_file()
    assert not (room / "node_modules").exists(), "an ignored directory was copied"
    assert not (room / ".git").exists(), "the repository's .git was copied"


def test_a_checkout_that_is_no_working_tree_is_copied_whole_but_its_git(tmp_path):
    plain = tmp_path / "plain"
    (plain / "docs").mkdir(parents=True)
    (plain / "docs" / "a.md").write_text("a\n", encoding="utf-8")
    (plain / ".git").mkdir()            # a directory named .git that is not a repository
    (plain / ".git" / "junk").write_text("x\n", encoding="utf-8")

    room = _a_copy_of(plain, tmp_path / "copy")

    assert (room / "docs" / "a.md").read_text(encoding="utf-8") == "a\n"
    assert not (room / ".git").exists()


def test_the_harness_is_asked_in_the_copy_which_is_gone_after(tmp_path, monkeypatch):
    checkout = _repo(tmp_path / "repo")
    asked: list[Path] = []

    def bind(agent, *, sandbox, workspace, **_kw):
        def ask(prompt: str) -> str:
            room = Path(workspace.path)
            asked.append(room)
            (room / "wrote.txt").write_text("disobeyed\n", encoding="utf-8")
            return "done"
        return ask

    monkeypatch.setattr(ctx, "agent_ask", bind)
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")

    answer = _semantic_pass(None, checkout, ctx)("What does this repository build?")

    assert answer == "done"
    assert asked and asked[0] != checkout and checkout not in asked[0].parents
    assert not asked[0].exists(), "the copy was left behind"
    assert not (checkout / "wrote.txt").exists(), "the write reached the person's checkout"


def test_a_harness_that_cannot_judge_is_refused_before_anything_is_copied(tmp_path, monkeypatch):
    checkout = _repo(tmp_path / "repo")
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("beeverforge.adapters.agent.build_asker", lambda project: object())
    copied: list[Path] = []
    monkeypatch.setattr("beeverforge.actions.catalog._a_copy_of",
                        lambda checkout, room: copied.append(room) or room)

    with pytest.raises(TypeError, match="no read-only `ask`"):
        _semantic_pass(None, checkout, ctx)

    assert copied == []
