"""A `docker rm -f` the daemon does not finish in time is retried once, then named — never a
traceback, and never in place of the run's own outcome.

MEASURED ON A DEPLOYMENT. A job started, found the box an interrupted attempt had left behind, and
removed it first; the daemon was slow to remove a container whose processes the host's OOM killer
had just killed, `_host`'s `subprocess.run(..., timeout=120)` raised `TimeoutExpired`, and the job
errored out before any work with a traceback. The removal finished on its own minutes later. The
same call ends every run (`cleanup`, from `run()`'s `finally`), and there it cost more: the
`TimeoutExpired` raised inside the `finally` replaced a hold reached after 2 h 18 min of repair
passes, so the hold's reason never reached the card and nothing was pushed.

No test here waits on real time: the daemon is a fake that raises `TimeoutExpired` at once, and
the wait before the retry is read from a clock the test hands the box.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

import pytest

import beeverforge.adapters.sandbox.container as box_mod
from beeverforge.adapters.sandbox import WorktreeSandbox
from beeverforge.adapters.sandbox.base import DaemonTimedOut
from beeverforge.adapters.sandbox.container import ContainerSandbox
from beeverforge.contracts import AcceptanceCriterion, JobState, Manifest, Ticket

ROOT = Path(__file__).resolve().parent.parent
NAME = "beeverforge-acme-12"


#: THE HOSTED DOOR, BUILT HERE ON 0.1: main's shared test bed (#337) is not on this line, so the
#: same shape is built per test: a bare `forge.git` holding `main` and the card's branch, the
#: `seed` that pushed them, and `myapp`, a clone one push behind on the card's branch.
_CARD_BRANCH = "beeverforge/28"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, capture_output=True, check=True)


def _card_commit(repo: Path, name: str, text: str, message: str) -> None:
    (repo / name).write_text(text)
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgSign=false",
         "commit", "-q", "-m", message)


def _a_hosted_door(where: Path) -> Path:
    where.mkdir()
    origin = where / "forge.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)],
                   capture_output=True, check=True)
    seed = where / "seed"
    subprocess.run(["git", "init", "-q", "-b", "main", str(seed)], capture_output=True, check=True)
    _card_commit(seed, "README.md", "# app\n", "base")
    _git(seed, "switch", "-q", "-c", _CARD_BRANCH)
    _card_commit(seed, "work.py", "WORK = True\n", "the job's work")
    _git(seed, "switch", "-q", "main")
    _git(seed, "push", "-q", str(origin), "main", _CARD_BRANCH)
    subprocess.run(["git", "clone", "-q", str(origin), str(where / "myapp")],
                   capture_output=True, check=True)
    _git(seed, "switch", "-q", _CARD_BRANCH)
    _card_commit(seed, "work.py", "WORK = 2\n", "the factory's second pass")
    _git(seed, "push", "-q", str(origin), _CARD_BRANCH)
    return where


class _Daemon:
    """A host daemon whose `docker rm -f` does not finish within the bound `slow` times, then does.

    `slow=None` never finishes. `stuck` names one other docker verb that never finishes."""

    def __init__(self, *, leftover: bool = False, slow: int | None = 0, stuck: str = "") -> None:
        self.calls: list[list[str]] = []
        self.leftover, self.slow, self.stuck = leftover, slow, stuck
        self.rm_tries = 0

    def __call__(self, args, timeout=120, env=None):
        self.calls.append(list(args))
        if args[0] == "docker" and args[1] == self.stuck:
            raise subprocess.TimeoutExpired(list(args), timeout)
        if args[:2] == ["docker", "inspect"]:
            return (0, "cid\n") if self.leftover else (1, "No such object")
        if args[:3] == ["docker", "rm", "-f"]:
            self.rm_tries += 1
            if self.slow is None or self.rm_tries <= self.slow:
                raise subprocess.TimeoutExpired(list(args), timeout)
            self.leftover = False
            return 0, args[-1]
        return 0, ""

    def ran(self) -> bool:
        return any(c[:2] == ["docker", "run"] for c in self.calls)


def _box(daemon, monkeypatch) -> tuple[ContainerSandbox, list[float]]:
    monkeypatch.setattr(box_mod, "_host", daemon)
    box = ContainerSandbox(image="img", project="acme")
    waits: list[float] = []
    box.sleep = waits.append  # the clock the retry's wait is read from
    return box, waits


def _start(box):
    return box.prepare(repo_path=ROOT, base_branch="main", branch="beeverforge/12")


def _says_the_remedy(text: str) -> None:
    assert NAME in text, text
    assert "Docker daemon did not remove" in text, text
    assert f"`docker rm -f {NAME}`" in text, text
    assert "\n" not in text and "Traceback" not in text, text


# ── the start of a run ──────────────────────────────────────────────────────────────────────────

def test_a_leftover_removal_that_times_out_once_is_retried_and_the_job_starts(monkeypatch):
    daemon = _Daemon(leftover=True, slow=1)
    box, waits = _box(daemon, monkeypatch)

    _start(box)

    assert daemon.rm_tries == 2, "the timed-out removal was not tried again"
    assert waits == [box_mod.REMOVE_RETRY_WAIT], waits
    assert 0 < box_mod.REMOVE_RETRY_WAIT <= 30, "the wait before the retry is not a short one"
    assert daemon.ran() and box._container == NAME, "the job did not start after the retry"


def test_a_leftover_removal_that_always_times_out_parks_with_one_sentence(monkeypatch):
    daemon = _Daemon(leftover=True, slow=None)
    box, waits = _box(daemon, monkeypatch)

    with pytest.raises(DaemonTimedOut) as refused:
        _start(box)

    _says_the_remedy(str(refused.value))
    assert "resume" in str(refused.value), str(refused.value)
    assert refused.value.name == NAME
    assert daemon.rm_tries == 2 and len(waits) == 1, (daemon.rm_tries, waits)
    assert not daemon.ran(), "a box was started over a leftover still wearing its name"
    assert box._container is None


def test_a_removal_that_answers_in_time_waits_for_nothing(monkeypatch):
    daemon = _Daemon(leftover=True, slow=0)
    box, waits = _box(daemon, monkeypatch)

    _start(box)

    assert daemon.rm_tries == 1 and waits == [], (daemon.rm_tries, waits)


@pytest.mark.parametrize("verb", ["run", "exec"])
def test_any_other_docker_step_of_the_start_that_times_out_is_named(monkeypatch, tmp_path, verb):
    """Every `_host` call of the start is covered, not only the removal: `prepare` turns a
    timeout of any of them into the same named refusal, and leaves no clone behind."""
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))  # where `prepare` makes its clone
    daemon = _Daemon(stuck=verb)
    box, _ = _box(daemon, monkeypatch)

    with pytest.raises(DaemonTimedOut) as refused:
        _start(box)

    said = str(refused.value)
    assert f"`docker {verb}`" in said and NAME in said and "resume" in said, said
    assert "\n" not in said, said
    assert box._container is None
    assert not any(tmp_path.glob("beeverforge-*")), "the clone of a start that timed out was kept"


# ── the end of a run ────────────────────────────────────────────────────────────────────────────

def _started(daemon, monkeypatch):
    box, waits = _box(daemon, monkeypatch)
    ws = _start(box)
    return box, waits, ws


def test_a_cleanup_removal_that_times_out_once_is_retried(monkeypatch):
    daemon = _Daemon(slow=0)
    box, waits, ws = _started(daemon, monkeypatch)
    daemon.slow, daemon.rm_tries = 1, 0
    clone = ws.host_path

    box.cleanup(workspace=ws)

    assert daemon.rm_tries == 2 and waits == [box_mod.REMOVE_RETRY_WAIT], (daemon.rm_tries, waits)
    assert box._container is None and not clone.exists()


def test_a_cleanup_removal_that_always_times_out_is_named_and_still_cleans_up(monkeypatch):
    daemon = _Daemon(slow=0)
    box, waits, ws = _started(daemon, monkeypatch)
    daemon.slow, daemon.rm_tries = None, 0
    clone = ws.host_path

    with pytest.raises(DaemonTimedOut) as refused:
        box.cleanup(workspace=ws)

    _says_the_remedy(str(refused.value))
    assert daemon.rm_tries == 2 and len(waits) == 1
    assert box._container is None, "the handle outlived the cleanup"
    assert not clone.exists(), "the clone was kept because the container could not be removed"


# ── the run's outcome survives its cleanup ──────────────────────────────────────────────────────

def _a_daemon_that_never_removes(monkeypatch) -> list[float]:
    def _host(args, timeout=120, env=None):
        raise subprocess.TimeoutExpired(list(args), timeout)

    monkeypatch.setattr(box_mod, "_host", _host)
    return []


class _ItsBoxOutlivesTheRun(WorktreeSandbox):
    """A worktree box whose cleanup ends with the container box's own removal, against a daemon
    that never finishes it: the run reaches its outcome, and only then the removal times out."""

    def __init__(self, waits: list[float], **kw) -> None:
        super().__init__(**kw)
        self.waits = waits

    def cleanup(self, *, workspace) -> None:
        super().cleanup(workspace=workspace)
        box_mod.remove_the_box(NAME, sleep=self.waits.append, at_start=False)


class _ItsLeftoverWillNotGo(WorktreeSandbox):
    def __init__(self, waits: list[float], **kw) -> None:
        super().__init__(**kw)
        self.waits = waits

    def prepare(self, **kw):
        box_mod.remove_the_box(NAME, sleep=self.waits.append, at_start=True)
        return super().prepare(**kw)

    def prepare_tip(self, **kw):
        box_mod.remove_the_box(NAME, sleep=self.waits.append, at_start=True)
        return super().prepare_tip(**kw)


def _ticket() -> Ticket:
    return Ticket(id="#12", title="add feature", objective="add a feature", repo="o/app",
                  acceptance_criteria=[AcceptanceCriterion(text="feature.py exists")])


@pytest.mark.parametrize("stuck", [False, True], ids=["pr-open", "on-hold"])
def test_a_run_whose_cleanup_removal_times_out_returns_its_own_result(
        tmp_path, monkeypatch, caplog, stuck):
    from tests.test_walking_skeleton import FakeAgent, FakeStuckAgent, FakeTracker, _runner

    repo = _a_hosted_door(tmp_path / "door") / "myapp"
    waits = _a_daemon_that_never_removes(monkeypatch)
    tracker = FakeTracker(_ticket(), assignees=["alice"])
    runner = _runner(repo, tracker, Manifest(validate={"test": "true"}), tmp_path,
                     agent=FakeStuckAgent() if stuck else FakeAgent(),
                     sandbox=_ItsBoxOutlivesTheRun(waits, root=tmp_path / "wt"))

    with caplog.at_level(logging.WARNING):
        result = runner.run("#12")

    if stuck:
        assert result.state is JobState.ON_HOLD, result.state
        assert any("on hold" in c for c in tracker.comments), "the hold's reason left the card"
    else:
        assert result.state is JobState.PR_OPEN, result.state
        assert result.pr_url == "https://forge/pr/1"
    assert len(waits) == 1, "the cleanup removal was not retried once"
    told = [c for c in tracker.comments if f"docker rm -f {NAME}" in c]
    assert len(told) == 1, tracker.comments
    _says_the_remedy(told[0])
    assert any(f"docker rm -f {NAME}" in r.getMessage() for r in caplog.records), (
        "the leftover box is not in the log")


#: Each door that starts a box: a run, a CI repair of an open pull request, a re-review of one.
_DOORS = {
    "run": lambda runner: runner.run("#12"),
    "repair_ci": lambda runner: runner.repair_ci("#12", "CI failed: test_x broke",
                                                 pr_url="https://forge/pr/1"),
    "review_pr": lambda runner: runner.review_pr("#12", pr_url="https://forge/pr/1"),
}


@pytest.mark.parametrize("door", sorted(_DOORS))
def test_a_leftover_that_will_not_go_parks_the_job_with_the_sentence(tmp_path, monkeypatch,
                                                                     door):
    from tests.test_walking_skeleton import FakeReviewer, FakeTracker, _runner

    repo = _a_hosted_door(tmp_path / "door") / "myapp"
    waits = _a_daemon_that_never_removes(monkeypatch)
    tracker = FakeTracker(_ticket(), assignees=["alice"])
    runner = _runner(repo, tracker, Manifest(validate={"test": "true"}), tmp_path,
                     reviewer=FakeReviewer(),
                     sandbox=_ItsLeftoverWillNotGo(waits, root=tmp_path / "wt"))

    result = _DOORS[door](runner)
    assert result.state is JobState.ON_HOLD, result.state
    held = [c for c in tracker.comments if "on hold" in c.lower()]
    assert len(held) == 1, tracker.comments
    _says_the_remedy(held[0])
    assert "resume" in held[0]
    assert len(waits) == 1
