"""The host's push, from a git directory the host owns (#386).

A JOB CAN WRITE THE GIT CONFIGURATION OF THE REPOSITORY IT WORKS IN. On the worktree box that is
the common `.git/config` and the worktree's `config.worktree`; on the container box it is the host
clone bind-mounted as /workspace. The push used to run with that repository as its git directory,
so it read the job's configuration with the forge's credential in hand: `url.<base>.insteadOf`
and `pushInsteadOf` sent the authenticated push wherever the job chose (no `-c` override reaches
them key by key, because the job picks `<base>`), and `core.sshCommand` named a program the host
ran.

SO NO GIT COMMAND RUNS IN THE JOB'S REPOSITORY. Each push makes a bare repository of its own
outside every mount and borrows the job's objects through `objects/info/alternates`, which git
reads as object directories and nothing else: no configuration, no hooks, no refs. The branch's
commit is read from the job's ref file (or `packed-refs`) as data, and refused unless it is a plain
object name. Which git directory that is was settled before the job ran: the worktree box reads
its repository's common directory in `prepare`, and the container box refuses a clone whose `.git`
is no longer a directory (a job can repoint either at another repository). The push then runs in
the host's own repository, with the forge's URL as an argument, never written into any config. The
directory goes when the push is done, pass or fail.

THE LEASE, AND KEEPING WHAT IT REFUSED, GO THE SAME WAY (#11). The push replaces only the tip the
workspace last saw (`--force-with-lease`), and answers the commit it pushed, read as data, so the
next lease needs no git command in the job's repository. When the lease is refused, the remote's
tip is copied to a branch of its own (`keep_the_remote_tip`) by a fetch and a push run in a host
repository made the same way and under the same door's configuration; the fetch's negotiation is
told not to run `for-each-ref` in the borrowed repository (`core.alternateRefsCommand`).

NO GIT VERSION IS RELIED ON FOR THIS (review of #403). The design before this one fetched the
branch into the host's repository, and the fetch ran git's serving side (`upload-pack`) in the
job's repository, which reads its config; whether that config could make it run a program was a
question of git's version (the partial-clone lazy-fetch class, closed in the May 2024 security
releases: 2.45.1 and the matching maintenance releases). Nothing runs there now, on any git. The
borrowing also means nothing is copied: the push sends what the forge lacks, as the push from the
job's repository did. Measured on git 2.43.0 (2026-11-03, a branch one commit ahead of a forge
holding its base, a repository of 1.4 GiB packed): 55 to 70 s per push with the fetch, under the
fetch's 180 s timeout, and 20 ms with the borrowing; 0.3 to 1.2 s and 17 ms on two of 11 and 16
MiB.

AN OBJECTS DIRECTORY THAT REACHES ELSEWHERE IS REFUSED (review of #403). Git follows the borrowed
directory's own `info/alternates` recursively, and follows any symlink inside it, so a job that
wrote either (on the container box, naming a host path the box cannot even see, such as another
project's cache) could make the push send that directory's objects to this project's forge. So
before anything is borrowed the push walks the job's `objects` with `lstat`, following no link,
and refuses a symlink anywhere in it (`objects` itself, `info`, `pack`, a fan-out directory, an
object file), any entry that is neither a regular file nor a directory, and an
`info/alternates` or `info/http-alternates`. No box makes any of these. Before #386, and with
the fetch, git followed all of them.

THE WALK RUNS ONCE, so what holds it still differs by box (review of #403). The container box
pauses its container (`docker pause`) before the ref is read and the walk runs, and unpauses it
only once the push's git calls are done: nothing the job left running in it can plant a link in
between, and if the pause fails nothing is pushed. The worktree box has no container to freeze, so
a process the job left running can still plant one between the walk and git reading the objects;
that process runs as the worker's user, who can already read every repository that user can, so
what it could have pushed is what it could already read.

WHICH CONFIGURATION THE PUSH READS, PER DOOR:

  * THE FORGE DOOR (a forge URL, which carries the token): the host's own repository's config and
    the command line, nothing else. On the worktree box the job runs as the worker's user with the
    worker's HOME, so the user-level git config and the user's ssh config are the job's to write
    too, and so is the system config wherever that user can write it (review of #403).
    The calls run with `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=/dev/null`, `HOME` and
    `XDG_CONFIG_HOME` pointed at an empty directory of the push's own (`GIT_CONFIG_GLOBAL` is git
    2.32+, and HOME is also where curl reads `.netrc`), and `GIT_SSH_COMMAND="ssh -F /dev/null"`,
    which reads no ssh configuration file. The forge's URL is all this push needs; a proxy or a CA
    a deployment set in its git config does not reach it, and must be set in the environment
    (`HTTPS_PROXY`, `GIT_SSL_CAINFO`).
  * THE AMBIENT DOOR (no forge URL: the `origin` the repository had before the job ran). It is the
    person's own push, with the person's own credential, so it keeps what that credential lives
    in: the user-level and system git config (a credential helper, a URL rewrite the person set)
    and the user's ssh config (keys, host aliases). The box passes the environment it runs in.
    The worktree box gives it the workload's own scrubbed environment, so a program a job names
    in those files runs as the job's user with the job's environment, which is nothing the job
    cannot already run, and the person's credential it reaches is one the job, as that user, can
    already read; `SECURITY.md` (credential reach) says so. The container box gives it the
    worker's own environment: no mount puts the worker's HOME in that box's reach.

Hooks are off in the host's repository (`core.hooksPath=/dev/null` on every call made there, so a
hooks directory the ambient door's user config names, or a template hook it copies in, never
runs), and every call carries the transport pin (`gitpin.argv`).

WHAT THIS DOES NOT COVER. With the local forge the target is a repository on this machine, and git
starts its receiving side there, under that repository's own config and hooks: that is the local
forge's reach, tracked with the other host-side calls in #400.
"""

