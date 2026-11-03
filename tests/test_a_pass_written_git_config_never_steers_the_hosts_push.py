"""The host's authenticated push never reads git configuration a pass could write (#386).

THE CLASS OF PROBLEM. A pass runs in a repository it may write to, `.git/config` included (on the
worktree box the common git directory and the worktree's `config.worktree`; on the container box
the host clone bind-mounted as /workspace). The host then pushes that repository's branch with the
forge's credential. A push run with the pass's repository as its git directory reads the pass's
configuration, and two kinds of key in it act on the host:

  * URL rewriting (`url.<base>.insteadOf`, `url.<base>.pushInsteadOf`), which sends the
    authenticated push somewhere other than the forge. No `-c` override neutralises it key by key,
    because the pass picks `<base>`;
  * keys naming a program git runs (`core.sshCommand`, `core.fsmonitor`).

So the push goes from a bare repository the host makes for it, outside every mount: the pass's
commits are fetched into it as objects, and the push runs there with the forge URL as an argument.

THE STAND-INS ARE INERT. The "program" each key names is a script that creates a sentinel file and
exits 1; the rewritten push URL points at `example.invalid`; the other rewrite points at a local
bare decoy. Nothing reaches a network. A control proves the configuration is live with the push's
old shape, so the proofs below are not proving an absence that would hold anyway.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from beeverforge import gitpin
from tests import the_git_bed

git_bed = the_git_bed.git_bed


def _git(where, *args, check: bool = True) -> subprocess.CompletedProcess:
    done = subprocess.run(["git", "-C", str(where), *args], capture_output=True, text=True,
                          check=False)
    if check:
        assert done.returncode == 0, done.stdout + done.stderr
    return done


def _refs(repo: Path) -> str:
    return _git(repo, "for-each-ref", "--format=%(refname) %(objectname)").stdout.strip()


@pytest.fixture
def scene(tmp_path, monkeypatch, git_bed):
    """A bare forge holding `main` and a clone of it (the bed's hosted door), a second bare
    repository as the decoy, a sentinel directory and two stand-ins.

    THE SUITE'S `GIT_ALLOW_PROTOCOL=file` IS LIFTED HERE, so git takes the ssh door a rewritten
    push URL opens and reaches `core.sshCommand`: with ssh refused outright the stand-in could
    never run, and its absence would prove nothing. What ssh would run is the stand-in, and the
    host is `example.invalid`, which never resolves; the socket guard stays on."""
    monkeypatch.delenv("GIT_ALLOW_PROTOCOL", raising=False)
    side = the_git_bed.a_hosted_door(git_bed, tmp_path / "forge-side")
    forge, repo = side / "forge.git", side / "myapp"
    decoy = the_git_bed.a_hosted_door(git_bed, tmp_path / "decoy-side") / "forge.git"
    sentinel = tmp_path / "sentinel"
    sentinel.mkdir()
    standins = {}
    for name in ("ssh-command", "fsmonitor"):
        script = tmp_path / f"standin-{name}"
        script.write_text(f"#!/bin/sh\ntouch '{sentinel / name}'\nexit 1\n")
        script.chmod(0o755)
        standins[name] = script
    return {"root": tmp_path, "forge": forge, "repo": repo, "decoy": decoy,
            "decoy_refs": _refs(decoy), "sentinel": sentinel, "standins": standins}


def _the_pass_writes_its_config(scene, repo: Path, *, worktree: bool = False) -> None:
    """What a pass can leave in a git configuration it can write: the push remote's URL rewritten
    twice (to a decoy for fetch and push, to an unreachable ssh host for push alone), and the two
    program-naming keys pointing at the stand-ins. `worktree` writes them into the worktree's own
    `config.worktree` as well."""
    forge = str(scene["forge"])
    keys = [(f"url.{scene['decoy']}.insteadOf", forge),
            ("url.ssh://example.invalid/x.pushInsteadOf", forge),
            ("core.sshCommand", str(scene["standins"]["ssh-command"])),
            ("core.fsmonitor", str(scene["standins"]["fsmonitor"]))]
    for key, value in keys:
        _git(repo, "config", key, value)
    if worktree:
        _git(repo, "config", "extensions.worktreeConfig", "true")
        for key, value in keys:
            _git(repo, "config", "--worktree", key, value)


def _commit(where: Path, text: str) -> str:
    (where / "app.py").write_text(text)
    _git(where, "add", "-A")
    _git(where, "commit", "-qm", "the pass's work")
    return _git(where, "rev-parse", "HEAD").stdout.strip()


def _the_push_reached_the_forge_and_nothing_else(scene, branch: str, head: str) -> None:
    assert _git(scene["forge"], "rev-parse", f"refs/heads/{branch}").stdout.strip() == head
    assert _refs(scene["decoy"]) == scene["decoy_refs"]
    assert sorted(os.listdir(scene["sentinel"])) == []


@pytest.fixture
def worktree_box(scene):
    from beeverforge.adapters.sandbox.worktree import WorktreeSandbox

    return WorktreeSandbox(root=scene["root"] / "boxes"), scene["repo"]


# ── the control ─────────────────────────────────────────────────────────────────────────────────

def test_the_pass_written_config_is_live_for_a_push_run_in_the_passs_repository(scene,
                                                                                 worktree_box):
    """THE CONTROL: the push's old shape, run with the pass's repository as its git directory,
    goes where the pass's configuration says and runs the program it names."""
    box, repo = worktree_box
    ws = box.prepare(repo_path=repo, base_branch="main", branch="sdlc/1",
                     remote_url=str(scene["forge"]))
    _commit(Path(ws.path), "print('two')\n")
    _the_pass_writes_its_config(scene, Path(ws.path))

    done = subprocess.run(gitpin.argv(["-C", str(ws.path), "push", "--force", "--",
                                       str(scene["forge"]), "sdlc/1"]),
                          capture_output=True, text=True, check=False)

    assert done.returncode != 0
    assert (scene["sentinel"] / "ssh-command").exists(), done.stderr


# ── the worktree box ────────────────────────────────────────────────────────────────────────────

def test_the_worktree_boxs_push_reaches_the_forge_whatever_the_pass_wrote_in_its_config(
        scene, worktree_box):
    box, repo = worktree_box
    ws = box.prepare(repo_path=repo, base_branch="main", branch="sdlc/1",
                     remote_url=str(scene["forge"]))
    head = _commit(Path(ws.path), "print('two')\n")
    _the_pass_writes_its_config(scene, Path(ws.path), worktree=True)

    box.publish_branch(workspace=ws, remote_url=str(scene["forge"]))

    _the_push_reached_the_forge_and_nothing_else(scene, "sdlc/1", head)


def test_the_worktree_boxs_ambient_push_goes_to_the_origin_it_had_before_the_pass(
        scene, worktree_box):
    """With no forge URL the push goes to `origin` — the origin the repository had when the box
    was prepared, not the one the pass's configuration names at push time."""
    box, repo = worktree_box
    ws = box.prepare(repo_path=repo, base_branch="main", branch="sdlc/1")
    head = _commit(Path(ws.path), "print('two')\n")
    _the_pass_writes_its_config(scene, Path(ws.path))
    _git(ws.path, "config", "remote.origin.url", str(scene["decoy"]))
    _git(ws.path, "config", "remote.origin.pushurl", str(scene["decoy"]))

    box.publish_branch(workspace=ws)

    _the_push_reached_the_forge_and_nothing_else(scene, "sdlc/1", head)


def test_a_relative_origin_is_read_from_the_repository_it_belongs_to(scene, worktree_box):
    box, repo = worktree_box
    _git(repo, "config", "remote.origin.url", os.path.relpath(scene["forge"], repo))
    ws = box.prepare(repo_path=repo, base_branch="main", branch="sdlc/1")
    head = _commit(Path(ws.path), "print('two')\n")

    box.publish_branch(workspace=ws)

    _the_push_reached_the_forge_and_nothing_else(scene, "sdlc/1", head)


def test_a_repository_with_no_origin_and_no_forge_says_what_to_do(scene, worktree_box):
    box, repo = worktree_box
    _git(repo, "remote", "remove", "origin")
    ws = box.prepare(repo_path=repo, base_branch="main", branch="sdlc/1")
    _commit(Path(ws.path), "print('two')\n")

    with pytest.raises(RuntimeError) as refused:
        box.publish_branch(workspace=ws)

    said = str(refused.value)
    assert said.startswith("push failed:")
    assert "no origin" in said and "register the project with a forge" in said


# ── the container box ───────────────────────────────────────────────────────────────────────────

def test_the_container_boxs_push_reaches_the_forge_whatever_the_pass_wrote_in_its_config(scene):
    """The host clone is what the box sees as /workspace, so its `.git/config` is the pass's to
    write. Built without docker: the clone and the push are the host's half."""
    from beeverforge.adapters.sandbox.base import Workspace
    from beeverforge.adapters.sandbox.container import ContainerSandbox, _materialize_workspace

    cache = scene["repo"]
    host_clone = scene["root"] / "host-clone"
    _materialize_workspace(repo_path=cache, host_clone=host_clone, base_branch="main",
                           branch="sdlc/2", checkout_existing=False,
                           remote_url=str(scene["forge"]))
    box = ContainerSandbox(image="unused")
    box._host_clone, box._repo_path = host_clone, cache
    head = _commit(host_clone, "print('three')\n")
    _the_pass_writes_its_config(scene, host_clone)
    ws = Workspace(path=Path("/workspace"), host_path=host_clone, branch="sdlc/2",
                   base_branch="main")

    box.publish_branch(workspace=ws, remote_url=str(scene["forge"]))

    _the_push_reached_the_forge_and_nothing_else(scene, "sdlc/2", head)


# ── the refusals, and nothing left behind ───────────────────────────────────────────────────────

@pytest.fixture
def own_tmp(tmp_path, monkeypatch):
    import tempfile

    where = tmp_path / "hosts-tmp"
    where.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(where))
    return where


