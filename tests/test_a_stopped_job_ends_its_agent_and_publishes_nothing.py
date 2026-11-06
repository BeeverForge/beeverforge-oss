"""A stopped job ends its agent and publishes nothing after the stop (#44).

WHAT A DEPLOYMENT SAW (worktree box, `merge_policy: auto`). `stop` said "The job was terminated in
the engine" and freed the floor; 46 minutes later the same job opened a pull request, merged it and
wrote "Merged — and this job is done" on the stopped card, while the freed slot already ran another
card of the same repository against the same base.

WHY. `stop` terminates the job's workflow. `run_job` runs the blocking `JobRunner` in a thread
(`asyncio.to_thread`) under `_heartbeat_while`, and a cancellation cancelled only the asyncio
wrapper: a Python thread cannot be cancelled, so the runner went on, through the agent pass and on
to publish. The activity hears of a terminate at its next heartbeat (the server answers NotFound
and the SDK cancels the activity with `cancellation_details().not_found`).

WHAT IS HELD HERE:
1. a job stopped in the middle of its agent pass, driven through the real `_heartbeat_while`, the
   real `JobRunner` and a real `WorktreeSandbox`, kills the agent's whole process group, pushes,
   opens, merges and moves nothing, and removes its worktree;
2. each step that reaches the forge or the board is skipped when the stop arrives during the step
   before it;
3. only an ended workflow, a cancel request or a shutting worker ends the work — a timeout, a pause
   or a reset is not a stop (#259 handles those);
4. the adoption race: a command started after the stop is killed the moment it is adopted;
5. (review of #453) what a command leaves behind is killed too — a background child still in its
   group, and a descendant in a session of its own, reached by the mark its environment carries;
6. (review of #453) the runner asks the engine before it publishes, so a stop the heartbeat has not
   heard yet still publishes nothing;
7. (review of #453) a job's commands write their temporary files beside the worktree, and
   `cleanup` removes them with it.
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest
from temporalio.activity import ActivityCancellationDetails

from beeverforge.adapters.sandbox import WorktreeSandbox, stopping
from beeverforge.adapters.sandbox.base import Workspace
from beeverforge.adapters.sandbox.stopping import MARK_VAR, JobStopped, Stop
from beeverforge.adapters.sandbox.worktree import job_tmpdir
from tests import test_walking_skeleton as skeleton

# ── helpers: real processes, ended deterministically ────────────────────────────────────────────

_LINUX = sys.platform.startswith("linux") and Path("/proc/self/status").exists()


def _status(pid: int) -> dict[str, str] | None:
    try:
        text = Path(f"/proc/{pid}/status").read_text()
    except (FileNotFoundError, ProcessLookupError):
        return None
    return dict(line.split(":", 1) for line in text.splitlines() if ":" in line)


def _ended_or_killed(pid: int) -> bool:
    """True when `pid` is gone, a zombie, or already carries a SIGKILL it has not yet acted on.

    NO CLOCK IN IT. A SIGKILL sent to a group is queued on every member when `killpg` returns,
    and its delivery is the scheduler's business; asking whether it was SENT is the deterministic
    question, and a survivor (a kill aimed at the leader only, or no kill) answers False."""
    status = _status(pid)
    if status is None:
        return True
    if status.get("State", "").strip()[:1] in ("Z", "X"):
        return True
    pending = int(status.get("ShdPnd", "0").strip() or "0", 16) | \
        int(status.get("SigPnd", "0").strip() or "0", 16)
    return bool(pending & (1 << (signal.SIGKILL - 1)))


def _kill_quietly(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


# ── 3. a stop is not a timeout ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("details,ends", [
    (ActivityCancellationDetails(not_found=True), True),
    (ActivityCancellationDetails(cancel_requested=True), True),
    (ActivityCancellationDetails(worker_shutdown=True), True),
    (ActivityCancellationDetails(timed_out=True), False),
    (ActivityCancellationDetails(paused=True), False),
    (ActivityCancellationDetails(reset=True), False),
    (None, False),
])
def test_only_an_ended_workflow_or_a_shutting_worker_ends_the_work(details, ends):
    """A timeout is the engine giving up on a slow attempt, and #259 pushes that work for the
    retry; a stop is a person ending it, and nothing is pushed. They must stay apart."""
    from beeverforge.runtime.temporal.activities import _the_work_must_end

    assert _the_work_must_end(details) is ends


# ── 4. the stop and the process groups it kills ─────────────────────────────────────────────────

def _a_group_sleeping() -> subprocess.Popen:
    return subprocess.Popen(["sleep", "600"], process_group=0)


@pytest.mark.skipif(not _LINUX, reason="reads a process's pending signals from /proc")
def test_a_command_adopted_after_the_stop_is_killed_at_once():
    """THE RACE: a box that starts a command between the stop and its own next check. The group
    is killed on adoption, so nothing started after a stop outlives it."""
    stop = Stop()
    stop.request("someone stopped it")
    proc = _a_group_sleeping()
    try:
        stop.adopt(proc)
        assert _ended_or_killed(proc.pid), "a command started after the stop outlived it"
    finally:
        _kill_quietly(proc.pid)
        proc.wait()


@pytest.mark.skipif(not _LINUX, reason="reads a process's pending signals from /proc")
def test_a_stop_kills_every_group_it_adopted_and_is_said_once():
    stop = Stop()
    procs = [_a_group_sleeping(), _a_group_sleeping()]
    try:
        for p in procs:
            stop.adopt(p)
        assert not stop.requested
        stop.request("someone stopped it")
        stop.request("a second word does not replace the first")
        assert stop.requested and stop.why == "someone stopped it"
        assert all(_ended_or_killed(p.pid) for p in procs), "an adopted group outlived the stop"
    finally:
        for p in procs:
            _kill_quietly(p.pid)
            p.wait()


def _sigkills(monkeypatch) -> list[int]:
    """Every group id `stopping` sends SIGKILL to, recorded and sent."""
    sent: list[int] = []
    real = os.killpg

    def killpg(pgid, sig):
        if sig == signal.SIGKILL:
            sent.append(pgid)
        return real(pgid, sig)

    monkeypatch.setattr(stopping.os, "killpg", killpg)
    return sent


def test_a_group_is_let_go_of_once_it_is_empty_and_never_signalled_after(monkeypatch):
    """A group whose command returned is kept while anything lives in it — and let go of once
    nothing does, the first moment its id may be handed to somebody else, so a later stop never
    signals it."""
    sent = _sigkills(monkeypatch)
    stop = Stop()
    lives = _a_group_sleeping()
    other = subprocess.Popen(["true"], process_group=0)
    try:
        stop.adopt(lives)
        stop.settle(lives)  # its command returned, and a member (here, the leader) still lives
        assert lives.pid in stop._groups, "a group with a member alive was let go of"
        _kill_quietly(lives.pid)
        lives.wait()
        stop.adopt(other)
        other.wait()
        stop.settle(other)
        assert stop._groups == set(), "an emptied group is still the job's to kill"
        stop.request("someone stopped it")
        assert lives.pid not in sent and other.pid not in sent, "an emptied group was signalled"
    finally:
        for p in (lives, other):
            _kill_quietly(p.pid)
            p.wait()


def test_job_stopped_is_not_an_exception_a_best_effort_handler_swallows():
    """`_preserve_for_hold`, `_say_on_ticket` and many more catch `Exception` and carry on; a stop
    they swallowed would carry on to the comment it exists to prevent."""
    assert issubclass(JobStopped, BaseException) and not issubclass(JobStopped, Exception)
    said = str(JobStopped("open_pr", "someone stopped it"))
    assert "open_pr" in said and "someone stopped it" in said


# ── the runner, over a real repository with a bare origin ──────────────────────────────────────

#: THE WALKING SKELETON'S REPOSITORY: a real one with a bare `origin.git` beside it, which the job
#: pushes to for real. Registered by assignment, so this file builds no repository of its own.
repo = skeleton.repo


@pytest.fixture
def origin_and_repo(repo: Path) -> tuple[Path, Path]:
    return repo.parent / "origin.git", repo


def _ticket():
    from beeverforge.contracts import AcceptanceCriterion, Ticket

    return Ticket(id="#1", title="add feature", objective="add a feature", repo="o/app",
                  acceptance_criteria=[AcceptanceCriterion(text="feature.py exists")])


class _Hooks:
    """Where, in the walk, the person's stop arrives: `fire(event)` requests it at `at`."""

    def __init__(self, stop: Stop, at: str) -> None:
        self.stop = stop
        self.at = at

    def fire(self, event: str) -> None:
        if event == self.at:
            self.stop.request("someone stopped it")