from __future__ import annotations

import errno
import os
import re
import shutil
import tempfile
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

from beeverforge import gitpin
from beeverforge.adapters.sandbox.base import LEASE_REFUSED, PushRefused

#: The box's own door to the host: `(argv, timeout=…, env=…) -> (exit code, output)`.
Runner = Callable[..., tuple[int, str]]

#: A plain object name, lower-case hex as git writes it in a ref: SHA-1, and SHA-256, which is
#: recognised only to be refused by name.
_OBJECT_NAME = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")

#: Hooks off in the host's own repository, for every call made there.
_HOOKLESS = ("-c", "core.hooksPath=/dev/null")

#: The longest ref file this reads, as data. A ref is one line; a packed-refs file of a
#: very large repository is megabytes, never this.
_MOST = 64 * 1024 * 1024


def push_from_the_hosts_own_repository(*, git_dir: Path, branch: str, target: str, run: Runner,
                                       redact: Callable[[str], str],
                                       ambient_env: Mapping[str, str] | None = None,
                                       lease: str | None = None) -> str:
    """Push `branch` of the job's repository whose git directory is `git_dir` (the common one, for
    a linked worktree) to `target`, from a bare repository the host makes for it. Answers the
    commit it pushed, read as data from the job's ref before anything ran, so the caller's next
    lease is that commit with no git command run in the job's repository to learn it.

    `ambient_env` is None for the forge door (`target` is the forge's URL): the push reads no
    configuration but its own repository's. Given, it is the ambient door: the push keeps the
    user-level and system configuration and runs in `ambient_env` (see the module docstring).

    `lease` is what the push may replace (`Workspace.lease`, #11): None is a plain `--force`;
    otherwise `--force-with-lease=<ref>:<lease>`, where `""` says the branch must not be on the
    remote at all. A refused lease raises `PushRefused`, so the machine can keep the remote's
    commits (`keep_the_remote_tip`) before it pushes again.

    Raises RuntimeError starting `push failed:` naming the step that failed, with a remedy; the
    temporary directory is removed either way."""
    with _the_hosts_own_repository(git_dir=git_dir, branch=branch, run=run, redact=redact,
                                   ambient_env=ambient_env) as (own, env, ref, commit):
        # --no-verify beside the hooks override, as main's push had it (#182): a pre-push hook is
        # handed the authenticated URL
        rc, out = run(gitpin.argv([*_HOOKLESS, "-C", str(own), "push", *_force(ref, lease),
                                   "--no-verify", "--", target, f"{ref}:{ref}"]), env=env)
        if rc != 0:
            if LEASE_REFUSED in out:
                raise PushRefused(f"push refused: {redact(out)}", branch=branch)
            raise RuntimeError(f"push failed: {redact(out)}")
        return commit


