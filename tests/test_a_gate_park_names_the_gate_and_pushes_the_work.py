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
import sys
from types import SimpleNamespace

import test_walking_skeleton as spine

from beeverforge.adapters.sandbox import WorktreeSandbox
from beeverforge.contracts import (
    AcceptanceCriterion,
    AgentRunResult,
    JobState,
    Manifest,
    RunResult,
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
    assert "nothing was pushed" in note.lower(), note
    assert "unable to access" not in note, "git's raw words reached the note"
    assert any("unable to access" in e.message for e in events.events), (
        "the journal does not keep git's words")
    for surface in [note, *tracker.comments, *(e.message for e in events.events),
                    *(repr(e.data) for e in events.events)]:
        assert token not in surface, surface


# ── 7. a failed push says where the work is, on each box, and the Resume keeps the promise ─────

def _git(cwd, *args: str) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                          check=True).stdout.strip()


class _WatchingSandbox(_RecordingSandbox):
    """The real sandbox, recording the commit each workspace starts from."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.started_at: list[str] = []

    def prepare(self, **kwargs):
        ws = super().prepare(**kwargs)
        self.started_at.append(_git(ws.path, "rev-parse", "HEAD"))
        return ws


class _RefusingContainerLike(_RefusingSandbox):
    """A refused push on a box that keeps nothing once the job ends, as the container box says."""

    def kept_after_cleanup(self, *, workspace):
        return None


def test_on_the_worktree_box_a_failed_push_names_the_local_branch_and_resume_keeps_it(
        repo, tmp_path):
    """The remedy the note gives — push the local branch by hand, then Resume — is followed, and
    the resumed workspace starts from that work, not from the base."""
    refusing = _RefusingSandbox(root=tmp_path / "wt")
    result, tracker = _run(repo, tmp_path, "1111", {"test": _TEST_GATE}, sandbox=refusing)

    branch = result.branch
    local_tip = _git(repo, "rev-parse", f"refs/heads/{branch}")
    assert local_tip != _git(repo, "rev-parse", "main"), "the agent's commit is not on the branch"
    for surface in (result.note or "", _hold_comment(tracker)):
        assert f"local branch `{branch}`" in surface, surface
        assert f"`{repo}`" in surface, surface
        assert "push it to the forge by hand before resuming" in surface, surface
        assert "credential" not in surface, f"the remedy sends the reader elsewhere:\n{surface}"
    assert result.resume_handle, "a Resume after the push by hand would start from the base"

    _git(repo, "push", "origin", f"{branch}:{branch}")  # what the note asks of its reader
    watching = _WatchingSandbox(root=tmp_path / "wt")
    tracker2 = _tracker("1111")
    runner = spine._runner(repo, tracker2, Manifest(validate={"test": _TEST_GATE},
                                                     repair_max_attempts=1), tmp_path,
                           agent=spine.FakeRepairAgent(), sandbox=watching)
    runner.run("#1111", resume_handle=result.resume_handle)

    assert watching.started_at == [local_tip], (
        f"the resume started from {watching.started_at}, not the work at {local_tip}")


def test_on_a_box_that_keeps_nothing_a_failed_push_says_the_work_was_discarded(repo, tmp_path):
    sandbox = _RefusingContainerLike(root=tmp_path / "wt")
    result, _ = _run(repo, tmp_path, "1112", {"test": _TEST_GATE}, sandbox=sandbox)

    note = result.note or ""
    assert "nothing was pushed" in note.lower(), note
    assert "discarded" in note and "the work is lost" in note, note
    assert "by hand" not in note, note
    assert not result.resume_handle, "a Resume would promise to continue work that is gone"


def test_a_commit_that_fails_is_said_as_a_commit_and_not_as_a_push(repo, tmp_path):
    tracker = _tracker("1113")
    sandbox = _RecordingSandbox(root=tmp_path / "wt")
    runner = spine._runner(repo, tracker, Manifest(validate={"test": _TEST_GATE},
                                                    repair_max_attempts=1), tmp_path,
                           agent=spine.FakeRepairAgent(), sandbox=sandbox)
    commit = runner._commit

    def _commit(ws, ticket):
        # only the preserve's commit fails: the ones before the gates must land for a park
        if sys._getframe(1).f_code.co_name == "_preserve_for_hold":
            raise RuntimeError("the box did not answer")
        commit(ws, ticket)

    runner._commit = _commit
    result = runner.run("#1113")

    note = result.note or ""
    assert result.state is JobState.ON_HOLD
    assert sandbox.published == [], "a push was attempted after the commit failed"
    assert "could not be committed" in note, note
    assert "box prove" in note, f"no remedy for the commit:\n{note}"
    assert "push of" not in note and "credential" not in note, note
    assert not result.resume_handle


# ── 8. a push replaces only what the run started from ───────────────────────────────────────────

def _a_person_pushes(tmp_path, branch: str, name: str, *, start: str = "main") -> str:
    """A person's commit on `branch` in the origin, made from a clone of their own."""
    clone = tmp_path / f"person-{name}"
    if not clone.exists():
        subprocess.run(["git", "clone", "-q", str(tmp_path / "origin.git"), str(clone)],
                       check=True, capture_output=True)
        _git(clone, "config", "user.email", "someone@example.invalid")
        _git(clone, "config", "user.name", "someone")
    _git(clone, "fetch", "-q", "origin")
    _git(clone, "checkout", "-q", "-B", branch, start)
    (clone / f"{name}.txt").write_text("fixed by hand\n")
    _git(clone, "add", "-A")
    _git(clone, "commit", "-qm", f"{name} by hand")
    _git(clone, "push", "-q", "origin", f"{branch}:{branch}")
    return _git(clone, "rev-parse", "HEAD")


