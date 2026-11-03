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

So the push goes from a bare repository the host makes for it, outside every mount: it borrows
the pass's objects (`objects/info/alternates`), takes the branch's commit from the pass's ref file
read as data, and pushes with the forge URL as an argument. No git command starts in the pass's
repository, so no git version's behaviour there is relied on (review of #403).

THE WORKER'S OWN CONFIGURATION IS THE PASS'S TOO, ON THE WORKTREE BOX (review of #403): the pass
runs as the worker's user, with the worker's HOME, so the user-level git config (`~/.gitconfig`,
`$XDG_CONFIG_HOME/git/config`) and the ssh config are its to write. The forge door reads none of
them, nor the system config. The ambient door (no forge URL) is the person's own push and keeps
them, but runs in the workload's own scrubbed environment.

THE STAND-INS ARE INERT. The "program" each key names is a script that creates a sentinel file and
exits 1; the rewritten push URL points at `example.invalid`; the other rewrite points at a local
bare decoy. Nothing reaches a network. A control proves the configuration is live with the push's
old shape, so the proofs below are not proving an absence that would hold anyway.
"""

from __future__ import annotations

import os
import shutil
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

@pytest.fixture(autouse=True)
def own_tmp(tmp_path, monkeypatch):
    """The host's temporary directory, per test, so a mutant that leaves the push's repository
    behind leaves it here and never in the machine's /tmp."""
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


# ── the worker's own configuration (review of #403) ─────────────────────────────────────────────

def _plant_in(scene, config: Path) -> None:
    """The same classes `_the_pass_writes_its_config` plants, written into `config` as a file:
    the push remote's URL rewritten twice and the two program-naming keys at the stand-ins."""
    config.parent.mkdir(parents=True, exist_ok=True)
    forge = str(scene["forge"])
    for key, value in [(f"url.{scene['decoy']}.insteadOf", forge),
                       ("url.ssh://example.invalid/x.pushInsteadOf", forge),
                       ("core.sshCommand", str(scene["standins"]["ssh-command"])),
                       ("core.fsmonitor", str(scene["standins"]["fsmonitor"]))]:
        subprocess.run(["git", "config", "-f", str(config), key, value], check=True,
                       capture_output=True)


@pytest.fixture
def workers_home(tmp_path, monkeypatch):
    """A HOME the pass can write, as the worktree box's pass can write the worker's: HOME and
    XDG_CONFIG_HOME point here, and the suite's own `GIT_CONFIG_GLOBAL` is lifted so git reads
    the user-level files under it. Set only once the scene is built, by the test."""
    home = tmp_path / "workers-home"
    home.mkdir()

    def move_in() -> Path:
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
        monkeypatch.delenv("GIT_CONFIG_GLOBAL", raising=False)
        return home

    return move_in


@pytest.mark.parametrize("where", [".gitconfig", ".config/git/config"])
def test_the_worktree_boxs_forge_push_never_reads_a_user_config_the_pass_wrote(
        scene, worktree_box, workers_home, where):
    box, repo = worktree_box
    ws = box.prepare(repo_path=repo, base_branch="main", branch="sdlc/1",
                     remote_url=str(scene["forge"]))
    head = _commit(Path(ws.path), "print('two')\n")
    _plant_in(scene, workers_home() / where)

    box.publish_branch(workspace=ws, remote_url=str(scene["forge"]))

    _the_push_reached_the_forge_and_nothing_else(scene, "sdlc/1", head)


def test_the_forge_push_never_reads_the_system_config(scene, worktree_box, monkeypatch):
    """The suite points `GIT_CONFIG_SYSTEM` at nothing; here it points at a planted file, which is
    the system config git would read on a machine where the pass's user can write it."""
    box, repo = worktree_box
    ws = box.prepare(repo_path=repo, base_branch="main", branch="sdlc/1",
                     remote_url=str(scene["forge"]))
    head = _commit(Path(ws.path), "print('two')\n")
    system = scene["root"] / "etc" / "gitconfig"
    _plant_in(scene, system)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(system))

    box.publish_branch(workspace=ws, remote_url=str(scene["forge"]))

    _the_push_reached_the_forge_and_nothing_else(scene, "sdlc/1", head)


