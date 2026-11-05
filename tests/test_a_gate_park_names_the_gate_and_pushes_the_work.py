"""A park on failed gates names the gate and what it printed, and pushes the work it leaves (#11).

THE PARK USED TO BE ONE SENTENCE. `On hold — validations failed after 2 repair attempt(s)` was the
whole card, so whoever was asked to act — a person, or the tech-lead role reading the park — had
to guess which gate failed and why. On one ticket the gate was red for an environmental reason and
the tech-lead read the park three times and reasoned about the code each time, wrongly, because
the failing test names were never written down.

AND THE WORK WAS LEFT ON ONE MACHINE. The turn-cap, agent-stop and cost-ceiling holds preserve the
agent's commits through `_preserve_for_hold` (ADR-0013 D1); the gate park took neither that nor
the pause's `_preserve_partial`, so the branch lived only in the worker's worktree, which
`cleanup` removes and the next `RepoCache.sync` resets.

These tests drive `JobRunner.run` with the walking-skeleton harness: a real `WorktreeSandbox`, a
bare origin, and gates that are real shell commands failing after the repairs.
"""

from __future__ import annotations

import subprocess

import test_walking_skeleton as spine

from beeverforge.adapters.sandbox import WorktreeSandbox
from beeverforge.contracts import (
    AcceptanceCriterion,
    AgentRunResult,
    JobState,
    Manifest,
    Ticket,
    ValidationResult,
)
from beeverforge.observability import InMemoryEventSink
from beeverforge.orchestrator.machine import _failing_gates_said
from beeverforge.product.model import WITHHELD_CREDENTIAL
from beeverforge.techlead import memory
from beeverforge.techlead.classify import CODE, classify

#: the real-git harness — a bare origin and a repo with one commit — borrowed rather than rebuilt
repo = spine.repo

#: A command no PATH resolves, as in `test_a_gate_that_could_not_run.py`.
MISSING = "beeverforge-not-a-real-tool-7c1e"

#: what it prints is assembled by `printf`, so a line of output is never a substring of the command
_TEST_GATE = "printf 'E   assert %s == %s\\n%s failed in 0.01s\\n' 41 42 1; exit 1"
_SCAN_GATE = "printf 'scanner-only-line\\n'; exit 1"


def _token() -> str:
    """A synthetic token, built at run time so no credential-shaped literal sits in the tree."""
    return "ghp_" + "Z9" * 18


def _ticket(n: str) -> Ticket:
    return Ticket(id=f"#{n}", title="feature", objective="add a feature", repo="o/app",
                  acceptance_criteria=[AcceptanceCriterion(text="feature.py exists")])


def _tracker(n: str) -> spine.FakeTracker:
    return spine.FakeTracker(_ticket(n), assignees=["someone"])


def _hold_comment(tracker: spine.FakeTracker) -> str:
    said = [c for c in tracker.comments if "On hold" in c]
    assert said, f"no hold comment on the ticket: {tracker.comments!r}"
    return said[-1]


