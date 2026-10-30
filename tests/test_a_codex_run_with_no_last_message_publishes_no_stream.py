"""A Codex run that writes no last message publishes no event stream as the agent's words (#110).

`CodexAdapter._run` used to hand back the tail of the raw `--json` stream as the summary when the
`--output-last-message` file was empty. The pull request quotes that summary under
`AGENT_ACCOUNT_HEADING`, so a run with no final message published JSON events as if they were the
agent's account. Now the summary is empty, the body says the agent ended its pass without a final
message, and the stream stays in `raw_output` for diagnosis.
"""

from __future__ import annotations

from pathlib import Path

import test_walking_skeleton as spine
from test_agent_harness import _REAL_EVENTS, _ctx, _FakeSandbox, _ws

from beeverforge.adapters.agent.base import final_text
from beeverforge.adapters.agent.codex import CodexAdapter
from beeverforge.contracts import AcceptanceCriterion, AgentRunResult, Manifest, Ticket
from beeverforge.contracts.run import AGENT_ACCOUNT_HEADING
from beeverforge.orchestrator import machine

repo = spine.repo

_STREAM_MARKS = ("thread.started", '"type"', "item.completed", "turn.completed", "{")


def _silent_codex(context):
    return CodexAdapter().execute(sandbox=_FakeSandbox(run_out=_REAL_EVENTS, last_message=""),
                                  workspace=_ws(), context=context)


def test_a_codex_run_with_no_last_message_hands_back_no_summary():
    res = _silent_codex(_ctx())

    assert res.summary == "", f"the stream became the summary: {res.summary[:120]!r}"
    text = final_text(res)
    for mark in _STREAM_MARKS:
        assert mark not in text, f"{mark!r} from the event stream is in the agent's account"
    assert "thread.started" in res.raw_output, "the stream is lost for diagnosis"


class _SilentCodex:
    def execute(self, *, sandbox, workspace, context) -> AgentRunResult:
        (workspace.path / "health.py").write_text("OK = True\n")
        return _silent_codex(context)

    def repair(self, *, sandbox, workspace, context, failure_log) -> AgentRunResult:
        raise AssertionError("no repair pass is expected in this run")


def test_a_codex_run_with_no_last_message_says_so_on_the_pull_request(repo: Path,
                                                                        tmp_path: Path):
    ticket = Ticket(id="#7", title="add health check", objective="expose /health", repo="o/r",
                    acceptance_criteria=[AcceptanceCriterion(text="GET /health returns 200")])
    runner = spine._runner(repo, spine.FakeTracker(ticket), Manifest(validate={"test": "true"}),
                           tmp_path, agent=_SilentCodex())
    runner.run("#7")
    assert runner.forge.opened, "no pull request was opened — this guard is measuring nothing"

    body = runner.forge.opened["body"]
    assert AGENT_ACCOUNT_HEADING in body, "the pull request carries no account section"
    section = body[body.index(AGENT_ACCOUNT_HEADING):]
    assert machine._WROTE_NOTHING in section, section
    for mark in ("thread.started", '"type"', "item.completed", "turn.completed"):
        assert mark not in section, f"{mark!r} from the event stream is quoted as the agent's words"
    assert not [r for r in section.splitlines() if r.startswith("> {")], section
