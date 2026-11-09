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

    def execute(self, *, sandbox, workspace, context):
        where = Path(workspace.path)
        (where / "committed.py").write_text("DONE = 1\n")
        for args in (["add", "committed.py"],
                     ["-c", "user.email=agent@example.invalid", "-c", "user.name=agent",
                      "commit", "-qm", "the part the agent committed"]):
            subprocess.run(["git", "-C", str(where), *args], check=True, capture_output=True)
        (where / "uncommitted.py").write_text("HALF = 1\n")
        return super().execute(sandbox=sandbox, workspace=workspace, context=context)


async def _a_pass_cut_by(details, client, origin_and_repo, tmp_path, *, then=None):
    """Run a job whose agent blocks, cancel its activity with `details` (the engine answering
    `describe` through `client`, and answering `then` from the cancel on), and answer what the job
    left behind."""
    from temporalio.testing import ActivityEnvironment

    from beeverforge.contracts import Manifest
    from beeverforge.observability import InMemoryEventSink
    from beeverforge.orchestrator import JobRunner
    from beeverforge.runtime.temporal.activities import _heartbeat_while

    _, repo_path = origin_and_repo
    fifo = tmp_path / "pid.fifo"
    os.mkfifo(fifo)
    stop = Stop()
    hooks = stopped._Hooks(stop, at="")
    forge, tracker, reviewer = stopped._fakes(hooks)
    agent = _CommittingAgent(fifo)
    box = stopped._Box(root=tmp_path / "wt", hooks=hooks)
    runner = JobRunner(
        tracker=tracker, forge=forge, agent=agent, sandbox=box,
        manifest=Manifest(merge_policy="auto", validate={"test": "true", "security": "true"}),
        repo_path=repo_path, reviewer=reviewer, events=InMemoryEventSink())
    runner.hears(stop)

    env = ActivityEnvironment(client=client)
    job = asyncio.create_task(env.run(_heartbeat_while, lambda: runner.run("#1"), "p#1", stop=stop))
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
    """The one place a `run_job` failure becomes a park asks this first: without it the timed-out
    attempt parks as "job errored after retries", with no handle, and Resume starts from the base."""
    import inspect

    from beeverforge.runtime.temporal import workflow

    src = inspect.getsource(workflow)
    said = src.index('note=f"job errored after retries: {describe(exc, limit=150)}"')
    assert "_an_attempt_past_its_limit(exc, params) or RunResult(" in src[said - 200:said], (
        "a failed run_job no longer asks whether it ran past its limit")
