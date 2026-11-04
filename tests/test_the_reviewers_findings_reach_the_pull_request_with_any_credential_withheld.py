"""The reviewer's own findings reach the pull request with any credential withheld (#196).

MEASURED ON THE ISSUE. #885 withheld a credential from the implementing agent's account only
(`_quoted`, `_pass_words`). The reviewer's summary and each finding's description went to the
forge as written: `_review_lines` composes the body's review section (on the first publish and on
every `_republish_review` rewrite), `format_review` the review event posted on the pull request,
and `_review_sentence` the ready-for-review announcement on the ticket. Nothing between the
reviewer's result and those writes called `scrub_credentials`, so a finding that quoted a token
from a log, a fixture or an environment dump was published.

Every guard drives the real `JobRunner.run` and reads what the forge or the tracker was handed;
every absence is asserted on the raw text AND its CommonMark render, since `_as_text` and the
markdown source may escape a token a reader then sees whole.

Synthetic credentials are built at run time, never written whole, as the #885 guard does.
"""

from __future__ import annotations

import html as html_lib
import os
import re
from pathlib import Path

import pytest
import test_walking_skeleton as spine

from beeverforge.contracts import AcceptanceCheck, Finding, Manifest, ReviewResult
from beeverforge.orchestrator.machine import _REVIEW_HEADING
from beeverforge.product import model
from beeverforge.product.model import WITHHELD_CREDENTIAL

repo = spine.repo

PR = "https://forge/pr/1"

#: Words of the reviewer's that are no credential: each must reach the forge, so a fix that drops
#: the whole summary or finding cannot pass for one that withholds the credential in it.
SENTINEL_SUMMARY = "SENTINEL-196-SUMMARY"
SENTINEL_FINDING = "SENTINEL-196-FINDING"
SUMMARY_TOKEN = "ghp_" + "q7" + "REVIEWSUM" * 4
FINDING_TOKEN = "ghp_" + "q7" + "REVIEWFND" * 4

#: The fresh reading a republish carries: other words, other tokens.
SENTINEL_SUMMARY_2 = "SENTINEL-196-RESUMMARY"
SENTINEL_FINDING_2 = "SENTINEL-196-REFINDING"
SUMMARY_TOKEN_2 = "ghp_" + "q7" + "RESUMMARY" * 4
FINDING_TOKEN_2 = "ghp_" + "q7" + "REFINDING" * 4


@pytest.fixture(autouse=True)
def _no_secret_of_this_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """A secret-named variable of the machine running the suite must not change what is
    withheld: these tests hold the token SHAPE, not the environment."""
    for name in list(os.environ):
        if model._SECRET_NAME.search(name):
            monkeypatch.delenv(name, raising=False)


def _review(summary_words: str, summary_token: str, finding_words: str,
            finding_token: str) -> ReviewResult:
    return ReviewResult(
        decision="approved_with_findings",
        score=88,
        # cited to the gate that executed it, so the change is verified (#447)
        acceptance=[AcceptanceCheck(criterion="the feature exists", status="passed",
                                    evidence="gate:test — the suite ran it")],
        # `high`, so `headline` carries the finding into the announcement
        findings=[Finding(severity="high",
                          description=f"{finding_words}: the log shows GH_TOKEN={finding_token}")],
        summary=f"{summary_words}: the fixture holds {summary_token}",
    )


class _QuotesACredential:
    """A reviewer whose summary and finding each quote a synthetic token."""

    def review(self, *, sandbox, workspace, review_input) -> ReviewResult:
        return _review(SENTINEL_SUMMARY, SUMMARY_TOKEN, SENTINEL_FINDING, FINDING_TOKEN)


def _ran(repo: Path, tmp_path: Path):
    tracker = spine.FakeTracker(spine._sizing_ticket_id("#3"))
    manifest = Manifest(validate={"test": "true", "security": "true"}, review_mode="advisory")
    runner = spine._runner(repo, tracker, manifest, tmp_path, agent=spine.FakeAgent(),
                           reviewer=_QuotesACredential())
    runner.run("#3")
    assert runner.forge.opened, "no pull request was opened — this guard is measuring nothing"
    return runner, tracker