class _Box(WorktreeSandbox):
    """The real worktree box, counting what reaches the forge and whether it cleaned up."""

    def __init__(self, *, root: Path, hooks: _Hooks, rebases: bool = False) -> None:
        super().__init__(root=root)
        self.hooks = hooks
        self.rebases = rebases
        self.rebased = False
        self.pushes = 0
        self.cleanups = 0

    def publish_branch(self, *, workspace, remote_url=None) -> None:
        self.pushes += 1
        self.hooks.fire("publish_branch")
        super().publish_branch(workspace=workspace, remote_url=remote_url)

    def diff_paths(self, *, workspace):
        out = super().diff_paths(workspace=workspace)
        self.hooks.fire("diff_paths_after_rebase" if self.rebased else "diff_paths")
        return out

    def rebase_onto_base(self, *, workspace, base, remote_url=None) -> str:
        if self.rebases:  # the base moved while the ticket ran: the change is re-validated
            self.rebased = True
            return "rebased"
        return super().rebase_onto_base(workspace=workspace, base=base, remote_url=remote_url)

    def cleanup(self, *, workspace) -> None:
        self.cleanups += 1
        super().cleanup(workspace=workspace)


def _fakes(hooks: _Hooks, *, arm_only: bool = False):
    class Forge(skeleton.FakeForge):
        def merge_pr(self, **kw) -> None:
            super().merge_pr(**kw)
            hooks.fire("merge_pr")

        def open_pr(self, **kw) -> str:
            pr = super().open_pr(**kw)
            hooks.fire("open_pr")
            return pr

        def review_pr(self, **kw) -> None:
            super().review_pr(**kw)
            hooks.fire("review_pr")

        def request_reviewers(self, **kw) -> None:
            super().request_reviewers(**kw)
            hooks.fire("request_reviewers")

    class Tracker(skeleton.FakeTracker):
        def comment(self, ref: str, body: str) -> None:
            super().comment(ref, body)
            if "ready for review" in body:
                hooks.fire("ready_comment")

    class Reviewer(skeleton.FakeReviewer):
        def review(self, **kw):
            verdict = super().review(**kw)
            hooks.fire("review")
            return verdict

    return Forge(arm_only=arm_only), Tracker(_ticket()), Reviewer()


