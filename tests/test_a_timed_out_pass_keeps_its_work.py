"""A pass that runs past its time limit keeps what it wrote, and Resume continues it (#259).

The engine cancels a timed-out activity saying the task is gone (`not_found`) — with `timed_out`
when the worker's own timer fired first, and without it when the server noticed first. #44 read
`not_found` as a person's stop: the agent was killed, the worktree removed and nothing pushed, and
the workflow's park then resumed from the base. On a deployment three of four long passes lost
their commits that way in one day.

Real git and the real worktree box, as #44's end-to-end stop test runs them; the timeout is the
cancel the engine delivers, so nothing here waits for a clock.
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
from pathlib import Path

import pytest
from temporalio.activity import ActivityCancellationDetails

from beeverforge.adapters.sandbox.stopping import JobStopped, Stop
from tests import test_a_stopped_job_ends_its_agent_and_publishes_nothing as stopped
from tests.test_walking_skeleton import repo  # noqa: F401 — the fixture the harness builds on

_LINUX = os.name == "posix" and Path("/proc").is_dir()

origin_and_repo = stopped.origin_and_repo
BRANCH = "beeverforge/1"


def _remote(origin: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(origin), *args], check=True, capture_output=True,
                          text=True).stdout.strip()


class _CommittingAgent(stopped._BlockingAgent):
    """A pass that commits part of its work, leaves the rest written but uncommitted, and then
    blocks until it is ended — the shape of a four-hour pass the ceiling cuts."""

    def __init__(self, fifo: Path, files: tuple[str, str] = ("committed.py", "uncommitted.py"),
                 *, leaves_a_lock: bool = False):
        super().__init__(fifo)
        self.files = files
        self.found: set[str] = set()
        self.leaves_a_lock = leaves_a_lock

    def execute(self, *, sandbox, workspace, context):
        where = Path(workspace.path)
        self.found = {p.name for p in where.iterdir()}  # what the run started from
        committed, uncommitted = self.files
        (where / committed).write_text("DONE = 1\n")
        for args in (["add", committed],
                     ["-c", "user.email=agent@example.invalid", "-c", "user.name=agent",
                      "commit", "-qm", "the part the agent committed"]):
            subprocess.run(["git", "-C", str(where), *args], check=True, capture_output=True)
        (where / uncommitted).write_text("HALF = 1\n")
        if self.leaves_a_lock:  # a git the kill ends mid-write leaves its lock behind
            lock = subprocess.run(["git", "-C", str(where), "rev-parse", "--path-format=absolute",
                                   "--git-path", "index.lock"], check=True, capture_output=True,
                                  text=True).stdout.strip()
            Path(lock).write_text("")
        return super().execute(sandbox=sandbox, workspace=workspace, context=context)


async def _a_pass_cut_by(details, client, origin_and_repo, tmp_path, *, then=None,
                         files=("committed.py", "uncommitted.py"), resume_handle=None,
                         box_class=None, tag="1", leaves_a_lock=False):
    """Run a job whose agent blocks, cancel its activity with `details` (the engine answering
    `describe` through `client`, and answering `then` from the cancel on), and answer what the job
    left behind. `resume_handle` is the handle the run is resumed with; `box_class` a box of the
    test's own (`stopped._Box`'s shape)."""
    from temporalio.testing import ActivityEnvironment

    from beeverforge.contracts import Manifest
    from beeverforge.observability import InMemoryEventSink
    from beeverforge.orchestrator import JobRunner
    from beeverforge.runtime.temporal.activities import _heartbeat_while

    _, repo_path = origin_and_repo
    fifo = tmp_path / f"pid-{tag}.fifo"
    os.mkfifo(fifo)
    stop = Stop()
    hooks = stopped._Hooks(stop, at="")
    forge, tracker, reviewer = stopped._fakes(hooks)
    agent = _CommittingAgent(fifo, files, leaves_a_lock=leaves_a_lock)
    box = (box_class or stopped._Box)(root=tmp_path / f"wt-{tag}", hooks=hooks)
    runner = JobRunner(
        tracker=tracker, forge=forge, agent=agent, sandbox=box,
        manifest=Manifest(merge_policy="auto", validate={"test": "true", "security": "true"}),
        repo_path=repo_path, reviewer=reviewer, events=InMemoryEventSink())
    runner.hears(stop)

    env = ActivityEnvironment(client=client)
    job = asyncio.create_task(env.run(
        _heartbeat_while, lambda: runner.run("#1", resume_handle=resume_handle), "p#1", stop=stop))
    pid = None
    try:
        reading = asyncio.ensure_future(asyncio.to_thread(fifo.read_text))
        await asyncio.wait({reading, job}, return_when=asyncio.FIRST_COMPLETED)
        if not reading.done():
            with open(fifo, "w"):
                pass
            await reading
            pytest.fail(f"the job ended before its agent ran: {job.result()!r}")
        pid = int(reading.result().strip())

        if then is not None:
            client.answer = then  # the engine's state once the cancel is sent
        env.cancel(details)
        with pytest.raises(asyncio.CancelledError):
            await job
        return agent, forge, box, stop
    finally:
        if pid is not None:
            stopped._kill_quietly(pid)
        if not job.done():
            job.cancel()


@pytest.mark.skipif(not _LINUX, reason="the box's stop reads /proc")
@pytest.mark.parametrize("details,answer", [
    (ActivityCancellationDetails(not_found=True, timed_out=True), None),
    (ActivityCancellationDetails(not_found=True), "RUNNING"),
], ids=["the_workers_timer", "the_server_noticed_first"])
async def test_a_timed_out_pass_is_ended_and_what_it_wrote_reaches_its_branch(
        details, answer, origin_and_repo, tmp_path):
    from temporalio.client import WorkflowExecutionStatus

    origin, _ = origin_and_repo
    client = stopped._Client(getattr(WorkflowExecutionStatus, answer)) if answer else None

    agent, forge, box, stop = await _a_pass_cut_by(details, client, origin_and_repo, tmp_path)

    rc, _ = agent.ran
    assert rc == -signal.SIGKILL, f"the timed-out pass was not ended: it ended {rc}"
    assert stop.keep, "the timeout was read as a person's stop"
    pushed = _remote(origin, "ls-tree", "-r", "--name-only", f"refs/heads/{BRANCH}")
    assert "committed.py" in pushed, "the commit the pass made did not reach its branch"
    assert "uncommitted.py" in pushed, "what the pass wrote but had not committed was lost"
    assert forge.opened is None and forge.merge_calls == 0, "a timed-out pass went on to publish"
    assert agent.workspace is not None and not agent.workspace.exists(), (
        "the timed-out pass's worktree was not removed")
    assert box.cleanups == 1


@pytest.mark.skipif(not _LINUX, reason="the box's stop reads /proc")
async def test_a_stop_the_engine_confirms_keeps_nothing(origin_and_repo, tmp_path):
    """`not_found` with the workflow TERMINATED is a person's stop: nothing is pushed. The engine
    says RUNNING while the pass works (the runner asks it before each step) and TERMINATED once
    the stop is in."""
    from temporalio.client import WorkflowExecutionStatus

    origin, _ = origin_and_repo
    client = stopped._Client(WorkflowExecutionStatus.RUNNING)

    agent, forge, _, stop = await _a_pass_cut_by(
        ActivityCancellationDetails(not_found=True), client, origin_and_repo, tmp_path,
        then=WorkflowExecutionStatus.TERMINATED)

    assert agent.ran[0] == -signal.SIGKILL
    assert not stop.keep
    assert stopped._never_pushed(origin), "a person's stop pushed the job's branch"
    assert client.asked, "the engine was never asked whether the workflow still runs"


@pytest.mark.skipif(not _LINUX, reason="the box's stop reads /proc")
async def test_resume_after_the_timeout_starts_from_what_the_pass_kept(origin_and_repo, tmp_path):
    """The park's handle makes the next run restore the branch: the commit and the uncommitted
    file of the timed-out pass are in its worktree before its agent writes anything."""
    from beeverforge.contracts import AgentRunResult, Manifest
    from beeverforge.contracts.run import FROM_THE_FORGE
    from beeverforge.observability import NullEventSink
    from beeverforge.orchestrator import JobRunner

    _, repo_path = origin_and_repo
    await _a_pass_cut_by(ActivityCancellationDetails(not_found=True, timed_out=True), None,
                         origin_and_repo, tmp_path)

    seen: list[set[str]] = []

    class _Continuing:
        def execute(self, *, sandbox, workspace, context):
            seen.append({p.name for p in Path(workspace.path).iterdir()})
            return AgentRunResult(ok=True, summary="finished", cost_usd=0.01)

        def repair(self, *, sandbox, workspace, context, failure_log):
            return AgentRunResult(ok=True)

    hooks = stopped._Hooks(Stop(), at="")
    forge, tracker, reviewer = stopped._fakes(hooks)
    JobRunner(
        tracker=tracker, forge=forge, agent=_Continuing(),
        sandbox=stopped._Box(root=tmp_path / "wt2", hooks=hooks),
        manifest=Manifest(merge_policy="auto", validate={"test": "true", "security": "true"}),
        repo_path=repo_path, reviewer=reviewer, events=NullEventSink(),
    ).run("#1", resume_handle=FROM_THE_FORGE)

    assert seen, "the resumed run never reached its agent"
    assert {"committed.py", "uncommitted.py"} <= seen[0], (
        f"the resumed run did not start from what the timed-out pass kept: {sorted(seen[0])}")


@pytest.mark.skipif(not _LINUX, reason="the box's stop reads /proc")
async def test_a_person_who_stops_the_job_while_it_keeps_its_work_gets_nothing_pushed(
        origin_and_repo, tmp_path):
    """The real path (review of #503): the heartbeat loop has handled its one cancel and beats no
    more, so the person's stop reaches the keep only through the engine's answer. It says RUNNING
    while the pass works and TERMINATED from the timeout on — the person stopped the job as its
    attempt timed out — and the keep asks it before the push."""
    from temporalio.client import WorkflowExecutionStatus

    origin, _ = origin_and_repo
    client = stopped._Client(WorkflowExecutionStatus.RUNNING)

    _, forge, box, stop = await _a_pass_cut_by(
        ActivityCancellationDetails(not_found=True, timed_out=True), client, origin_and_repo,
        tmp_path, then=WorkflowExecutionStatus.TERMINATED)

    assert len(client.asked) > 1, "the keep never asked the engine before its push"
    assert not stop.keep, "the person's stop did not close the keep"
    assert box.pushes == 0 and stopped._never_pushed(origin), "the keep pushed after the stop"
    assert box.cleanups == 1


@pytest.mark.skipif(not _LINUX, reason="the box's stop reads /proc")
async def test_two_timeouts_in_a_row_keep_both_passes_on_the_branch(origin_and_repo, tmp_path):
    """The second Resume restores the branch the first keep pushed, so its own keep pushes over
    the tip it started from — its lease — and nothing of the first pass is replaced or set aside."""
    from beeverforge.contracts.run import FROM_THE_FORGE

    origin, _ = origin_and_repo
    timed_out = ActivityCancellationDetails(not_found=True, timed_out=True)
    await _a_pass_cut_by(timed_out, None, origin_and_repo, tmp_path,
                         files=("first.py", "first_half.py"), tag="1")
    second, *_ = await _a_pass_cut_by(timed_out, None, origin_and_repo, tmp_path,
                                      files=("second.py", "second_half.py"),
                                      resume_handle=FROM_THE_FORGE, tag="2")

    assert {"first.py", "first_half.py"} <= second.found, (
        f"the second attempt did not start from the first one's work: {sorted(second.found)}")
    pushed = set(_remote(origin, "ls-tree", "-r", "--name-only", f"refs/heads/{BRANCH}").split())
    assert {"first.py", "first_half.py", "second.py", "second_half.py"} <= pushed, pushed
    kept = _remote(origin, "for-each-ref", "--format=%(refname)", "refs/heads/")
    assert "-kept-" not in kept, f"the second keep set the first pass aside: {kept}"


class _RefusedBox(stopped._Box):
    """A box whose push fails after the commit: the forge refused it."""

    def publish_branch(self, *, workspace, remote_url=None) -> None:
        self.pushes += 1
        raise RuntimeError("push failed: the forge refused the push")


@pytest.mark.skipif(not _LINUX, reason="the box's stop reads /proc")
async def test_a_keep_whose_push_fails_leaves_the_commit_on_the_local_branch(
        origin_and_repo, tmp_path):
    """Nothing reaches the forge, the worktree goes as always, and what the pass wrote is
    committed on the job's branch in the repository the worktree was added to
    (`kept_after_cleanup`), where a person can push it by hand."""
    origin, repo_path = origin_and_repo

    _, _, box, _ = await _a_pass_cut_by(
        ActivityCancellationDetails(not_found=True, timed_out=True), None, origin_and_repo,
        tmp_path, box_class=_RefusedBox)

    assert box.pushes == 1 and stopped._never_pushed(origin)
    assert box.cleanups == 1
    local = _remote(repo_path, "ls-tree", "-r", "--name-only", f"refs/heads/{BRANCH}").split()
    assert {"committed.py", "uncommitted.py"} <= set(local), (
        f"the pass's work is not on the local branch after the failed push: {local}")
    assert _remote(repo_path, "status", "--porcelain") == "", "the keep left the repository dirty"


class _SlowPushBox(stopped._Box):
    """A box whose push waits for the test to let it go, and says when the job's walk is over."""

    def __init__(self, **kw) -> None:
        import threading

        super().__init__(**kw)
        self.release = threading.Event()
        self.reached = threading.Event()
        self.over = threading.Event()

    def publish_branch(self, *, workspace, remote_url=None) -> None:
        self.reached.set()
        assert self.release.wait(60), "the test never let the push go"
        super().publish_branch(workspace=workspace, remote_url=remote_url)

    def cleanup(self, *, workspace) -> None:
        super().cleanup(workspace=workspace)
        self.over.set()


@pytest.mark.skipif(not _LINUX, reason="the box's stop reads /proc")
async def test_a_keep_that_outlives_the_activitys_wait_finishes_whole(
        origin_and_repo, tmp_path, monkeypatch):
    """The activity waits a bounded time for the keep (`_A_TIMED_OUT_ATTEMPT_KEEPS_WITHIN`) and
    then returns; the runner's thread goes on. Held here mid-push past that wait, then let go: the
    branch gets the whole commit and the worktree goes — nothing is left half-kept."""
    from beeverforge.runtime.temporal import activities

    origin, _ = origin_and_repo
    # 0, NOT A SHORT WAIT (review of #503): `asyncio.wait(..., timeout=0)` returns at once with
    # the thread still pending, which is the case, and nothing here waits on a clock
    monkeypatch.setattr(activities, "_A_TIMED_OUT_ATTEMPT_KEEPS_WITHIN", 0)
    boxes: list[_SlowPushBox] = []

    class _Recorded(_SlowPushBox):
        def __init__(self, **kw) -> None:
            super().__init__(**kw)
            boxes.append(self)

    await _a_pass_cut_by(ActivityCancellationDetails(not_found=True, timed_out=True), None,
                         origin_and_repo, tmp_path, box_class=_Recorded)
    box = boxes[0]
    assert box.reached.wait(30), "the keep never reached its push"
    assert stopped._never_pushed(origin) and not box.over.is_set(), (
        "the case proves nothing: the keep finished inside the activity's wait")

    box.release.set()
    assert box.over.wait(30), "the runner's thread never finished its keep"
    pushed = _remote(origin, "ls-tree", "-r", "--name-only", f"refs/heads/{BRANCH}").split()
    assert {"committed.py", "uncommitted.py"} <= set(pushed), pushed
    assert box.cleanups == 1


@pytest.mark.parametrize("details,answer,timed_out", [
    (ActivityCancellationDetails(not_found=True, timed_out=True), None, True),
    (ActivityCancellationDetails(not_found=True), "RUNNING", True),
    (ActivityCancellationDetails(not_found=True), "TERMINATED", False),
    (ActivityCancellationDetails(not_found=True), "CANCELED", False),
    (ActivityCancellationDetails(not_found=True), "UNREACHABLE", False),
    (ActivityCancellationDetails(cancel_requested=True), "RUNNING", False),
    (ActivityCancellationDetails(worker_shutdown=True), "RUNNING", False),
    (None, "RUNNING", False),
], ids=["the_workers_timer", "server_first_running", "terminated", "canceled", "no_answer",
        "cancel_requested", "worker_shutdown", "no_details"])
async def test_a_timed_out_attempt_is_told_from_a_stop(details, answer, timed_out):
    """The first question, on its own: the end-to-end cases also pass through the keep's second
    one (`Stop.still_keeping`), which would hide a misread here."""
    from temporalio.client import WorkflowExecutionStatus
    from temporalio.service import RPCStatusCode
    from temporalio.testing import ActivityEnvironment

    from beeverforge.runtime.temporal.activities import _the_attempt_timed_out

    said = (stopped._rpc(RPCStatusCode.UNAVAILABLE) if answer == "UNREACHABLE"
            else getattr(WorkflowExecutionStatus, answer) if answer else None)
    client = stopped._Client(said) if said is not None else None

    assert await ActivityEnvironment(client=client).run(_the_attempt_timed_out, details) \
        is timed_out


@pytest.mark.skipif(not _LINUX, reason="the box's stop reads /proc")
async def test_a_lock_a_killed_git_left_does_not_cost_the_keep(origin_and_repo, tmp_path):
    """Found on main's CI after #503: a git the kill ended mid-write left `index.lock`, the keep's
    commit refused ("File exists"), and the work went with the worktree. Planted here, so the case
    does not depend on where the kill lands."""
    origin, _ = origin_and_repo

    await _a_pass_cut_by(ActivityCancellationDetails(not_found=True, timed_out=True), None,
                         origin_and_repo, tmp_path, leaves_a_lock=True)

    pushed = _remote(origin, "ls-tree", "-r", "--name-only", f"refs/heads/{BRANCH}").split()
    assert {"committed.py", "uncommitted.py"} <= set(pushed), (
        f"a stale index lock cost the timed-out pass its work: {pushed}")


# ── the stop's keeping window ───────────────────────────────────────────────────────────────────

def _a_group_sleeping() -> subprocess.Popen:
    return subprocess.Popen(["sleep", "60"], process_group=0)


def test_a_keeping_stop_runs_the_commands_of_its_window_and_kills_the_rest():
    stop = Stop()
    stop.request("ran past its limit", keep=True)
    inside = _a_group_sleeping()
    try:
        with stop.keeping() as keep:
            assert keep
            stop.adopt(inside)
            assert inside.poll() is None, "the keep's own command was killed"
        outside = _a_group_sleeping()
        stop.adopt(outside)
        assert outside.wait(timeout=5) == -signal.SIGKILL, "a command after the window ran"
    finally:
        for proc in (inside,):
            if proc.poll() is None:
                proc.kill()
                proc.wait()


def test_the_keeping_window_opens_only_once_the_kill_is_over(monkeypatch):
    """Found on main's CI after #503: the kill sweeps `/proc` for the job's mark, the keep's own
    `git commit` carries the mark, and a window opened mid-sweep had its commit killed — the work
    was lost with the worktree. Here the sweep holds until the runner is waiting to open the window
    (or has opened it), and the order they happened in is the answer. No clock: events and a lock
    that says when it is waited on."""
    import threading

    from beeverforge.adapters.sandbox import stopping

    order: list[str] = []
    waiting = threading.Event()  # the runner asked for the window, or already has it

    def sweep(_needle: bytes) -> None:
        assert waiting.wait(30), "the runner never asked for the window"
        order.append("the sweep ended")

    monkeypatch.setattr(stopping, "_kill_marked", sweep)
    stop = Stop()
    real = stop._killing

    class _Told:
        def __enter__(self):
            if threading.current_thread().name == "runner":
                waiting.set()
            return real.__enter__()

        def __exit__(self, *exc):
            return real.__exit__(*exc)

    stop._killing = _Told()

    def runner() -> None:
        with stop.keeping() as keep:
            order.append(f"the window opened ({keep})")
            waiting.set()

    killing = threading.Thread(target=stop.request, args=("ran past its limit",),
                               kwargs={"keep": True})
    killing.start()
    # the flag is set inside the kill, before the sweep: from here the runner has heard the stop
    assert stop._event.wait(30), "the stop was never requested"
    keeper = threading.Thread(target=runner, name="runner")
    keeper.start()
    killing.join(30)
    keeper.join(30)

    assert order == ["the sweep ended", "the window opened (True)"], order


def test_a_persons_stop_ends_the_keeping_and_a_plain_stop_never_opens_it():
    stop = Stop()
    stop.request("ran past its limit", keep=True)
    with stop.keeping() as keep:
        assert keep and stop.keeping_now
        stop.request("someone stopped it")
        assert not stop.keeping_now, "a person's stop left the keeping open"
    assert not stop.keep

    plain = Stop()
    plain.request("someone stopped it")
    with plain.keeping() as keep:
        assert not keep and not plain.keeping_now
    late = Stop()
    late.request("someone stopped it")
    late.request("ran past its limit", keep=True)
    assert not late.keep, "a timeout after a person's stop reopened the keeping"


def test_the_runners_publishing_check_lets_the_keeps_push_through():
    from beeverforge.orchestrator import JobRunner

    runner = JobRunner.__new__(JobRunner)
    runner.stop = Stop()
    runner.stop.request("ran past its limit", keep=True)
    with runner.stop.keeping():
        runner._unless_stopped("publish_branch for a hold")
    with pytest.raises(JobStopped):
        runner._unless_stopped("publish_branch for a hold")


# ── the workflow's park ─────────────────────────────────────────────────────────────────────────

def _activity_error(cause: BaseException):
    from temporalio.exceptions import ActivityError, RetryState

    err = ActivityError("Activity task failed", scheduled_event_id=1, started_event_id=2,
                        identity="w", activity_type="run_job", activity_id="1",
                        retry_state=RetryState.TIMEOUT)
    err.__cause__ = cause
    return err


def _params(change: int = 0):
    from beeverforge.runtime.temporal.io import JobParams

    return JobParams(project="acme", issue="#12", change=change)


@pytest.mark.parametrize("change,branch", [(0, "beeverforge/12"), (1, "beeverforge/12-2")])
def test_a_run_job_past_its_ceiling_parks_resumable_from_its_branch(change, branch):
    from temporalio.exceptions import TimeoutError as TimedOut
    from temporalio.exceptions import TimeoutType

    from beeverforge.contracts import JobState
    from beeverforge.contracts.run import FROM_THE_FORGE
    from beeverforge.runtime.temporal.workflow import _an_attempt_past_its_limit

    parked = _an_attempt_past_its_limit(
        _activity_error(TimedOut("activity StartToClose timeout",
                                 type=TimeoutType.START_TO_CLOSE, last_heartbeat_details=[])),
        _params(change))

    assert parked is not None and parked.state == JobState.ON_HOLD
    assert parked.resume_handle == FROM_THE_FORGE, "Resume would start from the base again"
    assert parked.branch == branch and f"`{branch}`" in parked.note
    assert "ran past its" in parked.note and "Resume continues from that branch" in parked.note
    assert "StartToClose" not in parked.note, "the park repeats the engine's words"


@pytest.mark.parametrize("cause", ["heartbeat", "other"])
def test_any_other_failure_parks_as_it_did(cause):
    from temporalio.exceptions import ApplicationError, TimeoutType
    from temporalio.exceptions import TimeoutError as TimedOut

    from beeverforge.runtime.temporal.workflow import _an_attempt_past_its_limit

    exc = (TimedOut("activity Heartbeat timeout", type=TimeoutType.HEARTBEAT,
                    last_heartbeat_details=[])
           if cause == "heartbeat" else ApplicationError("boom"))
    assert _an_attempt_past_its_limit(_activity_error(exc), _params()) is None
    assert _an_attempt_past_its_limit(RuntimeError("boom"), _params()) is None


def test_the_workflow_parks_a_failed_run_job_through_it():
    """The handler that turns a failed `run_job` into a park calls the seam this file tests, read
    from the parsed code (review of #503): the `except Exception as exc` around
    `self._run_job_once(...)` assigns `result = _the_park_of_a_failed_run_job(exc, params)`."""
    import ast
    import inspect

    from beeverforge.runtime.temporal import workflow

    tree = ast.parse(inspect.getsource(workflow))
    handlers = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        runs = any(isinstance(n, ast.Attribute) and n.attr == "_run_job_once"
                   for b in node.body for n in ast.walk(b))
        if runs:
            handlers += [h for h in node.handlers
                         if isinstance(h.type, ast.Name) and h.type.id == "Exception"]
    assert len(handlers) == 1, f"expected the one handler around run_job, found {len(handlers)}"
    calls = [n for n in ast.walk(handlers[0]) if isinstance(n, ast.Assign)
             and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name)
             and n.value.func.id == "_the_park_of_a_failed_run_job"
             and [a.id for a in n.value.args if isinstance(a, ast.Name)] == ["exc", "params"]
             and [t.id for t in n.targets if isinstance(t, ast.Name)] == ["result"]]
    assert calls, "a failed run_job no longer parks through `_the_park_of_a_failed_run_job`"


