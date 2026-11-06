"""The agent's own words reach the journal, the panel and the ticket with any credential withheld
(#197).

MEASURED AT 01bb5c6. #885 withheld a credential where the agent's account is quoted into the pull
request (`_quoted`, `_pass_words`), and nowhere else: the journal note `agent finished:
{agent_result.summary[:200]}` went to the event sinks and the panel as written, and so did every
repair's note, every `agent_action` the harness reported, a reviewer's finding in the `review`
event's detail, and the hold reasons `_hold` posts on the ticket (`agent stopped: {summary}`,
`ci-repair agent stopped: {summary}`) — a forge comment on a GitHub tracker.

THE ORDER IS THE POINT. Each note cuts the agent's words (`[:200]`, `[:150]`, `[:120]`), and a
credential straddling the cut keeps only its head: `ghp_` and ten characters match no shape, so a
scrub applied AFTER the cut shows them. Every case below places the synthetic token so 14 of its
characters fall before the cut, and asserts that neither the token nor its first 12 (the vendor
prefix and 8 more) reaches any event's message or data, any ticket comment, or the result's note.
Each case also finds its own note, so it cannot pass with the note gone.

THE PAYLOAD STAYS RAW. `RunResult.agent_account` is what `_pr_body` composes the account from, so
withholding there would make the body's withholding depend on the payload (ADR-0001, D-5).

Every guard drives the real `JobRunner.run` or `JobRunner.repair_ci`. The token is built at run
time, never written whole.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import test_walking_skeleton as spine
from test_an_adjust_pass_runs_the_gates import _an_open_pull_request

from beeverforge.contracts import AgentRunResult, Finding, Manifest, ReviewResult
from beeverforge.observability import InMemoryEventSink
from beeverforge.product import model
from beeverforge.product.model import scrub_credentials

repo = spine.repo

TOKEN = "ghp_" + "q7" + "SECRET" * 6
#: The vendor prefix and eight characters more: what must never be seen of the token.
HEAD = TOKEN[:12]
#: An action as a Claude harness reports it: the command line, whole.
ACTION = f"Bash: curl -H 'X-Token: {TOKEN}' https://api.example.test/x"
PR = "https://forge/pr/1"


def straddling(cut: int) -> str:
    """Words whose token starts 14 characters before `cut`: the cut keeps `ghp_` and 10 more."""
    return "x" * (cut - 15) + " " + TOKEN


@pytest.fixture(autouse=True)
def _no_secret_of_this_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """A secret-named variable of the machine running the suite must not change what is withheld:
    these tests hold the token's SHAPE, not the environment."""
    for name in list(os.environ):
        if model._SECRET_NAME.search(name):
            monkeypatch.delenv(name, raising=False)


def test_the_head_a_cut_keeps_matches_no_shape():
    """Precondition of every case: if the cut head were withheld on its own, a scrub after the cut
    would pass for one before it."""
    assert scrub_credentials(TOKEN[:14]) == TOKEN[:14], "the head matches a shape — wrong case"
    assert TOKEN not in scrub_credentials(ACTION)
    assert straddling(200)[:200].endswith(" " + TOKEN[:14])


# ── what a person reads ───────────────────────────────────────────────────────────────────────────

def _read(events: InMemoryEventSink, tracker: spine.FakeTracker, result) -> list[str]:
    """Every event's message and data, every ticket comment, and the result's note."""
    out = [f"{e.kind}: {e.message} {e.data!r}" for e in events.events]
    return out + list(tracker.comments) + [result.note or ""]


def _withheld(events, tracker, result, *, said: str) -> None:
    """Nothing read shows the token or its head, and `said` — the site's own note — is there."""
    read = _read(events, tracker, result)
    shown = [t for t in read if HEAD in t]
    assert not shown, f"the agent's credential reached what a person reads: {shown}"
    assert any(said in t for t in read), f"no {said!r} was written — this case measures nothing"


def _run(repo: Path, tmp_path: Path, agent, manifest: Manifest | None = None, reviewer=None):
    events = InMemoryEventSink()
    tracker = spine.FakeTracker(spine._sizing_ticket_id("#9"))
    runner = spine._runner(repo, tracker, manifest or Manifest(validate={"test": "true"}),
                           tmp_path, agent=agent, reviewer=reviewer, events=events)
    return runner.run("#9"), events, tracker