_A_DECISION = ('```json\n{"question": "which way?", "options": ['
               '{"key": "A", "label": "this way"}, {"key": "B", "label": "that way"}]}\n```')


class _Agent:
    """An executor that writes a file and ends its pass the way `ending` says."""

    def __init__(self, hooks: _Hooks, ending: str = "ok") -> None:
        self.hooks = hooks
        self.ending = ending

    def execute(self, *, sandbox, workspace, context):
        from beeverforge.contracts import AgentRunResult

        (workspace.path / "feature.py").write_text("VALUE = 42\n")
        self.hooks.fire("execute")
        if self.ending == "decision":
            return AgentRunResult(ok=False, summary="a choice is needed", raw_output=_A_DECISION)
        if self.ending == "stopped_unfinished":
            return AgentRunResult(ok=False, summary="stopped unfinished")
        if self.ending == "rate_limit":
            return AgentRunResult(ok=False, summary="usage limit", pause_reason="rate_limit")
        return AgentRunResult(ok=True, summary="added feature.py", cost_usd=0.01)

    def repair(self, *, sandbox, workspace, context, failure_log):
        from beeverforge.contracts import AgentRunResult

        return AgentRunResult(ok=True)


def _never_pushed(origin: Path) -> bool:
    refs = subprocess.run(["git", "ls-remote", str(origin)], check=True, capture_output=True,
                          text=True).stdout
    return "beeverforge/" not in refs


def _landed_says(tracker, *clauses: str) -> bool:
    """The one "what landed" comment exists and says each of `clauses`."""
    said = [c for c in tracker.comments if "was opened before the stop reached this job" in c]
    return len(said) == 1 and all(clause in said[0] for clause in clauses)


#: (case, where the stop arrives, how the pass ends, merge policy, what must not have happened)
_STEPS = [
    ("the_review", "review", "ok", "auto",
     lambda box, forge, tracker, runner: box.pushes == 0),
    ("publish_branch", "publish_branch", "ok", "auto",
     lambda box, forge, tracker, runner: forge.opened is None),
    # THE PULL REQUEST IS OPEN, and the stop cannot take it back: the review is skipped, and the
    # ticket is told what landed (review of #453)
    ("open_pr", "open_pr", "ok", "auto",
     lambda box, forge, tracker, runner: forge.reviews == [] and _landed_says(
         tracker, "no review was posted", "no reviewers were asked")),
    # …AND WHAT ELSE REACHED IT IS SAID AS IT HAPPENED (review of #453): a stop during the review
    # lands the review, and one during the reviewers' request asks them
    ("review_pr_auto", "review_pr", "ok", "auto",
     lambda box, forge, tracker, runner: forge.merge_calls == 0 and _landed_says(
         tracker, "the review was posted on it", "no reviewers were asked")),
    ("review_pr_human", "review_pr", "ok", "human",
     lambda box, forge, tracker, runner: forge.requested == []),
    ("request_reviewers", "request_reviewers", "ok", "human",
     lambda box, forge, tracker, runner: not any("ready for review" in c
                                                 for c in tracker.comments) and _landed_says(
         tracker, "the review was posted on it", "its reviewers were asked")),
    ("the_ready_comment", "ready_comment", "ok", "human",
     lambda box, forge, tracker, runner: runner._handed_back == []),
    ("a_decision", "execute", "decision", "auto",
     lambda box, forge, tracker, runner: not any("Decision needed" in c
                                                 for c in tracker.comments)),
    ("the_preserve_for_hold", "diff_paths", "stopped_unfinished", "auto",
     lambda box, forge, tracker, runner: box.pushes == 0),
    ("a_rate_limit_pause", "execute", "rate_limit", "auto",
     lambda box, forge, tracker, runner: box.pushes == 0),
    ("the_revalidation_after_a_rebase", "diff_paths_after_rebase", "ok", "auto",
     lambda box, forge, tracker, runner: box.pushes == 1 and forge.merge_calls == 0),
]


