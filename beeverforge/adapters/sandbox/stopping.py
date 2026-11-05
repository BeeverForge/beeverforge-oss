"""A STOP THAT REACHES THE WORK, NOT ONLY ITS WORKFLOW (#44).

`stop` terminates a job's workflow. The job's work is not there: `run_job` runs the blocking
`JobRunner` in a worker thread (`asyncio.to_thread`), and a Python thread cannot be cancelled. So
on a deployment a stopped job went on through its agent pass and, 46 minutes later, opened a pull
request, merged it and said "Merged" on the stopped card, while the slot it had freed ran another
card of the same repository.

`Stop` is the one object both halves hold. The activity's heartbeat loop, which is awake, calls
`request` when the engine says the workflow is gone. That sets a flag the runner thread checks
before each step that reaches the forge or the board (`JobRunner._unless_stopped`, which raises
`JobStopped`), and SIGKILLs every process group the job's box started, so the agent pass in
flight ends now instead of at its four-hour wall.

THREAD-SAFE BY ONE LOCK, and the lock is what closes the race: a box that starts a command after
the stop was requested is killed the moment it adopts it, so no command started between the stop
and the runner's next check outlives it.
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
from collections.abc import Iterator
from contextlib import contextmanager


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


class Stop:
    """The flag a job's runner checks, and the process groups its box started."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._groups: set[int] = set()
        self.why = ""

    @property
    def requested(self) -> bool:
        return self._event.is_set()

    def request(self, why: str = "") -> None:
        """End the work: set the flag and kill every group adopted so far. Idempotent — the first
        reason stays, and a second call only kills again what is still adopted."""
        with self._lock:
            if not self._event.is_set():
                self.why = why
                self._event.set()
            groups = list(self._groups)
        for pgid in groups:
            _kill_group(pgid)

    def adopt(self, proc: subprocess.Popen) -> None:
        """A command the box just started in its own group (`process_group=0`, so its pid is its
        group id). Killed at once when the stop is already requested."""
        with self._lock:
            if not self._event.is_set():
                self._groups.add(proc.pid)
                return
        _kill_group(proc.pid)

    def release(self, proc: subprocess.Popen) -> None:
        """The command returned: its group id is no longer this job's to signal."""
        with self._lock:
            self._groups.discard(proc.pid)


def own_group(stop: Stop | None) -> dict[str, int]:
    """The `Popen` keyword that puts a stoppable box's command in a group of its own — nothing for
    a box that carries no stop, which keeps today's behaviour (see `base.run_and_stream`)."""
    return {"process_group": 0} if stop is not None else {}


@contextmanager
def adopted(stop: Stop | None, proc: subprocess.Popen) -> Iterator[None]:
    """`proc` belongs to `stop` while the block runs."""
    if stop is None:
        yield
        return
    stop.adopt(proc)
    try:
        yield
    finally:
        stop.release(proc)
