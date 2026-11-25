"""Who git runs as for a path, and how a call is made to run as that user.

THE WORKER AND THE PANEL RUN AS ROOT ON THE COMPOSE STACK, and a local-forge project's repository
belongs to a person. Git refuses root there ("detected dubious ownership", exit 128). Trusting the
repository (`safe.directory`) makes the calls pass and leaves root's files in it: measured in the
worker image (git 2.47.3, a repository of uid 1000), 14 to 17 entries of 57 were root's after a
clone, a push and a merge, the person could not edit a merged file, delete the job's branch or run
`git gc`, and a hook of theirs ran as root. Run as the owner, git has nothing to refuse: 0 entries
were root's, and all of that worked.

So, when the process is root and another user owns the repository, the git that reads or writes
inside it runs as that user. Not root, or root's own repository: every call is what it was.

TWO FORMS, BECAUSE GIT IS STARTED TWO WAYS. `running_as_owner` is for a git this process starts.
`upload_pack` and `receive_pack` are for the side git starts itself, in the repository a clone, a
fetch or a push names: root's side stays root's, and only the served side switches.

THE ENVIRONMENT IS A SHORT LIST, NEVER THE WORKER'S. The repository's hooks and filters run in
that process, and the worker's environment holds credentials. `HOME` is an empty directory of the
call's own, so root's configuration is not read.

WHAT IS LEFT TO GIT. A path that is no repository, or whose ownership cannot be read, is not
switched: git run as root answers for it as it always did, and still refuses a repository it finds
by walking up. The common directory of a linked worktree is not looked at either.
"""

from __future__ import annotations

import os
import shlex
import shutil
import stat
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import NamedTuple
from urllib.parse import unquote

#: How long the one attempt to enter a directory as the owner may take.
_ENTER_TIMEOUT = 60
#: The most of a `.git` file that is read: it is one line naming a path.
_GITDIR_MOST = 8192


class Owner(NamedTuple):
    """The user git runs as, and the group: the git directory's."""

    uid: int
    gid: int


class Refused(RuntimeError):
    """A repository that cannot be reached as its owner, or that git refused its owner.

    `reason` opens with fixed words and the uids, before any path, so what is cut off a long
    message is never the cause. `remedy` is empty where the cause was not identified. `detail` is
    what was being done. A `RuntimeError`, so a caller that reported git's failure reports this."""

    def __init__(self, reason: str, remedy: str = "", detail: str = "") -> None:
        super().__init__(" — ".join(part for part in (reason, remedy, detail) if part))
        self.reason, self.remedy, self.detail = reason, remedy, detail

    def __reduce__(self):
        return (Refused, (self.reason, self.remedy, self.detail))


# ── who ─────────────────────────────────────────────────────────────────────────────────────────

def owner_of(path: object) -> Owner | None:
    """Who git runs as in the repository at `path`, or None for "as today". Raises `Refused` when
    its work tree and git directory have two owners, or its owner cannot enter it."""
    if os.geteuid() != 0 or not path:
        return None
    try:
        found = _repository_at(str(path))
        if found is None:
            return None
        tree, git_dir = found
        of_tree, of_git = Owner(*_ownership(tree)), Owner(*_ownership(git_dir))
    except OSError:
        return None
    if of_tree.uid != of_git.uid:
        raise _two_owners(tree, git_dir, of_tree, of_git)
    if of_git.uid == 0:
        return None
    _refuse_where_shut(of_git, tree, git_dir)
    return of_git


def is_switched(path: object) -> bool:
    """Whether git in the repository at `path` runs as its owner, or is refused."""
    try:
        return owner_of(path) is not None
    except Refused:
        return True


def _repository_at(path: str) -> tuple[Path, Path] | None:
    """The resolved work tree and git directory of `path`, or None when it is no repository's top.
    A bare repository is its own git directory."""
    tree = Path(os.path.realpath(path))
    dot = tree / ".git"
    if dot.is_dir():
        return tree, Path(os.path.realpath(dot))
    if dot.is_file():
        named = _gitdir_named(dot)
        return (tree, Path(os.path.realpath(tree / named))) if named else None
    if (tree / "HEAD").is_file() and (tree / "objects").is_dir():
        return tree, tree
    return None


def _gitdir_named(dot: Path) -> str:
    with open(dot, encoding="utf-8", errors="surrogateescape") as fh:
        text = fh.read(_GITDIR_MOST)
    prefix = "gitdir: "
    return text.removeprefix(prefix).rstrip("\r\n") if text.startswith(prefix) else ""


def _ownership(path: Path) -> tuple[int, int]:
    st = os.stat(path)
    return st.st_uid, st.st_gid


def _two_owners(tree: Path, git_dir: Path, of_tree: Owner, of_git: Owner) -> Refused:
    """The command names the owner that is not root, and the path the other one has."""
    keep, change = (of_tree, git_dir) if of_tree.uid else (of_git, tree)
    return Refused(
        f"the repository has two owners: work tree uid {of_tree.uid}, git directory uid "
        f"{of_git.uid}",
        f"give both one owner (`chown -R {keep.uid}:{keep.gid} {shlex.quote(str(change))}`): the "
        f"work tree is {tree} (uid {of_tree.uid}) and the git directory is {git_dir} (uid "
        f"{of_git.uid})")


# ── whether the owner can get there ─────────────────────────────────────────────────────────────

def _refuse_where_shut(owner: Owner, *ends: Path) -> None:
    on_the_way = dict.fromkeys(d for end in ends for d in (*reversed(end.parents), end))
    for directory in on_the_way:
        if not _can_enter(owner, directory):
            raise Refused(
                f"the repository's owner, uid {owner.uid}, cannot enter {directory}",
                f"let that user enter it (`chmod o+x {shlex.quote(str(directory))}`), or move the "
                "repository")