@pytest.mark.parametrize("case,at,ending,policy,skipped", _STEPS, ids=[s[0] for s in _STEPS])
def test_a_stop_arriving_during_a_step_skips_the_next(origin_and_repo, tmp_path, case, at, ending,
                                                      policy, skipped):
    """Each step that reaches the forge or the board asks first. `runner.stop` only — the box
    carries no stop here, so its commands run and the walk reaches the step under test."""
    from beeverforge.contracts import Manifest
    from beeverforge.observability import NullEventSink
    from beeverforge.orchestrator import JobRunner

    _, repo = origin_and_repo
    stop = Stop()
    hooks = _Hooks(stop, at)
    forge, tracker, reviewer = _fakes(hooks)
    box = _Box(root=tmp_path / "wt", hooks=hooks, rebases=case.endswith("rebase"))
    runner = JobRunner(
        tracker=tracker, forge=forge, agent=_Agent(hooks, ending), sandbox=box,
        manifest=Manifest(merge_policy=policy, validate={"test": "true", "security": "true"},
                          reviewers=["someone"], recovery_max_attempts=0),
        repo_path=repo, reviewer=reviewer, events=NullEventSink())
    runner.stop = stop

    with pytest.raises(JobStopped):
        runner.run("#1")

    assert stop.requested, f"the walk never reached {at!r}: the case proves nothing"
    assert skipped(box, forge, tracker, runner), (
        f"a stop that arrived during {at!r} still took the next step")
    assert box.cleanups == 1, "the stopped job's worktree was not removed"


# ── 1. a stop in the middle of the agent's pass ─────────────────────────────────────────────────

class _BlockingAgent:
    """A harness that blocks until it is ended: it starts `sleep` in the background, says its
    pid through a fifo, and waits on it. It ignores how its command ended and reports success —
    the worst case, a harness that would let the walk go on to publish."""

    def __init__(self, fifo: Path) -> None:
        self.fifo = fifo
        self.ran: tuple[int, str] | None = None
        self.workspace: Path | None = None

    def execute(self, *, sandbox, workspace, context):
        from beeverforge.contracts import AgentRunResult

        self.workspace = Path(workspace.path)
        (workspace.path / "feature.py").write_text("VALUE = 42\n")
        # THE BOX'S WALL OF 60 s ONLY BOUNDS A BROKEN RUN: the assertion is that the pass did NOT
        # end there, so a kill that never came fails the test instead of hanging it
        self.ran = sandbox.run(workspace=workspace,
                               command=f"sleep 600 & echo $! > {self.fifo}; wait", timeout=60)
        return AgentRunResult(ok=True, summary="done", cost_usd=0.01)

    def repair(self, *, sandbox, workspace, context, failure_log):
        from beeverforge.contracts import AgentRunResult

        return AgentRunResult(ok=True)


@pytest.mark.skipif(not _LINUX, reason="reads a process's pending signals from /proc")
async def test_a_job_stopped_mid_agent_pass_never_reaches_publish(origin_and_repo, tmp_path):
    from temporalio.testing import ActivityEnvironment

    from beeverforge.contracts import Manifest
    from beeverforge.observability import InMemoryEventSink
    from beeverforge.orchestrator import JobRunner
    from beeverforge.runtime.temporal.activities import _heartbeat_while

    origin, repo = origin_and_repo
    fifo = tmp_path / "pid.fifo"
    os.mkfifo(fifo)
    stop = Stop()
    hooks = _Hooks(stop, at="")
    forge, tracker, reviewer = _fakes(hooks)
    agent = _BlockingAgent(fifo)
    events = InMemoryEventSink()
    runner = JobRunner(
        tracker=tracker, forge=forge, agent=agent, sandbox=_Box(root=tmp_path / "wt", hooks=hooks),
        manifest=Manifest(merge_policy="auto", validate={"test": "true", "security": "true"}),
        repo_path=repo, reviewer=reviewer, events=events)
    runner.hears(stop)

    env = ActivityEnvironment()
    job = asyncio.create_task(env.run(_heartbeat_while, lambda: runner.run("#1"), "p#1", stop=stop))
    pid = None
    try:
        reading = asyncio.ensure_future(asyncio.to_thread(fifo.read_text))
        await asyncio.wait({reading, job}, return_when=asyncio.FIRST_COMPLETED)
        if not reading.done():  # the job ended before its agent said anything: unblock the read
            with open(fifo, "w"):
                pass
            await reading
            pytest.fail(f"the job ended before its agent ran: {job.result()!r}")
        pid = int(reading.result().strip())
        assert not _ended_or_killed(pid), "the agent's child was not running before the stop"
        states, comments, seen = list(tracker.states), list(tracker.comments), len(events.events)

        env.cancel(ActivityCancellationDetails(not_found=True))
        with pytest.raises(asyncio.CancelledError):
            await job

        rc, _ = agent.ran
        assert rc == -signal.SIGKILL, f"the agent's pass was not killed: it ended {rc}"
        assert _ended_or_killed(pid), "the agent's child outlived the stop"
        assert forge.opened is None and forge.reviews == [] and forge.merge_calls == 0
        assert forge.requested == []
        assert _never_pushed(origin), "the stopped job pushed its branch"
        assert tracker.states == states and tracker.comments == comments, (
            "the stopped job moved or commented on its card")
        assert runner._handed_back == []
        late = [e.kind for e in events.events[seen:] if e.kind in ("validation", "review", "pr")]
        assert late == [], f"the stopped job went on to {late}"
        assert agent.workspace is not None and not agent.workspace.exists(), (
            "the stopped job's worktree was not removed")
    finally:
        if pid is not None:
            _kill_quietly(pid)
        if not job.done():
            job.cancel()