def keep_the_remote_tip(*, git_dir: Path, branch: str, target: str, run: Runner,
                        redact: Callable[[str], str],
                        ambient_env: Mapping[str, str] | None = None) -> tuple[str, str]:
    """Copy the remote's tip of `branch` to a branch of its own on the remote (#11). Answers
    `(the kept branch's name, the tip)`; the caller leases its next push on that tip, so a commit
    landing between this copy and the push is refused again.

    WHAT A REFUSED LEASE DOES NEXT. The branch holds commits the workspace did not start from — a
    person's fix, the work a park preserved, a re-run's leftover — and the run must still land its
    own work there unattended (a self-heal resume, a card moved back). So the commits are copied
    first, to `<branch>-kept-<12 hex>`, and only then replaced. NEVER FORCED: a ref already at that
    name holding the same commit is "up to date"; one holding anything else refuses, and the caller
    holds the job rather than replace it.

    FROM THE HOST'S OWN REPOSITORY, as the push is (#386): the fetch and the push run in the bare
    repository `_the_hosts_own_repository` makes, under the same door's configuration, so the
    job's `insteadOf` or `core.sshCommand` never meets the forge's credential here either. It
    borrows the job's objects and names the job's branch, so the fetch tells the remote it has
    them and receives only the commits the job does not hold. `core.alternateRefsCommand` is
    `true` on the fetch: by default git runs `for-each-ref` in a borrowed repository to learn what
    it holds, which is a git command run in the job's repository; the branch named here is all the
    negotiation needs."""
    with _the_hosts_own_repository(git_dir=git_dir, branch=branch, run=run, redact=redact,
                                   ambient_env=ambient_env) as (own, env, ref, _):
        theirs = "refs/beeverforge/remote-tip"
        rc, out = run(gitpin.argv([*_HOOKLESS, "-c", "core.alternateRefsCommand=true", "-C",
                                   str(own), "fetch", "-q", "--no-tags", "--", target,
                                   f"+{ref}:{theirs}"]), timeout=180, env=env)
        if rc != 0:
            raise RuntimeError(f"could not read {branch!r} on the remote to keep it: "
                               f"{redact(out).strip()[:300]}")
        rc, out = run(gitpin.argv([*_HOOKLESS, "-C", str(own), "rev-parse", "--verify", "--quiet",
                                   f"{theirs}^{{commit}}"]), env=env)
        tip = out.strip()
        if rc != 0 or not _OBJECT_NAME.fullmatch(tip):
            raise RuntimeError(f"could not read {branch!r} on the remote to keep it: "
                               f"{redact(out).strip()[:300]}")
        kept = f"{branch}-kept-{tip[:12]}"
        rc, out = run(gitpin.argv([*_HOOKLESS, "-C", str(own), "push", "--no-verify", "--",
                                   target, f"{tip}:refs/heads/{kept}"]), env=env)
        if rc != 0:
            raise RuntimeError(f"could not keep {branch!r} on {kept!r}: "
                               f"{redact(out).strip()[:300]}")
        return kept, tip


def _force(ref: str, lease: str | None) -> list[str]:
    """How the push may replace the remote's branch: over the lease, or plainly when there is none
    (`Workspace.lease`). One spelling for both boxes, which the semaphore guard reads as a job
    branch's push."""
    if lease is None:
        return ["--force"]
    return [f"--force-with-lease={ref}:{lease}"]