def test_the_failed_run_jobs_park_is_the_timed_out_attempts_or_the_failure_named():
    from temporalio.exceptions import ApplicationError, TimeoutType
    from temporalio.exceptions import TimeoutError as TimedOut

    from beeverforge.contracts.run import FROM_THE_FORGE
    from beeverforge.runtime.temporal.workflow import _the_park_of_a_failed_run_job

    timed_out = _the_park_of_a_failed_run_job(
        _activity_error(TimedOut("activity StartToClose timeout",
                                 type=TimeoutType.START_TO_CLOSE, last_heartbeat_details=[])),
        _params())
    failed = _the_park_of_a_failed_run_job(_activity_error(ApplicationError("boom")), _params())

    assert timed_out.resume_handle == FROM_THE_FORGE
    assert failed.resume_handle is None and failed.note.startswith("job errored after retries")


def test_a_remote_box_past_its_ceiling_parks_as_any_failure():
    """A remote box's runner is not this worker's, and keeps nothing this way: no handle, and
    no sentence claiming a branch holds its work (review of #503)."""
    from temporalio.exceptions import TimeoutError as TimedOut
    from temporalio.exceptions import TimeoutType

    from beeverforge.runtime.temporal.io import JobParams
    from beeverforge.runtime.temporal.workflow import _an_attempt_past_its_limit

    remote = JobParams(project="acme", issue="#12", sandbox="fargate")
    assert remote.traits().remote, "the case proves nothing: fargate is not remote here"
    assert _an_attempt_past_its_limit(
        _activity_error(TimedOut("activity StartToClose timeout",
                                 type=TimeoutType.START_TO_CLOSE, last_heartbeat_details=[])),
        remote) is None
