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
        self.current: dict[str, list[str]] = {}

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
        self.current[ref] = list(logins)

    def assignees(self, ref):
        return list(self.current.get(ref, ["someone"]))


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


# -- second review of #708 (hcristia): the measured cases, each red on 82c8f06 --

@pytest.fixture(autouse=True)
def _no_card_record(monkeypatch):
    """No deployment store here: the card's record is one this module hands in, case by case."""
    from beeverforge.lifecycle import record

    def unrecordable():
        raise record.Unrecordable("no store in this test")

    monkeypatch.setattr(record, "keyed_sink", unrecordable)


def _a_view(tmp_path, monkeypatch, forges, repo, issue="#1"):
    """`build_runner` for a project whose tracker is on `repo`, its tracker the fake for `repo`:
    the view a card of another repository of the product runs on keeps the product's `name`."""
    from beeverforge import factory
    from beeverforge.contracts.project import Project, ProviderRef

    monkeypatch.setenv("BEEVERFORGE_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr("beeverforge.adapters.tracker.registry.build_tracker",
                        lambda project, *a, **k: forges[project.tracker.repo])
    monkeypatch.setattr("beeverforge.loader.load_manifest", lambda *a, **k: SimpleNamespace(
        environments={}, post_merge_deploy=None, base_branch="main", setup=[], validation={}))
    project = Project(name="acme", repo_path=str(tmp_path),
                      tracker=ProviderRef(kind="github", repo=repo))
    return factory.build_runner(project, issue, sandbox="worktree", image="", review=False)


def test_a_queued_entry_is_applied_only_by_a_runner_of_its_own_repository(tmp_path, monkeypatch):
    forges = {"acme/api": _Forge(), "acme/web": _Forge()}
    clock = _Clock()
    api = _a_view(tmp_path, monkeypatch, forges, "acme/api")
    web = _a_view(tmp_path, monkeypatch, forges, "acme/web")
    api.tracker._clock = web.tracker._clock = clock
    api.tracker.set_state("#1", JobState.VALIDATING)  # acme/api's #1, limited
    for forge in forges.values():
        forge.limited = False
    clock.now = RESET
    web.tracker.comment("#1", "web's own")  # acme/web's #1: another issue, nothing to wait on
    assert forges["acme/web"].applied == [("comment", "#1", "web's own")]
    assert web.tracker.pending == []
    assert [e["ref"] for e in api.tracker.pending] == ["#1"]  # still waiting for its own runner
    api.tracker.flush()
    assert forges["acme/api"].applied == [("state", "#1", JobState.VALIDATING, None)]


def _iso(epoch: float) -> str:
    from datetime import UTC, datetime

    return datetime.fromtimestamp(epoch, UTC).isoformat()


def _a_card_record(monkeypatch, moves: dict[str, list[tuple[str, float]]]):
    """The card's record, as the door wrote it: per card, its moves as (event, when)."""
    from beeverforge.lifecycle import record

    monkeypatch.setattr(record, "keyed_sink", lambda: object())

    def read(sink, project, card):
        return record.History(rows=tuple(
            record.Row(card=card, seq=n, event_id=f"e{n}", event=event, by="the workflow",
                       ts=_iso(when))
            for n, (event, when) in enumerate(moves.get(card, []), start=1)))

    monkeypatch.setattr(record, "read", read)


def test_a_queued_state_is_not_applied_over_a_move_the_card_record_holds_since(
        tmp_path, monkeypatch, caplog):
    forges = {"acme/api": _Forge()}
    clock = _Clock(now=100.0)
    runner = _a_view(tmp_path, monkeypatch, forges, "acme/api")
    runner.tracker._clock = clock
    runner.tracker.set_state("#1", JobState.VALIDATING)
    runner.tracker.add_label("#1", "beeverforge:working")
    runner.tracker.set_assignees("#1", ["bot"])
    runner.tracker.comment("#1", "what the job said")
    _a_card_record(monkeypatch, {"1": [("delivered", 500.0)]})  # the door wrote DONE after
    forges["acme/api"].limited = False
    clock.now = RESET
    with caplog.at_level(logging.INFO):
        runner.tracker.flush()
    assert forges["acme/api"].applied == [("comment", "#1", "what the job said")]
    assert runner.tracker.pending == []
    assert sum("BEEVERFORGE_QUEUED_EFFECT_SUPERSEDED" in r.getMessage()
               for r in caplog.records) == 3


