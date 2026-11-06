"""A review that did not complete holds the job, and no surface reports it as a scored rejection (#131).

A review that judged nothing never proceeds as reviewed. On a796cde one that did not complete, with
no pause to take, carried on as an ordinary rejection: in advisory mode `should_auto_merge` merged
it — with a surviving coverage pragma counted as vetted — because nothing between the review and
the merge read `not_a_verdict`. The job now holds there, through `_hold`, as it does on an executor
run it cannot trust, at the first review and at the re-review after a review-repair.

And every surface that reports a review reads the same function: the journal's `review` line (the
first review, the re-review after a repair, the review after a CI repair, a re-review a person asked
for), the pull request review's heading (`format_review`) and its event (`review_event`). On
a796cde they said `rejected (score 0)`, `**rejected** — score 0` and `request-changes` — the bot
asking for changes on a diff nobody read.
"""

from __future__ import annotations

import pytest

from beeverforge.contracts import JobState, Manifest, ReviewResult, RunResult, ValidationResult
from beeverforge.contracts.review import AcceptanceCheck
from beeverforge.orchestrator.merge_policy import format_review, review_event, should_auto_merge
from tests.test_the_review_is_charged_on_every_surface import (
    REVIEW_COST,
    _ci_repair,
    _journal,
    _journalled,
    _open,
    _Reviewer,
    _ReviewFixer,
    _ticket,
    _verdict,
)
from tests.test_walking_skeleton import (
    FakeForge,
    FakeTracker,
    _runner,
    repo,  # noqa: F401 — the fixture: a real repository with a bare origin to push to
)

PR = "https://forge/pr/1"
_GREEN = {"test": "true", "security": "true"}

#: What `ClaudeCodeReviewer._did_not_complete` says about a run that ended in error.
SUMMARY = ("the review did not complete: the reviewer's run ended in error (rc=1), so this diff "
           "has NOT been reviewed. Nothing here is a judgement about the code.")
#: The hold's one sentence, built from that summary.
NOTE = ("the review did not complete, so no pull request was opened — the reviewer's run ended "
        "in error (rc=1), so this diff has NOT been reviewed.")


def _did_not_complete(*acceptance: AcceptanceCheck) -> ReviewResult:
    return ReviewResult(decision="rejected", score=0, did_not_complete=True, summary=SUMMARY,
                        acceptance=list(acceptance), cost_usd=REVIEW_COST, harness="claude_code")


#: A criterion the `test` gate executed. Without one the review reads as not verified (#447) and
#: `should_auto_merge` refuses it on that ground alone, so the merge assertion below would hold on
#: a796cde for a reason that is not this one; with it, on a796cde, the job merged.
_EXECUTED = AcceptanceCheck(criterion="feature.py exists", status="passed", evidence="gate:test")


def _review_lines(clone) -> list[str]:
    return [e["message"] for e in _journalled(clone) if e["kind"] == "review"]


# ═══ the job holds ══════════════════════════════════════════════════════════════════════════════


def test_an_advisory_auto_merge_over_a_review_that_did_not_complete_holds_and_never_merges(
        repo, tmp_path):  # noqa: F811
    """THE REVIEWER'S REPRODUCTION, driven through the job: advisory, `merge_policy="auto"`, green
    gates. On a796cde it opened a pull request and merged it."""
    forge = FakeForge()

    result = _open(repo, tmp_path, forge, merge_policy="auto",
                   reviewer=_Reviewer(_did_not_complete(_EXECUTED)))

    assert forge.merged is False, "a change nobody reviewed was merged by itself"
    assert result.state is JobState.ON_HOLD, result.note
    assert result.note == NOTE
    assert forge.opened is None, "a pull request was opened over a review that did not complete"
    assert "review" in [m.role for m in result.agent_runs], "the review that ran was not charged"