def _origin_tip(tmp_path, branch: str) -> str:
    return _git(tmp_path / "origin.git", "rev-parse", f"refs/heads/{branch}")


def _kept(tmp_path, branch: str, tip: str) -> str:
    """The commit the kept branch for `tip` holds on the origin, or "" when there is none."""
    p = subprocess.run(["git", "-C", str(tmp_path / "origin.git"), "rev-parse", "--verify", "-q",
                        f"refs/heads/{branch}-kept-{tip[:12]}"], capture_output=True, text=True)
    return p.stdout.strip()


def _holds_the_runs_work(tmp_path, branch: str) -> bool:
    """Whether the origin's `branch` carries the agent's `feature.py`."""
    p = subprocess.run(["git", "-C", str(tmp_path / "origin.git"), "cat-file", "-e",
                        f"refs/heads/{branch}:feature.py"], capture_output=True)
    return p.returncode == 0


def _names_the_kept_branch(surfaces, branch: str, tip: str) -> bool:
    return any(f"`{branch}-kept-{tip[:12]}`" in s for s in surfaces)


def test_a_fresh_run_keeps_a_commit_it_did_not_make_and_pushes_its_own(repo, tmp_path):
    """A later run of the card without the handle starts from the base. Its pull-request push used
    to replace whatever a park had left on the branch, and the person's fix with it; now the
    forge's tip is kept on a branch of its own first, the card says where, and the run lands."""
    theirs = _a_person_pushes(tmp_path, "beeverforge/1114", "person")
    forge = spine.FakeForge()
    events = InMemoryEventSink()
    tracker = _tracker("1114")
    runner = spine._runner(repo, tracker, Manifest(validate={"test": "true"}), tmp_path,
                           forge=forge, events=events)
    result = runner.run("#1114")

    assert result.state is not JobState.ON_HOLD, result.note
    assert forge.opened is not None, "the run did not reach its pull request"
    assert _kept(tmp_path, "beeverforge/1114", theirs) == theirs, "the person's commit is lost"
    assert _holds_the_runs_work(tmp_path, "beeverforge/1114"), "the run's own work did not land"
    assert _names_the_kept_branch(tracker.comments, "beeverforge/1114", theirs), tracker.comments
    assert _names_the_kept_branch([e.message for e in events.events], "beeverforge/1114", theirs)