def test_a_push_that_cannot_bring_the_commits_out_says_which_step_and_what_to_do(
        scene, worktree_box, own_tmp):
    box, repo = worktree_box
    ws = box.prepare(repo_path=repo, base_branch="main", branch="sdlc/1",
                     remote_url=str(scene["forge"]))
    _git(ws.path, "checkout", "-q", "--detach")
    _git(repo, "branch", "-D", "sdlc/1")
    secret = "https://x-access-token:s3cr3t@example.invalid/o/r.git"

    with pytest.raises(RuntimeError) as refused:
        box.publish_branch(workspace=ws, remote_url=secret)

    said = str(refused.value)
    assert said.startswith("push failed:")
    assert "could not bring" in said and "sdlc/1" in said
    assert "check that the branch" in said
    assert "s3cr3t" not in said
    assert list(own_tmp.iterdir()) == []


def test_a_refused_push_keeps_its_sentence_and_leaves_nothing_behind(scene, worktree_box,
                                                                     own_tmp):
    box, repo = worktree_box
    ws = box.prepare(repo_path=repo, base_branch="main", branch="sdlc/1",
                     remote_url=str(scene["forge"]))
    _commit(Path(ws.path), "print('two')\n")

    with pytest.raises(RuntimeError) as refused:
        box.publish_branch(workspace=ws, remote_url=str(scene["root"] / "no-such-forge.git"))

    assert str(refused.value).startswith("push failed:")
    assert "could not bring" not in str(refused.value)
    assert list(own_tmp.iterdir()) == []