def test_a_move_recorded_before_the_entry_was_queued_supersedes_nothing(tmp_path, monkeypatch):
    forges = {"acme/api": _Forge()}
    clock = _Clock(now=600.0)
    runner = _a_view(tmp_path, monkeypatch, forges, "acme/api")
    runner.tracker._clock = clock
    runner.tracker.set_state("#1", JobState.VALIDATING)
    _a_card_record(monkeypatch, {"1": [("picked_up", 500.0)]})
    forges["acme/api"].limited = False
    clock.now = RESET
    runner.tracker.flush()
    assert forges["acme/api"].applied == [("state", "#1", JobState.VALIDATING, None)]


def test_a_job_that_ends_drops_its_own_queued_progress_marks(tmp_path, monkeypatch):
    forge, clock = _Forge(), _Clock()
    runner = _built_runner(tmp_path, monkeypatch, forge)
    runner.tracker._clock = clock
    runner.tracker.set_state("#1", JobState.VALIDATING)
    runner.tracker.comment("#1", "late")

    def get_ticket(ref):  # the reset passes while the job runs, and the job then ends
        forge.limited = False
        clock.now = RESET
        raise RuntimeError("no such ticket")

    forge.get_ticket = get_ticket
    with pytest.raises(RuntimeError):
        runner.run("#1")
    # the outcome the job hands back to the card's door is the card's newest state
    assert forge.applied == [("comment", "#1", "late")]
    assert runner.tracker.pending == []


def test_a_stopped_job_applies_nothing_it_queued(tmp_path, monkeypatch):
    from beeverforge.adapters.sandbox.stopping import JobStopped, Stop

    forge, clock = _Forge(), _Clock()
    runner = _built_runner(tmp_path, monkeypatch, forge)
    runner.tracker._clock = clock
    runner.tracker.set_state("#1", JobState.VALIDATING)
    forge.limited = False
    clock.now = RESET
    stop = Stop()
    stop.request("a person stopped it")
    runner.hears(stop)
    forge.get_ticket = lambda ref: (_ for _ in ()).throw(RuntimeError("no such ticket"))
    with pytest.raises((JobStopped, RuntimeError)):
        runner.run("#1")
    assert forge.applied == []
    assert [e["kind"] for e in runner.tracker.pending] == ["state"]


def test_a_queued_assignee_change_is_dropped_when_a_person_changed_them_meanwhile():
    forge, clock, t = _tracker()
    forge.limited = False
    t.set_assignees("#1", ["bot"])  # the claim lands
    forge.limited = True
    t.set_assignees("#1", ["owner"])  # the hand-back meets the limit
    forge.current["#1"] = ["a-person"]  # somebody reassigned the ticket meanwhile
    forge.limited = False
    clock.now = RESET
    t.flush()
    assert forge.applied == [("assignees", "#1", ("bot",))]
    assert t.pending == []


def test_a_queued_assignee_change_is_applied_when_nobody_changed_them():
    forge, clock, t = _tracker()
    forge.limited = False
    t.set_assignees("#1", ["bot"])
    forge.limited = True
    t.set_assignees("#1", ["owner"])
    forge.limited = False
    clock.now = RESET
    t.flush()
    assert forge.applied == [("assignees", "#1", ("bot",)), ("assignees", "#1", ("owner",))]


