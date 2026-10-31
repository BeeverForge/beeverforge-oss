"""A card objective that holds a section heading on its own line is not that section (#113).

The objective is written first and the platform's sections after it, so the platform's own
heading is the LAST row that matches. Taking the first spliced the next pass's line, or a fresh
review, into the objective: the objective lost the line after the heading and the real section
got nothing.
"""

from __future__ import annotations

from types import SimpleNamespace

import test_walking_skeleton as spine

from beeverforge.contracts import Manifest, ReviewResult, RunResult, ValidationResult
from beeverforge.contracts.run import AGENT_ACCOUNT_HEADING, PassAccount
from beeverforge.orchestrator.machine import _COST_LINE, JobRunner, _with_passes

PR = "https://forge/pr/1"
EXECUTOR = "EXEC-SENTINEL: rewrote the parser"
REVIEW = ReviewResult(decision="rejected", score=58, summary="OLD-SENTINEL", findings=[])
PASS = PassAccount(kind="gate repair 1", words="SENTINEL-PASS", head="a" * 40)
PASS_ROW = "> - gate repair 1 · `aaaaaaaaaaaa` — SENTINEL-PASS"
REVIEW_IN_OBJECTIVE = "## Review — approved (score 99)"


def _body(heading_in_objective: str) -> str:
    ticket = spine._sizing_ticket_id("#9")
    ticket = ticket.model_copy(update={
        "objective": f"A card about this section.\n{heading_in_objective}\nKEEP-THIS-LINE"})
    result = RunResult(
        ticket_id="#9", state="validating", branch="beeverforge/9",
        validations=[ValidationResult(name="test", command="true", exit_code=0, passed=True)],
        review=REVIEW, total_cost_usd=0.05,
        agent_account=EXECUTOR, agent_account_chars=len(EXECUTOR))
    holder = SimpleNamespace(manifest=Manifest(validate={"test": "true"}), _profile=None)
    return JobRunner._pr_body(holder, ticket, result)


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
    assert real < after.index(PASS_ROW) < cost


def test_a_pass_row_lands_in_the_real_section_when_the_objective_holds_its_heading():
    before = _body(AGENT_ACCOUNT_HEADING).splitlines()
    assert before.count(AGENT_ACCOUNT_HEADING) == 2  # the objective's and the platform's

    _assert_pass_in_the_real_section(before, _with_passes(before, [PASS]))


def test_a_republished_pass_row_lands_in_the_real_section_too():
    body = _body(AGENT_ACCOUNT_HEADING)
    holder = _holder(body)

    assert JobRunner._republish_review(holder, PR, account_passes=[PASS])
    _assert_pass_in_the_real_section(body.splitlines(), holder.forge.body.splitlines())


def test_a_fresh_review_replaces_the_real_section_when_the_objective_holds_its_heading():
    body = _body(REVIEW_IN_OBJECTIVE)
    holder = _holder(body)
    fresh = ReviewResult(decision="approved", score=77, summary="FRESH-SENTINEL", findings=[])

    assert JobRunner._republish_review(holder, PR, review=fresh)
    before, after = body.splitlines(), holder.forge.body.splitlines()
    assert _objective(after) == _objective(before), "the objective was spliced"
    below = after[after.index("## Validations"):]
    assert "## Review — approved (score 77)" in below
    assert any("FRESH-SENTINEL" in row for row in below)
    assert not any("OLD-SENTINEL" in row for row in after)


def test_a_dated_review_is_the_real_one_when_the_objective_holds_its_heading():
    body = _body(REVIEW_IN_OBJECTIVE)
    holder = _holder(body)

    assert JobRunner._republish_review(holder, PR, review=None)
    before, after = body.splitlines(), holder.forge.body.splitlines()
    assert _objective(after) == _objective(before), "the objective was dated"
    below = after[after.index("## Validations"):]
    assert "> out of date" in below
    assert any("**was:**" in row and "OLD-SENTINEL" in row for row in below)
