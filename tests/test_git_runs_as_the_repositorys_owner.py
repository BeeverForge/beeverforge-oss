"""Git that reads or writes inside a repository another user owns runs as that user, when the
platform is root.

WHAT WAS MEASURED. On the compose stack the worker and the panel are root and a `forge: local`
project's repository is the person's. Git refuses root there ("detected dubious ownership", exit
128), so such a project could be neither proven nor run. Trusting the repository instead left
root-owned files in it: the person could not edit a file the job merged, delete the job's branch
or run git's own collection, and the repository's hooks ran as root (git 2.47.3, the worker
image).

WITHOUT ROOT, AND WITH REAL GIT. Who the process is, who owns a path, whether the owner can enter
a directory and the change of owner are `gitowner`'s seams, set here. Every git the platform
starts runs for real through a recorder that drops only the change of user, and `setpriv` is a
stand-in on PATH that drops its own options and runs the rest, so the command git is given is
executed as it is quoted. What only real ownership can show is in
`test_git_run_as_root_leaves_the_repository_to_its_owner.py`, which needs root.

`gitowner` is imported inside the tests, never at module level: one test here also holds on the
code before it, and a failed import would fail the whole file.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import tempfile
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import NamedTuple

import pytest

from tests import the_git_bed

git_bed = the_git_bed.git_bed

ROOT = Path(__file__).resolve().parents[1]

#: The owner of the repository, as far as the platform can tell. No such user exists here.
UID, GID = 4242, 4343


def _git(where, *args, check: bool = True) -> str:
    done = subprocess.run(["git", "-C", str(where), *args], capture_output=True, text=True,
                          check=False)
    if check:
        assert done.returncode == 0, f"setup: git {' '.join(args)}: {done.stderr}"
    return done.stdout.strip()


# ── who git runs as ─────────────────────────────────────────────────────────────────────────────

def _owned_by(monkeypatch, owners: dict, *, euid: int = 0, enters=lambda owner, d: True) -> None:
    """The process is `euid`; each path of `owners` belongs to its `(uid, gid)`, the rest to
    root."""
    from beeverforge import gitowner

    table = {os.path.realpath(p): who for p, who in owners.items()}
    monkeypatch.setattr(os, "geteuid", lambda: euid)
    monkeypatch.setattr(gitowner, "_ownership", lambda p: table.get(os.path.realpath(p), (0, 0)))
    monkeypatch.setattr(gitowner, "_can_enter", enters)


@pytest.fixture
def shapes(git_bed, tmp_path):
    """One of each shape a repository has: `(path, its work tree, its git directory)`."""
    plain = the_git_bed.a_card_repository(git_bed, tmp_path / "plain")
    bare = the_git_bed.a_hosted_door(git_bed, tmp_path / "door") / "forge.git"
    (tmp_path / "link").symlink_to(plain)
    linked = tmp_path / "linked"
    _git(plain, "worktree", "add", "-q", str(linked), the_git_bed.CARD_BRANCH)
    admin = plain / ".git" / "worktrees" / "linked"
    relative = tmp_path / "relative"
    shutil.copytree(linked, relative)
    (relative / ".git").write_text("gitdir: ../plain/.git/worktrees/linked\n")
    elsewhere = tmp_path / "elsewhere"
    shutil.copytree(plain, elsewhere, symlinks=True)
    (elsewhere / ".git").rename(tmp_path / "elsewhere.git")
    (elsewhere / ".git").symlink_to(tmp_path / "elsewhere.git")
    return {"a directory": (plain, plain, plain / ".git"),
            "through a symlink": (tmp_path / "link", plain, plain / ".git"),
            "a file naming an absolute path": (linked, linked, admin),
            "a file naming a relative path": (relative, relative, admin),
            "a symlinked git directory": (elsewhere, elsewhere, tmp_path / "elsewhere.git"),
            "bare": (bare, bare, bare)}


SHAPES = ("a directory", "through a symlink", "a file naming an absolute path",
          "a file naming a relative path", "a symlinked git directory", "bare")


@pytest.mark.parametrize("who", ["not root", "root's own", "another user's"])
@pytest.mark.parametrize("shape", SHAPES)
def test_who_git_runs_as(monkeypatch, shapes, shape, who):
    from beeverforge import gitowner

    path, tree, git_dir = shapes[shape]
    owners = {} if who == "root's own" else {tree: (UID, 1), git_dir: (UID, GID)}
    _owned_by(monkeypatch, owners, euid=1000 if who == "not root" else 0)

    got = gitowner.owner_of(path)

    owned = gitowner.Owner(UID, 1 if shape == "bare" else GID)
    if shape == "bare" and owners:
        _owned_by(monkeypatch, {tree: (UID, 1)}, euid=1000 if who == "not root" else 0)
        got = gitowner.owner_of(path)
    assert got == (owned if who == "another user's" else None)
    assert gitowner.owner_of(str(path)) == got


def test_a_path_that_is_no_repository_is_nobodys(monkeypatch, shapes, tmp_path):
    """The current directory least of all: an empty path is no path."""
    from beeverforge import gitowner

    plain = shapes["a directory"][0]
    (plain / "src").mkdir()
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / ".git").write_text("not a git directory's name\n")
    gone = tmp_path / "gone"
    gone.mkdir()
    (gone / ".git").write_text("gitdir: /nowhere/at/all\n")
    real = gitowner._ownership
    _owned_by(monkeypatch, {})
    monkeypatch.setattr(gitowner, "_ownership", lambda p: real(p) and (UID, GID))
    monkeypatch.chdir(plain)

    assert gitowner.owner_of(".") == gitowner.Owner(UID, GID)
    for path in ("", None, tmp_path, plain / "src", broken, gone, tmp_path / "absent"):
        assert gitowner.owner_of(path) is None, path


@pytest.mark.parametrize(("tree_owner", "git_owner", "said"), [
    ((UID, GID), (0, 0), f"chown -R {UID}:{GID} {{git_dir}}"),
    ((0, 0), (UID, GID), f"chown -R {UID}:{GID} {{tree}}"),
    ((UID, GID), (77, 78), f"chown -R {UID}:{GID} {{git_dir}}"),
])
def test_two_owners_are_refused_and_never_guessed(monkeypatch, shapes, tree_owner, git_owner,
                                                  said):
    from beeverforge import gitowner

    path, tree, git_dir = shapes["a symlinked git directory"]
    _owned_by(monkeypatch, {tree: tree_owner, git_dir: git_owner})

    with pytest.raises(gitowner.Refused) as refused:
        gitowner.owner_of(path)

    exc = refused.value
    assert exc.reason == (f"the repository has two owners: work tree uid {tree_owner[0]}, "
                          f"git directory uid {git_owner[0]}")
    assert said.format(tree=tree, git_dir=git_dir) in exc.remedy
    assert f"{tree} (uid {tree_owner[0]})" in exc.remedy
    assert f"{git_dir} (uid {git_owner[0]})" in exc.remedy
    assert str(exc) == f"{exc.reason} — {exc.remedy}"


# ── whether the owner can get there ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("who", ["a parent", "the work tree", "an outside git directory"])
def test_a_directory_the_owner_cannot_enter_is_named(monkeypatch, shapes, tmp_path, who):
    from beeverforge import gitowner

    path, tree, git_dir = shapes["a symlinked git directory"]
    closed = {"a parent": tmp_path, "the work tree": tree,
              "an outside git directory": git_dir}[who]
    _owned_by(monkeypatch, {tree: (UID, GID), git_dir: (UID, GID)},
              enters=lambda owner, d: Path(d) != closed)

    with pytest.raises(gitowner.Refused) as refused:
        gitowner.owner_of(path)

    assert refused.value.reason == f"the repository's owner, uid {UID}, cannot enter {closed}"
    assert f"`chmod o+x {closed}`" in refused.value.remedy
    assert "move the repository" in refused.value.remedy


def test_the_way_to_a_symlinked_repository_is_the_real_one(monkeypatch, shapes, tmp_path):
    """The directories git goes through are those the link leads to, not those it is spelled by."""
    from beeverforge import gitowner

    _, tree, git_dir = shapes["a directory"]
    far = tmp_path / "far"
    far.mkdir()
    (far / "link").symlink_to(tree)
    asked = []
    _owned_by(monkeypatch, {tree: (UID, GID), git_dir: (UID, GID)},
              enters=lambda owner, d: asked.append(Path(d)) or True)

    assert gitowner.owner_of(far / "link") == gitowner.Owner(UID, GID)
    assert tree in asked and git_dir in asked and far not in asked


@pytest.mark.parametrize(("mode", "owner", "enters"), [
    (0o100, "itself", True), (0o077, "itself", False), (0o010, "its group", True),
    (0o107, "its group", False), (0o001, "a stranger", True), (0o110, "a stranger", False),
])
def test_the_mode_bits_are_read_before_anybody_is_asked(monkeypatch, tmp_path, mode, owner,
                                                        enters):
    """Only where the bits deny is it tried once as that user: bits alone would refuse a directory
    an access list opens."""
    from beeverforge import gitowner

    door = tmp_path / "door"
    door.mkdir()
    st = door.stat()
    door.chmod(mode)
    who = {"itself": gitowner.Owner(st.st_uid, 99999),
           "its group": gitowner.Owner(99999, st.st_gid),
           "a stranger": gitowner.Owner(99999, 99998)}[owner]
    tried = []

    def probe(argv, **how):
        tried.append((argv, how))
        return subprocess.CompletedProcess(argv, 1 if len(tried) == 1 else 0, "", "")

    monkeypatch.setenv("WORKER_SECRET", "planted")
    monkeypatch.setattr(subprocess, "run", probe)
    try:
        assert gitowner._can_enter(who, door) is enters
        assert len(tried) == (0 if enters else 1)
        if not enters:
            (argv, how), = tried
            assert argv == ["test", "-x", str(door)]
            assert (how["user"], how["group"], how["extra_groups"]) == (who.uid, who.gid, [])
            assert how["cwd"] == "/" and "WORKER_SECRET" not in how["env"]
            assert gitowner._can_enter(who, door) is True, "an access list lets the owner in"
    finally:
        door.chmod(0o700)


@pytest.mark.parametrize("trouble", [
    PermissionError(1, "Operation not permitted"), subprocess.TimeoutExpired(["test"], 60),
], ids=["it cannot start", "it never ends"])
def test_an_attempt_that_could_not_be_made_refuses_nothing(monkeypatch, tmp_path, trouble):
    from beeverforge import gitowner

    def cannot(*a, **k):
        raise trouble

    monkeypatch.setattr(gitowner, "_bits_let_in", lambda owner, d: False)
    monkeypatch.setattr(subprocess, "run", cannot)

    assert gitowner._can_enter(gitowner.Owner(UID, GID), tmp_path) is True


# ── the environment, and git that Python starts ─────────────────────────────────────────────────

@pytest.fixture
def own_tmp(tmp_path, monkeypatch):
    """Where temporary directories go, so a test can ask what was left."""
    where = tmp_path / "tmp"
    where.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(where))
    return where


def _only_this_environment(monkeypatch, *, path: str = "/usr/bin:/bin") -> None:
    for name in list(os.environ):
        if name == "LANG" or name.startswith(("LC_", "LANGUAGE")):
            monkeypatch.delenv(name)
    monkeypatch.setenv("LC_ALL", "C.UTF-8")
    monkeypatch.setenv("LANG", "pt_BR.UTF-8")
    monkeypatch.setenv("PATH", path)
    monkeypatch.setenv("WORKER_SECRET", "planted")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "0")


def test_git_started_by_the_platform_is_given_the_user_and_a_short_environment(
        monkeypatch, shapes, own_tmp):
    from beeverforge import gitowner

    path, tree, git_dir = shapes["through a symlink"]
    _owned_by(monkeypatch, {tree: (UID, GID), git_dir: (UID, GID)})
    _only_this_environment(monkeypatch)
    given = []
    monkeypatch.setattr(gitowner, "_chown", lambda *a: given.append(a))

    with gitowner.running_as_owner(path) as (where, how):
        home = Path(how["env"]["HOME"])
        assert where == str(tree)
        assert how == {"user": UID, "group": GID, "extra_groups": [], "cwd": "/", "env": {
            "PATH": "/usr/bin:/bin", "LC_ALL": "C.UTF-8", "LANG": "pt_BR.UTF-8",
            "HOME": str(home), "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_TERMINAL_PROMPT": "0"}}
        assert list(home.iterdir()) == [] and home.stat().st_mode & 0o777 == 0o700
        assert given == [(str(home), UID, GID)]
    assert list(own_tmp.iterdir()) == []

    with pytest.raises(KeyError), gitowner.running_as_owner(path):
        raise KeyError("the call itself failed")
    assert list(own_tmp.iterdir()) == []


def test_a_repository_that_needs_no_switch_is_called_as_it_was_named(monkeypatch, shapes, own_tmp):
    from beeverforge import gitowner

    path = shapes["through a symlink"][0]
    _owned_by(monkeypatch, {})

    with gitowner.running_as_owner(str(path)) as got:
        assert got == (str(path), {})
        assert list(own_tmp.iterdir()) == []
    with gitowner.running_as_owner("") as got:
        assert got == ("", {})


def test_a_refused_call_makes_no_home(monkeypatch, shapes, own_tmp):
    from beeverforge import gitowner

    path, tree, git_dir = shapes["a directory"]
    _owned_by(monkeypatch, {tree: (UID, GID)})

    for side in (gitowner.running_as_owner, gitowner.upload_pack, gitowner.receive_pack):
        with pytest.raises(gitowner.Refused), side(path):
            pytest.fail("the call was let through")
    assert list(own_tmp.iterdir()) == []


def test_a_git_that_cannot_be_started_as_the_owner_says_so_and_invents_no_remedy(
        monkeypatch, shapes, own_tmp):
    from beeverforge import gitowner

    path, tree, git_dir = shapes["a directory"]
    _owned_by(monkeypatch, {tree: (UID, GID), git_dir: (UID, GID)})
    monkeypatch.setattr(gitowner, "_chown", lambda *a: None)
    monkeypatch.setattr(gitowner, "_setpriv", lambda: "/usr/bin/setpriv")

    with pytest.raises(gitowner.Refused) as refused, gitowner.running_as_owner(path):
        raise PermissionError(1, "Operation not permitted")
    assert refused.value.remedy == ""
    assert refused.value.reason == (f"git could not be started as the repository's owner, uid "
                                    f"{UID}: [Errno 1] Operation not permitted")

    with pytest.raises(subprocess.TimeoutExpired), gitowner.running_as_owner(path):
        raise subprocess.TimeoutExpired(["git"], 60)
    with pytest.raises(FileNotFoundError), gitowner.upload_pack(path):
        raise FileNotFoundError("the root side's own trouble is not the owner's")

    def closed(*a):
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(gitowner, "_chown", closed)
    for side in (gitowner.running_as_owner, gitowner.upload_pack):
        with pytest.raises(gitowner.Refused, match="could not be started"), side(path):
            pytest.fail("the call was let through")
    assert list(own_tmp.iterdir()) == []


# ── git that git starts ─────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("side", ["upload-pack", "receive-pack"])
def test_the_served_command_is_quoted_word_by_word(monkeypatch, shapes, tmp_path, side):
    from beeverforge import gitowner

    path, tree, git_dir = shapes["a directory"]
    _owned_by(monkeypatch, {tree: (UID, GID), git_dir: (UID, GID)})
    _only_this_environment(monkeypatch, path="/opt/a b's/bin:/usr/bin")
    monkeypatch.setattr(gitowner, "_chown", lambda *a: None)
    monkeypatch.setattr(gitowner, "_setpriv", lambda: "/usr/bin/setpriv")
    homes = tmp_path / "a b's tmp"
    homes.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(homes))
    serve = {"upload-pack": gitowner.upload_pack, "receive-pack": gitowner.receive_pack}[side]

    for target in (path, str(path), path.as_uri()):
        with serve(target) as option:
            home, = homes.iterdir()
            word, = option
            flag, _, command = word.partition("=")
            assert flag == f"--{side}"
            names = ["PATH=/opt/a b's/bin:/usr/bin", "LANG=pt_BR.UTF-8", "LC_ALL=C.UTF-8",
                     f"HOME={home}", "GIT_CONFIG_NOSYSTEM=1", "GIT_CONFIG_GLOBAL=/dev/null",
                     "GIT_TERMINAL_PROMPT=0"]
            names += ["GIT_PROTOCOL=version=2"] if side == "upload-pack" else []
            words = shlex.split(command)
            assert words[:2] == ["env", "-i"]
            assert sorted(words[2:2 + len(names)]) == sorted(names)
            assert words[2 + len(names):] == ["setpriv", "--reuid", str(UID), "--regid", str(GID),
                                              "--clear-groups", f"git-{side}"]
            assert command == " ".join(shlex.quote(w) for w in words)
        assert list(homes.iterdir()) == []


@pytest.mark.parametrize("target", [
    "https://example.invalid/a.git", "ssh://git@example.invalid/a.git", "git@example.invalid:a",
    "origin", "", None, ".", "./plain", "ext::plain"])
def test_a_target_that_is_not_a_path_adds_nothing(monkeypatch, shapes, tmp_path, target):
    """A remote's name is not a path, even where a directory of that name stands beside it."""
    from beeverforge import gitowner

    plain = shapes["a directory"][0]
    shutil.copytree(plain, tmp_path / "origin")
    monkeypatch.chdir(tmp_path)
    _owned_by(monkeypatch, {})
    monkeypatch.setattr(gitowner, "_ownership", lambda p: (UID, GID))

    for side in (gitowner.upload_pack, gitowner.receive_pack):
        with side(target) as option:
            assert option == []


