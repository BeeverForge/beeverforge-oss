"""#651 — a held job leaves /api/attention once its workflow is gone and its ticket is closed."""
import pytest

from beeverforge.api.attention import settle

HELD = [{"project": "acme", "issue": "1", "state": "on_hold"},
        {"project": "acme", "issue": "2", "state": "on_hold"}]


def _direct(fn, _timeout):
    return fn()


class Tracker:
    """Answers which of the refs it is ASKED about are closed, and remembers what it was asked."""

    def __init__(self, closed):
        self.closed, self.calls, self.asked, self.timeouts = closed, 0, [], []

    def __call__(self, project, refs, timeout):
        self.calls += 1
        self.asked.append((project, sorted(refs)))
        self.timeouts.append(timeout)
        return None if self.closed is None else set(self.closed) & set(refs)


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
    def boom(_p, _refs, _timeout):
        raise RuntimeError("down")

    assert "could not be read" in settle(HELD, running=set(), closed_refs=boom,
                                         bounded=_direct)[0]["note"]
    assert "could not be read" in settle(HELD, running=set(), closed_refs=Tracker(None),
                                         bounded=_direct)[0]["note"]


def test_tracker_is_asked_only_for_the_candidates():
    tracker = Tracker({"1", "2", "3", "4"})
    jobs = HELD + [{"project": "acme", "issue": "5", "state": "on_hold"}]
    settle(jobs, running={("acme", "5")}, closed_refs=tracker, bounded=_direct)
    assert tracker.asked == [("acme", ["1", "2"])]


def test_tracker_is_not_asked_when_every_job_still_runs():
    tracker = Tracker({"1"})
    settle(HELD, running={("acme", "1"), ("acme", "2")}, closed_refs=tracker, bounded=_direct)
    assert tracker.calls == 0


def test_the_bound_goes_down_to_the_tracker_and_is_strictly_inside_it():
    tracker, seen = Tracker(set()), []

    def spy(fn, timeout):
        seen.append(timeout)
        return fn()

    settle(HELD, running=set(), closed_refs=tracker, bounded=spy, timeout=8.0)
    assert seen == [8.0] and tracker.timeouts == [pytest.approx(7.0)]
    assert tracker.timeouts[0] < seen[0]


def test_a_non_set_answer_is_not_a_closed_ticket():
    out = settle(HELD, running=set(), closed_refs=lambda *_: ["1", "2"], bounded=_direct)
    assert len(out) == 2 and "could not be read" in out[0]["note"]


def test_unknown_engine_keeps_entries_with_reason():
    out = settle(HELD, running=None, closed_refs=Tracker({"1"}), bounded=_direct)
    assert len(out) == 2 and "workflow" in out[0]["note"]


def test_run_bounded_times_out_without_waiting_on_the_worker():
    import threading

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
    assert tracker.asked == [("acme", ["1", "2"])]


def test_route_lists_everything_when_engine_unreadable(monkeypatch):
    out, tracker = _route(monkeypatch, running=None, closed={"1", "2"})
    assert len(out) == 2 and tracker.calls == 0


# ── the two functions the route patches out, run against fakes ─────────────────────────────────

class Engine:
    """A stand-in for `runtime.temporal.view`: what `list_jobs` answers, and what it was asked."""

    def __init__(self, rows=None, *, connect_error=None, list_error=None, hang=False):
        self.rows, self.connect_error, self.list_error = rows or [], connect_error, list_error
        self.hang, self.asked = hang, []

    async def connect(self):
        if self.connect_error:
            raise self.connect_error
        return "client"

    async def list_jobs(self, client, namespace, **kwargs):
        import asyncio

        self.asked.append((client, namespace, kwargs))
        if self.hang:
            await asyncio.Event().wait()
        if self.list_error:
            raise self.list_error
        return self.rows


def _read_running(monkeypatch, engine, *, wait=5):
    import asyncio

    from beeverforge.api import app

    monkeypatch.setattr(app, "_temporal", lambda: (engine, "addr", "ns"))
    real = asyncio.wait_for

    async def quick(awaitable, timeout):
        return await real(awaitable, timeout=0.01 if engine.hang else timeout)

    monkeypatch.setattr(app.asyncio, "wait_for", quick)
    return asyncio.run(app._running_workflows())


def _row(issue, status="running", project="acme"):
    return {"project": project, "issue": issue, "status": status}


def test_running_workflows_keeps_only_the_running_status(monkeypatch):
    engine = Engine([_row(1), _row(2, "completed"), _row(3, "failed", "b"), _row(4, project="b")])
    assert _read_running(monkeypatch, engine) == {("acme", "1"), ("b", "4")}


