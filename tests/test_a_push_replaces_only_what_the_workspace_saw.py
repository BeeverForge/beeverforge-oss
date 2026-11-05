"""A box's push replaces only the tip its workspace saw, on both boxes (#11, `Workspace.lease`).

`publish_branch` pushed with a plain `--force`, on the premise that the job's branch "is only ever
the bot's". A park that pushes the agent's work and names the branch for a person to fix by hand
made that false: a later run of the card without the handle starts from the base, and its push
replaced the preserved commits and the person's fix with them.

So each push is `--force-with-lease=<branch>:<tip>`: the tip `prepare` fetched on a resume, the
tip the box pushed itself after each push (a repair pass's second push, a rebase's), and nothing on
a fresh start, which says the branch must not be on the remote yet.

Real git, scratch repositories, a bare repository as the remote; no docker — the container box's
push runs on the host clone, and `_materialize_workspace` is the docker-free half of its prepare.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import test_walking_skeleton as spine

from beeverforge.adapters.sandbox.base import PushRefused, Workspace
from beeverforge.adapters.sandbox.container import (
    ContainerSandbox,
    _lease_of,
    _materialize_workspace,
)
from beeverforge.adapters.sandbox.worktree import WorktreeSandbox

#: the real-git harness — a bare origin and a repo with one commit — borrowed rather than rebuilt
repo = spine.repo

BRANCH = "beeverforge/7"


def _git(cwd: Path, *args: str) -> str:
    p = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, f"git {' '.join(args)}: {p.stderr}"
    return p.stdout.strip()


def _commit(where: Path, name: str, *, amend: bool = False) -> str:
    (where / f"{name}.txt").write_text(f"{name}\n")
    _git(where, "add", "-A")
    _git(where, "-c", "user.email=bot@example.invalid", "-c", "user.name=bot", "commit", "-qm",
         name, *(["--amend"] if amend else []))
    return _git(where, "rev-parse", "HEAD")


@pytest.fixture
def remote(repo, tmp_path) -> Path:
    """A bare remote with `main`, and the worker's repository (`tmp_path / "repo"`) pushing to it:
    the walking skeleton's pair, borrowed rather than rebuilt."""
    return tmp_path / "origin.git"


def _a_person_pushes(tmp_path: Path, remote: Path, *, start: str = "main",
                     name: str = "fixed-by-hand") -> str:
    clone = tmp_path / "person"
    if not clone.exists():
        subprocess.run(["git", "clone", "-q", str(remote), str(clone)], check=True)
    _git(clone, "fetch", "-q", "origin")
    _git(clone, "checkout", "-q", "-B", BRANCH, start)
    tip = _commit(clone, name)
    _git(clone, "push", "-q", "origin", f"{BRANCH}:{BRANCH}")
    return tip


def _tip(remote: Path) -> str:
    return _git(remote, "rev-parse", f"refs/heads/{BRANCH}")


# ── the worktree box ────────────────────────────────────────────────────────────────────────────

def _worktree(tmp_path: Path, remote: Path, *, resuming: bool = False):
    box = WorktreeSandbox(root=tmp_path / "wt")
    ws = box.prepare(repo_path=tmp_path / "repo", base_branch="main", branch=BRANCH,
                     checkout_existing=resuming, remote_url=str(remote))
    return box, ws


def test_a_fresh_workspace_pushes_and_pushes_again_over_its_own_tip(tmp_path, remote):
    """A normal run's second push — after a repair pass, or a rebase that is no fast-forward —
    still lands: its lease is the tip it pushed itself."""
    box, ws = _worktree(tmp_path, remote)
    assert ws.lease == "", "a fresh start must say the branch is not on the remote yet"

    _commit(ws.path, "first")
    box.publish_branch(workspace=ws, remote_url=str(remote))
    second = _commit(ws.path, "repair")
    box.publish_branch(workspace=ws, remote_url=str(remote))
    rewritten = _commit(ws.path, "rebased", amend=True)
    box.publish_branch(workspace=ws, remote_url=str(remote))

    assert second != rewritten
    assert _tip(remote) == rewritten


def test_a_fresh_workspace_does_not_push_over_a_branch_already_on_the_remote(tmp_path, remote):
    theirs = _a_person_pushes(tmp_path, remote)
    box, ws = _worktree(tmp_path, remote)
    _commit(ws.path, "the run's own")

    with pytest.raises(PushRefused) as refused:
        box.publish_branch(workspace=ws, remote_url=str(remote))

    assert refused.value.branch == BRANCH
    assert _tip(remote) == theirs, "the person's commit was replaced"


def test_a_resumed_workspace_does_not_push_over_a_commit_made_after_it_started(tmp_path, remote):
    _a_person_pushes(tmp_path, remote)
    box, ws = _worktree(tmp_path, remote, resuming=True)
    assert ws.lease == _tip(remote)
    later = _a_person_pushes(tmp_path, remote, start=f"origin/{BRANCH}", name="fixed-again")
    _commit(ws.path, "the run's own")

    with pytest.raises(PushRefused):
        box.publish_branch(workspace=ws, remote_url=str(remote))
    assert _tip(remote) == later


def test_a_resumed_workspace_pushes_over_the_tip_it_started_from(tmp_path, remote):
    started = _a_person_pushes(tmp_path, remote)
    box, ws = _worktree(tmp_path, remote, resuming=True)
    ours = _commit(ws.path, "continued")
    box.publish_branch(workspace=ws, remote_url=str(remote))

    assert _tip(remote) == ours
    assert _git(remote, "rev-parse", f"{ours}~1") == started


# ── the container box ───────────────────────────────────────────────────────────────────────────

def _container(tmp_path: Path, remote: Path, *, resuming: bool = False):
    """The container box's workspace without a container: its clone, as `prepare` makes it."""
    clone = tmp_path / "box-clone"
    _materialize_workspace(repo_path=tmp_path / "repo", host_clone=clone, base_branch="main",
                           branch=BRANCH, checkout_existing=resuming, remote_url=str(remote))
    box = ContainerSandbox(image="img")
    box._host_clone, box._repo_path = clone, tmp_path / "repo"
    ws = Workspace(path=Path("/workspace"), host_path=clone, branch=BRANCH, base_branch="main",
                   lease=_lease_of(clone, BRANCH, resuming))
    return box, ws, clone


def test_the_container_box_pushes_and_pushes_again_over_its_own_tip(tmp_path, remote):
    box, ws, clone = _container(tmp_path, remote)
    assert ws.lease == ""
    _commit(clone, "first")
    box.publish_branch(workspace=ws, remote_url=str(remote))
    rewritten = _commit(clone, "rebased", amend=True)
    box.publish_branch(workspace=ws, remote_url=str(remote))

    assert _tip(remote) == rewritten


def test_the_container_box_does_not_push_over_a_branch_already_on_the_remote(tmp_path, remote):
    theirs = _a_person_pushes(tmp_path, remote)
    box, ws, clone = _container(tmp_path, remote)
    _commit(clone, "the run's own")

    with pytest.raises(PushRefused):
        box.publish_branch(workspace=ws, remote_url=str(remote))
    assert _tip(remote) == theirs


def test_the_container_box_resumes_from_the_fetched_tip_and_pushes_over_it(tmp_path, remote):
    started = _a_person_pushes(tmp_path, remote)
    box, ws, clone = _container(tmp_path, remote, resuming=True)
    assert ws.lease == started
    ours = _commit(clone, "continued")
    box.publish_branch(workspace=ws, remote_url=str(remote))

    assert _tip(remote) == ours