def test_a_gate_park_keeps_a_commit_it_did_not_make_and_pushes_its_own(repo, tmp_path):
    theirs = _a_person_pushes(tmp_path, "beeverforge/1115", "person")
    result, tracker = _run(repo, tmp_path, "1115", {"test": _TEST_GATE})

    assert _kept(tmp_path, "beeverforge/1115", theirs) == theirs, "the person's commit is lost"
    assert _holds_the_runs_work(tmp_path, "beeverforge/1115")
    assert "The work is on branch `beeverforge/1115`" in (result.note or ""), result.note
    assert _names_the_kept_branch(tracker.comments, "beeverforge/1115", theirs), tracker.comments


class _ARaceAfterTheKeep(WorktreeSandbox):
    """The real sandbox, with a person pushing again right after the box kept the forge's tip."""

    def __init__(self, *args, again, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.again = again

    def keep_remote_tip(self, *, workspace, remote_url=None) -> str:
        kept = super().keep_remote_tip(workspace=workspace, remote_url=remote_url)
        self.again()
        return kept


def test_a_commit_landing_between_the_keep_and_the_push_is_refused_and_the_job_holds(
        repo, tmp_path):
    theirs = _a_person_pushes(tmp_path, "beeverforge/1119", "person")
    later: list[str] = []

    def again() -> None:
        later.append(_a_person_pushes(tmp_path, "beeverforge/1119", "again",
                                      start="origin/beeverforge/1119"))

    forge = spine.FakeForge()
    runner = spine._runner(repo, _tracker("1119"), Manifest(validate={"test": "true"}), tmp_path,
                           forge=forge, sandbox=_ARaceAfterTheKeep(root=tmp_path / "wt",
                                                                   again=again))
    result = runner.run("#1119")

    assert later, "the race never ran"
    assert _origin_tip(tmp_path, "beeverforge/1119") == later[0], "the later commit was replaced"
    assert _kept(tmp_path, "beeverforge/1119", theirs) == theirs
    assert result.state is JobState.ON_HOLD, result.note
    assert forge.opened is None
    note = result.note or ""
    assert f"kept them on `beeverforge/1119-kept-{theirs[:12]}`" in note, note
    assert "moved again" in note, note
    assert result.resume_handle


def test_a_kept_name_already_holding_something_else_is_never_replaced(repo, tmp_path):
    """The keep is never forced: a branch already at its name holding another commit stays as it
    is, nothing is replaced, and the job holds naming the branch."""
    theirs = _a_person_pushes(tmp_path, "beeverforge/1120", "person")
    planted = _a_person_pushes(tmp_path, f"beeverforge/1120-kept-{theirs[:12]}", "planted")
    forge = spine.FakeForge()
    runner = spine._runner(repo, _tracker("1120"), Manifest(validate={"test": "true"}), tmp_path,
                           forge=forge)
    result = runner.run("#1120")

    assert _kept(tmp_path, "beeverforge/1120", theirs) == planted, "the kept name was forced"
    assert _origin_tip(tmp_path, "beeverforge/1120") == theirs, "the person's commit was replaced"
    assert result.state is JobState.ON_HOLD and forge.opened is None, result.note
    assert "keeping a copy of them first failed" in (result.note or ""), result.note


def test_a_gate_park_that_cannot_keep_the_forges_commits_says_nothing_was_pushed(
        repo, tmp_path):
    theirs = _a_person_pushes(tmp_path, "beeverforge/1123", "person")
    planted = _a_person_pushes(tmp_path, f"beeverforge/1123-kept-{theirs[:12]}", "planted")
    result, _ = _run(repo, tmp_path, "1123", {"test": _TEST_GATE})

    assert _origin_tip(tmp_path, "beeverforge/1123") == theirs, "the person's commit was replaced"
    assert _kept(tmp_path, "beeverforge/1123", theirs) == planted
    note = result.note or ""
    assert "Nothing was pushed: `beeverforge/1123` on the forge has commits" in note, note
    assert "keeping a copy of them first failed" in note, note
    assert result.resume_handle


class _WritesThenHitsTheLimit:
    """Writes part of the feature, then pauses on a rate limit with a session to continue."""

    def execute(self, *, sandbox, workspace, context) -> AgentRunResult:
        (workspace.path / "feature.py").write_text("HALF_DONE = 1\n")
        return AgentRunResult(ok=False, pause_reason="rate_limit", retry_at="16:00",
                              resume_handle="sess-abc")

    def repair(self, *, sandbox, workspace, context, failure_log) -> AgentRunResult:
        return AgentRunResult(ok=True)


def test_a_rate_limit_pause_keeps_a_commit_it_did_not_make_and_pushes_its_own(repo, tmp_path):
    """The pause's preserve pushed around `_publish`: on a fresh start its lease refused a branch
    an earlier park had left, the pause returned no handle, and the resume prepared from the base
    with `branch -D` — the agent's partial work gone. It goes through the one door now."""
    theirs = _a_person_pushes(tmp_path, "beeverforge/1124", "person")
    tracker = _tracker("1124")
    runner = spine._runner(repo, tracker, Manifest(validate={"test": "true"}), tmp_path,
                           agent=_WritesThenHitsTheLimit())
    result = runner.run("#1124")

    assert result.state is JobState.PAUSED, result.note
    assert _kept(tmp_path, "beeverforge/1124", theirs) == theirs, "the person's commit is lost"
    assert _holds_the_runs_work(tmp_path, "beeverforge/1124"), "the partial work was not pushed"
    assert result.resume_handle == "sess-abc", "the pause carries no way back into its work"
    assert _names_the_kept_branch(tracker.comments, "beeverforge/1124", theirs), tracker.comments


def test_a_rate_limit_pause_that_cannot_keep_the_forges_commits_hands_back_no_handle(
        repo, tmp_path):
    """Nothing pushed is nothing to continue: the pause says why, and carries no handle that would
    make the resume check out a branch this run never pushed."""
    theirs = _a_person_pushes(tmp_path, "beeverforge/1125", "person")
    planted = _a_person_pushes(tmp_path, f"beeverforge/1125-kept-{theirs[:12]}", "planted")
    events = InMemoryEventSink()
    tracker = _tracker("1125")
    runner = spine._runner(repo, tracker, Manifest(validate={"test": "true"}), tmp_path,
                           agent=_WritesThenHitsTheLimit(), events=events)
    result = runner.run("#1125")

    assert result.state is JobState.PAUSED, result.note
    assert _origin_tip(tmp_path, "beeverforge/1125") == theirs, "the person's commit was replaced"
    assert _kept(tmp_path, "beeverforge/1125", theirs) == planted
    assert result.resume_handle is None
    said = [e.message for e in events.events]
    assert not any("partial work pushed" in m for m in said), said
    warned = [m for m in said if "couldn't preserve partial work" in m]
    assert warned and "keeping a copy of them first failed" in warned[0], said
    assert "the resume starts fresh from the base" in warned[0], warned
    assert "Resume continues from the forge" not in warned[0], warned
    assert any("Nothing was pushed" in c for c in tracker.comments), tracker.comments


class _APersonPushesDuringTheRepair:
    """A CI-repair agent that fixes the check while a person pushes to the same branch."""

    def __init__(self, push) -> None:
        self.push, self.pushed = push, []

    def execute(self, *, sandbox, workspace, context) -> AgentRunResult:
        (workspace.path / "feature.py").write_text("VALUE = 42\n")
        return AgentRunResult(ok=True, cost_usd=0.01)

    def repair(self, *, sandbox, workspace, context, failure_log) -> AgentRunResult:
        self.pushed.append(self.push())
        (workspace.path / "repaired.txt").write_text("repaired\n")
        return AgentRunResult(ok=True, cost_usd=0.01, summary="repaired the check")


def test_a_ci_repair_keeps_a_commit_pushed_during_its_pass(repo, tmp_path):
    branch = "beeverforge/1121"
    agent = _APersonPushesDuringTheRepair(
        lambda: _a_person_pushes(tmp_path, branch, "person", start=f"origin/{branch}"))
    forge, tracker = spine.FakeForge(), _tracker("1121")
    runner = spine._runner(repo, tracker, Manifest(validate={"test": "true"}), tmp_path,
                           forge=forge, agent=agent)
    first = runner.run("#1121")
    assert forge.opened is not None, first.note

    runner.repair_ci("#1121", "CI failed: test_x broke", pr_url="https://forge/pr/1")

    theirs = agent.pushed[0]
    assert _kept(tmp_path, branch, theirs) == theirs, "the person's commit is lost"
    tip = _origin_tip(tmp_path, branch)
    assert subprocess.run(["git", "-C", str(tmp_path / "origin.git"), "cat-file", "-e",
                           f"{tip}:repaired.txt"]).returncode == 0, "the repair did not land"
    assert _names_the_kept_branch(tracker.comments, branch, theirs), tracker.comments


def test_the_auto_merge_rebase_push_keeps_a_commit_pushed_after_the_pull_request(
        repo, tmp_path):
    """The push after a rebase leases on the tip the pull request's push left; a person's commit
    since then is kept before the rebased branch replaces it, and the merge goes on."""
    branch = "beeverforge/1122"
    forge, tracker = spine.FakeForge(), _tracker("1122")
    runner = spine._runner(repo, tracker, Manifest(validate={"test": "true"}), tmp_path,
                           forge=forge)
    ws = runner.sandbox.prepare(repo_path=repo, base_branch="main", branch=branch)
    (ws.path / "feature.py").write_text("VALUE = 42\n")
    _git(ws.path, "add", "-A")
    _git(ws.path, "-c", "user.email=bot@example.invalid", "-c", "user.name=bot", "commit", "-qm",
         "the run's own")
    runner.sandbox.publish_branch(workspace=ws)
    theirs = _a_person_pushes(tmp_path, branch, "person", start=f"origin/{branch}")
    _a_person_pushes(tmp_path, "main", "moved-main")  # the base moves, so the branch is rebased
    result = RunResult(ticket_id="#1122", state=JobState.VALIDATING, branch=branch)
    held = runner._auto_merge(_ticket("1122"), ws, "https://forge/pr/1", "main", branch, result,
                              None)

    assert held is None, held and held.note
    assert forge.merge_calls == 1
    assert _kept(tmp_path, branch, theirs) == theirs, "the person's commit is lost"
    assert _holds_the_runs_work(tmp_path, branch)
    assert _names_the_kept_branch(tracker.comments, branch, theirs), tracker.comments


# ── 9. Resume continues the parked work, with a person's fix on top ─────────────────────────────

def test_resume_starts_from_the_forge_branch_with_the_persons_fix(repo, tmp_path):
    """The note promises "Resume continues it, or fix the gate there by hand". Both, in turn: the
    park pushes, a person commits the fix on that branch, and the resumed run starts from the
    forge's tip — their commit included — goes green and opens the pull request over it."""
    gate = {"test": "test -f person.txt"}
    sandbox = _WatchingSandbox(root=tmp_path / "wt")
    first, _ = _run(repo, tmp_path, "1116", gate, sandbox=sandbox)
    assert first.state is JobState.ON_HOLD and first.resume_handle, first.note
    parked = _origin_tip(tmp_path, first.branch)

    theirs = _a_person_pushes(tmp_path, first.branch, "person", start=f"origin/{first.branch}")
    assert _git(tmp_path / "origin.git", "rev-parse", f"{theirs}~1") == parked

    forge = spine.FakeForge()
    runner = spine._runner(repo, _tracker("1116"), Manifest(validate=gate, repair_max_attempts=1),
                           tmp_path, agent=spine.FakeRepairAgent(), forge=forge, sandbox=sandbox)
    second = runner.run("#1116", resume_handle=first.resume_handle)

    assert sandbox.started_at[-1] == theirs, (
        f"the resume started from {sandbox.started_at[-1]}, not the forge's tip {theirs}")
    assert second.state is not JobState.ON_HOLD, second.note
    assert forge.opened is not None, "no pull request after the resumed run went green"
    tip = _origin_tip(tmp_path, first.branch)
    subprocess.run(["git", "-C", str(tmp_path / "origin.git"), "merge-base", "--is-ancestor",
                    theirs, tip], check=True)


# ── 10. a credential no name gives away reaches no surface ──────────────────────────────────────

def test_a_pat_under_a_name_no_scrub_reads_is_withheld_from_every_surface(
        repo, tmp_path, monkeypatch):
    """SECURITY.md's two: the shipped `AZURE_DEVOPS_PAT`, which the worktree box passes to its
    workloads, and a project's `token_env`, which can be called anything. Neither value has a
    prefix, and neither name matched the scrub's (`TOKEN|SECRET|…`), so a gate that printed its
    environment put both in full on the card."""
    pat = "q7" * 26  # 52 characters, no prefix
    theirs = "m3" * 20  # 40 characters, under a name nothing reads as a credential's
    monkeypatch.setenv("AZURE_DEVOPS_PAT", pat)
    monkeypatch.setenv("ACME_ADO_AUTH", theirs)
    events = InMemoryEventSink()
    tracker = _tracker("1117")
    runner = spine._runner(
        repo, tracker, Manifest(validate={"test": "printenv AZURE_DEVOPS_PAT; "
                                                  "echo ACME_ADO_AUTH=$ACME_ADO_AUTH; exit 1"},
                                repair_max_attempts=1),
        tmp_path, agent=spine.FakeRepairAgent(), events=events,
        sandbox=_RefusingSandbox(root=tmp_path / "wt"))
    runner.project = SimpleNamespace(forge=SimpleNamespace(options={"token_env": "ACME_ADO_AUTH"}))

    def _refused(*, workspace, remote_url=None):
        raise RuntimeError(f"push failed: remote said {pat} and {theirs}")

    runner.sandbox.publish_branch = _refused
    result = runner.run("#1117")

    note = result.note or ""
    assert WITHHELD_CREDENTIAL in note and "ACME_ADO_AUTH=" in note, note
    for surface in [note, *tracker.comments, *(e.message for e in events.events),
                    *(repr(e.data) for e in events.events)]:
        assert pat not in surface, surface
        assert theirs not in surface, surface


# ── 11. what the gate printed cannot notify anybody ─────────────────────────────────────────────

def test_a_mention_and_a_card_number_the_gate_printed_sit_in_the_code_block(repo, tmp_path):
    tracker = spine.FakeTracker(_ticket("1118"), assignees=[])  # no owner to mention
    runner = spine._runner(repo, tracker, Manifest(
        validate={"test": "printf '@%s pinged\\n#%s failed\\n' someone 12; exit 1"},
        repair_max_attempts=1), tmp_path, agent=spine.FakeRepairAgent())
    runner.run("#1118")

    comment = _hold_comment(tracker)
    mentioned = [ln for ln in comment.splitlines() if "@someone" in ln]
    assert mentioned, comment
    assert all(ln.startswith("    ") for ln in mentioned), (
        f"an `@someone` the gate printed is outside the code block:\n{comment}")
    assert "#12" not in comment, f"`#12` names a card on a tracker that reads it:\n{comment}"
    numbered = [ln for ln in comment.splitlines() if "card 12 failed" in ln]
    assert numbered and all(ln.startswith("    ") for ln in numbered), comment


# ── 6. the memory recognises the same failure twice ──────────────────────────────────────────────

def test_two_gate_parks_that_differ_only_in_output_share_one_memory_signature():
    head = "validations failed after 2 repair attempt(s)"
    a = f"{head}\n\n`test` exited 1:\n\n    $ pytest\n    1 failed in 0.31s\n"
    b = f"{head}\n\n`test` exited 1:\n\n    $ pytest\n    3 failed in 2.07s\n"

    assert memory.signature(a) == memory.signature(b)
    assert memory.signature(a) == memory.signature(head)
    assert memory.signature("rate limit exceeded") != memory.signature(
        "could not clone the repository")