# ── the container box: its `docker exec` client, in a group the stop kills ──────────────────────

@pytest.mark.parametrize("stopping", [False, True], ids=["no_stop", "a_jobs_box"])
def test_the_container_box_starts_a_jobs_command_in_a_group_of_its_own(tmp_path, monkeypatch,
                                                                       stopping):
    """Docker substituted at `Popen` (the argv is thrown away and a real shell runs instead), so
    what is held is the keyword the box passes and the adoption around the run. A box with no stop
    — every judging role — starts its command as it always did."""
    from beeverforge.adapters.sandbox import container
    from beeverforge.adapters.sandbox.base import Workspace

    box = container.ContainerSandbox(image="irrelevant", project="p")
    box._container = "no-such-container"
    stop = Stop()
    if stopping:
        box.stop = stop
    real_popen = subprocess.Popen
    seen: dict = {}
    adopted_while_running: list[bool] = []

    def instead_of_docker(_argv, **kw):
        seen.update(kw)
        return real_popen("true", shell=True, **kw)

    real_adopt = stop.adopt

    def adopt(proc):
        adopted_while_running.append(True)
        real_adopt(proc)

    monkeypatch.setattr(container.subprocess, "Popen", instead_of_docker)
    monkeypatch.setattr(stop, "adopt", adopt)
    ws = Workspace(path=tmp_path, branch="beeverforge/1", base_branch="main")

    rc, _ = box.run(workspace=ws, command="claude -p ...", timeout=60)

    assert rc == 0
    assert (seen.get("process_group") == 0) is stopping
    assert bool(adopted_while_running) is stopping
    assert stop._groups == set(), "a finished command's group is still the job's to kill"


# ── the wiring: `run_job` hands one stop to its heartbeat loop and to its runner ────────────────

def test_run_job_hands_one_stop_to_its_heartbeat_and_to_its_runner(monkeypatch):
    from temporalio.testing import ActivityEnvironment

    import beeverforge.runtime.temporal.activities as mod
    from beeverforge.contracts import RunResult
    from beeverforge.runtime.temporal.io import RunJobInput

    seen: dict = {}

    async def heartbeat(fn, detail, *, tick=None, stop=None):
        seen["the loop"] = stop
        return fn()

    def do_run_job(inp, run_id=None, watch=None, stop=None):
        seen["the runner"] = stop
        return RunResult(ticket_id="12", state="pr_open")

    async def no_preview(*_a, **_k):
        return ""

    monkeypatch.setattr(mod, "_heartbeat_while", heartbeat)
    monkeypatch.setattr(mod, "_do_run_job", do_run_job)
    monkeypatch.setattr(mod, "_a_preview_starts_on_its_own", no_preview)
    monkeypatch.setattr(mod, "_watch_for", lambda _inp: None)

    asyncio.run(ActivityEnvironment().run(
        mod.run_job, RunJobInput(project="acme", issue="12", sandbox="worktree")))

    assert isinstance(seen.get("the loop"), Stop), "the heartbeat loop has no stop to request"
    assert seen.get("the runner") is seen["the loop"], "the runner hears another stop, or none"


