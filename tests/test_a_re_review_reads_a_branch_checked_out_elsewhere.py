"""#55 — a re-review reads the tip of a branch a person has out in their own review tree.

WHAT HAPPENED. Every door that checks a card's branch out with the worktree box refuses a branch
another working tree holds, and holds the job for a person (#623). That is right for the passes
that commit: an adjust, a CI repair, a resumed attempt. `JobRunner.review_pr` went through the same
`prepare(checkout_existing=True)`, so a re-review held too, though it writes nothing: a person who
asked for a fresh review while their review tree was open was told to remove that tree first.

WHAT IS PROVEN HERE, against real git. The box's `prepare_tip` checks the branch's tip out
detached (`git worktree add --detach`, which git allows while another tree has the branch out),
on the local forge and on a hosted one, and touches nothing of the person's: not their tree, not
their branch, and not on a failed forge read either. The machine's re-review then reads the pull
request's diff from that checkout and publishes a verdict, with no hold, no commit and no
`publish_branch`. A box without `prepare_tip` still holds, as before.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from beeverforge.adapters.sandbox import worktree as worktree_box
from beeverforge.adapters.sandbox.worktree import WorktreeSandbox
from beeverforge.contracts import JobState
from beeverforge.techlead.classify import TREE
from tests.test_a_branch_checked_out_elsewhere_holds_the_job import (
    _commit,
    _git,
    _registered,
    _repository,
    _sha,
)
from tests.test_an_adjust_on_a_branch_checked_out_elsewhere_holds_for_a_person import (
    BRANCH as CARD_BRANCH,
)
from tests.test_an_adjust_on_a_branch_checked_out_elsewhere_holds_for_a_person import (
    PR,
    _Agent,
    _an_open_pull_request_a_person_reviews,
    _CountingReviewer,
    _held_for_a_person,
    _machine,
)

BRANCH = "beeverforge/28"
NOTES = "what I noticed reviewing\n"


def _tip(box: WorktreeSandbox, repo: Path, remote_url: str | None):
    return box.prepare_tip(repo_path=repo, base_branch="main", branch=BRANCH,
                           remote_url=remote_url)


def _detached(ws_path: Path) -> bool:
    p = subprocess.run(["git", "-C", str(ws_path), "symbolic-ref", "-q", "HEAD"],
                       capture_output=True, text=True)
    return p.returncode != 0


@pytest.fixture
def held(tmp_path):
    """The local forge: the repository is the remote, and the person has the card's branch out in
    a review tree of their own, with an edit in it they have not committed."""
    repo = _repository(tmp_path / "myapp")
    review = tmp_path / "review tree"
    _git(repo, "worktree", "add", "-q", str(review), BRANCH)
    (review / "notes.txt").write_text(NOTES)
    return repo, review, WorktreeSandbox(root=tmp_path / "boxes")


@pytest.fixture
def hosted(tmp_path):
    """A hosted forge: a bare origin holds the card's branch, the person's clone has it out in a
    review tree, and the factory pushed again since, so the clone's branch is behind."""
    origin = tmp_path / "forge.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)],
                   capture_output=True, check=True)
    seed = _repository(tmp_path / "seed")
    _git(seed, "push", "-q", str(origin), "main", BRANCH)
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(origin), str(clone)], capture_output=True,
                   check=True)
    review = tmp_path / "review"
    _git(clone, "worktree", "add", "-q", str(review), BRANCH)
    (review / "notes.txt").write_text(NOTES)
    _git(seed, "switch", "-q", BRANCH)
    _commit(seed, "work.py", "WORK = 2\n", "the factory's second pass")
    _git(seed, "push", "-q", str(origin), BRANCH)
    return clone, review, origin, WorktreeSandbox(root=tmp_path / "boxes")


# ── the box ───────────────────────────────────────────────────────────────────────────────────────

def test_the_tip_of_a_held_branch_is_checked_out_detached(held):
    """On `main` there was no such door: `prepare(checkout_existing=True)` refused the branch."""
    repo, review, box = held
    before = _sha(repo, f"refs/heads/{BRANCH}")

    ws = _tip(box, repo, str(repo))

    assert _git(ws.path, "rev-parse", "HEAD") == before
    assert _detached(ws.path)
    assert ws.branch == BRANCH
    assert str(review.resolve()) in _registered(repo)
    assert _git(review, "symbolic-ref", "--short", "HEAD") == BRANCH
    assert (review / "notes.txt").read_text() == NOTES
    assert _sha(repo, f"refs/heads/{BRANCH}") == before

    box.cleanup(workspace=ws)
    assert not ws.path.exists()
    assert str(ws.path.resolve()) not in _registered(repo)
    assert _sha(repo, f"refs/heads/{BRANCH}") == before
    assert str(review.resolve()) in _registered(repo)
    assert (review / "notes.txt").read_text() == NOTES


def test_on_a_hosted_forge_the_tip_of_a_held_branch_is_read(hosted):
    """The forge is one push ahead of the clone: the review reads the forge's tip, and the clone's
    branch and the person's tree stay where they were."""
    clone, review, origin, box = hosted
    forge_tip = _sha(origin, f"refs/heads/{BRANCH}")
    mine, theirs = _sha(clone, f"refs/heads/{BRANCH}"), _git(review, "rev-parse", "HEAD")
    assert forge_tip != mine

    ws = _tip(box, clone, f"file://{origin}")

    assert _git(ws.path, "rev-parse", "HEAD") == forge_tip
    assert _detached(ws.path)
    assert ws.base_commit == _sha(origin, "refs/heads/main")
    assert _sha(clone, f"refs/heads/{BRANCH}") == mine
    assert _git(review, "rev-parse", "HEAD") == theirs
    assert (review / "notes.txt").read_text() == NOTES