def test_a_missing_setpriv_is_refused_by_name(monkeypatch, shapes, own_tmp, tmp_path):
    from beeverforge import gitowner

    path, tree, git_dir = shapes["a directory"]
    _owned_by(monkeypatch, {tree: (UID, GID), git_dir: (UID, GID)})
    (tmp_path / "empty").mkdir()
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))

    for side in (gitowner.upload_pack, gitowner.receive_pack):
        with pytest.raises(gitowner.Refused) as refused, side(path):
            pytest.fail("the call was let through")
        assert refused.value.reason == (f"git cannot run as the repository's owner, uid {UID}: "
                                        "`setpriv` is missing")
        assert "util-linux" in refused.value.remedy and "worker image" in refused.value.remedy
        assert "the image this version publishes" in refused.value.remedy
    assert list(own_tmp.iterdir()) == []


# ── every changed call, run for real ────────────────────────────────────────────────────────────

CARD = the_git_bed.CARD_BRANCH
JOB = "beeverforge/9"
#: `subprocess.run` as it was when this file was read: what a test's own setup runs through, so
#: only what the platform starts is recorded.
_RUN = subprocess.run

#: What a switched git may know of the worker's environment. The rest of the list is the call's.
KEPT = ("PATH", "LANG", "LANGUAGE", "LC_")
#: What a hook sees beyond the short list: its shell's own variables. Git's own (`GIT_DIR` and the
#: like) are not the worker's.
THE_SHELLS = ("PWD", "OLDPWD", "SHLVL", "_")


