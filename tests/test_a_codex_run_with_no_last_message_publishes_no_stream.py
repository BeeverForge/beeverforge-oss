"""A Codex run that writes no last message publishes no event stream as the agent's words (#110).

`CodexAdapter._run` used to hand back the tail of the raw `--json` stream as the summary when the
`--output-last-message` file was empty. The pull request quotes that summary under
`AGENT_ACCOUNT_HEADING`, so a run with no final message published JSON events as if they were the
agent's account. Now the summary is empty, the body says the agent ended its pass without a final
message, and the stream stays in `raw_output` for diagnosis.

The same fallback stood in two other harnesses (review of #306). Kimi handed back the raw JSONL as
its summary when the stream parsed but held no `role: assistant` line, and OpenCode's failure
summary ended with the stream's tail, which a gate-repair pass row quotes whether or not the pass
succeeded. Both now hand back no stream: Kimi an empty summary, OpenCode a fixed sentence.
"""

from __future__ import annotations

from pathlib import Path

import test_opencode_harness as oc
import test_walking_skeleton as spine
from test_agent_harness import _REAL_EVENTS, _ctx, _FakeSandbox, _ws

from beeverforge.adapters.agent.base import final_text
from beeverforge.adapters.agent.codex import CodexAdapter
from beeverforge.adapters.agent.kimi import KimiAdapter
from beeverforge.adapters.agent.opencode import OpenCodeAdapter
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


# ── Kimi: a stream that parses but holds no assistant line ───────────────────────────────────────

#: A tool result and the `meta` resume hint, shaped as kimi-code 0.31.1 prints them, with no
#: `role: assistant` line: the run said nothing of its own.
_KIMI_NO_ASSISTANT = "\n".join([
    '{"role":"tool","tool_call_id":"c1","content":"a.txt"}',
    '{"role":"meta","type":"session.resume_hint","session_id":"session_c0c4",'
    '"command":"kimi -r session_c0c4","content":"To resume this session: kimi -r session_c0c4"}',
])
_KIMI_MARKS = ('"role"', "tool_call_id", "session.resume_hint", "{")


def _silent_kimi(context):
    return KimiAdapter().execute(sandbox=_FakeSandbox(run_out=_KIMI_NO_ASSISTANT),
                                 workspace=_ws(), context=context)


def test_a_kimi_run_with_no_assistant_line_hands_back_no_summary():
    res = _silent_kimi(_ctx())

    assert res.summary == "", f"the stream became the summary: {res.summary[:120]!r}"
    text = final_text(res)
    for mark in _KIMI_MARKS:
        assert mark not in text, f"{mark!r} from the Kimi stream is in the agent's account"
    assert "tool_call_id" in res.raw_output, "the stream is lost for diagnosis"


class _SilentKimi:
    def execute(self, *, sandbox, workspace, context) -> AgentRunResult:
        (workspace.path / "health.py").write_text("OK = True\n")
        return _silent_kimi(context)

    def repair(self, *, sandbox, workspace, context, failure_log) -> AgentRunResult:
        raise AssertionError("no repair pass is expected in this run")


def test_a_kimi_run_with_no_assistant_line_says_so_on_the_pull_request(repo: Path,
                                                                        tmp_path: Path):
    ticket = Ticket(id="#7", title="add health check", objective="expose /health", repo="o/r",
                    acceptance_criteria=[AcceptanceCriterion(text="GET /health returns 200")])
    runner = spine._runner(repo, spine.FakeTracker(ticket), Manifest(validate={"test": "true"}),
                           tmp_path, agent=_SilentKimi())
    runner.run("#7")
    assert runner.forge.opened, "no pull request was opened — this guard is measuring nothing"

    body = runner.forge.opened["body"]
    section = body[body.index(AGENT_ACCOUNT_HEADING):]
    assert machine._WROTE_NOTHING in section, section
    for mark in ('"role"', "tool_call_id", "session.resume_hint", "session_c0c4"):
        assert mark not in section, f"{mark!r} from the Kimi stream is quoted as the agent's words"
    assert not [r for r in section.splitlines() if r.startswith("> {")], section


# ── OpenCode: a failed gate-repair pass with no text ─────────────────────────────────────────────

#: A pass that read a file and stopped without a word: no text, no error event, no refused tool.
_OPENCODE_SILENT = "\n".join([oc._step_start(), oc._tool("read"), oc._step_finish(10, 0, 0.001)])
_OPENCODE_MARKS = ("step_start", "step_finish", "tool_use", "sessionID", oc.SESSION, "{")


def _silent_opencode_repair(context):
    return OpenCodeAdapter().repair(sandbox=oc._FakeSandbox(_OPENCODE_SILENT, code=0),
                                    workspace=oc._ws(), context=context, failure_log="red")


def test_an_opencode_pass_with_no_text_hands_back_no_stream():
    res = _silent_opencode_repair(oc._ctx())

    assert not res.ok
    for mark in _OPENCODE_MARKS:
        assert mark not in res.summary, f"{mark!r} from the OpenCode stream is in the summary"
    assert "without a final message" in res.summary, res.summary
    assert "step_finish" in res.raw_output, "the stream is lost for diagnosis"


class _SilentOpenCodeRepair:
    def execute(self, *, sandbox, workspace, context) -> AgentRunResult:
        (workspace.path / "health.py").write_text("OK = True\n")
        return AgentRunResult(ok=True, summary="added the health check")

    def repair(self, *, sandbox, workspace, context, failure_log) -> AgentRunResult:
        (workspace.path / "gate_ok.txt").write_text("ok\n")
        return _silent_opencode_repair(context)


def test_a_failed_opencode_gate_repair_quotes_no_stream_in_its_pass_row(repo: Path,
                                                                        tmp_path: Path):
    ticket = Ticket(id="#7", title="add health check", objective="expose /health", repo="o/r",
                    acceptance_criteria=[AcceptanceCriterion(text="GET /health returns 200")])
    runner = spine._runner(repo, spine.FakeTracker(ticket),
                           Manifest(validate={"test": "test -f gate_ok.txt"}), tmp_path,
                           agent=_SilentOpenCodeRepair())
    runner.run("#7")
    assert runner.forge.opened, "no pull request was opened — this guard is measuring nothing"

    section = runner.forge.opened["body"]
    section = section[section.index(AGENT_ACCOUNT_HEADING):]
    rows = [r for r in section.splitlines() if r.startswith("> - gate repair 1")]
    assert rows, f"the gate-repair pass has no row — this guard is measuring nothing: {section}"
    for mark in ("step\\_start", "step\\_finish", "tool\\_use", "sessionID", "{"):
        assert mark not in rows[0], f"{mark!r} from the OpenCode stream is in the pass row"
    assert "without a final message" in rows[0], rows[0]