def test_do_run_job_tells_the_runner_and_its_box(monkeypatch):
    import beeverforge.runtime.temporal.activities as mod
    from beeverforge.contracts import RunResult
    from beeverforge.orchestrator import JobRunner
    from beeverforge.runtime.temporal.io import RunJobInput

    class _FakeBox:
        stop = None

    class _FakeRunner:
        sandbox = _FakeBox()
        stop = None
        hears = JobRunner.hears

        def run(self, *_a, **_k):
            return RunResult(ticket_id="12", state="pr_open")

        def knowledge_arm(self):
            return None

    runner = _FakeRunner()
    monkeypatch.setattr(mod, "build_runner", lambda *a, **k: runner)
    monkeypatch.setattr(mod, "ProjectRegistry",
                        lambda: type("R", (), {"get": staticmethod(lambda _n: object())})())
    monkeypatch.setattr(mod, "_runner_view", lambda *a, **k: (object(), "acme"))
    stop = Stop()

    mod._do_run_job(RunJobInput(project="acme", issue="12", sandbox="worktree"), stop=stop)

    assert runner.stop is stop, "the runner never heard the stop"
    assert runner.sandbox.stop is stop, "the box starts its commands where no stop can kill them"


# ── 5. what a command leaves behind: a background child, and a session of its own ──────────────

def _carrying(mark: str) -> set[int]:
    """The pids whose environment carries this mark — read here, not through `stopping`, so a
    test that fails still finds what to kill."""
    needle = f"{MARK_VAR}={mark}".encode()
    found = set()
    for entry in Path("/proc").iterdir():
        if entry.name.isdigit():
            try:
                if needle in (entry / "environ").read_bytes().split(b"\0"):
                    found.add(int(entry.name))
            except OSError:
                continue
    return found


def _announced(fifo: Path) -> int:
    """The pid a child writes into `fifo` once it is what the case needs. A blocking read, and a
    deadline that only fails the test: a child that never announces itself is a broken case."""
    from concurrent.futures import ThreadPoolExecutor
    from concurrent.futures import TimeoutError as Late

    with ThreadPoolExecutor(1) as pool:
        reading = pool.submit(fifo.read_text)
        try:
            return int(reading.result(timeout=30).strip())
        except Late:
            with open(fifo, "w"):  # unblocks the read, so the pool can close
                pass
            pytest.fail(f"no child announced itself through {fifo}")


@pytest.mark.skipif(not _LINUX, reason="reads environments and pending signals from /proc")
def test_a_stop_kills_what_a_returned_command_left_running(tmp_path):
    """MEASURED ON THE REAL HARNESS: Claude Code runs every Bash tool command in a session of its
    own (`pid == pgid == sid`), outside the group the box started it in. So the command here
    returns at once and leaves three `sleep`s behind:

    - one in a SESSION OF ITS OWN (`setsid`): only the mark its environment carries reaches it;
    - one in the command's group WITHOUT the mark (`env -u`): only the group, kept adopted after
      its leader returned, reaches it;
    - one in the group with the mark, as a background child usually is.

    The stop must end all three."""
    stop = Stop()
    box = WorktreeSandbox(root=tmp_path / "wt")
    box.stop = stop
    path = tmp_path / "wt" / "beeverforge-1"
    path.mkdir(parents=True)
    ws = Workspace(path=path, branch="beeverforge/1", base_branch="main")
    # READINESS IS AN EVENT, NOT A WAIT: the two children whose case depends on a step taken after
    # they started — the new session, the dropped mark — announce themselves through a fifo once
    # that step is taken, then exec `sleep`. The plain one carries the mark and sits in the group
    # from its first instruction, so it needs no announcement.
    in_a_session, unmarked_fifo = tmp_path / "session.fifo", tmp_path / "unmarked.fifo"
    os.mkfifo(in_a_session)
    os.mkfifo(unmarked_fifo)
    command = (f"setsid sh -c 'echo $$ > {in_a_session}; exec sleep 600' >/dev/null 2>&1 & "
               f"env -u {MARK_VAR} sh -c 'echo $$ > {unmarked_fifo}; exec sleep 600' "
               f">/dev/null 2>&1 & "
               f"sleep 600 >/dev/null 2>&1 & echo $!")
    pids: list[int] = []
    groups: set[int] = set()
    try:
        rc, out = box.run(workspace=ws, command=command, timeout=60)
        groups = set(stop._groups)
        assert rc == 0, out
        plain = int(out.split()[-1])
        pids = [plain]
        session = _announced(in_a_session)
        pids.append(session)
        unmarked = _announced(unmarked_fifo)
        pids.append(unmarked)
        # the case is what it says, or it proves nothing
        assert os.getsid(session) == session, "the setsid'd sleep is not in a session of its own"
        assert os.getpgid(unmarked) in groups and os.getpgid(plain) in groups, (
            "the command's group was let go of while its background children lived")
        assert unmarked not in _carrying(stop.mark) and {session, plain} <= _carrying(stop.mark)
        assert not any(_ended_or_killed(p) for p in pids), "a sleep ended before the stop"

        stop.request("someone stopped it")

        assert _ended_or_killed(session), "a descendant in a session of its own outlived the stop"
        assert _ended_or_killed(unmarked), "a background child in the command's group outlived it"
        assert _ended_or_killed(plain), "a background child outlived the stop"
    finally:
        for pid in set(pids) | _carrying(stop.mark):
            _kill_quietly(pid)
        for pgid in groups:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass


# ── 6. a stop the heartbeat has not heard yet ───────────────────────────────────────────────────

def test_a_stop_the_heartbeat_has_not_heard_yet_publishes_nothing(origin_and_repo, tmp_path):
    """The heartbeat reaches the server at most once a throttled minute (temporalio 1.35), so a
    terminate can be in the engine while `stop.requested` is still False. The runner asks the
    engine (`Stop.ask`) before it publishes: here the engine says the workflow ended during the
    review, and nothing ever requests the stop."""
    from beeverforge.contracts import Manifest
    from beeverforge.observability import NullEventSink
    from beeverforge.orchestrator import JobRunner

    origin, repo = origin_and_repo
    stop = Stop()
    ended: list[str] = []

    class _Engine(_Hooks):
        def fire(self, event: str) -> None:
            if event == "review":
                ended.append("terminated")

    hooks = _Engine(stop, at="")
    stop.ask = lambda: "its workflow was terminated in the engine (a stop)" if ended else None
    forge, tracker, reviewer = _fakes(hooks)
    box = _Box(root=tmp_path / "wt", hooks=hooks)
    runner = JobRunner(
        tracker=tracker, forge=forge, agent=_Agent(hooks), sandbox=box,
        manifest=Manifest(merge_policy="auto", validate={"test": "true", "security": "true"},
                          recovery_max_attempts=0),
        repo_path=repo, reviewer=reviewer, events=NullEventSink())
    runner.stop = stop

    with pytest.raises(JobStopped):
        runner.run("#1")

    assert ended, "the walk never reached the review: the case proves nothing"
    assert box.pushes == 0 and forge.opened is None and forge.merge_calls == 0
    assert _never_pushed(origin), "a stop the heartbeat had not heard still pushed"
    assert stop.requested and "terminated" in stop.why, "the engine's answer did not stop the job"


class _Described:
    def __init__(self, status) -> None:
        self.status = status


class _Client:
    """The activity's client, answering `describe` with `answer` (a status or an exception)."""

    def __init__(self, answer) -> None:
        self.answer = answer
        self.asked: list[tuple[str, str | None]] = []

    def get_workflow_handle(self, workflow_id, *, run_id=None):
        client = self

        class _Handle:
            async def describe(self):
                client.asked.append((workflow_id, run_id))
                if isinstance(client.answer, BaseException):
                    raise client.answer
                return _Described(client.answer)

        return _Handle()


def _rpc(code):
    from temporalio.service import RPCError

    return RPCError("said the engine", code, b"")


@pytest.mark.parametrize("answer,stopped", [
    ("TERMINATED", True),
    ("CANCELED", True),
    ("RUNNING", False),
    ("NOT_FOUND", True),
    ("UNAVAILABLE", False),
], ids=["terminated", "canceled", "running", "not_found", "unreachable"])
async def test_the_runner_asks_the_engine_through_the_heartbeat_loop(answer, stopped):
    """`_heartbeat_while` gives the stop an `ask` the RUNNER'S THREAD calls, answered on the
    activity's loop through the activity's own client: a run that is not running is a stop, and so
    is a run the engine no longer has; an engine that cannot be reached is no answer."""
    from temporalio.client import WorkflowExecutionStatus
    from temporalio.service import RPCStatusCode
    from temporalio.testing import ActivityEnvironment

    from beeverforge.runtime.temporal.activities import _heartbeat_while

    if answer in ("NOT_FOUND", "UNAVAILABLE"):
        said = _rpc(getattr(RPCStatusCode, answer))
    else:
        said = getattr(WorkflowExecutionStatus, answer)
    client = _Client(said)
    stop = Stop()

    confirmed = await ActivityEnvironment(client=client).run(
        _heartbeat_while, stop.confirm, "p#1", stop=stop)

    assert client.asked, "the runner's thread never asked the engine"
    assert confirmed is stopped and stop.requested is stopped


# ── 7. a job's temporary files ──────────────────────────────────────────────────────────────────