def test_an_entry_is_out_of_the_file_while_it_is_applied(tmp_path):
    import json

    forge, clock, t = _tracker(tmp_path)
    t.comment("#1", "once")
    seen: list = []
    real = forge.comment

    def comment(ref, body):  # what another runner would read, at the moment of the apply
        seen.append(json.loads((tmp_path / "queue.json").read_text()))
        real(ref, body)

    forge.comment = comment
    forge.limited = False
    clock.now = RESET
    t.flush()
    assert seen == [[]] and forge.applied == [("comment", "#1", "once")]


def test_the_hourly_drain_applies_each_repositorys_entries_with_its_own_tracker(
        tmp_path, monkeypatch):
    from beeverforge import factory

    forges = {"acme/api": _Forge(), "acme/web": _Forge()}
    api = _a_view(tmp_path, monkeypatch, forges, "acme/api")
    web = _a_view(tmp_path, monkeypatch, forges, "acme/web", "#7")
    api.tracker._clock = web.tracker._clock = _Clock()
    api.tracker.comment("#1", "for api")
    web.tracker.comment("#7", "for web")  # both jobs end; no next job comes
    for forge in forges.values():
        forge.limited = False
    seen: list[str] = []

    def tracker_for(view):
        seen.append(view.tracker.repo)
        return forges[view.tracker.repo]

    factory.drain_queued_effects(api.project, tracker_for=tracker_for, clock=lambda: RESET - 1)
    assert forges["acme/api"].applied == forges["acme/web"].applied == []
    factory.drain_queued_effects(api.project, tracker_for=tracker_for, clock=lambda: RESET)
    assert forges["acme/api"].applied == [("comment", "#1", "for api")]
    assert forges["acme/web"].applied == [("comment", "#7", "for web")]


def test_the_hourly_round_drains_what_a_finished_job_left(tmp_path, monkeypatch):
    from beeverforge import lifecycle
    from beeverforge.runtime.temporal import activities

    forges = {"acme/api": _Forge()}
    runner = _a_view(tmp_path, monkeypatch, forges, "acme/api")
    runner.tracker._clock = _Clock()
    runner.tracker.comment("#1", "left behind")
    forges["acme/api"].limited = False
    monkeypatch.setattr(lifecycle, "observe", lambda project: [])
    monkeypatch.setattr(lifecycle, "converge", lambda project: [])
    monkeypatch.setattr(activities, "_tracker_for", lambda project: forges[project.tracker.repo])
    monkeypatch.setattr(activities.activity, "logger", logging.getLogger("test.activity"))
    activities._converge_card_transitions(runner.project)
    assert forges["acme/api"].applied == [("comment", "#1", "left behind")]


def test_the_diagnosis_a_rate_limit_refuses_is_queued_for_after_the_reset(tmp_path, monkeypatch):
    import beeverforge.contracts as contracts
    from beeverforge import factory
    from beeverforge.contracts.project import Project, ProviderRef
    from beeverforge.runtime.temporal import activities
    from beeverforge.techlead import diagnosis

    monkeypatch.setenv("BEEVERFORGE_LOG_DIR", str(tmp_path / "logs"))
    forge = _Forge()
    forge.ticket_url = lambda ref: "https://example.test/1"
    project = Project(name="acme", repo_path=str(tmp_path),
                      tracker=ProviderRef(kind="github", repo="acme/api"))
    monkeypatch.setattr(activities.ProjectRegistry, "get", lambda self, name: project)
    monkeypatch.setattr(activities, "_tracker_for", lambda p: forge)
    monkeypatch.setattr(activities.activity, "logger", logging.getLogger("test.activity"))
    monkeypatch.setattr(diagnosis, "diagnose", lambda *a, **k: object())
    monkeypatch.setattr(contracts, "handoff_to_markdown", lambda ho, raw_note="": "the diagnosis")
    monkeypatch.setattr(contracts, "handoff_to_plain", lambda ho, ref="": "the diagnosis")
    monkeypatch.setattr(factory, "notifier_for_project",
                        lambda p: SimpleNamespace(notify=lambda **k: None))
    activities._do_diagnose(SimpleNamespace(project="acme", issue="#1", state="on_hold",
                                            note="it broke"))
    assert (tmp_path / "logs" / "acme" / "queued-tracker-effects.json").exists()
    forge.limited = False
    factory.drain_queued_effects(project, tracker_for=lambda view: forge, clock=lambda: RESET)
    assert forge.applied == [("comment", "#1", "the diagnosis")]