def _rendered(markdown: str) -> str:
    markdown_it = pytest.importorskip("markdown_it", reason="markdown-it-py renders the body")
    return markdown_it.MarkdownIt("commonmark").render(markdown)


def _shown(fragment_html: str) -> str:
    """The text a reader sees: the tags dropped, the entities decoded."""
    return html_lib.unescape(re.sub(r"<[^>]+>", "", fragment_html))


def _review_section(body: str) -> list[str]:
    """The rows from the review heading up to the next `## ` heading or the `Cost:` row."""
    rows = body.splitlines()
    start = next((i for i in range(len(rows) - 1, -1, -1)
                  if rows[i].startswith(_REVIEW_HEADING)), None)
    assert start is not None, f"the pull request carries no review section: {body}"
    end = next((i for i in range(start + 1, len(rows))
                if rows[i].startswith("## ") or rows[i].startswith("Cost:")), len(rows))
    return rows[start:end]


def _assert_absent(text: str, *secrets: str) -> str:
    """No `secret` in `text` as written nor as rendered; returns what a reader sees."""
    seen = _shown(_rendered(text))
    for secret in secrets:
        assert secret not in text, f"the credential reached the forge as written: {text}"
        assert secret not in html_lib.unescape(_rendered(text)), (
            f"the credential reached the forge as rendered: {seen}")
    return seen


def test_a_credential_in_the_reviewers_summary_and_finding_is_withheld_from_the_pull_request_body(
        repo: Path, tmp_path: Path):
    runner, _ = _ran(repo, tmp_path)
    body = runner.forge.opened["body"]

    _assert_absent(body, SUMMARY_TOKEN, FINDING_TOKEN)
    section = _shown(_rendered("\n".join(_review_section(body))))
    assert section.count(WITHHELD_CREDENTIAL) >= 2, (
        f"the review section does not say a credential was withheld: {section}")
    assert SENTINEL_SUMMARY in section and SENTINEL_FINDING in section, (
        f"the reviewer's own words did not reach the review section: {section}")


def test_a_republished_review_withholds_the_credential_in_its_fresh_summary_and_finding(
        repo: Path, tmp_path: Path):
    runner, _ = _ran(repo, tmp_path)
    fresh = _review(SENTINEL_SUMMARY_2, SUMMARY_TOKEN_2, SENTINEL_FINDING_2, FINDING_TOKEN_2)

    assert runner._republish_review(PR, review=fresh) is True
    body = runner.forge.opened["body"]

    _assert_absent(body, SUMMARY_TOKEN, FINDING_TOKEN, SUMMARY_TOKEN_2, FINDING_TOKEN_2)
    section = _shown(_rendered("\n".join(_review_section(body))))
    assert SENTINEL_SUMMARY_2 in section and SENTINEL_FINDING_2 in section, (
        f"the fresh review did not replace the section: {section}")
    assert section.count(WITHHELD_CREDENTIAL) >= 2, (
        f"the republished section does not say a credential was withheld: {section}")


def test_a_credential_in_the_review_posted_on_the_pull_request_is_withheld(
        repo: Path, tmp_path: Path):
    runner, _ = _ran(repo, tmp_path)
    assert len(runner.forge.reviews) == 1, runner.forge.reviews
    posted = runner.forge.reviews[0]["body"]

    seen = _assert_absent(posted, SUMMARY_TOKEN, FINDING_TOKEN)
    assert seen.count(WITHHELD_CREDENTIAL) >= 2, (
        f"the posted review does not say a credential was withheld: {seen}")
    assert SENTINEL_SUMMARY in seen and SENTINEL_FINDING in seen, (
        f"the reviewer's own words did not reach the posted review: {seen}")


def test_a_credential_in_a_finding_is_withheld_from_the_ready_for_review_announcement(
        repo: Path, tmp_path: Path):
    _, tracker = _ran(repo, tmp_path)
    ready = [c for c in tracker.comments if "ready for review" in c]
    assert ready, f"no ready-for-review announcement on the ticket: {tracker.comments}"
    said = "\n".join(ready)

    assert FINDING_TOKEN not in said, f"the credential reached the ticket as written: {said}"
    assert WITHHELD_CREDENTIAL in said, f"the announcement does not say it was withheld: {said}"
    assert SENTINEL_FINDING in said, f"the finding did not reach the announcement: {said}"