class Call(NamedTuple):
    argv: list
    how: dict


def _ok(where, *args) -> str:
    done = _RUN(["git", "-c", "core.hooksPath=/dev/null", "-C", str(where), *args],
                capture_output=True, text=True, check=False)
    assert done.returncode == 0, f"setup: git {' '.join(map(str, args))}: {done.stderr}"
    return done.stdout.strip()


def _commit(where, name: str, text: str) -> str:
    (where / name).write_text(text)
    _ok(where, "add", "-A")
    _ok(where, "-c", "user.name=someone", "-c", "user.email=someone@example.invalid", "commit",
        "-qm", name)
    return _ok(where, "rev-parse", "HEAD")


def _the_owned_repositories(where: Path, _env) -> None:
    """The card's repository and a bare one of the same commits, with no maintenance behind the
    test's back: a git that runs as the owner does not read the suite's own configuration."""
    where.mkdir()
    repo, bare = where / "myapp", where / "context.git"
    the_git_bed._card_repository(repo, the_git_bed.WORK)
    _RUN(["git", "clone", "-q", "--bare", str(repo), str(bare)], check=True, capture_output=True)
    for made in (repo, bare):
        for key, value in (("gc.auto", "0"), ("maintenance.auto", "false"),
                           ("receive.autogc", "false")):
            _ok(made, "config", key, value)


class Scene:
    """The person's repository, one the installation owns, and every process the platform
    started."""

    def __init__(self, root: Path, git_bed) -> None:
        self.root = root
        made = git_bed.copy("owned-repositories", root / "owned", _the_owned_repositories)
        self.repo, self.bare = made / "myapp", made / "context.git"
        self.cache = the_git_bed.a_card_repository(git_bed, root / "roots" / "cache")
        self.ws = root / "roots" / "ws"
        self.calls: list[Call] = []
        self.served = root / "served.log"

    @property
    def owned(self) -> tuple[Path, ...]:
        return self.repo, self.bare

    def the_job_commits(self, branch: str = JOB) -> str:
        """A workspace of the box on `branch`, with one commit of the job's, made by hand."""
        _RUN(["git", "clone", "-q", "--no-local", str(self.repo), str(self.ws)], check=True,
             capture_output=True)
        _ok(self.ws, "checkout", "-q", "-B", branch)
        return _commit(self.ws, "job.py", "JOB = True\n")

    def forge(self, repo: Path | None = None):
        from beeverforge.adapters.forge.local import LocalForge

        return LocalForge("myapp", str(repo or self.repo), base="main")

    def a_pull_request(self, repo: Path | None = None):
        forge = self.forge(repo)
        pr = forge.open_pr(head=CARD, base="main", title="t", body="b")
        self.calls.clear()
        return forge, pr

    def log(self) -> str:
        return self.served.read_text() if self.served.exists() else ""


@pytest.fixture
def scene(tmp_path, monkeypatch, git_bed, own_tmp):
    scene = Scene(tmp_path, git_bed)
    monkeypatch.setenv("BEEVERFORGE_BOARD_DB", str(tmp_path / "board.db"))
    monkeypatch.setenv("WORKER_SECRET", "planted")

    def run(argv, **how):
        scene.calls.append(Call(list(argv), dict(how)))
        return _RUN(argv, **{k: v for k, v in how.items()
                             if k not in ("user", "group", "extra_groups")})

    monkeypatch.setattr(subprocess, "run", run)
    return scene


def _root_and_the_owner(scene, monkeypatch, *, owner=(UID, GID), setpriv: bool = True,
                        shut: Path | None = None, git_dirs=None) -> list:
    """This process is root, and the scene's repositories belong to `owner`. Answers the list of
    paths whose owner was asked."""
    from beeverforge import gitowner

    given, asked = [], []

    def ownership(path):
        os.stat(path)
        asked.append(Path(path))
        if git_dirs is not None and Path(path).name == ".git":
            return git_dirs
        mine = any(Path(path).is_relative_to(d) for d in (*scene.owned, *given))
        return owner if mine else (0, 0)

    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(gitowner, "_ownership", ownership)
    monkeypatch.setattr(gitowner, "_can_enter", lambda who, d: d != shut)
    monkeypatch.setattr(gitowner, "_chown", lambda p, uid, gid: given.append(Path(p)))
    if setpriv:
        _a_setpriv_that_only_records(scene, monkeypatch)
    else:
        monkeypatch.setattr(gitowner, "_setpriv", lambda: None)
    return asked


def _a_setpriv_that_only_records(scene, monkeypatch) -> None:
    stand_in = scene.root / "bin" / "setpriv"
    stand_in.parent.mkdir(exist_ok=True)
    log = shlex.quote(str(scene.served))
    stand_in.write_text(
        "#!/bin/sh\n"
        f"echo \"$*\" >> {log}\n"
        f"env | sed 's/^/env /' >> {log}\n"
        'while [ $# -gt 0 ]; do case "$1" in\n'
        "  --reuid|--regid) shift 2 ;;\n"
        "  --clear-groups) shift ;;\n"
        "  *) break ;;\n"
        "esac; done\n"
        'exec "$@"\n')
    stand_in.chmod(0o755)
    monkeypatch.setenv("PATH", f"{stand_in.parent}{os.pathsep}{os.environ['PATH']}")