def test_every_comment_the_worker_posts_goes_through_the_queue():
    """The worker's own comments on a card, read off the module: each `.comment(` is called on
    `_queued(...)`, or on a name the same function bound to it."""
    import ast
    from pathlib import Path

    from beeverforge.runtime.temporal import activities

    tree = ast.parse(Path(activities.__file__).read_text())
    bare = []
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        queued = {t.id for n in ast.walk(fn) if isinstance(n, ast.Assign)
                  and isinstance(n.value, ast.Call) and getattr(n.value.func, "id", "") == "_queued"
                  for t in n.targets if isinstance(t, ast.Name)}
        for call in ast.walk(fn):
            if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                    and call.func.attr == "comment"):
                continue
            on = call.func.value
            if isinstance(on, ast.Name) and on.id == "live":  # the preview's text, not a write
                continue
            if isinstance(on, ast.Call) and getattr(on.func, "id", "") == "_queued":
                continue
            if isinstance(on, ast.Name) and on.id in queued:
                continue
            bare.append(f"{fn.name}:{call.lineno}")
    assert sorted(set(bare)) == [], bare


def test_a_tickets_later_entry_never_overtakes_one_still_waiting():
    forge, clock, t = _tracker()
    t.comment("#1", "first")
    clock.now = RESET

    def again(ref, body):
        raise RateLimited("spent", reset_at=RESET + 500)

    real = forge.comment
    forge.comment = again
    t.flush()  # "first" goes back, due at RESET + 500
    forge.comment = real
    forge.limited = True
    t.comment("#1", "second")  # joins behind "first"
    forge.limited = False
    clock.now = RESET + 1
    t.flush()
    assert forge.applied == []
    clock.now = RESET + 500
    t.flush()
    assert [c[2] for c in forge.applied] == ["first", "second"]


def test_a_long_queued_comment_is_applied_whole():
    forge, clock, t = _tracker()
    body = "x" * 30_060
    t.comment("#1", body)
    forge.limited = False
    clock.now = RESET
    t.flush()
    assert [len(c[2]) for c in forge.applied] == [30_060]


def test_the_queued_line_names_the_comment_and_never_its_words(caplog):
    forge, clock, t = _tracker()
    with caplog.at_level(logging.INFO):
        t.comment("#1", "pushed to https://x-access-token:ghs_SECRETVALUE@github.com/acme/api")
    said = "\n".join(r.getMessage() for r in caplog.records)
    assert "BEEVERFORGE_EFFECT_QUEUED" in said
    assert "ghs_SECRETVALUE" not in said and "x-access-token" not in said


def test_the_queue_file_is_readable_by_its_owner_only(tmp_path):
    forge, clock, t = _tracker(tmp_path)
    t.comment("#1", "words")
    assert (tmp_path / "queue.json").stat().st_mode & 0o077 == 0


def test_a_malformed_entry_is_dropped_by_name_and_the_rest_still_works(tmp_path, caplog):
    import json

    (tmp_path / "queue.json").write_text(json.dumps([{"id": "x"}]))
    forge, clock, t = _tracker(tmp_path)
    forge.limited = False
    with caplog.at_level(logging.ERROR):
        t.comment("#1", "a")
        t.set_state("#2", JobState.VALIDATING)
    assert [c[0] for c in forge.applied] == ["comment", "state"]
    assert any("BEEVERFORGE_QUEUED_EFFECT_UNREADABLE" in r.getMessage() and "x" in r.getMessage()
               for r in caplog.records)