@contextmanager
def _the_hosts_own_repository(*, git_dir: Path, branch: str, run: Runner,
                              redact: Callable[[str], str],
                              ambient_env: Mapping[str, str] | None
                              ) -> Iterator[tuple[Path, dict[str, str], str, str]]:
    """A bare repository of the host's own, outside every mount, borrowing the job's objects and
    naming the job's branch: `(its path, the door's environment, the ref, the branch's commit)`.
    The ref is read as data and the objects walked first (module docstring); the directory goes
    when the caller is done, pass or fail."""
    ref = f"refs/heads/{branch}"
    commit = _the_branchs_commit(git_dir, branch)
    _borrows_nothing(git_dir)
    scratch = Path(tempfile.mkdtemp(prefix="beeverforge-push-"))
    try:
        own = scratch / "repo.git"
        env = dict(ambient_env) if ambient_env is not None else _own_configuration_only(scratch)
        # hooks off here too (review of #403): from git 2.46 `init` writes HEAD through a ref
        # transaction, and a `reference-transaction` hook the person's config names runs on it
        rc, out = run(gitpin.argv([*_HOOKLESS, "init", "--bare", "-q", str(own)]), env=env)
        if rc != 0:
            raise RuntimeError(
                f"push failed: could not make the host's own repository to push {branch!r} from "
                f"(git init exited {rc}): {redact(out).strip()[:300]} — check that the host's "
                "temporary directory is writable and has space")
        (own / "objects" / "info").mkdir(parents=True, exist_ok=True)
        (own / "objects" / "info" / "alternates").write_text(f"{git_dir / 'objects'}\n")
        rc, out = run(gitpin.argv([*_HOOKLESS, "-C", str(own), "update-ref", ref, commit]),
                      env=env)
        if rc != 0:
            raise RuntimeError(
                f"push failed: could not bring {branch!r}'s commits out of the job's repository "
                f"{git_dir}: its branch names {commit}, which its objects do not hold (git "
                f"update-ref exited {rc}): {redact(out).strip()[:300]} — check that the job's "
                "repository is whole (`git fsck`), then publish again")
        yield own, env, ref, commit
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _own_configuration_only(scratch: Path) -> dict[str, str]:
    """The forge door's environment: the host's, with no git or ssh configuration file the job
    could write in reach. HOME is an empty directory of this push's own."""
    home = scratch / "home"
    home.mkdir()
    env = dict(os.environ)
    env.update({
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "GIT_SSH_COMMAND": "ssh -F /dev/null",
    })
    return env


def _borrows_nothing(git_dir: Path) -> None:
    """Refused, with a cause and a remedy, when the job's objects directory could hand the push
    anything but its own objects:

      * a symlink ANYWHERE under `objects` (and `objects` itself): the pack directory, a
        loose-object fan-out directory, an object file, `info`. Git follows each one, so a link
        reaches another directory's objects exactly as an alternates entry does (review of
        #403). The walk uses `lstat` alone and follows no link;
      * an entry that is neither a regular file nor a directory (a FIFO, a device, a socket),
        which git would open;
      * `info/alternates` or `info/http-alternates` present. Git follows an alternates chain
        recursively, so a job that wrote one could make the push send objects from any object
        directory on the host, another project's cache included. No box makes one (neither the
        cache, the worktree box nor the container clone, which is `--no-local`).

    ONCE, JUST BEFORE THE PUSH: on the container box the container is paused around it and the
    push (`ContainerSandbox.publish_branch`); on the worktree box a process the job left running
    could still plant one of these between this walk and git reading the objects (module
    docstring).

    WHAT THE WALK COSTS, measured 2026-11-03 (warm cache, five runs each): this repository's
    objects, 3,216 entries, 5 to 6 ms; a 1.38 GiB repository, 1,453 entries, 3 to 4 ms; two
    others of 16 MiB and 570 MiB, 3,607 and 2,556 entries, 5 to 6 and 4 to 5 ms. The walk is over
    the fan-out directories and the pack directory, so it grows with the loose objects, not with
    the size of the history."""
    objects = git_dir / "objects"
    if objects.is_symlink():
        raise _a_link(objects)
    pending = [objects]
    while pending:
        where = pending.pop()
        try:
            entries = list(os.scandir(where))
        except OSError as exc:
            raise RuntimeError(
                f"push failed: could not read {where} in the job's repository ({exc.strerror}) "
                "— check that the host can read the job's repository, then publish again") from exc
        for entry in entries:
            path = Path(entry.path)
            if entry.is_symlink():
                raise _a_link(path)
            if entry.is_dir(follow_symlinks=False):
                pending.append(path)
            elif not entry.is_file(follow_symlinks=False):
                raise RuntimeError(
                    f"push failed: {path} in the job's repository is neither a file nor a "
                    "directory, and git would open it — remove it (or run the job again), then "
                    "publish again")
    for name in ("alternates", "http-alternates"):
        borrowed = objects / "info" / name
        try:
            os.lstat(borrowed)
        except (FileNotFoundError, NotADirectoryError):
            continue
        raise RuntimeError(
            f"push failed: the job's repository {git_dir} borrows objects from elsewhere "
            f"({borrowed}), which the host's push never follows — make the repository hold its "
            f"own objects (`git repack -a -d`, then remove {borrowed}), or run the job again, "
            "then publish again")


