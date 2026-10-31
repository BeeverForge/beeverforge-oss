"""A section heading the platform did not write is not that section (#113).

Two defences, and both are tested. The platform is the ONLY writer that can put a section heading
row in the body: a row of the card objective, of the review's summary or of a finding that starts
with `## ` is escaped as it is written, so it reads as text and no reader can take it for a
section. And a body published before that escaping existed still carries the objective's heading
raw; since the objective is written first and the platform's sections after it, the platform's own
heading is the LAST row that matches. Taking the first spliced the next pass's line, or a fresh
review, into the objective: the objective lost the line after the heading and the real section
got nothing.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import test_walking_skeleton as spine

from beeverforge.contracts import Manifest, ReviewResult, RunResult, ValidationResult
from beeverforge.contracts.review import Finding
from beeverforge.contracts.run import AGENT_ACCOUNT_HEADING, PassAccount
from beeverforge.orchestrator.machine import _COST_LINE, _REVIEW_HEADING, JobRunner, _with_passes

PR = "https://forge/pr/1"
EXECUTOR = "EXEC-SENTINEL: rewrote the parser"
REVIEW = ReviewResult(decision="rejected", score=58, summary="OLD-SENTINEL", findings=[])
FRESH = ReviewResult(decision="approved", score=77, summary="FRESH-SENTINEL", findings=[])
PASS = PassAccount(kind="gate repair 1", words="SENTINEL-PASS", head="a" * 40)
PASS_ROW = "> - gate repair 1 · `aaaaaaaaaaaa` — SENTINEL-PASS"
REVIEW_IN_OBJECTIVE = "## Review — approved (score 99)"

#: `current`: the body as `_pr_body` writes it now. `published before the escaping`: the same body
#: as a pull request opened before it carries it — the objective's heading row raw.
BODIES = pytest.mark.parametrize("raw", [False, True],
                                 ids=["current", "published before the escaping"])


def _body(heading_in_objective: str, *, raw: bool = False, review: ReviewResult | None = REVIEW,
          account: str | None = EXECUTOR) -> str:
    ticket = spine._sizing_ticket_id("#9")
    ticket = ticket.model_copy(update={
        "objective": f"A card about this section.\n{heading_in_objective}\nKEEP-THIS-LINE"})
    result = RunResult(
        ticket_id="#9", state="validating", branch="beeverforge/9",
        validations=[ValidationResult(name="test", command="true", exit_code=0, passed=True)],
        review=review, total_cost_usd=0.05,
        agent_account=account, agent_account_chars=len(account or ""))
    holder = SimpleNamespace(manifest=Manifest(validate={"test": "true"}), _profile=None)
    body = JobRunner._pr_body(holder, ticket, result)
    if raw:
        body = body.replace(f"\\{heading_in_objective}", heading_in_objective, 1)
    return body


def _objective(rows: list[str]) -> list[str]:
    return rows[rows.index("## Objective"):rows.index("## Validations")]


class _Forge:
    def __init__(self, body: str) -> None:
        self.body = body

    def pr_body(self, *, pr: str, repo: str = "") -> str | None:
        return self.body

    def set_pr_body(self, *, pr: str, body: str, repo: str = "") -> bool:
        self.body = body
        return True


_SAY = {"pr.review.out-of-date": "> out of date", "pr.review.was": "**was:** "}
_SAYER = SimpleNamespace(_say=lambda key: _SAY[key])


def _holder(body: str):
    return SimpleNamespace(
        forge=_Forge(body), _cost_on_the_pr=0.0, _reported_cost=lambda: None,
        _say=lambda key: _SAY[key],
        _dated=lambda section: JobRunner._dated(_SAYER, section))


def _assert_pass_in_the_real_section(before: list[str], after: list[str]) -> None:
    assert _objective(after) == _objective(before), "the objective was spliced"
    assert after.count(PASS_ROW) == 1
    real = max(i for i, row in enumerate(after) if row == AGENT_ACCOUNT_HEADING)
    cost = max(i for i, row in enumerate(after) if row.startswith(_COST_LINE))
    assert after.index("## Validations") < real < after.index(PASS_ROW) < cost


def _review_headings(rows: list[str]) -> list[str]:
    return [row for row in rows if row.startswith(_REVIEW_HEADING)]


# ── the objective is written as text ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("heading", [AGENT_ACCOUNT_HEADING, REVIEW_IN_OBJECTIVE])
def test_the_objective_cannot_write_a_section_heading(heading):
    rows = _body(heading).splitlines()
    objective = _objective(rows)

    assert f"\\{heading}" in objective  # still says what the card said, as text
    assert not any(row.startswith("## ") for row in objective[1:])
    assert "KEEP-THIS-LINE" in objective


# ── the agent's section ─────────────────────────────────────────────────────────────────────────

@BODIES
def test_a_pass_row_lands_in_the_real_section_when_the_objective_holds_its_heading(raw):
    before = _body(AGENT_ACCOUNT_HEADING, raw=raw).splitlines()
    assert before.count(AGENT_ACCOUNT_HEADING) == (2 if raw else 1)

    _assert_pass_in_the_real_section(before, _with_passes(before, [PASS]))


@BODIES
def test_a_republished_pass_row_lands_in_the_real_section_too(raw):
    body = _body(AGENT_ACCOUNT_HEADING, raw=raw)
    holder = _holder(body)

    assert JobRunner._republish_review(holder, PR, account_passes=[PASS])
    _assert_pass_in_the_real_section(body.splitlines(), holder.forge.body.splitlines())


def test_a_body_opened_before_the_agents_section_gets_one_below_the_objective():
    """The upgrade path: no real section, so `_with_passes` inserts one before `Cost:` — and the
    objective's heading row must not be read as the section it lacks."""
    rows = _body(AGENT_ACCOUNT_HEADING).splitlines()
    real = rows.index(AGENT_ACCOUNT_HEADING)
    cost = max(i for i, row in enumerate(rows) if row.startswith(_COST_LINE))
    before = rows[:real] + rows[cost:]  # as a pull request opened before #627 carries it
    while not before[real - 1].strip():
        before.pop(real - 1)
        real -= 1
    assert AGENT_ACCOUNT_HEADING not in before

    after = _with_passes(before, [PASS])
    _assert_pass_in_the_real_section(before, after)
    assert after.count(AGENT_ACCOUNT_HEADING) == 1


