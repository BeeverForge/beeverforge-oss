"""A STOP THAT REACHES THE WORK, NOT ONLY ITS WORKFLOW (#44).

`stop` terminates a job's workflow. The job's work is not there: `run_job` runs the blocking
`JobRunner` in a worker thread (`asyncio.to_thread`), and a Python thread cannot be cancelled. So
on a deployment a stopped job went on through its agent pass and, 46 minutes later, opened a pull
request, merged it and said "Merged" on the stopped card, while the slot it had freed ran another
card of the same repository.

`Stop` is the one object both halves hold. The activity's heartbeat loop, which is awake, calls
`request` when the engine says the workflow is gone. That sets a flag the runner thread checks
before each step that reaches the forge or the board (`JobRunner._unless_stopped`, which raises
`JobStopped`), and kills what the job's box started, so the agent pass in flight ends now instead
of at its four-hour wall.

THE RUNNER ALSO ASKS THE ENGINE ITSELF before each of those steps (`confirm`, review of #453). The
heartbeat loop hears a terminate only when a heartbeat reaches the server, and temporalio throttles
heartbeats to `min(0.8 × heartbeat_timeout, max_heartbeat_throttle_interval)` — 60 s with the
job's 120 s timeout and the SDK's default (temporalio 1.35, `worker/_worker.py`). A runner whose
agent finished inside that minute would publish; `ask`, set by the heartbeat loop, closes it.

WHAT IS KILLED, AND WHY TWO WAYS (review of #453, measured). A process group alone does not hold
a job's processes: a background child outlives the command that started it (`npm run dev &`), and
a descendant that starts a session of its own leaves the group altogether (`setsid`, Node's
`spawn(..., {detached: true})`, a browser launcher). Claude Code is one: measured on this machine
(claude 2.1.317, started in a group of its own as the box starts it), every Bash tool command ran
with `pid == pgid == sid`, a session of its own, outside the harness's group. So:

- A GROUP STAYS ADOPTED UNTIL IT IS EMPTY, not until its leader returns (`settle`).
  `os.killpg(pgid, 0)` raising `ProcessLookupError` is the moment to let it go: a group id cannot
  be handed to anybody else while any member of it lives.
- EVERY PROCESS THE JOB STARTED CARRIES `MARK` IN ITS ENVIRONMENT (`MARK_VAR=<this stop's mark>`,
  set by the box), which every descendant inherits through `setsid` and a detached spawn alike;
  `request` kills each process whose `/proc/<pid>/environ` carries it. It reaches the agent's own
  tool commands: measured with claude 2.1.317 and `BEEVERFORGE_JOB_MARK` set in its environment, a
  Bash tool command it ran saw the variable (`env | grep -c` gave 1) while being its own session
  leader (`pid == sid == pgid`), out of the group's reach. LINUX ONLY: elsewhere there
  is no `/proc` to read, and the stop degrades to the group kill. Not airtight even on Linux: a
  process started with a cleared environment (`env -i`) drops the mark, and only a per-job cgroup
  would hold that one — which a worker without cgroup delegation cannot create.

THREAD-SAFE BY ONE LOCK, and the lock is what closes the race: a box that starts a command after
the stop was requested is killed the moment it adopts it, so no command started between the stop
and the runner's next check outlives it.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import threading
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

log = logging.getLogger("beeverforge.sandbox.stopping")

#: The variable a job's box puts in each command's environment, valued with its stop's `mark`.
MARK_VAR = "BEEVERFORGE_JOB_MARK"

#: How many sweeps of `/proc` a stop makes at most: one finds what runs, and the next ones find a
#: child forked while the first was reading. Bounded, because a sweep that kept finding processes
#: would be a fork bomb, and the stop must return.
_SWEEPS = 8


class JobStopped(BaseException):
    """The job was stopped by a person, and this step was not taken.

    A `BaseException`, NOT an `Exception`, and deliberately. The runner's best-effort writes —
    `_preserve_for_hold`, `_preserve_partial`, `_say_on_ticket`, the knowledge gate — catch
    `Exception` and carry on; a stop they swallowed would carry on to the push or the comment it
    exists to prevent. It leaves through `run()`'s `finally`, which removes the worktree."""

    def __init__(self, step: str, why: str = "") -> None:
        self.step = step
        self.why = why
        super().__init__(f"the job was stopped before `{step}`" + (f" ({why})" if why else ""))


def _kill_group(pgid: int) -> None:
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        # gone already (it finished, or another stop got there first): nothing left to end
        pass


def _group_is_empty(pgid: int) -> bool:
    """No process is left in group `pgid` — the only moment its id may be let go of."""
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False  # somebody lives in it: not ours to signal, and not empty
    return False


_PROC = Path("/proc")


def _marked(needle: bytes) -> set[int]:
    """The pids whose environment carries `needle` (`NAME=value`), read from `/proc`. Empty where
    there is no `/proc`. A process that went, or that is not this user's, is passed over."""
    if not sys.platform.startswith("linux") or not _PROC.is_dir():
        return set()
    found = set()
    me = os.getpid()
    for entry in _PROC.iterdir():
        if not entry.name.isdigit() or int(entry.name) == me:
            continue
        try:
            environ = (entry / "environ").read_bytes()
        except OSError:
            continue
        if needle in environ.split(b"\0"):
            found.add(int(entry.name))
    return found


def _kill_marked(needle: bytes) -> None:
    """SIGKILL every process carrying `needle`, sweeping again while a sweep finds a new one."""
    killed: set[int] = set()
    for _ in range(_SWEEPS):
        fresh = _marked(needle) - killed
        if not fresh:
            return
        for pid in fresh:
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        killed |= fresh
    log.warning("BEEVERFORGE_JOB_STOP_SWEEPS a stop swept /proc %s times and was still finding "
                "processes of the job; what started after the last sweep was not killed", _SWEEPS)