def _repair_ci(repo: Path, tmp_path: Path, agent, *, human: bool = False,
               manifest: Manifest | None = None):
    _an_open_pull_request(repo)
    events = InMemoryEventSink()
    tracker = spine.FakeTracker(spine._sizing_ticket_id("#9"))
    runner = spine._runner(repo, tracker, manifest or Manifest(validate={"test": "true"}),
                           tmp_path, agent=agent, forge=spine.FakeForge(), events=events)
    log = "the person's words" if human else "FAILED tests/test_x.py::test_it"
    return runner.repair_ci("#9", log, pr_url=PR, human=human), events, tracker


# ── the doubles: every pass reports a command line carrying the token ─────────────────────────────

def _said(summary: str, *, ok: bool = True, **extra) -> AgentRunResult:
    return AgentRunResult(ok=ok, summary=summary, cost_usd=0.01, actions=[ACTION], **extra)


class _Executor:
    """Writes `feature.py` and ends with `summary`; its repairs end with `repairs` in turn."""

    def __init__(self, summary: str = "added feature.py", *, ok: bool = True, raw: str = "",
                 repairs: tuple[str, ...] = ("repaired",), feature: str = "VALUE = 42\n",
                 fixes: str = "fixed.txt") -> None:
        self.summary, self.ok, self.raw, self.repairs = summary, ok, raw, repairs
        self.feature, self.fixes, self.passes = feature, fixes, 0

    def execute(self, *, sandbox, workspace, context) -> AgentRunResult:
        (workspace.path / "feature.py").write_text(self.feature)
        return _said(self.summary, ok=self.ok, raw_output=self.raw)

    def repair(self, *, sandbox, workspace, context, failure_log) -> AgentRunResult:
        self.passes += 1
        (workspace.path / "feature.py").write_text(f"VALUE = {42 + self.passes}\n")
        (workspace.path / self.fixes).write_text("fixed\n")
        return _said(self.repairs[min(self.passes, len(self.repairs)) - 1])


class _Recovers(_Executor):
    """Stops unfinished with `summary`; its recovery finishes with `recovered`."""

    def __init__(self, summary: str, recovered: str) -> None:
        super().__init__(summary, ok=False)
        self.recovered = recovered

    def recover(self, *, sandbox, workspace, context, brief) -> AgentRunResult:
        (workspace.path / "done.py").write_text("DONE = 1\n")
        return _said(self.recovered)


class _Plans(_Executor):
    """A planner that answers `plan`, then the executor above."""

    def __init__(self, plan: str, **extra) -> None:
        super().__init__()
        self.plan_text, self.extra = plan, extra

    def plan(self, *, sandbox, workspace, context) -> AgentRunResult:
        return _said(self.plan_text, **self.extra)


class _Fixes:
    """A CI or adjust pass: writes the change, and its later passes clear `red.txt`."""

    def __init__(self, *words: str, ok: bool = True, red: bool = False) -> None:
        self.words, self.ok, self.red, self.passes = words, ok, red, 0

    def repair(self, *, sandbox, workspace, context, failure_log) -> AgentRunResult:
        self.passes += 1
        tree = Path(workspace.path)
        if self.passes == 1:
            (tree / "button.py").write_text("SIDE = 'right'\n")
            if self.red:
                (tree / "red.txt").write_text("the gate is red\n")
        else:
            (tree / "red.txt").unlink(missing_ok=True)
        return _said(self.words[min(self.passes, len(self.words)) - 1], ok=self.ok)


def _rejected() -> ReviewResult:
    return ReviewResult(decision="rejected", score=40, summary="not done as submitted",
                        findings=[Finding(severity="critical", description="the wrong bundle",
                                          file="t.tsx", line=1)])


def _approved() -> ReviewResult:
    return ReviewResult(decision="approved", score=95, summary="fixed")


def _decision(question: str) -> str:
    """A DecisionRequest with the token in every free-text field: the question, its context, and
    each option's label and consequence. The keys carry none: an answer is matched on them."""
    return "```json\n" + json.dumps({
        "question": question,
        "context": f"the deploy key is {TOKEN}",
        "options": [{"key": "A", "label": f"keep it ({TOKEN})",
                     "consequence": f"nothing moves; {TOKEN} stays"},
                    {"key": "B", "label": "split it", "consequence": f"two cards, {TOKEN}"}],
        "default": "A"}) + "\n```"


# ── criterion: a journal note withholds a credential the cut straddles ───────────────────────────

def _agent_finished(repo, tmp_path):
    return _run(repo, tmp_path, _Executor(straddling(200))), "agent finished: "


