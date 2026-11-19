"""A merged job leaves a merge in the metrics (#609).

WHAT WAS WRONG. A pull request merged by hand, whose issue the forge closed before the workflow saw
the merge, left nothing past the merge in the metrics: the door judged `merged` from a card that
was already closed and refused it, and the job's own `job` row was written when the attempt ended,
at a state before the merge — so no row said the job ended merged.

WHAT IS PROVEN HERE, on fakes and with no wait on real time:

  · a job's ending writes ONE `job` row with its final state, its pull request and its platform
    stamp, told apart from the per-attempt rows by `extra.ending`, and writing it again writes
    nothing;
  · both drivers write it — the workflow's `record_outcome` and the attended driver;
  · the telling of a merge is recorded by the door on a card the forge already closed, once per
    pull request, without the writes the forge already made; the box's and the settle's `merged`
    are still refused there;
  · the readers that took every `job` row for an attempt skip the ending.
"""

from __future__ import annotations

import asyncio
import inspect

import pytest

from beeverforge.contracts.state import PAST_THE_MERGE
from beeverforge.lifecycle import CardEvent, record
from beeverforge.lifecycle.card import transition
from beeverforge.lifecycle.handed_back import merged_event
from beeverforge.lifecycle.ports import Seen
from beeverforge.lifecycle.table import State
from beeverforge.observability.job_record import record_job, record_job_ending
from beeverforge.observability.registry import deployment_metrics_sink
from tests.test_the_card_lifecycle_does_what_its_table_says import Ports, Project

PR = "https://forge.example/acme/pull/9"


@pytest.fixture(autouse=True)
def store(monkeypatch, tmp_path):
    monkeypatch.setenv("BEEVERFORGE_METRICS_SINK", "sqlite")
    monkeypatch.setenv("BEEVERFORGE_METRICS_DB", str(tmp_path / "metrics.db"))


def _jobs() -> list[dict]:
    return deployment_metrics_sink().records_of_kind("acme", "job")


def _endings() -> list[dict]:
    return [r for r in _jobs() if (r.get("extra") or {}).get("ending")]


def _moves(card: str = "#9") -> list[str]:
    from beeverforge.contracts.refs import canonical_ref

    return [r.event for r in record.read(record.keyed_sink(), "acme", canonical_ref(card)).rows]


def _closed_by_the_forge(state: State = State.CLOSED) -> Ports:
    return Ports(seen_as=Seen(state=state, open=False), sink_=record.keyed_sink())


def _the_telling(ports: Ports, *, pr: str = PR):
    return transition(Project(), "#9", CardEvent.MERGED, by="the workflow",
                      facts={"pr_url": pr, "stages_follow": False, "note": ""},
                      event_id=merged_event(pr), ports=ports)


# ── the door ───────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("state", [State.CLOSED, State.DELIVERED])
def test_a_merge_the_forge_closed_the_issue_before_is_still_recorded_once(state):
    ports = _closed_by_the_forge(state)
    first = _the_telling(ports)
    assert not first.refused and first.recorded and not first.replayed
    assert _moves() == ["merged"]
    # the forge already closed the card: nothing is written to it again
    written = {call[0] for call in ports.calls}
    assert not written & {"column", "place", "close", "comment", "remove", "reopen"}
    assert first.facts["late"] is True

    again = _the_telling(ports)
    assert again.replayed and _moves() == ["merged"]


def test_a_later_close_the_vendor_shows_is_still_judged_from_the_merge():
    ports = _closed_by_the_forge()
    _the_telling(ports)
    closed = transition(Project(), "#9", CardEvent.CLOSED, by="observed",
                        facts={"before": ""}, ports=ports)
    assert not closed.refused and closed.before is State.MERGED


def test_the_boxes_and_the_settles_merged_are_still_refused_on_a_closed_card():
    ports = _closed_by_the_forge()
    moved = transition(Project(), "#9", CardEvent.MERGED, by="the job",
                       facts={"note": ""}, ports=ports)
    assert moved.refused and _moves() == []