# ── the calls ───────────────────────────────────────────────────────────────────────────────────

def _the_boxs_clone(s: Scene) -> None:
    from beeverforge.adapters.sandbox.container import _materialize_workspace

    _materialize_workspace(repo_path=s.repo, host_clone=s.ws, base_branch="main", branch=JOB,
                           checkout_existing=False, remote_url=str(s.repo))
    assert (s.ws / "README.md").exists()


def _the_existing_branch(s: Scene) -> None:
    from beeverforge.adapters.sandbox.container import _materialize_workspace

    _materialize_workspace(repo_path=s.repo, host_clone=s.ws, base_branch="main", branch=CARD,
                           checkout_existing=True)
    assert (s.ws / "work.py").exists()


def _the_existing_branch_on_the_forge(s: Scene) -> None:
    from beeverforge.adapters.sandbox.container import _materialize_workspace

    _materialize_workspace(repo_path=s.repo, host_clone=s.ws, base_branch="main", branch=CARD,
                           checkout_existing=True, remote_url=str(s.repo))
    assert (s.ws / "work.py").exists()


def _the_forges_base(s: Scene) -> None:
    """A workspace cloned from the worker's cache, its base read from the person's repository."""
    from beeverforge.adapters.sandbox.container import _materialize_workspace

    _materialize_workspace(repo_path=s.cache, host_clone=s.ws, base_branch="main", branch=JOB,
                           checkout_existing=False, remote_url=str(s.repo))
    assert (s.ws / "README.md").exists()


def _the_rebase_before_a_merge(s: Scene) -> None:
    from beeverforge.adapters.sandbox.base import Workspace
    from beeverforge.adapters.sandbox.container import ContainerSandbox

    s.the_job_commits()
    _commit(s.repo, "moved.py", "MOVED = True\n")
    box = ContainerSandbox(image="unused")
    box._host_clone, box._repo_path = s.ws, s.repo
    ws = Workspace(path=Path("/workspace"), host_path=s.ws, branch=JOB, base_branch="main")
    assert box.rebase_onto_base(workspace=ws, base="main", remote_url=str(s.repo)) == "rebased"


def _push(s: Scene, target: str, **how) -> str:
    from beeverforge.adapters.sandbox import container, host_push

    return host_push.push_from_the_hosts_own_repository(
        git_dir=s.ws / ".git", branch=JOB, target=target, run=container._host,
        redact=container._redact, **how)


def _the_jobs_push(s: Scene) -> None:
    head = s.the_job_commits()
    assert _push(s, str(s.repo)) == head
    assert _ok(s.repo, "rev-parse", f"refs/heads/{JOB}") == head


def _the_keep(s: Scene) -> None:
    from beeverforge.adapters.sandbox import container, host_push

    s.the_job_commits()
    tip = _ok(s.repo, "rev-parse", CARD)
    if JOB not in _ok(s.repo, "for-each-ref", "--format=%(refname:short)").split():
        _ok(s.repo, "update-ref", f"refs/heads/{JOB}", tip)
    kept, got = host_push.keep_the_remote_tip(
        git_dir=s.ws / ".git", branch=JOB, target=str(s.repo), run=container._host,
        redact=container._redact)
    assert got == tip and _ok(s.repo, "rev-parse", f"refs/heads/{kept}") == tip


def _the_caches_clone(s: Scene) -> None:
    from beeverforge.runtime.repo_cache import RepoCache

    served = RepoCache(root=s.root / "roots" / "served").sync("p", str(s.repo), "")
    assert served is not None and (served / "README.md").exists()


def _the_caches_refresh(s: Scene) -> None:
    from beeverforge.runtime.repo_cache import RepoCache

    cache = RepoCache(root=s.root / "roots" / "served")
    assert cache.sync("p", str(s.repo), "main") is not None
    _commit(s.repo, "later.py", "LATER = True\n")
    served = cache.sync("p", str(s.repo), "main")
    assert served is not None and (served / "later.py").exists()


def _list_branches(s: Scene) -> None:
    assert s.forge().list_branches() == [CARD, "main"]


def _pr_diff(s: Scene) -> None:
    forge, pr = s.a_pull_request()
    assert "work.py" in forge.pr_diff(pr=pr)


def _delete_branch(s: Scene) -> None:
    assert s.forge().delete_branch(CARD) is True
    assert _ok(s.repo, "for-each-ref", "--format=%(refname:short)") == "main"


def _update_branch(s: Scene) -> None:
    forge, pr = s.a_pull_request()
    moved = _commit(s.repo, "moved.py", "MOVED = True\n")
    assert forge.mergeable_state(pr=pr) == "behind"
    assert forge.update_branch(pr=pr) is True
    assert _ok(s.repo, "rev-parse", f"{CARD}~1") == moved


def _the_merge(s: Scene) -> None:
    forge, pr = s.a_pull_request()
    assert forge.mergeable_state(pr=pr) == "clean"
    forge.merge_pr(pr=pr)
    assert (s.repo / "work.py").exists() and forge.pr_merged(pr=pr)


def _the_merge_with_the_base_not_out(s: Scene) -> None:
    _ok(s.repo, "switch", "-q", "-c", "the-persons-own")
    forge, pr = s.a_pull_request()
    forge.merge_pr(pr=pr)
    assert not (s.repo / "work.py").exists()
    assert _ok(s.repo, "rev-parse", "main") == _ok(s.repo, "rev-parse", CARD)


def _the_bare_rebase(s: Scene) -> None:
    moved = _ok(s.bare, "-c", "user.name=someone", "-c", "user.email=someone@example.invalid",
                "commit-tree", "main^{tree}", "-p", "main", "-m", "moved")
    _ok(s.bare, "update-ref", "refs/heads/main", moved)
    forge, pr = s.a_pull_request(s.bare)
    forge.merge_pr(pr=pr)
    assert _ok(s.bare, "rev-parse", "main~1") == moved


BOX = (_the_boxs_clone, _the_existing_branch, _the_existing_branch_on_the_forge, _the_forges_base,
       _the_rebase_before_a_merge)
PUSHES = (_the_jobs_push, _the_keep)
CACHE = (_the_caches_clone, _the_caches_refresh)
FORGE = (_list_branches, _pr_diff, _delete_branch, _update_branch, _the_merge,
         _the_merge_with_the_base_not_out, _the_bare_rebase)
ALL = (*BOX, *PUSHES, *CACHE, *FORGE)
every_call = pytest.mark.parametrize("call", ALL, ids=lambda f: f.__name__.strip("_"))


def _options(call: Call) -> list[str]:
    return [w for w in call.argv if w.startswith(("--upload-pack", "--receive-pack"))]


def _names(call: Call, owned) -> bool:
    """Whether this git call is about a repository of `owned`: a word of it or the directory it
    runs in, or the `origin` a workspace was cloned from."""
    from beeverforge import gitpin

    words = [w for w in (*call.argv, call.how.get("cwd") or "") if str(w).startswith("/")]
    if any(Path(w).is_relative_to(o) for w in words for o in owned):
        return True
    return "origin" in call.argv and gitpin.subcommand(call.argv) == "fetch"


def _about_the_owned(scene) -> list[Call]:
    return [c for c in scene.calls if c.argv[:1] == ["git"] and _names(c, scene.owned)]


@every_call
def test_every_changed_call_succeeds_with_git_run_as_the_owner(scene, monkeypatch, own_tmp, call):
    _root_and_the_owner(scene, monkeypatch)

    call(scene)

    about = _about_the_owned(scene)
    assert about, "the call never touched the repository, so it proves nothing"
    for done in about:
        if done.how.get("user") is not None:
            assert (done.how["user"], done.how["group"], done.how["extra_groups"]) == (UID, GID, [])
            assert done.how["cwd"] == "/" and Path(done.argv[2]).is_absolute()
            continue
        word, = _options(done)
        assert done.argv.index(word) < done.argv.index("--")
        command = shlex.split(word.partition("=")[2])
        assert command[:2] == ["env", "-i"]
        assert command[-6:-1] == ["--reuid", str(UID), "--regid", str(GID), "--clear-groups"]
        assert command[-1] == f"git-{word[2:].partition('=')[0]}"
    served = [c for c in about if _options(c)]
    assert scene.log().count(f"--reuid {UID} --regid {GID} --clear-groups git-") == len(served)
    assert [p.name for p in own_tmp.iterdir()] == [], "a directory of the call's own was left"