def _gate_repair(repo, tmp_path):
    return (_run(repo, tmp_path, _Executor(repairs=(straddling(150),)),
                 Manifest(validate={"test": "test -f fixed.txt"})), "repair 1: ")


def _suppression_repair(repo, tmp_path):
    agent = _Executor(feature="VALUE = 42  # pragma: no cover\n", repairs=(straddling(150),))
    return (_run(repo, tmp_path, agent, Manifest(validate={"test": "true", "security": "true"})),
            "suppression-repair 1: ")


def _review_repair(repo, tmp_path):
    manifest = Manifest(validate={"test": "true", "security": "true"}, review_mode="blocking",
                        review_repair_max_attempts=1)
    reviewer = spine._ScriptedReviewer([_rejected(), _approved()])
    return (_run(repo, tmp_path, _Executor(repairs=(straddling(150),)), manifest, reviewer),
            "review-repair 1: ")


def _ci_repair(repo, tmp_path):
    return _repair_ci(repo, tmp_path, _Fixes(straddling(150))), "ci-repair: "


def _adjust_repair(repo, tmp_path):
    return (_repair_ci(repo, tmp_path, _Fixes("pass 1", straddling(150), red=True), human=True,
                       manifest=Manifest(validate={"test": "test ! -e red.txt"})),
            "adjust repair 1: ")


def _planner_paused(repo, tmp_path):
    agent = _Plans(straddling(200), ok=False, pause_reason="rate_limit", retry_at="16:00")
    return (_run(repo, tmp_path, agent, Manifest(validate={"test": "true"}, planner_stage=True)),
            "planner paused: ")


def _plan_ready(repo, tmp_path):
    return (_run(repo, tmp_path, _Plans(straddling(200)),
                 Manifest(validate={"test": "true"}, planner_stage=True)), "plan ready: ")


def _recovery(repo, tmp_path):
    agent = _Recovers(straddling(120), straddling(150))
    return (_run(repo, tmp_path, agent, Manifest(validate={"test": "true"},
                                                 recovery_max_attempts=1)),
            "recovery 1 finished: ")


@pytest.mark.parametrize("case", [
    _agent_finished, _gate_repair, _suppression_repair, _review_repair, _ci_repair,
    _adjust_repair, _planner_paused, _plan_ready, _recovery,
], ids=["agent-finished", "repair", "suppression-repair", "review-repair", "ci-repair",
        "adjust-repair", "planner-paused", "plan-ready", "recovery"])
def test_the_agents_words_in_a_journal_note_withhold_a_credential_the_cut_straddles(
        repo: Path, tmp_path: Path, case):
    """At 01bb5c6 each note quoted the cut words as written: the token whole (and its command
    line in the `agent_action` beside it), or `ghp_` and ten characters once the scrub follows
    the cut."""
    (result, events, tracker), said = case(repo, tmp_path)
    _withheld(events, tracker, result, said=said)


def test_the_recovery_note_withholds_what_the_executor_said_when_it_stopped(repo, tmp_path):
    """`stopped unfinished ({summary[:120]})`: its own cut, its own case."""
    (result, events, tracker), _ = _recovery(repo, tmp_path)
    _withheld(events, tracker, result, said="stopped unfinished (")


# ── criterion: a hold note on the ticket withholds the agent's credential ────────────────────────

def _agent_stopped(repo, tmp_path):
    agent = _Executor(f"stopped: pushed with {TOKEN} and gave up", ok=False)
    return (_run(repo, tmp_path, agent, Manifest(validate={"test": "true"},
                                                 recovery_max_attempts=0)), "agent stopped: ")


def _ci_repair_stopped(repo, tmp_path):
    return (_repair_ci(repo, tmp_path, _Fixes(f"stopped: pushed with {TOKEN}", ok=False)),
            "ci-repair agent stopped: ")


def _executor_decision(repo, tmp_path):
    agent = _Executor("stopped to ask", ok=False, raw=_decision(straddling(200)))
    return _run(repo, tmp_path, agent), "decision needed — "


def _planner_decision(repo, tmp_path):
    plan = '{"status": "blocked"}\n' + _decision(straddling(200))
    return (_run(repo, tmp_path, _Plans(plan),
                 Manifest(validate={"test": "true"}, planner_stage=True)), "decision needed — ")


def _too_large(repo, tmp_path):
    lead = "SPLIT NEEDED: "
    return (_run(repo, tmp_path, _Plans(lead + straddling(400 - len(lead))),
                 Manifest(validate={"test": "true"}, planner_stage=True)), "ticket too large — ")