# ── the review section ──────────────────────────────────────────────────────────────────────────

@BODIES
def test_a_fresh_review_replaces_the_real_section_when_the_objective_holds_its_heading(raw):
    body = _body(REVIEW_IN_OBJECTIVE, raw=raw)
    holder = _holder(body)

    assert JobRunner._republish_review(holder, PR, review=FRESH)
    before, after = body.splitlines(), holder.forge.body.splitlines()
    assert _objective(after) == _objective(before), "the objective was spliced"
    below = after[after.index("## Validations"):]
    assert _review_headings(below) == ["## Review — approved (score 77)"]
    assert any("FRESH-SENTINEL" in row for row in below)
    assert not any("OLD-SENTINEL" in row for row in after)


@BODIES
def test_a_dated_review_is_the_real_one_when_the_objective_holds_its_heading(raw):
    body = _body(REVIEW_IN_OBJECTIVE, raw=raw)
    holder = _holder(body)

    assert JobRunner._republish_review(holder, PR, review=None)
    before, after = body.splitlines(), holder.forge.body.splitlines()
    assert _objective(after) == _objective(before), "the objective was dated"
    below = after[after.index("## Validations"):]
    assert "> out of date" in below
    assert any("**was:**" in row and "OLD-SENTINEL" in row for row in below)


def test_a_body_opened_with_no_review_keeps_its_objective_when_a_review_arrives():
    """The upgrade path: no review section to replace, so nothing is spliced anywhere — and the
    objective's heading row must not be read as the section it lacks."""
    body = _body("## Review — a (score 1)", review=None)
    holder = _holder(body)

    assert not JobRunner._republish_review(holder, PR, review=FRESH)
    assert holder.forge.body == body
    assert not _review_headings(body.splitlines())


def _with_a_heading_in_the_review(where: str) -> ReviewResult:
    words = f"OLD-SENTINEL\n{REVIEW_IN_OBJECTIVE}\nOLD-TAIL"
    if where == "summary":
        return ReviewResult(decision="rejected", score=58, summary=words, findings=[])
    return ReviewResult(decision="rejected", score=58, summary="OLD-SUMMARY",
                        findings=[Finding(severity="high", description=words)])


@pytest.mark.parametrize("where", ["summary", "finding"])
def test_the_review_cannot_write_a_section_heading(where):
    rows = _body("no heading here", review=_with_a_heading_in_the_review(where)).splitlines()

    assert _review_headings(rows) == ["## Review — rejected (score 58)"]
    assert any(row.endswith(f"\\{REVIEW_IN_OBJECTIVE}") for row in rows)  # said, as text


@pytest.mark.parametrize("where", ["summary", "finding"])
def test_a_fresh_review_replaces_the_whole_old_one_when_it_held_a_heading(where):
    """#187's case: a stale verdict left standing as the first review heading."""
    body = _body("no heading here", review=_with_a_heading_in_the_review(where))
    holder = _holder(body)

    assert JobRunner._republish_review(holder, PR, review=FRESH)
    before, after = body.splitlines(), holder.forge.body.splitlines()
    assert _objective(after) == _objective(before)
    assert _review_headings(after) == ["## Review — approved (score 77)"]
    assert not any("OLD-" in row for row in after)
    assert any("FRESH-SENTINEL" in row for row in after)


@pytest.mark.parametrize("where", ["summary", "finding"])
def test_a_dated_review_that_held_a_heading_stays_one_section(where):
    body = _body("no heading here", review=_with_a_heading_in_the_review(where))
    holder = _holder(body)

    assert JobRunner._republish_review(holder, PR, review=None)
    after = holder.forge.body.splitlines()
    assert _review_headings(after) == ["## Review — rejected (score 58)"]
    assert after.count("> out of date") == 1
    tail = next(row for row in after if "OLD-TAIL" in row)
    assert "**was:**" in tail