def test_a_merge_with_no_pull_request_is_refused_on_a_closed_card():
    ports = _closed_by_the_forge()
    moved = transition(Project(), "#9", CardEvent.MERGED, by="the workflow",
                       facts={"stages_follow": False, "note": ""}, ports=ports)
    assert moved.refused


# ── the ending ─────────────────────────────────────────────────────────────────────────────────

def test_an_ending_is_one_job_row_told_apart_by_a_field():
    record_job(project="acme", issue="9", ts="2026-11-01T10:00:00+00:00", state="awaiting_merge",
               pr_url=PR, wall_s=12.0)
    assert record_job_ending(project="acme", issue="9", state="merged", pr_url=PR)
    assert record_job_ending(project="acme", issue="9", state="merged", pr_url=PR) is False

    (ending,) = _endings()
    assert ending["state"] == "merged" and ending["pr_url"] == PR
    assert ending["state"] in PAST_THE_MERGE
    assert ending["extra"]["platform"]["version"]
    attempts = [r for r in _jobs() if not (r.get("extra") or {}).get("ending")]
    assert [a["state"] for a in attempts] == ["awaiting_merge"]      # the attempt's row is as it was


def test_a_job_that_ends_in_another_state_writes_its_own_ending():
    record_job_ending(project="acme", issue="9", state="merged", pr_url=PR)
    record_job_ending(project="acme", issue="9", state="done", pr_url=PR)
    assert sorted(r["state"] for r in _endings()) == ["done", "merged"]


def test_an_ending_nobody_can_write_never_raises(monkeypatch):
    def broken():
        raise RuntimeError("no store")
    monkeypatch.setattr("beeverforge.observability.registry.deployment_metrics_sink", broken)
    assert record_job_ending(project="acme", issue="9", state="merged") is False


def test_the_scenario_a_hand_merge_the_forge_closed_first():
    ports = _closed_by_the_forge()
    for _ in range(2):                       # the workflow's telling, and its replay
        _the_telling(ports)
        record_job_ending(project="acme", issue="9", state="merged", pr_url=PR)

    assert len(_endings()) == 1 and _endings()[0]["state"] in PAST_THE_MERGE
    assert _moves() == ["merged"]


def test_the_workflows_exit_writes_the_ending(monkeypatch, tmp_path):
    from beeverforge.runtime.temporal import activities as acts
    from beeverforge.runtime.temporal.io import HoldSyncInput

    class _Registry:
        def get(self, name):
            return Project()

    monkeypatch.setattr(acts, "ProjectRegistry", _Registry)
    monkeypatch.setattr("beeverforge.observability.job_record.record_ending",
                        lambda *a, **k: k.get("state", a[2]))
    asyncio.run(acts.record_outcome(HoldSyncInput(project="acme", issue="9", state="merged",
                                                  pr_url=PR)))
    (ending,) = _endings()
    assert ending["state"] == "merged" and ending["pr_url"] == PR


def test_the_workflow_hands_its_pull_request_to_the_exit():
    from beeverforge.runtime.temporal.workflow import JobWorkflow

    assert 'pr_url=result.pr_url or ""' in inspect.getsource(JobWorkflow.run)
    assert "pr_url=pr_url" in inspect.getsource(JobWorkflow._journal_outcome)


def test_the_attended_driver_writes_the_ending_too():
    from beeverforge import cli

    assert "record_job_ending(" in inspect.getsource(cli._drive_one)


# ── the readers of `job` rows ──────────────────────────────────────────────────────────────────

def test_the_dashboard_keeps_the_attempts_wall_clock_beside_an_ending():
    from beeverforge.api import metrics_view

    record_job(project="acme", issue="9", ts="2026-11-01T10:00:00+00:00", state="merged",
               wall_s=12.0, agent_runs=[{"role": "executor", "cost_usd": 1.0}])
    record_job_ending(project="acme", issue="9", state="merged", pr_url=PR)
    rows = deployment_metrics_sink().records_of_kind("acme", "job") + \
        deployment_metrics_sink().records_of_kind("acme", "agent_run")
    (task,) = metrics_view.dashboard(rows, "acme")["tasks"]
    assert task["wall_s"] == 12.0