class Stop:
    """The flag a job's runner checks, the process groups its box started, and the mark its
    commands carry."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._groups: set[int] = set()
        self.why = ""
        #: This job's own value of `MARK_VAR`: random, so no other job's process carries it.
        self.mark = uuid.uuid4().hex
        #: The engine's answer, asked from the runner's thread (`confirm`): a reason when the
        #: job's workflow is no longer running, None while it is or when the engine cannot say.
        #: Set by the activity's heartbeat loop; None asks nothing.
        self.ask: Callable[[], str | None] | None = None
        #: The attempt ended without a person ending the job (#259): its activity timed out and
        #: the job's workflow is still running. Killed like a stop, but what the agent wrote is
        #: committed and pushed to the job's branch before the worktree goes (`keeping`). A later
        #: request that keeps nothing (a person's stop) clears it.
        self.keep = False
        self._keeping = False
        #: Held by `request` from before the flag is set until its last kill is done, and taken by
        #: `keeping` before the window opens (#259, found on main's CI after #503): the kill sweeps
        #: `/proc` for this job's mark up to `_SWEEPS` times, and the keep's own commands carry the
        #: mark, so a window opened during the sweep had its `git commit` killed and the work was
        #: lost with the worktree.
        self._killing = threading.Lock()

    @property
    def requested(self) -> bool:
        return self._event.is_set()

    def confirm(self) -> bool:
        """Whether the job is stopped, asking the engine when the heartbeat has not said so yet —
        and requesting the stop when it answers that the workflow is gone."""
        if self.requested:
            return True
        ask = self.ask
        why = ask() if ask is not None else None
        if why:
            self.request(why)
        return self.requested

    def env(self) -> dict[str, str]:
        """What a job's box adds to each command's environment."""
        return {MARK_VAR: self.mark}

    def request(self, why: str = "", *, keep: bool = False) -> None:
        """End the work: set the flag, kill every group adopted so far and every process carrying
        this job's mark. Idempotent — the first reason stays, and a second call only kills again
        what is still there.

        `keep` (#259): the attempt ended and the job did not — keep what the agent wrote
        (`keeping`). Only the first request can ask for it; a request that keeps nothing clears
        it, so a person's stop arriving after a timeout publishes nothing."""
        with self._killing:
            with self._lock:
                if not self._event.is_set():
                    self.why = why
                    self.keep = keep
                    self._event.set()
                elif not keep:
                    self.keep = self._keeping = False  # a person's stop closes an open window too
                groups = list(self._groups)
            for pgid in groups:
                _kill_group(pgid)
            _kill_marked(f"{MARK_VAR}={self.mark}".encode())

    def adopt(self, proc: subprocess.Popen) -> None:
        """A command the box just started in its own group (`process_group=0`, so its pid is its
        group id). Killed at once when the stop is already requested."""
        with self._lock:
            self._prune()
            if not self._event.is_set() or self._keeping:
                self._groups.add(proc.pid)
                return
        _kill_group(proc.pid)

    @property
    def keeping_now(self) -> bool:
        """Inside `keeping`: the runner is committing and pushing what the attempt wrote."""
        return self._keeping

    def still_keeping(self) -> bool:
        """Inside `keeping`, whether the push may still go: ASKS THE ENGINE (review of #503).
        Nothing else can deliver a person's stop here — the heartbeat loop has handled its one
        cancellation and beats no more — so a workflow that is no longer running (a person stopped
        the job while its timed-out attempt was keeping) closes the window through `request`,
        which keeps nothing. An engine that cannot say leaves the window open: the workflow was
        running when the timeout was read, and the push is the job's own branch."""
        if not self._keeping:
            return False
        ask = self.ask
        why = ask() if ask is not None else None
        if why:
            self.request(why)
        return self._keeping

    @contextmanager
    def keeping(self) -> Iterator[bool]:
        """The window in which a timed-out attempt's runner keeps its work (#259): the commands
        it starts run instead of being killed on adoption, and its publishing checks let the push
        through. Yields whether there is anything to keep — False for a stop that keeps nothing,
        and then the window does not open.

        NOT BEFORE THE KILL IS OVER (`_killing`): the keep's commands carry the job's mark, and a
        sweep still running would kill them."""
        with self._killing, self._lock:
            self._keeping = self.keep
        try:
            yield self._keeping
        finally:
            with self._lock:
                self._keeping = False

    def settle(self, proc: subprocess.Popen) -> None:
        """The command returned. Its group is let go of only once it is EMPTY: a child it left
        running in the background is still the job's, and still killed by a stop."""
        with self._lock:
            if _group_is_empty(proc.pid):
                self._groups.discard(proc.pid)
            self._prune()

    def _prune(self) -> None:
        """Let go of every group that has emptied since (under the lock)."""
        self._groups = {g for g in self._groups if not _group_is_empty(g)}


def own_group(stop: Stop | None) -> dict[str, int]:
    """The `Popen` keyword that puts a stoppable box's command in a group of its own — nothing for
    a box that carries no stop, which keeps today's behaviour (see `base.run_and_stream`)."""
    return {"process_group": 0} if stop is not None else {}


@contextmanager
def adopted(stop: Stop | None, proc: subprocess.Popen) -> Iterator[None]:
    """`proc`'s group belongs to `stop` while the block runs, and after it for as long as anything
    is left in it."""
    if stop is None:
        yield
        return
    stop.adopt(proc)
    try:
        yield
    finally:
        stop.settle(proc)
