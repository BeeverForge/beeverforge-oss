"""#653 — `dismiss` closes a held job whose workflow has ended, and leaves the card where it is."""
import json
import logging
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from beeverforge import actions
from beeverforge.actions import catalog
from beeverforge.observability.job_record import record_ending
from beeverforge.paths import events_file

ACME = SimpleNamespace(name="acme")
BY = actions.Actor(id="ana", display="Ana", via="panel", admin=True)


@pytest.fixture(autouse=True)
def world(monkeypatch, tmp_path):
    monkeypatch.setenv("BEEVERFORGE_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(catalog, "_project", lambda name: (ACME, None))

    async def running(client, project, issue):
        return _Engine.running

    monkeypatch.setattr(catalog, "_running", running)

    async def connected():
        return object(), None

    monkeypatch.setattr(catalog, "_connected", connected)
    _Engine.running = False


class _Engine:
    running = False


def _hold(issue="7"):
    record_ending(ACME, issue, "on_hold", by="the workflow",
                  note="the workflow was cancelled or terminated")


def _journal(issue="7") -> list[dict]:
    path = events_file(ACME, issue)
    return [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []


async def _dismiss(issue="7", **params):
    return await actions.perform("dismiss", by=BY, project="acme", issue=issue, **params)


async def test_it_writes_one_dismissed_event_with_who_and_why_and_moves_no_card(monkeypatch):
    moved = []
    monkeypatch.setattr(catalog, "_through_the_door", lambda *a, **k: moved.append(a))
    _hold()
    out = await _dismiss(why="shipped by hand")
    assert out.ok, out.message
    (event,) = [e for e in _journal() if e["message"] == "dismissed"]
    assert event["kind"] == "state"
    assert "Ana" in event["data"]["by"] and event["data"]["reason"] == "shipped by hand"
    assert moved == []


async def test_a_second_dismissal_writes_nothing_more():
    _hold()
    await _dismiss()
    out = await _dismiss()
    assert out.ok
    assert len([e for e in _journal() if e["message"] == "dismissed"]) == 1


async def test_a_workflow_that_still_runs_is_refused_naming_skip():
    _hold()
    _Engine.running = True
    out = await _dismiss()
    assert out.code == actions.CONFLICT and "skip" in out.message
    assert not [e for e in _journal() if e["message"] == "dismissed"]


async def test_an_issue_nothing_ran_for_is_not_found():
    out = await _dismiss("99")
    assert out.code == actions.NOT_FOUND
    assert _journal("99") == []


@pytest.mark.parametrize("bad", ["../7", "CONT-7", "7a", "7\n"])
async def test_the_issue_must_be_digits(bad):
    out = await _dismiss(bad)
    assert not out.ok and out.code in (actions.INVALID, actions.NOT_FOUND)
    assert not [e for e in _journal() if e["message"] == "dismissed"]


async def test_allowed_and_refused_each_leave_one_audit_record(caplog):
    _hold()
    with caplog.at_level(logging.INFO):
        await _dismiss()
        _Engine.running = True
        await _dismiss()
    lines = [r for r in caplog.records if "dismiss" in r.getMessage()]
    assert len(lines) == 2


def test_the_cli_invokes_the_action(monkeypatch):
    from beeverforge import cli

    asked = []

    async def perform(name, *, by, **params):
        asked.append((name, params, by.via))
        return actions.base.done("ok")

    monkeypatch.setattr(actions, "perform", perform)
    out = CliRunner().invoke(cli.app, ["job", "dismiss", "acme", "7", "--why", "shipped"])
    assert out.exit_code == 0, out.output
    assert asked == [("dismiss", {"project": "acme", "issue": "7", "why": "shipped"}, "cli")]


def test_the_panel_attention_row_offers_it_escaped():
    from pathlib import Path

    html = (Path(catalog.__file__).parents[1] / "api" / "panel.html").read_text()
    assert 'data-k="dismiss"' in html and "act/dismiss" in html


class _Handle:
    def __init__(self, result):
        self.result = result

    async def describe(self):
        if isinstance(self.result, BaseException):
            raise self.result
        return SimpleNamespace(status=self.result)


async def _ask_running(monkeypatch, result):
    from beeverforge.runtime.temporal import view as tv

    monkeypatch.setattr(tv, "job_handle", lambda client, project, issue: _Handle(result))
    # the autouse fixture replaces `_running`; call the real one
    return await _real_running(object(), "acme", "7")


_real_running = catalog._running


@pytest.mark.asyncio
async def test_running_reads_the_engines_status_and_a_missing_workflow_is_not_running(monkeypatch):
    from temporalio.client import WorkflowExecutionStatus
    from temporalio.service import RPCError, RPCStatusCode

    assert await _ask_running(monkeypatch, WorkflowExecutionStatus.RUNNING) is True
    assert await _ask_running(monkeypatch, WorkflowExecutionStatus.COMPLETED) is False
    missing = RPCError("workflow not found", RPCStatusCode.NOT_FOUND, b"")
    assert await _ask_running(monkeypatch, missing) is False
    other = RPCError("deadline exceeded", RPCStatusCode.DEADLINE_EXCEEDED, b"")
    with pytest.raises(RPCError):
        await _ask_running(monkeypatch, other)