def test_one_tickets_wait_does_not_hold_another_tickets_due_entry():
    forge, clock, t = _tracker()
    real = forge._write

    def write(*call):
        if forge.limited:
            raise RateLimited("spent", reset_at=3600.0 if call[1] == "#1" else 60.0)
        real(*call)

    forge._write = write
    t.comment("#1", "late")
    t.comment("#2", "soon")
    forge.limited = False
    clock.now = 61.0
    t.flush()
    assert forge.applied == [("comment", "#2", "soon")]


def test_a_copy_of_the_tracker_does_not_recurse():
    import copy

    forge, clock, t = _tracker()
    assert copy.copy(t).assignees("#1") == ["someone"]


# -- hcristia's five guards from the first review of #708, as he wrote them --

def test_a_limit_met_again_keeps_the_order_the_new_reset_and_whom_the_state_waits_on():
    forge, clock, t = _tracker()
    t.set_state("#1", JobState.VALIDATING, needs_person=True)
    t.comment("#1", "a")
    clock.now = RESET
    t.comment("#1", "b")  # still limited: joins behind, never overtakes
    assert [e["kind"] for e in t.pending] == ["state", "comment", "comment"]
    forge.limited = False
    t.flush()
    assert [c[0] for c in forge.applied] == ["state", "comment", "comment"]
    assert forge.applied[0][3] is True
    assert [c[2] for c in forge.applied[1:]] == ["a", "b"]


def test_a_write_before_the_reset_joins_behind_its_tickets_queue():
    forge, clock, t = _tracker()
    t.comment("#1", "a")
    forge.limited = False  # the forge would take it now; the ticket's order would be lost
    t.comment("#1", "b")
    t.comment("#2", "c")
    assert forge.applied == [("comment", "#2", "c")]
    assert [e["payload"]["body"] for e in t.pending] == ["a", "b"]


def test_a_limit_met_again_moves_the_entry_to_the_new_reset():
    forge, clock, t = _tracker()
    t.comment("#1", "a")
    clock.now = RESET

    def again(ref, body):
        raise RateLimited("spent", reset_at=RESET + 500)

    forge.comment = again
    t.flush()
    assert t.pending[0]["reset_at"] == RESET + 500


def test_an_entry_refused_for_another_reason_is_dropped_and_the_next_is_applied():
    forge, clock, t = _tracker()
    t.add_label("#1", "bot")
    t.comment("#2", "kept")
    forge.limited = False

    def gone(ref, label):
        raise RuntimeError("404")

    forge.add_label = gone
    clock.now = RESET
    t.flush()
    assert forge.applied == [("comment", "#2", "kept")] and t.pending == []


def test_the_runner_the_factory_composes_queues_in_the_projects_log_directory(
        tmp_path, monkeypatch):
    import subprocess

    from beeverforge import factory, namespace
    from beeverforge.adapters.tracker import github as row
    from beeverforge.contracts.project import Project, ProviderRef
    monkeypatch.setenv("BEEVERFORGE_LOG_DIR", str(tmp_path / "logs"))
    repo = tmp_path / "repo"
    (repo / namespace.MANIFEST).parent.mkdir(parents=True)
    (repo / namespace.MANIFEST).write_text("{}\n")
    project = Project(name="acme", repo_path=str(repo),
                      tracker=ProviderRef(kind="github", repo="acme/api"),
                      forge=ProviderRef(kind="github", repo="acme/api"))
    monkeypatch.setattr(row.time, "sleep", lambda s: None)
    monkeypatch.setattr(row.subprocess, "run", lambda argv, *a, **k: subprocess.CompletedProcess(
        argv, 1, "", "API rate limit exceeded"))
    runner = factory.build_runner(project, "#1", sandbox="worktree", image="img", review=False)
    runner.tracker.comment("#1", "kept")
    assert len(runner.tracker.pending) == 1
    assert list((tmp_path / "logs" / "acme").glob("queued-tracker-effects.json"))