class _RecordingSandbox(WorktreeSandbox):
    """The real sandbox, recording each `publish_branch` before it pushes."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.published: list[str] = []

    def publish_branch(self, *, workspace, remote_url=None) -> None:
        self.published.append(workspace.branch)
        super().publish_branch(workspace=workspace, remote_url=remote_url)


class _RefusingSandbox(_RecordingSandbox):
    """A push the forge refuses, with git's words carrying the push URL's credential."""

    def publish_branch(self, *, workspace, remote_url=None) -> None:
        self.published.append(workspace.branch)
        raise RuntimeError(f"push failed: fatal: unable to access "
                           f"'https://x-access-token:{_token()}@forge.invalid/o/app.git/'")


class _WritesNothingAgent:
    """Ends every pass having changed nothing."""

    def execute(self, *, sandbox, workspace, context) -> AgentRunResult:
        return AgentRunResult(ok=True, cost_usd=0.01)

    def repair(self, *, sandbox, workspace, context, failure_log) -> AgentRunResult:
        return AgentRunResult(ok=True, cost_usd=0.01)


def _run(repo, tmp_path, n: str, validate: dict, *, agent=None, sandbox=None, events=None,
         attempts: int = 1):
    tracker = _tracker(n)
    manifest = Manifest(validate=validate, repair_max_attempts=attempts)
    runner = spine._runner(repo, tracker, manifest, tmp_path, agent=agent or spine.FakeRepairAgent(),
                           sandbox=sandbox, events=events)
    result = runner.run(f"#{n}")
    return result, tracker


# ── 1. the note names the gate, its command and what it printed ──────────────────────────────────

def test_the_note_and_the_comment_name_the_failing_gate_its_command_and_its_output(repo, tmp_path):
    result, tracker = _run(repo, tmp_path, "1101", {
        "test": _TEST_GATE,
        "scan": {"command": _SCAN_GATE, "advisory": True},
    })

    assert result.state is JobState.ON_HOLD
    note, comment = result.note or "", _hold_comment(tracker)
    for surface in (note, comment):
        assert "`test`" in surface, surface
        assert _TEST_GATE in surface, surface
        assert "E   assert 41 == 42" in surface and "1 failed in 0.01s" in surface, surface
        assert "scan" not in surface, f"an advisory gate is named as the cause:\n{surface}"
        assert "scanner-only-line" not in surface, surface
    assert comment.startswith("@someone "), comment


def test_past_three_failing_gates_the_note_says_how_many_more(repo, tmp_path):
    result, _ = _run(repo, tmp_path, "1102", {
        "test": "echo red-a; exit 1", "lint": "echo red-b; exit 1",
        "security": "echo red-c; exit 1", "type": "echo red-d; exit 1",
    })

    note = result.note or ""
    named = [role for role in ("test", "lint", "security", "type") if f"`{role}`" in note]
    assert len(named) == 3, note
    assert "and 1 more" in note, note


# ── 2. the journal holds the long form ───────────────────────────────────────────────────────────

def test_the_journal_holds_the_whole_tail_and_the_note_the_short_one(repo, tmp_path):
    events = InMemoryEventSink()
    gate = "for i in 01 02 03 04 05 06 07 08 09 10 11 12; do echo line-$i; done; exit 1"
    result, _ = _run(repo, tmp_path, "1103", {"test": gate}, events=events)

    note = result.note or ""
    assert "line-12" in note, note
    assert "line-01" not in note, f"the card holds the whole tail:\n{note}"
    tails = [g.get("output_tail", "") for e in events.events
             for g in (e.data.get("gates") or [])]
    assert any(all(f"line-{i:02d}" in t for i in range(1, 13)) for t in tails), (
        f"no journal event carries the whole tail: {tails!r}")


# ── 3. a credential the gate printed reaches no surface ──────────────────────────────────────────

def test_a_token_in_the_gate_output_reaches_no_surface(repo, tmp_path):
    token = _token()
    events = InMemoryEventSink()
    result, tracker = _run(repo, tmp_path, "1104", {
        # the shell assembles the token, so it is in what the gate PRINTED and not in its command
        "test": "t=$(printf 'Z9%.0s' $(seq 18)); echo \"Authorization: Bearer ghp_$t\"; "
                "echo \"GH_TOKEN=ghp_$t\"; exit 1",
    }, events=events)

    note = result.note or ""
    assert WITHHELD_CREDENTIAL in note, note
    assert token not in note, note
    for comment in tracker.comments:
        assert token not in comment, comment
    for e in events.events:
        assert token not in e.message, e.message
        assert token not in repr(e.data), e.data


def test_a_token_in_the_gates_command_is_withheld_from_the_gate_line():
    """A manifest command can carry a credential too (`curl -H 'Authorization: …'`)."""
    token = _token()
    said = _failing_gates_said([
        ValidationResult(name="test", command=f"curl -H 'Authorization: Bearer {token}' x",
                         exit_code=22, passed=False, output_tail="curl: (22) 404"),
    ])

    assert "curl -H" in said and WITHHELD_CREDENTIAL in said, said
    assert token not in said, said


# ── 4. the note keeps its first sentence, and its classification ─────────────────────────────────

def test_the_note_still_starts_with_its_sentence_and_reads_as_the_change(repo, tmp_path):
    result, _ = _run(repo, tmp_path, "1105", {"test": _TEST_GATE})

    note = result.note or ""
    assert note.startswith("validations failed after 1 repair attempt(s)\n"), note
    assert classify(note).detail == "the-change"
    assert classify(note, cause=result.hold_cause).detail == "the-change"
    assert result.hold_cause == CODE


def test_a_gate_that_prints_a_network_word_is_still_the_change(repo, tmp_path):
    """The project's output cannot steer the verdict: the park declares its own cause."""
    result, _ = _run(repo, tmp_path, "1106", {"test": "echo 'connection refused'; exit 1"})

    note = result.note or ""
    assert "connection refused" in note, note
    assert classify(note, cause=result.hold_cause).detail == "the-change"