def test_the_forge_push_starts_ssh_reading_no_configuration_file(scene, worktree_box,
                                                                  monkeypatch):
    """ssh finds the user's config through the password database, not HOME, so a planted one
    cannot be put in front of it here. What is measured is what ssh is told: an `ssh` stand-in
    first on PATH records its arguments, and they must name no configuration file but
    /dev/null. The host is `example.invalid`; the stand-in exits 1, so the push fails."""
    box, repo = worktree_box
    ws = box.prepare(repo_path=repo, base_branch="main", branch="sdlc/1",
                     remote_url=str(scene["forge"]))
    _commit(Path(ws.path), "print('two')\n")
    bin_dir = scene["root"] / "bin"
    bin_dir.mkdir()
    said = scene["sentinel"] / "ssh-argv"
    (bin_dir / "ssh").write_text(f"#!/bin/sh\nprintf '%s\\n' \"$@\" > '{said}'\nexit 1\n")
    (bin_dir / "ssh").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    with pytest.raises(RuntimeError) as refused:
        box.publish_branch(workspace=ws, remote_url="ssh://example.invalid/x")

    assert str(refused.value).startswith("push failed:")
    argv = said.read_text().splitlines()
    assert argv[argv.index("-F") + 1] == "/dev/null", argv


def test_the_container_boxs_forge_push_never_reads_the_workers_user_config(scene,
                                                                          workers_home):
    """No mount puts the worker's HOME in the box's reach; the forge door reads none of it on
    either box all the same, so the claim is one sentence."""
    from beeverforge.adapters.sandbox.base import Workspace
    from beeverforge.adapters.sandbox.container import ContainerSandbox, _materialize_workspace

    host_clone = scene["root"] / "host-clone"
    _materialize_workspace(repo_path=scene["repo"], host_clone=host_clone, base_branch="main",
                           branch="sdlc/2", checkout_existing=False,
                           remote_url=str(scene["forge"]))
    box = ContainerSandbox(image="unused")
    box._host_clone, box._repo_path = host_clone, scene["repo"]
    head = _commit(host_clone, "print('three')\n")
    _plant_in(scene, workers_home() / ".gitconfig")
    ws = Workspace(path=Path("/workspace"), host_path=host_clone, branch="sdlc/2",
                   base_branch="main")

    box.publish_branch(workspace=ws, remote_url=str(scene["forge"]))

    _the_push_reached_the_forge_and_nothing_else(scene, "sdlc/2", head)


def test_the_ambient_push_runs_what_the_users_config_names_with_the_workloads_own_environment(
        scene, worktree_box, workers_home, monkeypatch):
    """THE AMBIENT DOOR KEEPS THE USER'S CONFIGURATION: it is the person's own push, and their
    credential helper, keys and URL rewrites live there. So what a pass plants there still runs —
    in the workload's scrubbed environment, which carries no credential the pass does not
    already hold. The stand-in records whether the worker's forge token reached it."""
    box, repo = worktree_box
    ws = box.prepare(repo_path=repo, base_branch="main", branch="sdlc/1")
    _commit(Path(ws.path), "print('two')\n")
    monkeypatch.setenv("GH_TOKEN", "a-stand-in-for-the-workers-forge-token")
    sentinel = scene["sentinel"]
    standin = scene["root"] / "standin-env"
    standin.write_text(f"#!/bin/sh\ntouch '{sentinel / 'ran'}'\n"
                       f"[ -n \"$GH_TOKEN\" ] && touch '{sentinel / 'saw-the-token'}'\nexit 1\n")
    standin.chmod(0o755)
    config = workers_home() / ".gitconfig"
    for key, value in [("url.ssh://example.invalid/x.pushInsteadOf", str(scene["forge"])),
                       ("core.sshCommand", str(standin))]:
        subprocess.run(["git", "config", "-f", str(config), key, value], check=True)

    with pytest.raises(RuntimeError):
        box.publish_branch(workspace=ws)

    assert (sentinel / "ran").exists(), "the control: the user's config is read on this door"
    assert not (sentinel / "saw-the-token").exists()