@every_call
def test_no_changed_call_starts_git_in_the_repository_as_root(scene, monkeypatch, call):
    """Who each git in the repository is started as. Whose its files then are, and that the owner
    goes on working there, only real ownership shows: the file that needs root."""
    _root_and_the_owner(scene, monkeypatch)

    call(scene)

    about = _about_the_owned(scene)
    assert about
    as_root = [c.argv for c in about if c.how.get("user") != UID and not _options(c)]
    assert as_root == []


@every_call
def test_no_changed_call_passes_safe_directory(scene, monkeypatch, call):
    _root_and_the_owner(scene, monkeypatch)

    call(scene)

    assert [c for c in _about_the_owned(scene) if c.how.get("user") == UID or _options(c)], (
        "nothing was switched, so this proves nothing about a switched call")
    for done in scene.calls:
        given = done.how.get("env") or {}
        said = [*done.argv, *given, *given.values()]
        assert not [w for w in said if "safe.directory" in str(w).lower()], done
    switched = [c.how["env"] for c in scene.calls if "user" in c.how]
    for env in switched:
        assert not [n for n in env if n.startswith(("GIT_CONFIG_COUNT", "GIT_CONFIG_KEY",
                                                    "GIT_CONFIG_PARAMETERS"))], env
    served = [line for line in scene.log().splitlines() if line.startswith("env ")]
    assert not [line for line in served if "safe.directory" in line.lower()
                or line.startswith("env GIT_CONFIG_PARAMETERS")], served
    for config in (scene.repo / ".git" / "config", scene.ws / ".git" / "config"):
        if config.exists():
            assert "safe" not in _RUN(["git", "config", "--file", str(config), "--list"],
                                      capture_output=True, text=True).stdout


@pytest.mark.parametrize("call", [_the_jobs_push, _the_merge, _the_merge_with_the_base_not_out],
                         ids=lambda f: f.__name__.strip("_"))
def test_a_hook_run_by_the_push_or_the_merge_sees_only_the_short_environment(
        scene, monkeypatch, call):
    """The repository's hooks run in git's process, and the worker's environment holds
    credentials."""
    _root_and_the_owner(scene, monkeypatch)
    seen = scene.root / "hook.env"
    for name in ("reference-transaction", "pre-receive", "post-merge"):
        hook = scene.repo / ".git" / "hooks" / name
        hook.parent.mkdir(exist_ok=True)
        hook.write_text(f"#!/bin/sh\nenv >> {shlex.quote(str(seen))}\n")
        hook.chmod(0o755)
    workers = dict(os.environ)

    call(scene)

    read = [line.partition("=")[::2] for line in seen.read_text().splitlines()]
    assert read, "no hook ran"
    leaked = sorted({name for name, value in read
                     if name in workers and name not in THE_SHELLS and not name.startswith(KEPT)
                     and workers[name] == value
                     and name not in ("GIT_CONFIG_NOSYSTEM", "GIT_TERMINAL_PROMPT")})
    assert leaked == []
    assert "WORKER_SECRET" not in dict(read)
    homes = {value for name, value in read if name == "HOME"}
    assert homes and os.environ["HOME"] not in homes


def test_the_boxs_clone_does_not_keep_the_owners_command(scene, monkeypatch):
    """The clone is the job's workspace: the box reads its configuration."""
    _root_and_the_owner(scene, monkeypatch)

    _the_boxs_clone(scene)

    clone, = (c for c in scene.calls if "clone" in c.argv)
    assert _options(clone), "the clone named no command, so this proves nothing"
    config = _ok(scene.ws, "config", "--local", "--list")
    assert "remote.origin.url" in config
    assert "uploadpack" not in config.lower() and "setpriv" not in config


# ── nothing changes where nothing must ──────────────────────────────────────────────────────────

_FETCH_JOB = f"+{CARD}:refs/remotes/origin/{CARD}"


def _remote_calls(s: Scene, call) -> list[list[str]]:
    """The literal command line of every remote-reaching call of `call`, as it was before."""
    from beeverforge import gitpin

    ws, repo, pin = str(s.ws), str(s.repo), list(gitpin.PIN)
    off = ["-c", "core.hooksPath=/dev/null"]
    master = str(s.root / "roots" / "served" / ".masters" / "p")
    clone = ["git", *pin, "clone", "--no-local", "--", repo, ws]
    own = ["git", *pin, *off, "-C", "<the push's own>"]
    ref = f"refs/heads/{JOB}"
    tip = _ok(s.repo, "rev-parse", CARD)
    cached = ["git", *off, *pin]
    spec = "+refs/heads/main:refs/remotes/origin/main"
    return {
        _the_boxs_clone: [clone],
        _the_existing_branch: [clone, ["git", *pin, "-C", ws, "fetch", "--", "origin",
                                       _FETCH_JOB]],
        _the_existing_branch_on_the_forge: [clone, ["git", *pin, "-C", ws, "fetch", "--", repo,
                                                    _FETCH_JOB]],
        _the_forges_base: [["git", *pin, "clone", "--no-local", "--", str(s.cache), ws],
                           ["git", *pin, "-C", ws, "fetch", "--", repo, "refs/heads/main"]],
        _the_rebase_before_a_merge: [["git", *pin, "-C", ws, "fetch", "--", repo, "main"]],
        _the_jobs_push: [[*own, "push", "--force", "--no-verify", "--", repo, f"{ref}:{ref}"]],
        _the_keep: [["git", *pin, *off, "-c", "core.alternateRefsCommand=true", "-C",
                     "<the push's own>", "fetch", "-q", "--no-tags", "--", repo,
                     f"+{ref}:refs/beeverforge/remote-tip"],
                    [*own, "push", "--no-verify", "--", repo,
                     f"{tip}:refs/heads/{JOB}-kept-{tip[:12]}"]],
        _the_caches_clone: [[*cached, "ls-remote", "--symref", "--", repo, "HEAD"],
                            [*cached, "clone", "--no-local", "--", repo, master]],
        _the_caches_refresh: [[*cached, "clone", "--no-local", "--branch", "main", "--", repo,
                               master],
                              [*cached, "fetch", "--", repo, spec]],
        _the_merge_with_the_base_not_out: [["git", "-C", repo, *pin, "fetch", "--", ".",
                                            f"{CARD}:main"]],
        _the_bare_rebase: [["git", "-C", str(s.bare), *pin, "fetch", "--", ".", f"{CARD}:main"]],
    }.get(call, [])


def _what_it_was(scene, call) -> None:
    from beeverforge import gitpin

    expected = _remote_calls(scene, call)
    scene.calls.clear()

    call(scene)

    mine = [c for c in scene.calls if c.argv[:1] == ["git"]]
    assert mine
    reached = [["<the push's own>" if "beeverforge-push-" in w else w for w in c.argv]
               for c in mine
               if gitpin.subcommand(c.argv) in ("clone", "fetch", "ls-remote", "push")]
    assert reached == expected
    assert not [c for c in mine if {"user", "group", "extra_groups"} & set(c.how)]
    assert not [c for c in mine if _options(c)]
    if call in FORGE:
        for done in mine:
            assert done.how.pop("input", "") is not None
            assert done.how == {"capture_output": True, "text": True, "timeout": 60,
                                "check": False}, done
            assert done.argv[1] == "-C" or done.argv == ["git", "patch-id", "--stable"], done
        repo = scene.bare if call is _the_bare_rebase else scene.repo
        at = {c.argv[2] for c in mine if c.argv[1] == "-C"}
        assert str(repo) in at and all(w == str(repo) or "beeverforge-rebase-" in w for w in at)
    if call in BOX:
        timeouts = {c.how["timeout"] for c in mine}
        assert timeouts == {120} and {c.how["env"] for c in mine} == {None}
    if call in PUSHES:
        for done in mine:
            changed = {n for n, v in done.how["env"].items() if os.environ.get(n) != v}
            assert changed <= {"GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL", "HOME",
                               "XDG_CONFIG_HOME", "GIT_SSH_COMMAND"}, changed
            assert done.how["env"]["WORKER_SECRET"] == "planted"
    if call in CACHE:
        for done in mine:
            assert done.how["env"] == {**os.environ, "GIT_TERMINAL_PROMPT": "0",
                                       "GCM_INTERACTIVE": "never"}


