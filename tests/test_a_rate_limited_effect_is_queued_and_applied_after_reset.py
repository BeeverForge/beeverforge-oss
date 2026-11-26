"""A tracker write that fails on the forge's rate limit is queued, then applied after `reset_at`
(#699) — in order, at most once, and with the newest state per ticket winning.

The clock is injected and the tracker is a fake: nothing here waits or touches a forge.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from beeverforge.adapters.rate_limit import RateLimited
from beeverforge.adapters.tracker.deferred import DeferringTracker
from beeverforge.contracts import JobState

RESET = 1_000.0


class _Clock:
    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


class _Forge:
    """A tracker whose writes raise `RateLimited` until `limited` is cleared."""

    def __init__(self) -> None:
        self.limited = True
        self.applied: list[tuple] = []

    def _write(self, *call) -> None:
        if self.limited:
            raise RateLimited("API rate limit exceeded", reset_at=RESET)
        self.applied.append(call)

    def set_state(self, ref, state, reason=None, *, needs_person=None):
        self._write("state", ref, state, needs_person)
        return True

    def comment(self, ref, body):
        self._write("comment", ref, body)

    def add_label(self, ref, label):
        self._write("add_label", ref, label)

    def remove_label(self, ref, label):
        self._write("remove_label", ref, label)

    def set_assignees(self, ref, logins):
        self._write("assignees", ref, tuple(logins))

    def assignees(self, ref):
        return ["someone"]


def _tracker(tmp_path=None):
    forge, clock = _Forge(), _Clock()
    path = (tmp_path / "queue.json") if tmp_path else None
    return forge, clock, DeferringTracker(forge, clock=clock, path=path)


def test_a_failed_effect_is_queued_not_dropped_and_applied_after_reset():
    forge, clock, t = _tracker()
    assert t.set_state("#1", JobState.VALIDATING) is False
    t.comment("#1", "diagnosis")
    t.add_label("#1", "bot")
    t.set_assignees("#1", ["bot"])
    assert forge.applied == []
    forge.limited = False
    clock.now = RESET - 1
    t.flush()
    assert forge.applied == []  # not yet
    clock.now = RESET
    t.flush()
    assert [c[0] for c in forge.applied] == ["state", "comment", "add_label", "assignees"]


def test_each_effect_is_applied_at_most_once():
    forge, clock, t = _tracker()
    t.comment("#1", "hello")
    forge.limited = False
    clock.now = RESET
    t.flush()
    t.flush()
    assert forge.applied == [("comment", "#1", "hello")]


def test_only_the_newest_state_per_ticket_is_applied():
    forge, clock, t = _tracker()
    t.set_state("#1", JobState.PLANNING)
    t.set_state("#2", JobState.PLANNING)
    t.set_state("#1", JobState.IMPLEMENTING)
    t.set_state("#1", JobState.VALIDATING)
    forge.limited = False
    clock.now = RESET
    t.flush()
    assert forge.applied == [("state", "#2", JobState.PLANNING, None),
                             ("state", "#1", JobState.VALIDATING, None)]


def test_the_newest_label_operation_wins():
    forge, clock, t = _tracker()
    t.add_label("#1", "bot")
    t.remove_label("#1", "bot")
    forge.limited = False
    clock.now = RESET
    t.flush()
    assert forge.applied == [("remove_label", "#1", "bot")]


def test_a_write_after_the_reset_drains_the_queue_first_and_keeps_order():
    forge, clock, t = _tracker()
    t.comment("#1", "first")
    forge.limited = False
    clock.now = RESET
    t.comment("#1", "second")
    assert [c[2] for c in forge.applied] == ["first", "second"]


def test_still_limited_after_the_reset_keeps_the_entry_for_the_next_reset():
    forge, clock, t = _tracker()
    t.comment("#1", "x")
    clock.now = RESET
    t.flush()  # forge still limited
    assert forge.applied == []
    forge.limited = False
    clock.now = RESET + 1
    t.flush()
    assert len(forge.applied) == 1


def test_unrecorded_names_the_entry_and_a_later_line_says_when_it_was_recorded(caplog):
    forge, clock, t = _tracker()
    with caplog.at_level(logging.INFO):
        t.set_state("#7", JobState.VALIDATING)
        forge.limited = False
        clock.now = RESET + 5
        t.flush()
    unrecorded = [r.getMessage() for r in caplog.records
                  if "BEEVERFORGE_TICKET_STATE_UNRECORDED" in r.getMessage()]
    recorded = [r.getMessage() for r in caplog.records
                if "BEEVERFORGE_TICKET_STATE_RECORDED" in r.getMessage()]
    assert len(unrecorded) == 1 and len(recorded) == 1
    entry = unrecorded[0].split("entry=")[1].split()[0]
    assert f"entry={entry}" in recorded[0]
    assert str(RESET + 5) in recorded[0] or "at=" in recorded[0]


def test_the_queue_survives_a_restart(tmp_path):
    forge, clock, t = _tracker(tmp_path)
    t.comment("#1", "kept")
    t.set_state("#1", JobState.VALIDATING)

    again = DeferringTracker(forge, clock=clock, path=tmp_path / "queue.json")
    forge.limited = False
    clock.now = RESET
    again.flush()
    assert [c[0] for c in forge.applied] == ["comment", "state"]
    # and applied once: a third process finds nothing left
    third = DeferringTracker(forge, clock=clock, path=tmp_path / "queue.json")
    third.flush()
    assert len(forge.applied) == 2


def test_other_failures_still_raise_and_reads_pass_through():
    class Broken(_Forge):
        def comment(self, ref, body):
            raise RuntimeError("boom")

    t = DeferringTracker(Broken(), clock=_Clock())
    try:
        t.comment("#1", "x")
    except RuntimeError as exc:
        assert "boom" in str(exc)
    else:
        raise AssertionError("a non-rate-limit failure must propagate")
    assert t.assignees("#1") == ["someone"]


def test_a_write_for_a_ticket_with_entries_waiting_joins_behind_them():
    forge, clock, t = _tracker()
    t.comment("#1", "first")
    forge.limited = False  # the forge would take a write now, but "first" waits for its reset
    clock.now = RESET - 1
    t.comment("#1", "second")
    t.comment("#2", "other ticket")
    assert forge.applied == [("comment", "#2", "other ticket")]
    clock.now = RESET
    t.flush()
    assert [c[2] for c in forge.applied] == ["other ticket", "first", "second"]


def test_an_entry_that_fails_for_another_reason_is_dropped_and_the_next_applied(caplog):
    forge, clock, t = _tracker()
    t.comment("#1", "broken")
    t.comment("#1", "fine")
    forge.limited = False
    real = forge.comment

    def comment(ref, body):
        if body == "broken":
            raise RuntimeError("422 unprocessable")
        real(ref, body)

    forge.comment = comment
    clock.now = RESET
    with caplog.at_level(logging.ERROR):
        t.flush()
    assert forge.applied == [("comment", "#1", "fine")]
    assert t.pending == []
    assert any("BEEVERFORGE_QUEUED_EFFECT_DROPPED" in r.getMessage() for r in caplog.records)


# -- review of #708: one file shared by several trackers --

def test_two_trackers_on_one_path_lose_no_entry(tmp_path):
    forge, clock = _Forge(), _Clock()
    path = tmp_path / "queue.json"
    a = DeferringTracker(forge, clock=clock, path=path)
    b = DeferringTracker(forge, clock=clock, path=path)
    a.comment("#1", "from a")
    b.comment("#2", "from b")
    forge.limited = False
    clock.now = RESET
    DeferringTracker(forge, clock=clock, path=path).flush()
    assert sorted(c[2] for c in forge.applied) == ["from a", "from b"]


def test_an_entry_a_live_tracker_applied_is_not_applied_again_by_another(tmp_path):
    forge, clock = _Forge(), _Clock()
    path = tmp_path / "queue.json"
    a = DeferringTracker(forge, clock=clock, path=path)
    a.comment("#1", "once")
    b = DeferringTracker(forge, clock=clock, path=path)  # loaded a's entry
    forge.limited = False
    clock.now = RESET
    a.flush()
    b.flush()
    assert forge.applied == [("comment", "#1", "once")]


# -- review of #708: who drains --

def _built_runner(tmp_path, monkeypatch, forge, issue="#1"):
    from beeverforge import factory
    from beeverforge.contracts.project import Project

    monkeypatch.setenv("BEEVERFORGE_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr("beeverforge.adapters.tracker.registry.build_tracker",
                        lambda *a, **k: forge)
    monkeypatch.setattr("beeverforge.loader.load_manifest", lambda *a, **k: SimpleNamespace(
        environments={}, post_merge_deploy=None, base_branch="main", setup=[], validation={}))
    project = Project(name="someone", repo_path=str(tmp_path))
    return factory.build_runner(project, issue, sandbox="worktree", image="", review=False)


def test_a_runner_from_build_runner_queues_and_drains_when_its_job_ends(tmp_path, monkeypatch):
    forge, clock = _Forge(), _Clock()
    runner = _built_runner(tmp_path, monkeypatch, forge)
    assert isinstance(runner.tracker, DeferringTracker)
    runner.tracker._clock = clock
    runner.tracker.comment("#1", "late")
    assert [e["kind"] for e in runner.tracker.pending] == ["comment"]

    def get_ticket(ref):  # the reset passes while the job runs, and the job then fails
        forge.limited = False
        clock.now = RESET
        raise RuntimeError("no such ticket")

    forge.get_ticket = get_ticket
    with pytest.raises(RuntimeError):
        runner.run("#1")
    assert forge.applied == [("comment", "#1", "late")]
    assert runner.tracker.pending == []


def test_a_later_runner_drains_what_a_finished_job_left_when_it_starts(tmp_path, monkeypatch):
    forge, clock = _Forge(), _Clock()
    first = _built_runner(tmp_path, monkeypatch, forge, "#1")
    first.tracker._clock = clock
    first.tracker.comment("#1", "left behind")  # the job ends before the reset
    forge.limited = False
    clock.now = RESET
    second = _built_runner(tmp_path, monkeypatch, forge, "#2")
    second.tracker._clock = clock
    seen: list = []

    def get_ticket(ref):  # the first thing a job reads: what was applied by now?
        seen.extend(forge.applied)
        raise RuntimeError("no such ticket")

    forge.get_ticket = get_ticket
    with pytest.raises(RuntimeError):
        second.run("#2")
    assert seen == [("comment", "#1", "left behind")]