def test_the_ambient_push_runs_no_hook_the_users_config_names(scene, worktree_box, workers_home):
    box, repo = worktree_box
    ws = box.prepare(repo_path=repo, base_branch="main", branch="sdlc/1")
    head = _commit(Path(ws.path), "print('two')\n")
    hooks = scene["root"] / "planted-hooks"
    hooks.mkdir()
    # `pre-push` alone: it is the pushing side's. A receiving-side hook would run in the forge
    # here, which is a local repository reading the same user config; that side is the forge's.
    (hooks / "pre-push").write_text(f"#!/bin/sh\ntouch '{scene['sentinel'] / 'pre-push'}'\n"
                                    "exit 1\n")
    (hooks / "pre-push").chmod(0o755)
    subprocess.run(["git", "config", "-f", str(workers_home() / ".gitconfig"), "core.hooksPath",
                    str(hooks)], check=True)

    box.publish_branch(workspace=ws)

    _the_push_reached_the_forge_and_nothing_else(scene, "sdlc/1", head)


# ── no git command in the job's repository (review of #403) ─────────────────────────────────────

def test_no_git_command_starts_in_the_jobs_repository(scene, worktree_box, monkeypatch):
    """The serving side of a fetch (`upload-pack`) runs in the repository it serves and reads its
    config; what that config can make it run has depended on git's version. So no git command
    starts there at all: git's own trace of every process the push starts names neither the
    job's repository nor a serving side."""
    box, repo = worktree_box
    ws = box.prepare(repo_path=repo, base_branch="main", branch="sdlc/1",
                     remote_url=str(scene["forge"]))
    head = _commit(Path(ws.path), "print('two')\n")
    trace = scene["root"] / "trace"
    monkeypatch.setenv("GIT_TRACE", str(trace))

    box.publish_branch(workspace=ws, remote_url=str(scene["forge"]))

    monkeypatch.delenv("GIT_TRACE")
    said = trace.read_text()
    assert "upload-pack" not in said
    for job in (Path(ws.path), repo):
        assert str(job) not in said and str(job.resolve()) not in said
    _the_push_reached_the_forge_and_nothing_else(scene, "sdlc/1", head)


def _a_decoy_branch(scene, branch: str) -> Path:
    """A clone holding `branch` at a commit that is not the job's: what a repointed `.git` would
    name instead."""
    decoy = scene["root"] / "decoy-side" / "myapp"
    _git(decoy, "switch", "-q", "-c", branch)
    _commit(decoy, "print('the decoy')\n")
    return decoy


def test_the_worktree_boxs_push_reads_the_repository_it_prepared_not_the_one_the_pass_points_at(
        scene, worktree_box):
    box, repo = worktree_box
    ws = box.prepare(repo_path=repo, base_branch="main", branch="sdlc/1",
                     remote_url=str(scene["forge"]))
    head = _commit(Path(ws.path), "print('two')\n")
    decoy = _a_decoy_branch(scene, "sdlc/1")
    (Path(ws.path) / ".git").write_text(f"gitdir: {decoy / '.git'}\n")

    box.publish_branch(workspace=ws, remote_url=str(scene["forge"]))

    _the_push_reached_the_forge_and_nothing_else(scene, "sdlc/1", head)


def test_a_container_clone_whose_git_directory_the_job_replaced_is_refused(scene):
    from beeverforge.adapters.sandbox.base import Workspace
    from beeverforge.adapters.sandbox.container import ContainerSandbox, _materialize_workspace

    host_clone = scene["root"] / "host-clone"
    _materialize_workspace(repo_path=scene["repo"], host_clone=host_clone, base_branch="main",
                           branch="sdlc/2", checkout_existing=False,
                           remote_url=str(scene["forge"]))
    box = ContainerSandbox(image="unused")
    box._host_clone, box._repo_path = host_clone, scene["repo"]
    decoy = _a_decoy_branch(scene, "sdlc/2")
    (host_clone / ".git").rename(scene["root"] / "the-clones-own-git")
    (host_clone / ".git").symlink_to(decoy / ".git")
    ws = Workspace(path=Path("/workspace"), host_path=host_clone, branch="sdlc/2",
                   base_branch="main")

    with pytest.raises(RuntimeError) as refused:
        box.publish_branch(workspace=ws, remote_url=str(scene["forge"]))

    said = str(refused.value)
    assert said.startswith("push failed:") and "no longer the git directory" in said
    assert "run the job again" in said
    assert _git(scene["forge"], "rev-parse", "--verify", "--quiet", "refs/heads/sdlc/2",
                check=False).returncode != 0