def _assumption(repo, tmp_path):
    plan = json.dumps({"status": "assume", "assumption": f"the key {TOKEN} is a test one"})
    return (_run(repo, tmp_path, _Plans(plan),
                 Manifest(validate={"test": "true"}, planner_stage=True)), "assumption (auto")


@pytest.mark.parametrize("case", [
    _agent_stopped, _ci_repair_stopped, _executor_decision, _planner_decision, _too_large,
    _assumption,
], ids=["agent-stopped", "ci-repair-stopped", "executor-decision", "planner-decision",
        "too-large", "assumption"])
def test_a_hold_note_on_the_ticket_withholds_the_agents_credential(repo, tmp_path, case):
    """At 01bb5c6 `_hold` posted the reason on the ticket, set it on the `state` event and the
    result's note, and notified it — the agent's words in it as written."""
    (result, events, tracker), said = case(repo, tmp_path)
    _withheld(events, tracker, result, said=said)
    assert any(said in c for c in tracker.comments), f"no {said!r} on the ticket: {tracker.comments}"


@pytest.mark.parametrize("case", [_executor_decision, _planner_decision],
                         ids=["executor-decision", "planner-decision"])
def test_the_decision_the_result_carries_withholds_the_agents_credential(repo, tmp_path, case):
    """At 5055c6b `_hold(..., decision=dr)` carried the agent's DecisionRequest as written: it
    becomes `RunResult.decision`, which the impediment payload, the panel's needs-you API and the
    coordinator's channel item quote. Every free-text field withholds; the keys stay as written,
    so an answer still matches."""
    (result, events, tracker), _ = case(repo, tmp_path)
    dr = result.decision
    assert dr is not None, "the hold carried no decision — this case measures nothing"
    assert HEAD not in dr.model_dump_json(), f"the agent's credential is on the decision: {dr}"
    assert dr.question.startswith("x" * 100), dr.question
    assert model.WITHHELD_CREDENTIAL in dr.question
    assert dr.context == f"the deploy key is {model.WITHHELD_CREDENTIAL}", dr.context
    assert [o.key for o in dr.options] == ["A", "B"] and dr.default == "A"
    assert [o.label for o in dr.options] == [f"keep it ({model.WITHHELD_CREDENTIAL})", "split it"]
    assert all(model.WITHHELD_CREDENTIAL in o.consequence for o in dr.options)
    assert dr.option("b") is not None, "an answer no longer matches its option"


def test_the_decision_comment_withholds_the_question_whole(repo, tmp_path):
    """`_record_decision` posts the question uncut, beside the hold that cuts it at 200."""
    agent = _Executor("stopped to ask", ok=False, raw=_decision(f"may I push {TOKEN}?"))
    result, events, tracker = _run(repo, tmp_path, agent)
    _withheld(events, tracker, result, said="**Decision needed**")


# ── criterion: the review event's detail withholds a credential in a finding ─────────────────────

class _Finds:
    def review(self, *, sandbox, workspace, review_input) -> ReviewResult:
        return ReviewResult(
            decision="approved_with_findings", score=88, summary="looks correct",
            findings=[Finding(severity="low", description=straddling(200),
                              file=f"src/{TOKEN}.py", line=3)])


def test_the_review_event_detail_withholds_a_credential_in_a_finding(repo, tmp_path):
    assert scrub_credentials(f"src/{TOKEN}.py") != f"src/{TOKEN}.py", "the file is no credential"
    result, events, tracker = _run(repo, tmp_path, _Executor(), reviewer=_Finds())
    details = [f for e in events.events if e.kind == "review" for f in e.data.get("detail", [])]
    assert details, "no review event carried a detail — this case measures nothing"
    assert all(f["description"].startswith("x" * 100) and f["line"] == 3 for f in details)
    shown = [f for f in details if HEAD in f["description"] or HEAD in f["file"]]
    assert not shown, f"the reviewer's credential reached the panel: {shown}"
    _withheld(events, tracker, result, said="review: ")


# ── criterion: the activity payload keeps the account raw ────────────────────────────────────────

def test_the_activity_payload_keeps_the_agents_account_raw(repo, tmp_path):
    """Pinned so the decision is not undone by accident: `_pr_body` withholds from this."""
    (result, events, tracker), _ = _agent_finished(repo, tmp_path)
    assert TOKEN in (result.agent_account or ""), "the account was withheld in the payload"
    _withheld(events, tracker, result, said="agent finished: ")
