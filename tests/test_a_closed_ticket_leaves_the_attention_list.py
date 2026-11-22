"""#651 — a held job leaves /api/attention once its workflow is gone and its ticket is closed."""
from beeverforge.api.attention import settle

HELD = [{"project": "acme", "issue": "1", "state": "on_hold"},
        {"project": "acme", "issue": "2", "state": "on_hold"}]


def _direct(fn, _timeout):
    return fn()


class Tracker:
    def __init__(self, closed):
        self.closed, self.calls = closed, 0

    def __call__(self, _project):
        self.calls += 1
        return self.closed


def test_closed_ticket_without_workflow_is_dropped():
    assert settle(HELD, running=set(), closed_refs=Tracker({"1", "2"}), bounded=_direct) == []


def test_open_ticket_is_listed():
    out = settle(HELD, running=set(), closed_refs=Tracker(set()), bounded=_direct)
    assert [j["issue"] for j in out] == ["1", "2"]


def test_running_workflow_is_listed_even_if_closed():
    out = settle(HELD, running={("acme", "1")}, closed_refs=Tracker({"1", "2"}), bounded=_direct)
    assert [j["issue"] for j in out] == ["1"]


def test_tracker_is_asked_once_per_project():
    tracker = Tracker({"1"})
    settle(HELD + [{"project": "b", "issue": "9", "state": "on_hold"}],
           running=set(), closed_refs=tracker, bounded=_direct)
    assert tracker.calls == 2


def test_timeout_keeps_entry_with_reason():
    def late(_fn, _timeout):
        raise TimeoutError

    out = settle(HELD, running=set(), closed_refs=Tracker(set()), bounded=late)
    assert len(out) == 2 and "timed out" in out[0]["note"]


def test_failed_or_unreadable_read_keeps_entry_with_reason():
    def boom(_p):
        raise RuntimeError("down")

    assert "could not be read" in settle(HELD, running=set(), closed_refs=boom,
                                         bounded=_direct)[0]["note"]
    assert "could not be read" in settle(HELD, running=set(), closed_refs=Tracker(None),
                                         bounded=_direct)[0]["note"]


def test_unknown_engine_keeps_entries_with_reason():
    out = settle(HELD, running=None, closed_refs=Tracker({"1"}), bounded=_direct)
    assert len(out) == 2 and "workflow" in out[0]["note"]


def test_run_bounded_times_out_without_waiting_on_the_worker():
    import threading

    import pytest

    from beeverforge.api.attention import run_bounded

    gate = threading.Event()
    try:
        with pytest.raises(TimeoutError):
            run_bounded(gate.wait, 0.01)
    finally:
        gate.set()
    assert run_bounded(lambda: 7, 5) == 7


def _route(monkeypatch, *, running, closed):
    import asyncio

    from beeverforge.api import app

    tracker = Tracker(closed)

    async def _running():
        return running

    monkeypatch.setattr(app, "list_jobs", lambda: HELD + [
        {"project": "acme", "issue": "3", "state": "running"}])
    monkeypatch.setattr(app, "_running_workflows", _running)
    monkeypatch.setattr(app, "_closed_refs_of", tracker)
    return asyncio.run(app.attention()), tracker


def test_route_drops_closed_held_job_and_reads_tracker_once(monkeypatch):
    out, tracker = _route(monkeypatch, running=set(), closed={"1"})
    assert [j["issue"] for j in out] == ["2"] and tracker.calls == 1


def test_route_lists_everything_when_engine_unreadable(monkeypatch):
    out, tracker = _route(monkeypatch, running=None, closed={"1", "2"})
    assert len(out) == 2 and tracker.calls == 0