@every_call
def test_not_root_every_changed_call_is_what_it_was(scene, monkeypatch, call):
    """Held on the code before this, too: these are the calls as they were."""
    monkeypatch.setattr(os, "geteuid", lambda: 1000)

    _what_it_was(scene, call)


@every_call
def test_in_roots_own_repository_every_changed_call_is_what_it_was(scene, monkeypatch, call):
    """Asked whose it is, and nothing changed by the answer."""
    asked = _root_and_the_owner(scene, monkeypatch, owner=(0, 0))

    _what_it_was(scene, call)

    assert [p for p in asked if any(p.is_relative_to(o) for o in scene.owned)], (
        "nobody asked who owns the repository")


# ── what is refused ─────────────────────────────────────────────────────────────────────────────

def _a_repository_with_two_owners(scene, monkeypatch) -> tuple[str, str]:
    _root_and_the_owner(scene, monkeypatch, git_dirs=(0, 0))
    return (f"the repository has two owners: work tree uid {UID}, git directory uid 0",
            f"chown -R {UID}:{GID} {scene.repo / '.git'}")


def _a_repository_its_owner_cannot_enter(scene, monkeypatch) -> tuple[str, str]:
    _root_and_the_owner(scene, monkeypatch, shut=scene.repo.parent)
    return (f"the repository's owner, uid {UID}, cannot enter {scene.repo.parent}",
            f"chmod o+x {scene.repo.parent}")


def _a_missing_setpriv(scene, monkeypatch) -> tuple[str, str]:
    _root_and_the_owner(scene, monkeypatch, setpriv=False)
    return (f"git cannot run as the repository's owner, uid {UID}: `setpriv` is missing",
            "util-linux's `setpriv`")


CAUSES = (_a_repository_with_two_owners, _a_repository_its_owner_cannot_enter, _a_missing_setpriv)
every_cause = pytest.mark.parametrize("cause", CAUSES, ids=lambda f: f.__name__.strip("_"))


def _tree(where: Path) -> list:
    return sorted((str(p.relative_to(where)), p.lstat().st_mtime_ns) for p in where.rglob("*"))


#: The local forge's git is started by Python, which needs no `setpriv`, so it is no cause there.
REFUSALS = [(place, cause) for cause in CAUSES
            for place in (_the_boxs_clone, _the_existing_branch, _the_jobs_push, _the_keep,
                          _the_caches_clone, "the forge")
            if (place, cause) != ("the forge", _a_missing_setpriv)]


@pytest.mark.parametrize(("place", "cause"), REFUSALS,
                         ids=lambda f: f if isinstance(f, str) else f.__name__.strip("_"))
def test_each_refusal_says_its_cause_and_remedy_and_starts_nothing(
        scene, monkeypatch, caplog, own_tmp, place, cause):
    if place in PUSHES:
        scene.the_job_commits()
        _ok(scene.repo, "update-ref", f"refs/heads/{JOB}", "main")
        monkeypatch.setattr(scene, "the_job_commits", lambda: "")
    forge, pr = scene.a_pull_request()
    reason, remedy = cause(scene, monkeypatch)
    before, rows = _tree(scene.repo), _rows()

    if place == "the forge":
        said = _the_forge_refused(scene, forge, pr, caplog)
    elif place in CACHE:
        with pytest.raises(AssertionError):
            place(scene)
        said = caplog.text
    else:
        with pytest.raises(RuntimeError) as refused:
            place(scene)
        said = str(refused.value)
        assert said.removeprefix("push failed: ").startswith(reason), said

    assert reason in said and remedy in said, said
    assert _about_the_owned(scene) == [], "git was started in the repository"
    assert _tree(scene.repo) == before
    assert _rows() == rows and list(own_tmp.iterdir()) == []


def _rows() -> int:
    from beeverforge.adapters.board_db import connect

    with connect() as conn:
        return conn.execute("SELECT count(*) FROM pull_requests").fetchone()[0]


def _the_forge_refused(scene, forge, pr, caplog) -> str:
    """Every caller keeps its contract, and the sentence reaches the page and the log."""
    from beeverforge import gitowner

    assert forge.list_branches() is None
    assert forge.delete_branch(CARD) is False
    assert forge.pr_diff(pr=pr) is None
    assert forge.update_branch(pr=pr) is False
    assert forge.mergeable_state(pr=pr) == "dirty"
    said = forge.pr_refusal(pr=pr)
    assert "is gone" not in said
    forge.close_pr(pr=pr, reason="")
    _reopen()
    with pytest.raises(RuntimeError) as refused:
        forge.merge_pr(pr=pr)
    assert str(refused.value) == said == forge.pr_refusal(pr=pr)
    with pytest.raises(gitowner.Refused) as opened:
        forge.open_pr(head="beeverforge/77", base="main", title="t", body="b")
    assert str(opened.value) == said
    logged = [r.getMessage() for r in caplog.records]
    assert f"git was not run in {scene.repo}: {said}" in logged, logged
    return said


def _reopen() -> None:
    from beeverforge.adapters.board_db import connect

    with connect(write=True) as conn:
        conn.execute("UPDATE pull_requests SET state = 'open', refused = ''")


def _a_box_that_raises(monkeypatch, tmp_path, exc: BaseException):
    from beeverforge import box_prove
    from beeverforge.adapters.sandbox import registry as sandboxes

    class Box:
        def prepare(self, **_kw):
            raise exc

        def cleanup(self, **_kw):
            pass

        def harness_path(self, name):
            return name

    monkeypatch.setattr(box_prove, "PROOF_DIR", tmp_path / "proofs")  # its lock, never /var/lib
    monkeypatch.setattr(sandboxes, "installed_box_traits",
                        lambda _kind: SimpleNamespace(honours_image=False))
    monkeypatch.setattr(sandboxes, "build_sandbox", lambda *_a, **_kw: Box())
    project = SimpleNamespace(name="myapp", box=None)
    manifest = SimpleNamespace(base_branch="main", setup=[], validation={})
    return box_prove.box_probes(project, "img", repo_path=tmp_path, manifest=manifest,
                                key="myapp", sandbox="worktree")


def _the_box_line(probes):
    from beeverforge import box_prove

    proof = box_prove.prove("myapp", "img", replace(probes, inlined_documents=None,
                                                    machine_stamp=lambda: ""))
    return next(f for f in proof.findings if f.check == "box")


def test_the_proofs_box_line_is_the_refusal_and_its_remedy(monkeypatch, tmp_path):
    from beeverforge import gitowner

    reason = "the repository has two owners: work tree uid 1, git directory uid 0"
    remedy = f"give both one owner (`chown -R 1:1 /{'long/' * 120}x`)"
    with _a_box_that_raises(monkeypatch, tmp_path, gitowner.Refused(reason, remedy)) as probes:
        line = _the_box_line(probes)
    assert not line.ok and (line.message, line.remedy) == (reason, remedy)

    words = "fatal: detected dubious ownership in repository at '/srv/x'\n" + "more " * 100
    gits = gitowner.Refused(words, detail="cloning /srv/x into the box's workspace failed (128)")
    with _a_box_that_raises(monkeypatch, tmp_path, gits) as probes:
        line = _the_box_line(probes)
    assert line.message == words
    assert "git's own words" in line.remedy
    assert "leftover" not in line.remedy and "docker" not in line.remedy