def test_a_gate_that_never_ran_keeps_its_own_reason_and_declares_no_code_cause(repo, tmp_path):
    result, _ = _run(repo, tmp_path, "1107", {"test": "true", "lint": f"{MISSING} check ."})

    note = result.note or ""
    assert note.startswith("a gate could not run"), note
    assert result.hold_cause != CODE


# ── 5. the work is pushed, or the note says why not ──────────────────────────────────────────────

def test_the_work_is_pushed_and_the_hold_is_resumable(repo, tmp_path):
    sandbox = _RecordingSandbox(root=tmp_path / "wt")
    result, tracker = _run(repo, tmp_path, "1108", {"test": _TEST_GATE}, sandbox=sandbox)

    assert sandbox.published, "the gate park pushed nothing"
    listed = subprocess.run(["git", "branch", "--list", result.branch],
                            cwd=tmp_path / "origin.git", capture_output=True, text=True,
                            check=True).stdout
    assert result.branch in listed, f"{result.branch} is not in the origin"
    assert result.resume_handle, "the hold is not resumable"
    for surface in (result.note or "", _hold_comment(tracker)):
        assert f"`{result.branch}`" in surface, surface
        assert "Resume continues it" in surface, surface


def test_with_no_work_written_nothing_is_pushed_and_the_note_says_so(repo, tmp_path):
    sandbox = _RecordingSandbox(root=tmp_path / "wt")
    result, _ = _run(repo, tmp_path, "1109", {"test": "false"}, sandbox=sandbox,
                     agent=_WritesNothingAgent())

    assert result.state is JobState.ON_HOLD
    assert sandbox.published == []
    assert not result.resume_handle
    assert "nothing was pushed" in (result.note or "").lower(), result.note


def test_a_push_that_fails_is_said_and_carries_no_credential(repo, tmp_path):
    token = _token()
    events = InMemoryEventSink()
    sandbox = _RefusingSandbox(root=tmp_path / "wt")
    result, tracker = _run(repo, tmp_path, "1110", {"test": _TEST_GATE}, sandbox=sandbox,
                           events=events)

    note = result.note or ""
    assert sandbox.published, "no push was attempted"
    assert not result.resume_handle
    assert "nothing was pushed" in note.lower(), note
    assert "push" in note and "credential" in note, f"no cause and remedy for the push:\n{note}"
    assert "unable to access" not in note, "git's raw words reached the note"
    assert any("unable to access" in e.message for e in events.events), (
        "the journal does not keep git's words")
    for surface in [note, *tracker.comments, *(e.message for e in events.events),
                    *(repr(e.data) for e in events.events)]:
        assert token not in surface, surface


# ── 6. the memory recognises the same failure twice ──────────────────────────────────────────────

def test_two_gate_parks_that_differ_only_in_output_share_one_memory_signature():
    head = "validations failed after 2 repair attempt(s)"
    a = f"{head}\n\n`test` exited 1:\n\n    $ pytest\n    1 failed in 0.31s\n"
    b = f"{head}\n\n`test` exited 1:\n\n    $ pytest\n    3 failed in 2.07s\n"

    assert memory.signature(a) == memory.signature(b)
    assert memory.signature(a) == memory.signature(head)
    assert memory.signature("rate limit exceeded") != memory.signature(
        "could not clone the repository")