def test_a_branch_in_packed_refs_is_read_from_there(scene, worktree_box):
    box, repo = worktree_box
    ws = box.prepare(repo_path=repo, base_branch="main", branch="sdlc/1",
                     remote_url=str(scene["forge"]))
    head = _commit(Path(ws.path), "print('two')\n")
    _git(repo, "pack-refs", "--all")
    assert not (repo / ".git" / "refs" / "heads" / "sdlc" / "1").exists()

    box.publish_branch(workspace=ws, remote_url=str(scene["forge"]))

    _the_push_reached_the_forge_and_nothing_else(scene, "sdlc/1", head)


@pytest.mark.parametrize("shape", ["symbolic", "symlink", "not-a-name", "sha256", "absent"])
def test_a_branch_ref_that_is_not_a_plain_object_name_is_refused(scene, worktree_box, shape):
    """The ref is read as data, so anything git would resolve further — a symbolic ref, a
    symlink — or anything that is not an object name is refused, with the remedy; so is an
    object name the job's objects do not hold."""
    box, repo = worktree_box
    ws = box.prepare(repo_path=repo, base_branch="main", branch="sdlc/1",
                     remote_url=str(scene["forge"]))
    _commit(Path(ws.path), "print('two')\n")
    ref = repo / ".git" / "refs" / "heads" / "sdlc" / "1"
    main = _git(repo, "rev-parse", "main").stdout.strip()
    ref.unlink()
    if shape == "symbolic":
        ref.write_text("ref: refs/heads/main\n")
    elif shape == "symlink":
        (scene["root"] / "elsewhere").write_text(f"{main}\n")
        ref.symlink_to(scene["root"] / "elsewhere")
    elif shape == "absent":
        ref.write_text(f"{'0' * 39}1\n")
    elif shape == "sha256":
        ref.write_text(f"{'ab' * 32}\n")
    else:
        ref.write_text("a branch name, not an object name\n")

    with pytest.raises(RuntimeError) as refused:
        box.publish_branch(workspace=ws, remote_url=str(scene["forge"]))

    said = str(refused.value)
    assert said.startswith("push failed:")
    assert "refs/heads/sdlc/1" in said or shape in ("sha256", "absent")
    cause, remedy = {"symbolic": ("not a plain object name", "then publish again"),
                     "symlink": ("is a symlink", "then publish again"),
                     "not-a-name": ("not a plain object name", "then publish again"),
                     "sha256": ("SHA-256", "publish from a SHA-1 repository"),
                     "absent": ("which its objects do not hold", "(`git fsck`), then publish "
                                "again")}[shape]
    assert cause in said and remedy in said, said
    assert _git(scene["forge"], "rev-parse", "--verify", "--quiet", "refs/heads/sdlc/1",
                check=False).returncode != 0


def test_a_repository_that_keeps_its_refs_in_a_reftable_is_refused_with_the_remedy(
        scene, worktree_box):
    """git 2.45+ can keep refs in a reftable, which is not read here as data. The marker is the
    `reftable` directory itself; the git here (2.43) cannot make a real one."""
    box, repo = worktree_box
    ws = box.prepare(repo_path=repo, base_branch="main", branch="sdlc/1",
                     remote_url=str(scene["forge"]))
    _commit(Path(ws.path), "print('two')\n")
    (repo / ".git" / "reftable").mkdir()

    with pytest.raises(RuntimeError) as refused:
        box.publish_branch(workspace=ws, remote_url=str(scene["forge"]))

    said = str(refused.value)
    assert said.startswith("push failed:") and "reftable" in said
    assert "git refs migrate --ref-format=files" in said


def test_a_box_that_could_not_read_its_git_directory_at_prepare_says_so(scene, worktree_box,
                                                                        own_tmp):
    box, repo = worktree_box
    ws = box.prepare(repo_path=repo, base_branch="main", branch="sdlc/1",
                     remote_url=str(scene["forge"]))
    _commit(Path(ws.path), "print('two')\n")
    box._git_dir = None  # what `prepare` keeps when git could not be asked

    with pytest.raises(RuntimeError) as refused:
        box.publish_branch(workspace=ws, remote_url=str(scene["forge"]))

    said = str(refused.value)
    assert said.startswith("push failed:") and "could not be read when the box was prepared" in said
    assert "run the job again" in said
    assert list(own_tmp.iterdir()) == []