def test_an_ordinary_start_error_reads_as_it_did(monkeypatch, tmp_path):
    with _a_box_that_raises(monkeypatch, tmp_path, RuntimeError("no such image")) as probes:
        line = _the_box_line(probes)
        older = _the_box_line(replace(probes, box_start_exception=lambda: None))
    for got in (line, older):
        assert got.message == "the box could not be started: no such image"
        assert "leftover container" in got.remedy and "docker ps -a" in got.remedy


@every_cause
def test_the_parks_cut_keeps_the_reason(scene, monkeypatch, cause):
    """The park keeps 150 characters of `Type: message`, and the proof 300."""
    from beeverforge.util.causes import describe

    scene.the_job_commits()
    reason, _remedy = cause(scene, monkeypatch)
    opens = reason if cause is not _a_repository_its_owner_cannot_enter else (
        f"the repository's owner, uid {UID}, cannot enter /")

    with pytest.raises(RuntimeError) as cloning:
        _the_boxs_clone(SimpleNamespace(repo=scene.repo, ws=scene.root / "roots" / "other"))
    with pytest.raises(RuntimeError) as pushing:
        _push(scene, str(scene.repo))

    assert describe(cloning.value, limit=150).startswith(f"Refused: {opens}")
    assert f"push failed: {opens}" in describe(pushing.value, limit=150)
    assert opens in str(pushing.value)[:300]


def test_the_longest_reason_fits_before_any_path(monkeypatch, shapes):
    from beeverforge import gitowner

    path, tree, git_dir = shapes["a symlinked git directory"]
    most = 2 ** 32 - 2
    said = []
    _owned_by(monkeypatch, {tree: (most, GID), git_dir: (most - 1, GID)})
    with pytest.raises(gitowner.Refused) as refused:
        gitowner.owner_of(path)
    said.append(refused.value.reason)
    monkeypatch.setattr(gitowner, "_setpriv", lambda: None)
    _owned_by(monkeypatch, {tree: (most, GID), git_dir: (most, GID)})
    with pytest.raises(gitowner.Refused) as refused, gitowner.upload_pack(path):
        pytest.fail("the call was let through")
    said.append(refused.value.reason)
    _owned_by(monkeypatch, {tree: (most, GID), git_dir: (most, GID)}, enters=lambda o, d: False)
    with pytest.raises(gitowner.Refused) as refused:
        gitowner.owner_of(path)
    said.append(refused.value.reason.partition("/")[0])

    assert [s for s in said if len(s) > 90] == []
    assert not [s for s in said if "not found" in s.lower()], "read as a branch already gone"


# ── the rest of each call's own promises ────────────────────────────────────────────────────────

def test_the_boxs_clone_is_quiet_only_where_it_is_switched(scene, monkeypatch):
    """A progress line before git's reason would be the first thing a cut message keeps."""
    _root_and_the_owner(scene, monkeypatch)
    _the_boxs_clone(scene)
    clone, = (c for c in scene.calls if "clone" in c.argv)
    assert clone.argv[-5:-3] == ["--quiet", *_options(clone)]


def _a_setpriv_that_fails(scene, monkeypatch, words: str) -> None:
    _root_and_the_owner(scene, monkeypatch)
    stand_in = scene.root / "bin" / "setpriv"
    stand_in.write_text(f"#!/bin/sh\necho {shlex.quote(words)} >&2\nexit 1\n")


@pytest.mark.parametrize(("call", "doing"), [
    (_the_boxs_clone, "cloning {repo} into the box's workspace failed (128)"),
    (_the_existing_branch_on_the_forge, "cloning {repo} into the box's workspace failed (128)"),
    (_the_forges_base, "could not read 'main' from the forge"),
    (_the_rebase_before_a_merge, "fetching 'main' to rebase onto it failed (128)"),
], ids=lambda v: v.__name__.strip("_") if callable(v) else "")
def test_gits_own_refusal_of_a_switched_read_leads_uncut_and_redacted(scene, monkeypatch, call,
                                                                      doing):
    from beeverforge import gitowner

    said = "fatal: https://user:secret@example.invalid " + "refused " * 80 + "at the end"
    _a_setpriv_that_fails(scene, monkeypatch, said)

    with pytest.raises(gitowner.Refused) as refused:
        call(scene)

    exc = refused.value
    assert exc.reason.startswith("fatal: https://***@example.invalid refused "), exc.reason
    assert "at the end" in exc.reason and "secret" not in str(exc)
    assert exc.remedy == "" and exc.detail.startswith(doing.format(repo=scene.repo))


def test_a_switched_read_that_said_nothing_says_what_failed(monkeypatch, tmp_path):
    """A clone a signal ended leaves no words of git's to lead with, nor to send anybody to."""
    from beeverforge import gitowner
    from beeverforge.adapters.sandbox import container

    monkeypatch.setattr(gitowner, "upload_pack", lambda _t: nullcontext(["--upload-pack=x"]))
    monkeypatch.setattr(container, "_host", lambda *a, **k: (-9, " \n"))
    with pytest.raises(gitowner.Refused) as refused:
        _the_boxs_clone(SimpleNamespace(repo=tmp_path / "repo", ws=tmp_path / "ws"))

    what = f"cloning {tmp_path / 'repo'} into the box's workspace failed (-9)"
    assert str(refused.value) == f"{what} — git said nothing more"
    with _a_box_that_raises(monkeypatch, tmp_path, refused.value) as probes:
        line = _the_box_line(probes)
    assert (line.message, line.remedy) == (what, "git said nothing more")


def test_an_existing_branch_the_owner_could_not_serve_leads_with_gits_words(scene, monkeypatch):
    from beeverforge import gitowner
    from beeverforge.adapters.sandbox.container import _materialize_workspace

    _a_setpriv_that_fails(scene, monkeypatch, "fatal: refused")
    with pytest.raises(gitowner.Refused) as refused:
        _materialize_workspace(repo_path=scene.cache, host_clone=scene.ws, base_branch="main",
                               branch=CARD, checkout_existing=True, remote_url=str(scene.repo))
    assert refused.value.reason.startswith("fatal: refused")
    assert refused.value.detail == f"fetching the existing branch {CARD!r} failed (128)"


def test_an_unswitched_failure_reads_as_it_did(scene, monkeypatch):
    from beeverforge import gitowner
    from beeverforge.adapters.sandbox import container

    said = "Cloning into 'x'...\nfatal: " + "no " * 200
    monkeypatch.setattr(container, "_host", lambda *a, **k: (128, said))

    for call, message in (
            (_the_boxs_clone, f"cloning {scene.repo} into the box's workspace failed (128): "
                              f"{said.strip()[:300]}"),
            (_the_rebase_before_a_merge, f"fetch failed: {said}")):
        with pytest.raises(RuntimeError) as failed:
            call(scene)
        assert str(failed.value) == message and not isinstance(failed.value, gitowner.Refused)
        shutil.rmtree(scene.ws, ignore_errors=True)


def test_a_base_the_owner_does_not_have_is_still_said_by_name(scene, monkeypatch):
    from beeverforge import gitowner
    from beeverforge.adapters.sandbox.container import _materialize_workspace

    _root_and_the_owner(scene, monkeypatch)
    with pytest.raises(RuntimeError) as refused:
        _materialize_workspace(repo_path=scene.cache, host_clone=scene.ws, base_branch="nowhere",
                               branch=JOB, checkout_existing=False, remote_url=str(scene.repo))
    assert not isinstance(refused.value, gitowner.Refused) and "nowhere" in str(refused.value)


def test_a_push_git_refuses_keeps_its_own_environment_and_reads_as_it_did(scene, monkeypatch):
    """Root's side of the forge door is what it was: only the side in the repository changes."""
    head = scene.the_job_commits()
    _root_and_the_owner(scene, monkeypatch)

    assert _push(scene, str(scene.repo), lease="") == head

    push, = (c for c in scene.calls if "push" in c.argv)
    assert push.how["env"]["WORKER_SECRET"] == "planted"
    assert push.how["env"]["GIT_SSH_COMMAND"] == "ssh -F /dev/null"
    assert f"--force-with-lease=refs/heads/{JOB}:" in push.argv
    assert "env WORKER_SECRET=planted" not in scene.log()
    _a_setpriv_that_fails(scene, monkeypatch, "fatal: refused")
    with pytest.raises(RuntimeError, match="^push failed: fatal: refused"):
        _push(scene, str(scene.repo))