def test_a_jobs_temporary_files_go_with_its_worktree(tmp_path):
    """A test run SIGKILLed by a stop never reaches its own `finally`, so whatever it made under
    `$TMPDIR` stays — in `/tmp`, for good, unless `$TMPDIR` is the job's. The box names one beside
    the worktree, makes it before the first command, and `cleanup` removes it."""
    stop = Stop()
    box = WorktreeSandbox(root=tmp_path / "wt")
    box.stop = stop
    path = tmp_path / "wt" / "beeverforge-1"
    path.mkdir(parents=True)
    ws = Workspace(path=path, branch="beeverforge/1", base_branch="main")
    written: Path | None = None
    try:
        rc, out = box.run(workspace=ws, timeout=60,
                          command='f="$TMPDIR/left-by-a-test"; echo x > "$f" && echo "$f"')
        assert rc == 0, out
        written = Path(out.strip().splitlines()[-1])
        assert written.parent == job_tmpdir(ws), f"the command's TMPDIR was {written.parent}"
        assert not written.is_relative_to(ws.path), "the job's TMPDIR is inside its worktree"
        assert written.exists()

        stop.request("someone stopped it")
        box.cleanup(workspace=ws)

        assert not job_tmpdir(ws).exists(), "the stopped job's TMPDIR outlived its cleanup"
    finally:
        if written is not None and written.exists():
            written.unlink()


# ── 8. what landed on the forge before the stop reached the job ─────────────────────────────────

@pytest.mark.parametrize("at,arm_only,kind,said", [
    ("open_pr", False, "opened", "was opened before the stop reached this job"),
    ("merge_pr", False, "merged", "was merged into"),
    ("merge_pr", True, "armed", "Auto-merge was armed on the pull request"),
], ids=["inside_open_pr", "inside_merge_pr", "inside_merge_pr_armed"])
def test_what_landed_before_the_stop_is_said_and_nothing_after_it_runs(
        origin_and_repo, tmp_path, at, arm_only, kind, said):
    """A STOP THAT ARRIVES DURING AN IRREVERSIBLE FORGE CALL. The pull request opens, or the merge
    lands, and nothing the stop does takes it back — while the card the stop put in the backlog says
    the work stopped. So the job says on the ticket what landed and what a person does about it,
    journals the same fact, and then stops: no review, no reviewers, no card move."""
    from beeverforge.contracts import Manifest
    from beeverforge.observability import InMemoryEventSink
    from beeverforge.orchestrator import JobRunner

    _, repo = origin_and_repo
    stop = Stop()
    hooks = _Hooks(stop, at)
    forge, tracker, reviewer = _fakes(hooks, arm_only=arm_only)
    box = _Box(root=tmp_path / "wt", hooks=hooks)
    events = InMemoryEventSink()
    runner = JobRunner(
        tracker=tracker, forge=forge, agent=_Agent(hooks), sandbox=box,
        manifest=Manifest(merge_policy="auto", validate={"test": "true", "security": "true"},
                          recovery_max_attempts=0),
        repo_path=repo, reviewer=reviewer, events=events)
    runner.stop = stop
    seen_states: list = []

    real_fire = hooks.fire

    def fire(event: str) -> None:
        real_fire(event)
        if event == at:
            seen_states[:] = list(tracker.states)

    hooks.fire = fire

    with pytest.raises(JobStopped):
        runner.run("#1")

    assert stop.requested, f"the walk never reached {at!r}: the case proves nothing"
    landed = [c for c in tracker.comments if "before the stop reached this job" in c]
    assert len(landed) == 1 and said in landed[0] and "https://forge/pr/1" in landed[0], (
        tracker.comments)
    notes = [e for e in events.events if e.kind == "note" and e.data.get("landed") == kind]
    assert len(notes) == 1 and said in notes[0].message, [e.message for e in events.events]
    assert tracker.comments[-1] == landed[0], "the job said more after what landed"
    assert tracker.states == seen_states, "the stopped job moved its card after the stop"
    assert runner._handed_back == [], "the stopped job handed an outcome back"
    assert forge.reviews == [] if at == "open_pr" else forge.merge_calls == 1
    assert forge.requested == []
    assert box.cleanups == 1


def test_a_stop_before_anything_landed_says_nothing_of_a_landing(origin_and_repo, tmp_path):
    """THE LANDED SENTENCE IS NOT A BYPASS: a job stopped before any forge call returned writes no
    comment at all, and `_say_on_ticket` goes on refusing after a stop."""
    from beeverforge.contracts import Manifest
    from beeverforge.observability import NullEventSink
    from beeverforge.orchestrator import JobRunner

    _, repo = origin_and_repo
    stop = Stop()
    hooks = _Hooks(stop, "review")
    forge, tracker, reviewer = _fakes(hooks)
    runner = JobRunner(
        tracker=tracker, forge=forge, agent=_Agent(hooks), sandbox=_Box(root=tmp_path / "wt",
                                                                          hooks=hooks),
        manifest=Manifest(merge_policy="auto", validate={"test": "true", "security": "true"},
                          recovery_max_attempts=0),
        repo_path=repo, reviewer=reviewer, events=NullEventSink())
    runner.stop = stop

    with pytest.raises(JobStopped):
        runner.run("#1")
    said = list(tracker.comments)
    with pytest.raises(JobStopped):
        runner._say_on_ticket("#1", "anything at all")

    assert not any("before the stop reached this job" in c for c in said), said
    assert tracker.comments == said, "a comment went through after the stop"
