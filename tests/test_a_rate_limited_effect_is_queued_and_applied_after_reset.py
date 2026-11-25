"""A tracker write that fails on the forge's rate limit is queued, then applied after `reset_at`
(#699) — in order, at most once, and with the newest state per ticket winning.

The clock is injected and the tracker is a fake: nothing here waits or touches a forge.
"""

from __future__ import annotations

import logging

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
