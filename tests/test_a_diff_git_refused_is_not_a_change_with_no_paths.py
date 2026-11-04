"""A `git diff --name-only` git refused is not a change that touched no paths (#368).

`JobRunner._pr_diff_paths` used to answer a failed read with `[]`. Its two callers read that as
"nothing reached the verifier": the CI-repair pass left an ARMED auto-merge standing on a push
nobody had checked against the protected paths, and the knowledge gate judged an empty change.
Git's own words (exit 128, dubious ownership, a lock) reached nobody.

MEASURED ON THE UNCHANGED CODE, 2026-11-03: the CI-repair test below, with the box's git refusing
the diff, ended `PR_OPEN` with auto-merge still armed. The path is reachable: `_pr_diff` turns the
same refusal into `None` without stopping, `_commit` runs `|| true`, and the push runs from the
HOST on both boxes, so a box whose own git refuses the workspace still pushes and reaches the read.

BOTH DIRECTIONS ARE GUARDED: an empty diff git DID answer with exit 0 is still no paths changed.
"""

from __future__ import annotations

from pathlib import Path

import test_walking_skeleton as spine
from test_a_pass_that_changed_nothing import _pr_branch, _WritingAgent

from beeverforge.adapters.sandbox.worktree import WorktreeSandbox
from beeverforge.contracts import JobState, Manifest, RunResult
from beeverforge.orchestrator.machine import DiffPathsUnread

repo = spine.repo

REMEDY = "make git usable on this workspace in the box"
REFUSED = (128, "fatal: detected dubious ownership in repository at '/work'\n"
                "To add an exception for this directory, call:\n\n"
                "\tgit config --global --add safe.directory /work")


class _NamesDiffAs:
    """A real worktree box whose `git diff --name-only` answers what the test scripts."""

    def __init__(self, inner: WorktreeSandbox, answer: tuple[int, str]) -> None:
        self._inner = inner
        self._answer = answer

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def run(self, *, workspace, command, timeout, **kw):
        if command.startswith("git diff --name-only"):
            return self._answer
        return self._inner.run(workspace=workspace, command=command, timeout=timeout, **kw)


def _repair(repo: Path, tmp_path: Path, answer: tuple[int, str]):
    _pr_branch(repo, "beeverforge/9")
    tracker = spine.FakeTracker(spine._sizing_ticket_id("#9"))
    forge = spine.FakeForge()
    box = _NamesDiffAs(WorktreeSandbox(root=tmp_path / "wt"), answer)
    runner = spine._runner(repo, tracker, Manifest(validate={"test": "true"}), tmp_path,
                           agent=_WritingAgent(), forge=forge, sandbox=box)
    return runner.repair_ci("#9", "CI failed: test_x broke", "https://forge/pr/1"), forge


# ── the CI-repair pass: a push to an armed auto-merge ────────────────────────────────────────────

def test_a_ci_repair_whose_diff_git_refuses_is_held_and_disarmed(repo: Path, tmp_path: Path):
    result, forge = _repair(repo, tmp_path, REFUSED)

    assert result.state is JobState.ON_HOLD, (
        "git would not name the paths this push changed and the armed auto-merge was left standing")
    assert forge.auto_merge_disabled is True
    note = result.note or ""
    assert "128" in note, note
    assert "dubious ownership" in note, note
    assert REMEDY in note, note
    assert "\n" not in note, note


def test_an_empty_diff_git_answered_is_no_paths_on_the_ci_repair(repo: Path, tmp_path: Path):
    result, forge = _repair(repo, tmp_path, (0, ""))

    assert result.state is JobState.PR_OPEN, result.note
    assert not forge.auto_merge_disabled
    assert "could not" not in (result.note or "")


# ── the knowledge gate: informs, never fails the job ─────────────────────────────────────────────

def _gate(repo: Path, tmp_path: Path, answer: tuple[int, str]) -> RunResult:
    from beeverforge.adapters.sandbox.base import Workspace

    tracker = spine.FakeTracker(spine._sizing_ticket_id("#9"))
    box = _NamesDiffAs(WorktreeSandbox(root=tmp_path / "wt"), answer)
    runner = spine._runner(repo, tracker, Manifest(okf_gate="advise"), tmp_path, sandbox=box)
    runner._published_okf = lambda: None
    runner._change_repo = lambda: "o/app"
    ws = Workspace(path=repo, branch="beeverforge/9", base_branch="main", host_path=repo)
    result = RunResult(ticket_id="#9", state=JobState.PR_OPEN)
    runner._knowledge_gate(tracker.ticket, ws, "main", result)
    return result


def test_the_knowledge_gate_says_git_refused_the_diff(repo: Path, tmp_path: Path):
    result = _gate(repo, tmp_path, REFUSED)

    note = result.knowledge_note or ""
    assert "128" in note, note
    assert "dubious ownership" in note, note
    assert REMEDY in note, note
    assert "nothing was judged" in note, note
    assert "\n" not in note, note
    assert not result.knowledge_stance, "a stance was recorded on a change nothing judged"


def test_an_empty_diff_git_answered_is_judged_by_the_knowledge_gate(repo: Path, tmp_path: Path):
    result = _gate(repo, tmp_path, (0, ""))

    assert not (result.knowledge_note or "").startswith("could not run"), result.knowledge_note
    assert result.knowledge_stance, "the gate judged nothing on a diff git answered"


# ── the read itself ──────────────────────────────────────────────────────────────────────────────

def test_pr_diff_paths_tells_a_refusal_from_an_empty_answer(tmp_path: Path):
    class _Says:
        answer: tuple[int, str] = (0, "")

        def run(self, *, workspace, command, timeout):
            return self.answer

    box = _Says()
    tracker = spine.FakeTracker(spine._sizing_ticket_id("#9"))
    runner = spine._runner(tmp_path, tracker, Manifest(), tmp_path, sandbox=box)

    assert runner._pr_diff_paths(None, "main") == []
    box.answer = (0, "a.py\n")
    assert runner._pr_diff_paths(None, "main") == ["a.py"]
    box.answer = REFUSED
    try:
        runner._pr_diff_paths(None, "main")
    except DiffPathsUnread as exc:
        said = str(exc)
        assert "128" in said and "safe.directory /work" in said, said
        assert REMEDY in said and "\n" not in said, said
    else:
        raise AssertionError("a diff git refused came back as a list of paths")