def test_a_re_review_after_a_repair_that_did_not_complete_holds_the_job(repo, tmp_path):  # noqa: F811
    forge = FakeForge()
    reviewer = _Reviewer(_verdict("rejected"), _did_not_complete())

    result = _open(repo, tmp_path, forge, review_mode="blocking", review_repair_max_attempts=1,
                   agent=_ReviewFixer(), reviewer=reviewer)

    assert reviewer.calls == 2, "the re-review never ran — this guard is measuring the first"
    assert result.state is JobState.ON_HOLD, result.note
    assert result.note == NOTE
    assert forge.opened is None


# ═══ the merge policy, as defence in depth ══════════════════════════════════════════════════════


@pytest.mark.parametrize("suppressions", [[], ["pragma: no cover"]], ids=["plain", "pragma"])
def test_a_review_that_did_not_complete_never_lets_a_change_merge_by_itself(suppressions):
    """On a796cde both answered True: advisory mode reads a rejection as information, and the
    pragma branch asked only `result.review is None`, so an unread review vetted the pragma."""
    result = RunResult(
        ticket_id="#1", state="pr_open", added_suppressions=suppressions,
        validations=[ValidationResult(name="test", command="t", exit_code=0, passed=True)],
        review=_did_not_complete())

    assert should_auto_merge(Manifest(merge_policy="auto"), result) is False


# ═══ every surface says the review did not complete ═════════════════════════════════════════════


def test_the_first_reviews_journal_line_says_it_did_not_complete(repo, tmp_path):  # noqa: F811
    _open(repo, tmp_path, FakeForge(), reviewer=_Reviewer(_did_not_complete()))

    assert _review_lines(repo) == ["the review did not complete · advisory"]


def test_the_re_reviews_journal_line_says_it_did_not_complete(repo, tmp_path):  # noqa: F811
    _open(repo, tmp_path, FakeForge(), review_mode="blocking", review_repair_max_attempts=1,
          agent=_ReviewFixer(), reviewer=_Reviewer(_verdict("rejected"), _did_not_complete()))

    assert _review_lines(repo)[-1] == "the review did not complete [after repair 1]"


def test_the_review_after_a_ci_repair_says_it_did_not_complete(repo, tmp_path):  # noqa: F811
    """A path the hold does not stop: the pull request is already open, and the review that
    follows a CI repair is reported, not acted on."""
    forge = FakeForge()
    _open(repo, tmp_path, forge)

    _ci_repair(repo, tmp_path, forge, reviewer=_Reviewer(_did_not_complete()))

    assert _review_lines(repo)[-1] == "the review did not complete [after repair]"


def test_a_re_review_a_person_asked_for_says_it_did_not_complete(repo, tmp_path):  # noqa: F811
    forge = FakeForge()
    _open(repo, tmp_path, forge)

    _runner(repo, FakeTracker(_ticket()), Manifest(validate=_GREEN), tmp_path,
            reviewer=_Reviewer(_did_not_complete()), forge=forge,
            events=_journal(repo)).review_pr("#1", pr_url=PR)

    assert _review_lines(repo)[-1] == "the review did not complete [re-reviewed]"


def test_the_pull_request_reviews_heading_says_it_did_not_complete():
    first = format_review(_did_not_complete()).splitlines()[0]

    assert first == ("**The review did not complete** — this diff has not been reviewed, and "
                     "nothing here is a judgement about the code")


def test_the_pull_request_heading_says_a_paused_review_never_ran():
    paused = ReviewResult(decision="rejected", score=0, pause_reason="rate_limit",
                          summary="THE REVIEW NEVER RAN (claude_code): rate_limit.")

    assert format_review(paused).splitlines()[0].startswith("**The review never ran**")


def test_a_review_that_did_not_complete_does_not_request_changes():
    """Blocking mode maps `rejected` to `request-changes`: the bot asked for changes on a diff
    nobody read. It is a comment."""
    assert review_event(_did_not_complete(), "blocking") == "comment"
    # the positive twin: a real rejection still requests changes
    assert review_event(_verdict("rejected"), "blocking") == "request-changes"
