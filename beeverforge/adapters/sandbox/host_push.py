"""The host's push, from a git directory the host owns (#386).

A PASS CAN WRITE THE GIT CONFIGURATION OF THE REPOSITORY IT WORKS IN. On the worktree box that is
the common `.git/config` and the worktree's `config.worktree`; on the container box it is the host
clone bind-mounted as /workspace. The push used to run with that repository as its git directory,
so it read the pass's configuration with the forge's credential in hand: `url.<base>.insteadOf`
and `pushInsteadOf` sent the authenticated push wherever the pass chose (no `-c` override reaches
them key by key, because the pass picks `<base>`), and `core.sshCommand` named a program the host
ran.

SO THE PUSH NEVER RUNS THERE. Each push makes a bare repository of its own outside every mount,
fetches the job's branch into it as objects (the pass's repository is only a path source), and
pushes from it, with the forge's URL as an argument: never written into any config, and read
against the host's own configuration alone. The directory goes when the push is done.

WHAT THE FETCH STILL READS. `upload-pack` runs in the pass's repository and reads its config, and
runs no program named there: `uploadpack.packObjectsHook` is honoured only from protected
configuration (system, global, command line), not from the repository's (git-config(1)). The
tests beside this run git 2.43.0 under a pass-written `core.sshCommand` and `core.fsmonitor` whose
stand-ins leave a sentinel if anything runs them, and none does
(`tests/test_a_pass_written_git_config_never_steers_the_hosts_push.py`).
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

from beeverforge import gitpin

#: The box's own door to the host: `(argv, timeout=…) -> (exit code, output)`.
Runner = Callable[..., tuple[int, str]]


def push_from_the_hosts_own_repository(*, source: Path, branch: str, target: str, run: Runner,
                                       redact: Callable[[str], str]) -> None:
    """Push `branch` of `source` to `target`, from a bare repository the host makes for it.

    Raises RuntimeError starting `push failed:` naming the step that failed; the temporary
    repository is removed either way."""
    ref = f"refs/heads/{branch}"
    own = Path(tempfile.mkdtemp(prefix="beeverforge-push-"))
    try:
        rc, out = run(["git", "init", "--bare", "-q", str(own)])
        if rc != 0:
            raise RuntimeError(
                f"push failed: could not make the host's own repository to push {branch!r} from "
                f"(git init exited {rc}): {redact(out).strip()[:300]} — check that the host's "
                "temporary directory is writable and has space")
        rc, out = run(gitpin.argv(["-c", "core.hooksPath=/dev/null", "-C", str(own), "fetch",
                                   "--no-tags", "--", str(source), f"+{ref}:{ref}"]),
                      timeout=180)
        if rc != 0:
            raise RuntimeError(
                f"push failed: could not bring {branch!r}'s commits out of the job's repository "
                f"{source} into the host's own (git fetch exited {rc}): "
                f"{redact(out).strip()[:300]} — check that the branch still exists in the job's "
                "repository, then publish again")
        rc, out = run(gitpin.argv(["-c", "core.hooksPath=/dev/null", "-C", str(own), "push",
                                   "--force", "--", target, f"{ref}:{ref}"]))
        if rc != 0:
            raise RuntimeError(f"push failed: {redact(out)}")
    finally:
        shutil.rmtree(own, ignore_errors=True)
