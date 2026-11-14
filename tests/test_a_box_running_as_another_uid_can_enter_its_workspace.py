"""A box daemon that runs as another uid than the core can enter the job's workspace (#519).

`ContainerSandbox.prepare` makes each workspace with `tempfile.mkdtemp(dir=BEEVERFORGE_WORK_DIR)`,
which is always 0700. A deployment whose box daemon runs as a different uid — a rootless daemon,
whose container root is an unprivileged uid on the host — lets it into the shared work dir with a
default ACL. The new directory inherits the entry, but its ACL mask is the group bits of the mode
it was made with, `---` for 0700, so the entry reads `user:<uid>:rwx  #effective:---` and the box
refused to start, measured: `docker run` exited 126, `chdir to cwd ("/workspace") set in
config.json failed: permission denied`. `chmod 0770` on the directory made the same `docker run`
write.

What this covers is a work dir shared through a DEFAULT ACL. A work dir shared through a setgid
group keeps its setgid bit on the workspace (tested below), but that case also needs the core to
run with umask 0002/0007: under 0022 the clone's subdirectories are 0755 and the box's
`git commit` is still refused. Nothing here claims more.

The clone is stubbed: what is measured is the directory `prepare` hands to `docker run -v`, not
git, so these tests run no git and wait on nothing.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

import beeverforge.adapters.sandbox.container as mod
from beeverforge.adapters.sandbox.container import ContainerSandbox

#: A uid no test machine runs as (`nobody` on Debian and Ubuntu), named by number so that
#: `setfacl` needs no passwd entry for it.
_OTHER_UID = 65534


def _no_daemon(args, timeout=None, env=None):
    return 0, ""


def _workspace(monkeypatch, work_dir: Path | None) -> Path:
    """The directory `prepare` mounts at /workspace, with the daemon and the clone stubbed."""
    if work_dir is None:
        monkeypatch.delenv("BEEVERFORGE_WORK_DIR", raising=False)
    else:
        monkeypatch.setenv("BEEVERFORGE_WORK_DIR", str(work_dir))
    monkeypatch.setattr(mod, "_host", _no_daemon)
    monkeypatch.setattr(mod, "_materialize_workspace", lambda **_: "0" * 40)
    ws = ContainerSandbox(image="img", project="acme").prepare(
        repo_path=Path("unused"), base_branch="main", branch="beeverforge/12")
    return ws.host_path


@pytest.fixture
def strict_umask():
    """The umask a hardened host runs with: a mode handed to a mkdir would lose its group bits
    to it, and the workspace's mode must not depend on it."""
    old = os.umask(0o077)
    try:
        yield
    finally:
        os.umask(old)


def test_a_workspace_in_the_shared_work_dir_lets_its_group_in_and_keeps_others_out(
        monkeypatch, tmp_path, strict_umask):
    work = tmp_path / "work"
    work.mkdir()

    host_clone = _workspace(monkeypatch, work)

    assert host_clone.parent == work
    mode = stat.S_IMODE(host_clone.stat().st_mode)
    assert mode == 0o770, (
        f"the workspace is {oct(mode)}: a group or ACL principal must be let in (0770), "
        "and 'other' never")


def test_without_a_work_dir_the_workspace_stays_private(monkeypatch, strict_umask):
    """No shared directory means no other uid to let in: the clone lives in the system temp
    directory, where group bits would open it to the core's group for nothing."""
    host_clone = _workspace(monkeypatch, None)
    try:
        assert stat.S_IMODE(host_clone.stat().st_mode) == 0o700
    finally:
        shutil.rmtree(host_clone, ignore_errors=True)


def test_the_work_dirs_default_acl_entry_is_effective_on_the_new_workspace(monkeypatch, tmp_path):
    """The deployment's own mechanism, read back with `getfacl`: the inherited entry for the
    daemon's uid is effective, because the mask is rwx."""
    if not (shutil.which("setfacl") and shutil.which("getfacl")):
        pytest.skip("setfacl/getfacl are not on PATH (the acl package)")
    work = tmp_path / "work"
    work.mkdir()
    for spec in (f"u:{_OTHER_UID}:rwx", f"d:u:{_OTHER_UID}:rwx"):
        done = subprocess.run(["setfacl", "-m", spec, str(work)], capture_output=True, text=True)
        if done.returncode != 0:
            pytest.skip(f"this filesystem takes no ACL: {done.stderr.strip()[:120]}")

    host_clone = _workspace(monkeypatch, work)

    acl = subprocess.run(["getfacl", "-n", "-p", "-E", str(host_clone)],
                         capture_output=True, text=True, check=True).stdout.splitlines()
    assert f"user:{_OTHER_UID}:rwx" in acl, f"the work dir's entry was not inherited: {acl}"
    assert "mask::rwx" in acl, (
        f"the inherited entry for uid {_OTHER_UID} is masked, so that uid cannot enter: {acl}")


def test_a_workspace_in_a_setgid_work_dir_keeps_the_setgid_bit(monkeypatch, tmp_path):
    """A work dir shared through a group is setgid so what is made in it carries the group; a
    chmod that drops the bit hands every directory the clone makes to the core's own group."""
    work = tmp_path / "work"
    work.mkdir()
    os.chmod(work, 0o2770)
    host_clone = _workspace(monkeypatch, work)
    assert host_clone.stat().st_mode & stat.S_ISGID


def test_the_workspace_is_open_when_docker_run_mounts_it(monkeypatch, tmp_path):
    """The mode that matters is the one `docker run` meets: chmod after it is too late, the
    daemon has already refused to chdir into /workspace (exit 126)."""
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setenv("BEEVERFORGE_WORK_DIR", str(work))
    monkeypatch.setattr(mod, "_materialize_workspace", lambda **_: "0" * 40)
    seen = []

    def host(args, timeout=None, env=None):
        if args[:2] == ["docker", "run"]:
            mount = args[args.index("-w") - 1]
            seen.append(stat.S_IMODE(os.stat(mount.rsplit(":", 1)[0]).st_mode) & 0o777)
        return 0, ""

    monkeypatch.setattr(mod, "_host", host)
    ContainerSandbox(image="img", project="acme").prepare(
        repo_path=Path("unused"), base_branch="main", branch="beeverforge/12")
    assert seen == [0o770]