def test_a_hosted_push_is_what_it_was_under_root(scene, monkeypatch):
    from beeverforge import gitpin
    from beeverforge.adapters.sandbox import container, host_push

    scene.the_job_commits()
    _root_and_the_owner(scene, monkeypatch, setpriv=False)
    ran = []

    def run(argv, timeout=120, env=None):
        ran.append(argv)
        return (0, "") if "push" in argv else container._host(argv, timeout=timeout, env=env)

    url = "https://user:secret@example.invalid/a.git"
    host_push.push_from_the_hosts_own_repository(
        git_dir=scene.ws / ".git", branch=JOB, target=url, run=run, redact=container._redact)

    ref = f"refs/heads/{JOB}"
    own = ran[-1][ran[-1].index("-C") + 1]
    assert ran[-1] == gitpin.argv(["-c", "core.hooksPath=/dev/null", "-C", own, "push", "--force",
                                   "--no-verify", "--", url, f"{ref}:{ref}"])


def test_a_refused_refresh_keeps_the_caches_master_and_is_logged_whole(scene, monkeypatch, caplog):
    from beeverforge.runtime.repo_cache import RepoCache, remote_default_branch

    cache = RepoCache(root=scene.root / "roots" / "served")
    served = cache.sync("p", str(scene.repo), "main")
    master = scene.root / "roots" / "served" / ".masters" / "p"
    assert served and (master / ".git").exists()
    reason, remedy = _a_repository_with_two_owners(scene, monkeypatch)

    for base in ("main", ""):
        caplog.clear()
        assert cache.sync("p", str(scene.repo), base) is None
        assert (master / ".git").exists(), "a refusal was read as a corrupt master"
        assert reason in caplog.text and f"git directory is {scene.repo / '.git'} (uid 0))" in (
            caplog.text), caplog.text
    assert remote_default_branch(str(scene.repo)) == ""
    _ok(master, "checkout", "-q", "--detach")
    assert cache.sync("p", str(scene.repo), "") is None
    assert (master / ".git").exists(), "the clone's refusal came after the master was deleted"


def test_another_failure_of_a_sync_is_cut_as_it_was(tmp_path, monkeypatch, caplog):
    from beeverforge.runtime.repo_cache import RepoCache

    def broken(*a, **k):
        raise RuntimeError("x" * 500)

    monkeypatch.setattr(RepoCache, "_sync", broken)
    assert RepoCache(root=tmp_path).sync("p", "https://example.invalid/a", "main") is None
    assert "x" * 160 in caplog.text and "x" * 161 not in caplog.text


def test_a_members_repository_is_git_run_as_its_own_owner(scene, monkeypatch):
    """The directory the call is about decides, not the project's own."""
    from beeverforge import gitowner

    _root_and_the_owner(scene, monkeypatch)
    first = gitowner._ownership
    monkeypatch.setattr(gitowner, "_ownership", lambda p: (
        (77, 78) if Path(p).is_relative_to(scene.bare) else first(p)))
    forge = scene.forge()
    monkeypatch.setattr(forge, "clone_url", lambda repo: str(scene.bare if repo else scene.repo))

    assert forge.list_branches() == forge.list_branches("another") == [CARD, "main"]

    assert [(c.how["user"], c.argv[2]) for c in scene.calls] == [
        (UID, str(scene.repo)), (77, str(scene.bare))]


def test_the_scratch_tree_is_handed_to_the_owner_and_gone_after(scene, monkeypatch, own_tmp):
    from beeverforge import gitowner

    given = []
    _root_and_the_owner(scene, monkeypatch)
    kept = gitowner._chown
    monkeypatch.setattr(gitowner, "_chown", lambda p, uid, gid: (
        given.append((Path(p).name.rpartition("-")[0], uid, gid)), kept(p, uid, gid)))

    _update_branch(scene)

    assert ("beeverforge-rebase", UID, GID) in given
    in_tree = [c for c in scene.calls if "beeverforge-rebase-" in c.argv[2]]
    assert in_tree and all(c.how["user"] == UID for c in in_tree)
    assert list(own_tmp.iterdir()) == []


def test_a_directory_that_cannot_be_handed_over_escapes_nothing(scene, monkeypatch, own_tmp):
    from beeverforge import gitowner

    forge, pr = scene.a_pull_request()
    _commit(scene.repo, "moved.py", "MOVED = True\n")
    before = _ok(scene.repo, "rev-parse", CARD)
    asked = []

    def refused(path):
        asked.append(path)
        raise gitowner.Refused("why")

    with monkeypatch.context() as m:
        _root_and_the_owner(scene, m)
        hand, given = gitowner.hand_to_the_owner_of, own_tmp / "given"
        given.mkdir()
        m.setattr(gitowner, "_chown", lambda *a: (_ for _ in ()).throw(PermissionError(1, "no")))
        assert hand(str(scene.repo), str(given)) is None
        assert forge.update_branch(pr=pr) is False
        m.setattr(gitowner, "owner_of", refused)
        assert hand(str(scene.repo), str(given)) is None and asked
        given.rmdir()
    assert _ok(scene.repo, "rev-parse", CARD) == before
    assert list(own_tmp.iterdir()) == []


def test_a_head_that_could_not_be_read_is_not_a_branch_that_is_gone(scene, monkeypatch):
    """Git's own words when it runs as the owner and cannot be run there; the branch is gone when
    git can be, and nothing is recorded for the merge then, as before."""
    forge, pr = scene.a_pull_request()
    _ok(scene.repo, "branch", "-D", CARD)
    _root_and_the_owner(scene, monkeypatch)
    gone = f"the branch {CARD} is gone from this repository"

    with pytest.raises(RuntimeError, match=f"^{gone} — nothing to merge$"):
        forge.merge_pr(pr=pr)
    assert forge.pr_refusal(pr=pr) == ""
    assert forge.mergeable_state(pr=pr) == "dirty" and forge.pr_refusal(pr=pr) == gone

    def unreadable(argv, **how):
        return subprocess.CompletedProcess(argv, 128, "", "fatal: detected dubious ownership\n")

    _reopen()
    with monkeypatch.context() as m:
        m.setattr(subprocess, "run", unreadable)
        with pytest.raises(RuntimeError, match="^fatal: detected dubious ownership$"):
            forge.merge_pr(pr=pr)
        assert forge.pr_refusal(pr=pr) == "fatal: detected dubious ownership"
        _reopen()
        assert forge.mergeable_state(pr=pr) == "dirty"
        assert forge.pr_refusal(pr=pr) == "fatal: detected dubious ownership"
        m.setattr(os, "geteuid", lambda: 1000)
        _reopen()
        with pytest.raises(RuntimeError, match=f"^{gone} — nothing to merge$"):
            forge.merge_pr(pr=pr)


def test_a_forge_call_that_takes_too_long_is_still_a_timeout(scene, monkeypatch):
    _root_and_the_owner(scene, monkeypatch)

    def slow(argv, **how):
        raise subprocess.TimeoutExpired(argv, how["timeout"])

    monkeypatch.setattr(subprocess, "run", slow)
    with pytest.raises(subprocess.TimeoutExpired):
        scene.forge().list_branches()


def test_the_operations_guide_says_who_git_runs_as():
    text = (ROOT / "docs" / "operations.md").read_text(encoding="utf-8")
    start = text.index("## The compose stack, or the worker image as one container")
    section = " ".join(text[start:text.index("\n## ", start + 1)].split())
    said = [s for s in section.split(". ") if "local forge" in s and "owner" in s]
    assert len(said) == 1, said
    for word in ("root", "the box's clone", "the repository cache", "the job's push",
                 "the local forge's git", "refused", "remedy"):
        assert word in said[0], word


def test_a_refusal_survives_being_pickled():
    import pickle

    from beeverforge import gitowner

    exc = pickle.loads(pickle.dumps(gitowner.Refused("why", "what to do", "while cloning")))

    assert (exc.reason, exc.remedy, exc.detail) == ("why", "what to do", "while cloning")
    assert str(exc) == "why — what to do — while cloning"
