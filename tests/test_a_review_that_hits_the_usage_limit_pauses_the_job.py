"""A review that hit the usage limit pauses the job; one that was not logged in holds it (#131).

`ReviewResult.pause_reason` is read where the job reads the review, `JobRunner.run`, after the
review is counted (#262) and before it is journalled as a verdict: the first review and the
re-review after a review-repair. A pause there goes through `_paused`, as an executor pause does:
`rate_limit` is PAUSED with its reset, `auth` is ON_HOLD. On main the review's pause had no field
to travel in, and the job opened a pull request headed by a rejection nobody made.

The generic `HarnessReviewer` carries the agent's pause onto the review it returns, so a non-Claude
reviewer's limit pauses the job the same way.
"""

from __future__ import annotations

from beeverforge.adapters.reviewer.base import ReviewInput
from beeverforge.adapters.reviewer.harness import HarnessReviewer
from beeverforge.contracts import (
    AcceptanceCriterion,
    AgentRunResult,
    Finding,
    JobState,
    Manifest,
    ReviewResult,
    Ticket,
)
from tests import test_walking_skeleton as skeleton

#: the real repository with a bare origin, from the walking skeleton
repo = skeleton.repo

_GREEN = {"test": "true", "security": "true"}


def _ticket() -> Ticket:
    return Ticket(id="#1", title="add feature", objective="add a feature", repo="o/app",
                  acceptance_criteria=[AcceptanceCriterion(text="feature.py exists")])


class _Answers:
    """A reviewer that answers each review with the next of `answers`."""

    def __init__(self, *answers: ReviewResult) -> None:
        self.answers = list(answers)
        self.asked = 0

    def review(self, **_):
        self.asked += 1
        return self.answers.pop(0)


def _limited(reason: str, retry_at: str | None = None) -> ReviewResult:
    return ReviewResult(decision="rejected", score=0, pause_reason=reason, retry_at=retry_at,
                        summary="THE REVIEW NEVER RAN (claude_code): limited", cost_usd=0.2,
                        harness="claude_code")


def _run(repo_path, tmp_path, reviewer, **manifest):
    forge = skeleton.FakeForge()
    result = skeleton._runner(
        repo_path, skeleton.FakeTracker(_ticket()),
        Manifest(validate=_GREEN, review_mode="blocking", **manifest), tmp_path,
        reviewer=reviewer, forge=forge).run("#1")
    return result, forge


def test_a_review_that_hit_the_usage_limit_pauses_the_job(repo, tmp_path):
    result, forge = _run(repo, tmp_path, _Answers(_limited("rate_limit", "16:00")))

    assert result.state is JobState.PAUSED, result.note
    assert result.retry_at == "16:00"
    assert forge.opened is None, "a pull request was opened over a review that never ran"
    assert "review" in [m.role for m in result.agent_runs], "the paused review was not charged"


def test_a_review_that_is_not_logged_in_holds_the_job(repo, tmp_path):
    result, forge = _run(repo, tmp_path, _Answers(_limited("auth")))

    assert result.state is JobState.ON_HOLD, result.note
    assert result.note == "agent auth failed"
    assert forge.opened is None


def test_a_re_review_after_a_repair_that_hit_the_usage_limit_pauses_the_job(repo, tmp_path):
    rejects = ReviewResult(
        decision="rejected", score=40, summary="not done as submitted",
        findings=[Finding(severity="critical", description="asserts the wrong value",
                          file="feature.py", line=1)])
    reviewer = _Answers(rejects, _limited("rate_limit", "16:00"))

    result, forge = _run(repo, tmp_path, reviewer, review_repair_max_attempts=1)

    assert reviewer.asked == 2, "the re-review never ran — this guard is measuring the first"
    assert result.state is JobState.PAUSED, result.note
    assert forge.opened is None


class _LimitedAgent:
    name = "codex"

    def ask(self, **_):
        return AgentRunResult(ok=False, pause_reason="rate_limit", retry_at="16:00",
                              summary="usage limit")


def test_the_harness_reviewer_carries_the_agents_pause_reason():
    review = HarnessReviewer(_LimitedAgent()).review(
        sandbox=None, workspace=None,
        review_input=ReviewInput(ticket=_ticket(), diff="- a\n+ b", validations=[]))

    assert (review.pause_reason, review.retry_at) == ("rate_limit", "16:00"), review
    assert review.decision == "rejected"
    assert review.summary.startswith("THE REVIEW NEVER RAN"), review.summary