# ── a job-written alternates chain (review of #403) ─────────────────────────────────────────────

def _a_job_borrowing_from_elsewhere(scene, git_dir: Path, shape: str) -> str:
    """What a job can do to the objects directory it can write: name another object directory on
    the host (here a decoy repository's, standing in for another project's cache), and point its
    branch at a commit only that directory holds. Returns the decoy's commit."""
    decoy = _a_decoy_branch(scene, "elsewhere")
    theirs = _git(decoy, "rev-parse", "HEAD").stdout.strip()
    objects = git_dir / "objects"
    elsewhere = f"{decoy / '.git' / 'objects'}\n"
    if shape == "alternates":
        (objects / "info" / "alternates").write_text(elsewhere)
    elif shape == "http-alternates":
        (objects / "info" / "http-alternates").write_text("https://example.invalid/objects\n")
    elif shape == "info-symlink":
        planted = scene["root"] / "planted-info"
        planted.mkdir()
        (planted / "alternates").write_text(elsewhere)
        shutil.rmtree(objects / "info")
        (objects / "info").symlink_to(planted)
    else:  # objects-symlink
        moved = scene["root"] / "moved-objects"
        objects.rename(moved)
        objects.symlink_to(moved)
    return theirs


@pytest.mark.parametrize("shape", ["alternates", "http-alternates", "info-symlink",
                                   "objects-symlink"])
def test_the_worktree_boxs_push_refuses_a_job_that_borrows_objects_from_elsewhere(
        scene, worktree_box, own_tmp, shape):
    box, repo = worktree_box
    ws = box.prepare(repo_path=repo, base_branch="main", branch="sdlc/1",
                     remote_url=str(scene["forge"]))
    _commit(Path(ws.path), "print('two')\n")
    theirs = _a_job_borrowing_from_elsewhere(scene, repo / ".git", shape)
    if shape == "alternates":
        (repo / ".git" / "refs" / "heads" / "sdlc" / "1").write_text(f"{theirs}\n")

    with pytest.raises(RuntimeError) as refused:
        box.publish_branch(workspace=ws, remote_url=str(scene["forge"]))

    said = str(refused.value)
    assert said.startswith("push failed:")
    cause = "is a symlink" if shape.endswith("symlink") else "borrows objects from elsewhere"
    assert cause in said and "then publish again" in said, said
    assert _git(scene["forge"], "cat-file", "-e", theirs, check=False).returncode != 0
    assert _git(scene["forge"], "rev-parse", "--verify", "--quiet", "refs/heads/sdlc/1",
                check=False).returncode != 0
    assert list(own_tmp.iterdir()) == []


def test_the_container_boxs_push_never_sends_objects_from_a_directory_the_box_cannot_see(scene):
    """The box sees only /workspace, but an alternates entry is resolved by the host's git, on
    the host's filesystem: a job that names another project's cache there would have that
    project's objects pushed to this project's forge."""
    from beeverforge.adapters.sandbox.base import Workspace
    from beeverforge.adapters.sandbox.container import ContainerSandbox, _materialize_workspace

    host_clone = scene["root"] / "host-clone"
    _materialize_workspace(repo_path=scene["repo"], host_clone=host_clone, base_branch="main",
                           branch="sdlc/2", checkout_existing=False,
                           remote_url=str(scene["forge"]))
    box = ContainerSandbox(image="unused")
    box._host_clone, box._repo_path = host_clone, scene["repo"]
    _commit(host_clone, "print('three')\n")
    theirs = _a_job_borrowing_from_elsewhere(scene, host_clone / ".git", "alternates")
    (host_clone / ".git" / "refs" / "heads" / "sdlc" / "2").write_text(f"{theirs}\n")
    ws = Workspace(path=Path("/workspace"), host_path=host_clone, branch="sdlc/2",
                   base_branch="main")

    with pytest.raises(RuntimeError) as refused:
        box.publish_branch(workspace=ws, remote_url=str(scene["forge"]))

    assert "borrows objects from elsewhere" in str(refused.value)
    assert _git(scene["forge"], "cat-file", "-e", theirs, check=False).returncode != 0