def test_running_workflows_asks_the_engine_for_the_running_ones_only(monkeypatch):
    engine = Engine([_row(1)])
    _read_running(monkeypatch, engine)
    (_client, _ns, kwargs), = engine.asked
    assert "Running" in kwargs["query"]


def test_a_full_page_of_running_workflows_is_unknown_not_absent(monkeypatch):
    from beeverforge.api import app

    page = [_row(n) for n in range(app._RUNNING_PAGE)]
    assert _read_running(monkeypatch, Engine(page)) is None
    assert _read_running(monkeypatch, Engine(page[:-1])) is not None


def test_running_workflows_is_none_when_the_engine_cannot_be_asked(monkeypatch):
    assert _read_running(monkeypatch, Engine(connect_error=ConnectionError("down"))) is None
    assert _read_running(monkeypatch, Engine(list_error=RuntimeError("boom"))) is None


def test_running_workflows_is_none_when_the_engine_times_out(monkeypatch):
    assert _read_running(monkeypatch, Engine(hang=True)) is None


class FakeTracker:
    def __init__(self, answer=None, error=None):
        self.answer, self.error, self.asked = answer, error, []

    def closed_among(self, refs, timeout):
        self.asked.append((list(refs), timeout))
        if self.error:
            raise self.error
        return self.answer


def _closed_refs(monkeypatch, tracker, *, project="acme"):
    from fastapi import HTTPException

    from beeverforge import credentials
    from beeverforge.adapters.tracker import registry
    from beeverforge.api import app

    def registered(name):
        if name != "acme":
            raise HTTPException(404, "no project")
        return "the-project"

    built = []
    monkeypatch.setattr(app, "_project_or_404", registered)
    monkeypatch.setattr(credentials, "tracker_token_for", lambda _p: "tok")
    monkeypatch.setattr(credentials, "deployment_tracker_token", lambda _p: "dep")
    monkeypatch.setattr(registry, "build_tracker",
                        lambda proj, token=None: built.append((proj, token)) or tracker)
    return app._closed_refs_of(project, ["1", "2"], 7.0), built


def test_closed_refs_asks_the_tracker_for_those_refs_under_the_bound(monkeypatch):
    tracker = FakeTracker({"1"})
    got, built = _closed_refs(monkeypatch, tracker)
    assert got == {"1"} and tracker.asked == [(["1", "2"], 7.0)]
    assert built == [("the-project", "tok")]


def test_closed_refs_is_none_when_the_tracker_cannot_say(monkeypatch):
    assert _closed_refs(monkeypatch, FakeTracker(None))[0] is None
    assert _closed_refs(monkeypatch, FakeTracker(error=RuntimeError("gh gone")))[0] is None


def test_closed_refs_is_none_for_a_tracker_with_no_such_read(monkeypatch):
    assert _closed_refs(monkeypatch, object())[0] is None


def test_closed_refs_is_none_for_an_unregistered_project(monkeypatch):
    assert _closed_refs(monkeypatch, FakeTracker({"1"}), project="ghost")[0] is None


# ── the GitHub tracker's one batched read ──────────────────────────────────────────────────────

def _github(monkeypatch, *, stdout="", returncode=0):
    import subprocess

    from beeverforge.adapters.tracker.github import GitHubIssuesTracker

    tracker = GitHubIssuesTracker(repo="acme/web")
    calls = []

    def gh(args, timeout=60, **_kw):
        calls.append((args, timeout))
        return subprocess.CompletedProcess(args, returncode, stdout, "")

    monkeypatch.setattr(tracker, "_gh", gh)
    return tracker, calls


def test_github_reads_the_state_of_the_asked_refs_in_one_call(monkeypatch):
    answer = '{"data":{"repository":{"i1":{"state":"CLOSED"},"i2":{"state":"OPEN"}}}}'
    tracker, calls = _github(monkeypatch, stdout=answer)
    assert tracker.closed_among(["1", "2"], 7.0) == {"1"}
    (args, timeout), = calls
    query = next(a for a in args if a.startswith("query="))
    assert "graphql" in args and "body" not in query and "issue(number: 1)" in query
    assert timeout == 7.0


def test_github_skips_a_ref_that_is_not_a_plain_number(monkeypatch):
    tracker, calls = _github(monkeypatch, stdout='{"data":{"repository":{}}}')
    assert tracker.closed_among(["acme/api#3", "1) { x }"], 7.0) == set()
    assert calls == []


def test_github_says_none_when_the_read_fails_or_is_garbled(monkeypatch):
    assert _github(monkeypatch, returncode=1)[0].closed_among(["1"], 7.0) is None
    assert _github(monkeypatch, stdout="not json")[0].closed_among(["1"], 7.0) is None
    assert _github(monkeypatch, stdout='{"data":null}')[0].closed_among(["1"], 7.0) is None