def _can_enter(owner: Owner, directory: Path) -> bool:
    """The mode bits, and only where they deny, one attempt as that user: an access list opens a
    directory the bits do not."""
    return _bits_let_in(owner, directory) or _tried_and_entered(owner, directory)


def _bits_let_in(owner: Owner, directory: Path) -> bool:
    try:
        st = os.stat(directory)
    except OSError:
        return False
    if st.st_uid == owner.uid:
        return bool(st.st_mode & stat.S_IXUSR)
    if st.st_gid == owner.gid:
        return bool(st.st_mode & stat.S_IXGRP)
    return bool(st.st_mode & stat.S_IXOTH)


def _tried_and_entered(owner: Owner, directory: Path) -> bool:
    """A COMMAND RUN AS THE USER, never `cwd=`: the process changes directory before it changes
    user, so `cwd=` would be tried as root. An attempt that could not be made, or did not end,
    denies nothing; what git says next stands."""
    try:
        tried = subprocess.run(["test", "-x", str(directory)], capture_output=True, check=False,
                               timeout=_ENTER_TIMEOUT, **_as(owner, _kept_from_the_worker()))
    except (OSError, subprocess.TimeoutExpired):
        return True
    return tried.returncode == 0


# ── how ─────────────────────────────────────────────────────────────────────────────────────────

@contextmanager
def running_as_owner(path: str) -> Iterator[tuple[str, dict]]:
    """For a git this process starts in the repository at `path`: what to hand `-C`, and the
    process arguments. `path` itself and none, where there is no switch.

    An `OSError` while it starts is refused in its own words. A timeout stays a timeout."""
    owner = owner_of(path)
    if owner is None:
        yield path, {}
        return
    with _an_empty_home(owner) as home, _said_as_a_refusal(owner):
        yield os.path.realpath(path), _as(owner, _environment(home))


def upload_pack(target: object) -> AbstractContextManager[list[str]]:
    """The option of a clone, a fetch or an ls-remote that reads `target`: none, or the one word
    that makes the side serving it run as the repository's owner."""
    return _served(target, "upload-pack", GIT_PROTOCOL="version=2")


def receive_pack(target: object) -> AbstractContextManager[list[str]]:
    """The same for a push that writes `target`."""
    return _served(target, "receive-pack")


@contextmanager
def _served(target: object, side: str, **more: str) -> Iterator[list[str]]:
    """GIT STARTS THIS SIDE, with the environment of the git that starts it: for the push's forge
    door, the worker's whole environment. So `env -i` empties it and sets the short list, then
    `setpriv` changes the user. Git hands the command to a shell, so every word is quoted."""
    owner = owner_of(_local_path(target))
    if owner is None:
        yield []
        return
    if not _setpriv():
        raise Refused(
            f"git cannot run as the repository's owner, uid {owner.uid}: `setpriv` is missing",
            "the worker image must hold util-linux's `setpriv`; the image this version publishes "
            "does")
    with _an_empty_home(owner) as home:
        names = {**_environment(home), **more}
        command = shlex.join(["env", "-i", *(f"{name}={value}" for name, value in names.items()),
                              "setpriv", "--reuid", str(owner.uid), "--regid", str(owner.gid),
                              "--clear-groups", f"git-{side}"])
        yield [f"--{side}={command}"]


def hand_to_the_owner_of(path: str, directory: str) -> None:
    """Give `directory`, this process's own, to whoever git runs as at `path`. Left as it is when
    that is refused: the git call that follows says why."""
    try:
        owner = owner_of(path)
        if owner is not None:
            _chown(directory, *owner)
    except (Refused, OSError):
        return


def _local_path(target: object) -> str:
    """The path `target` names on this machine, or `""`. Absolute paths and `file://` URLs only: a
    remote's name is not a path, and a relative one is read from wherever git stands."""
    text = str(target or "")
    if text.startswith("file://"):
        text = unquote(text.removeprefix("file://"))
    return text if text.startswith("/") else ""


def _setpriv() -> str | None:
    return shutil.which("setpriv")


def _chown(path: str, uid: int, gid: int) -> None:
    os.chown(path, uid, gid)


def _as(owner: Owner, env: dict[str, str]) -> dict:
    """The process arguments that start a command as `owner`. From `/`, because the worker's own
    directory may be one the owner cannot enter."""
    return {"user": owner.uid, "group": owner.gid, "extra_groups": [], "cwd": "/", "env": env}


def _kept_from_the_worker() -> dict[str, str]:
    """All that crosses from the worker's environment: where programs are, and the locale."""
    return {"PATH": os.environ.get("PATH") or os.defpath,
            **{name: value for name, value in os.environ.items()
               if name in ("LANG", "LANGUAGE") or name.startswith("LC_")}}


def _environment(home: str) -> dict[str, str]:
    """One list for every switched git. No configuration but the repository's own is read."""
    return {**_kept_from_the_worker(), "HOME": home, "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0"}


@contextmanager
def _an_empty_home(owner: Owner) -> Iterator[str]:
    """An empty directory of the call's own, the owner's alone, gone when the call ends."""
    with _said_as_a_refusal(owner):
        home = tempfile.mkdtemp(prefix="beeverforge-git-home-")
    try:
        with _said_as_a_refusal(owner):
            _chown(home, *owner)
        yield home
    finally:
        shutil.rmtree(home, ignore_errors=True)


@contextmanager
def _said_as_a_refusal(owner: Owner) -> Iterator[None]:
    try:
        yield
    except OSError as exc:
        raise Refused("git could not be started as the repository's owner, uid "
                      f"{owner.uid}: {exc}") from exc