def _a_link(path: Path) -> RuntimeError:
    return RuntimeError(
        f"push failed: {path} in the job's repository is a symlink, which the host does not "
        "follow — replace it with what it points at (or run the job again), then publish again")


def _the_branchs_commit(git_dir: Path, branch: str) -> str:
    """The object name `refs/heads/<branch>` holds in `git_dir`, read as data: the loose ref file,
    else its line in `packed-refs`. Refused, with a cause and a remedy, when the ref is missing,
    symbolic, a symlink, or anything but a plain object name, and when the repository keeps its
    refs in a reftable, which this does not read."""
    ref = f"refs/heads/{branch}"
    if (git_dir / "reftable").exists():
        raise RuntimeError(
            f"push failed: the job's repository {git_dir} keeps its refs in a reftable, which the "
            "host does not read — convert it with `git refs migrate --ref-format=files`, then "
            "publish again")
    loose = _read_as_data(git_dir / ref, ref=ref, git_dir=git_dir)
    if loose is not None:
        return _plain(loose.rstrip("\n"), ref=ref, git_dir=git_dir, branch=branch)
    packed = _read_as_data(git_dir / "packed-refs", ref="packed-refs", git_dir=git_dir) or ""
    for line in packed.splitlines():
        if line.startswith(("#", "^")):
            continue
        name, _, refname = line.partition(" ")
        if refname == ref:
            return _plain(name, ref=ref, git_dir=git_dir, branch=branch)
    raise RuntimeError(
        f"push failed: could not bring {branch!r}'s commits out of the job's repository "
        f"{git_dir}: it has no such branch — check that the branch still exists in the job's "
        "repository, then publish again")


def _plain(name: str, *, ref: str, git_dir: Path, branch: str) -> str:
    if _OBJECT_NAME.fullmatch(name) and len(name) == 64:
        # The host's repository is made SHA-1, and git cannot borrow SHA-256 objects into it.
        # Refused by name rather than left to fail in update-ref's words; GitHub hosts no SHA-256
        # repository, so no deployment here has been measured pushing one.
        raise RuntimeError(
            f"push failed: the job's repository {git_dir} names its objects with SHA-256, which "
            "the host's push does not support — publish from a SHA-1 repository")
    if _OBJECT_NAME.fullmatch(name):
        return name
    raise RuntimeError(
        f"push failed: {ref} in the job's repository {git_dir} is not a plain object name (a "
        f"symbolic ref, or not a ref at all) — point it at the commit to publish (`git branch -f "
        f"{branch} <commit>`), then publish again")


def _read_as_data(path: Path, *, ref: str, git_dir: Path) -> str | None:
    """`path`'s text, never through a symlink at its last component; None when it is not there."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except (FileNotFoundError, NotADirectoryError, IsADirectoryError):
        return None
    except OSError as exc:
        if exc.errno != errno.ELOOP:
            raise RuntimeError(
                f"push failed: could not read {ref} in the job's repository {git_dir} "
                f"({exc.strerror}) — check that the host can read the job's repository, then "
                "publish again") from exc
        raise RuntimeError(
            f"push failed: {ref} in the job's repository {git_dir} is a symlink, which the host "
            "does not follow — replace it with the file itself, then publish again") from exc
    try:
        with os.fdopen(fd, "rb") as fh:
            data = fh.read(_MOST)
    except IsADirectoryError:
        return None
    return data.decode("ascii", errors="replace")