def test_a_failed_base_read_on_the_tip_keeps_the_persons_branch(hosted, monkeypatch):
    """The forge's base cannot be read from the box's checkout. The new door refuses, as the
    continuing door does, and never runs `branch -D` on the person's branch on the way out."""
    clone, review, origin, box = hosted
    _git(clone, "worktree", "remove", "--force", str(review))
    mine = _sha(clone, f"refs/heads/{BRANCH}")
    real = worktree_box._run

    def _run(cmd, **kw):
        if "fetch" in cmd and "refs/heads/main" in cmd:
            return 128, "fatal: unable to access the forge"
        return real(cmd, **kw)

    monkeypatch.setattr(worktree_box, "_run", _run)
    with pytest.raises(RuntimeError, match="could not read 'main' from the forge"):
        _tip(box, clone, f"file://{origin}")
    assert _sha(clone, f"refs/heads/{BRANCH}") == mine


# ── the machine ──────────────────────────────────────────────────────────────────────────────────

class _ReadingReviewer(_CountingReviewer):
    """Counts the reviews, and keeps the diff each one was handed."""

    def __init__(self):
        super().__init__()
        self.diffs: list[str] = []

    def review(self, *, sandbox, workspace, review_input):
        self.diffs.append(review_input.diff)
        return super().review(sandbox=sandbox, workspace=workspace, review_input=review_input)


class _NeverPublishes(WorktreeSandbox):
    """The worktree box, which records a push it was asked for and refuses it."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.published: list[str] = []

    def publish_branch(self, *, workspace, remote_url=None):
        self.published.append(workspace.branch)
        raise AssertionError("a re-review must never publish the branch")


class _WithoutTheTip(WorktreeSandbox):
    """A box that has never heard of `prepare_tip`, as a box from outside this tree."""

    prepare_tip = None


def _sha_of(git_dir: Path, ref: str) -> str:
    return subprocess.run(["git", "--git-dir", str(git_dir), "rev-parse", ref], check=True,
                          capture_output=True, text=True).stdout.strip()


def _count(repo: Path, ref: str) -> str:
    return subprocess.run(["git", "-C", str(repo), "rev-list", "--count", ref], check=True,
                          capture_output=True, text=True).stdout.strip()


def test_a_re_review_on_a_held_branch_reads_the_tip_and_publishes(repo, tmp_path):
    """Criterion 1. On `main`: `ON_HOLD`, `hold_cause` TREE, and the reviewer never called."""
    review = _an_open_pull_request_a_person_reviews(repo)
    reviewer = _ReadingReviewer()
    runner, _ = _machine(repo, tmp_path, _Agent(), reviewer=reviewer)

    got = runner.review_pr("#9", pr_url=PR)

    assert got.state is JobState.PR_OPEN
    assert got.hold_cause != TREE
    assert got.review is not None
    assert reviewer.calls == 1
    assert "feature.py" in reviewer.diffs[0]
    assert str(review) in _registered(repo)
    assert _git(review, "symbolic-ref", "--short", "HEAD") == CARD_BRANCH


def test_a_re_review_commits_nothing_and_never_publishes(repo, tmp_path):
    """Criterion 2, the reverse guard: the branch in the clone and on the forge is where it was,
    and the box was never asked to push."""
    _an_open_pull_request_a_person_reviews(repo)
    origin = repo.parent / "origin.git"
    here, there = _sha(repo, f"refs/heads/{CARD_BRANCH}"), _sha_of(origin, CARD_BRANCH)
    commits = _count(repo, CARD_BRANCH)
    box = _NeverPublishes(root=tmp_path / "wt")
    runner, _ = _machine(repo, tmp_path, _Agent(), reviewer=_ReadingReviewer())
    runner.sandbox = box

    got = runner.review_pr("#9", pr_url=PR)

    assert got.state is JobState.PR_OPEN
    assert box.published == []
    assert _sha(repo, f"refs/heads/{CARD_BRANCH}") == here
    assert _sha_of(origin, CARD_BRANCH) == there
    assert _count(repo, CARD_BRANCH) == commits


def test_a_box_without_the_tip_still_holds_the_re_review(repo, tmp_path):
    """The fallback: a box that cannot check a tip out detached goes through `prepare`, which
    refuses the held branch, and the re-review holds for a person as it did."""
    review = _an_open_pull_request_a_person_reviews(repo)
    reviewer = _ReadingReviewer()
    runner, tracker = _machine(repo, tmp_path, _Agent(), reviewer=reviewer)
    runner.sandbox = _WithoutTheTip(root=tmp_path / "wt")

    got = runner.review_pr("#9", pr_url=PR)

    _held_for_a_person(got, tracker, review)
    assert got.merge_refused is True and got.code_changed is False
    assert reviewer.calls == 0


# The fixture the machine tests stand on: a real repository with a bare origin to push to. A copy
# of `tests/test_walking_skeleton.py`'s, so this file imports no fixture by name.
@pytest.fixture
def repo(tmp_path: Path) -> Path:
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)], check=True,
                   capture_output=True)
    r = tmp_path / "repo"
    r.mkdir()
    for args in (["init", "-b", "main"], ["config", "user.email", "t@t.dev"],
                 ["config", "user.name", "t"], ["remote", "add", "origin", str(origin)]):
        subprocess.run(["git", *args], cwd=r, check=True, capture_output=True)
    (r / "README.md").write_text("# app\n")
    for args in (["add", "-A"], ["commit", "-m", "init"], ["push", "-u", "origin", "main"]):
        subprocess.run(["git", *args], cwd=r, check=True, capture_output=True)
    return r
