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


# ── every word the reviewer writes, not only the summary and the description (review of 584318d) ─
#
# MEASURED ON 584318d. `Finding(file="cfg/<token>.env", line=3)` reached the body as `(file:line)`
# and the announcement as `headline`'s `[file]`, the token whole in both; a `would_verify` pointer
# reached both through `headline`'s `wire \`…\`` cut at 120, so a token straddling the cut was
# shown in part, a part no credential shape matches; a criterion reached the announcement through
# `criterion NOT met: …` cut at 160.

FILE_TOKEN = "ghp_" + "q7" + "REVIEWFIL" * 4
POINTER_TOKEN = "ghp_" + "q7" + "REVIEWPTR" * 4
CRITERION_TOKEN = "ghp_" + "q7" + "REVIEWCRT" * 4
#: Everything a reader may not see of the pointer's token: `ghp_` and the 8 characters after it.
POINTER_PREFIX = POINTER_TOKEN[:len("ghp_") + 8]
#: The pointer's words before the token, so the token starts at character 104 and `headline`'s
#: cut at 120 keeps `ghp_` and 12 characters of it: too few for the token shape (16), so a scrub
#: AFTER the cut finds nothing there. At exactly 100 the cut keeps 16 and a late scrub still
#: matches, which could not tell the two orders apart. The space is the word boundary the shape
#: needs: `x…xghp_` is one word and no shape matches it in any order.
POINTER_WORDS = "x" * 103 + " "
SENTINEL_FILE = "SENTINEL-196-FILE"
SENTINEL_CRITERION = "SENTINEL-196-CRITERION"


class _Says:
    """A reviewer that returns `review`, whatever the diff."""

    def __init__(self, review: ReviewResult) -> None:
        self._review = review

    def review(self, *, sandbox, workspace, review_input) -> ReviewResult:
        return self._review.model_copy(deep=True)


def _ran_with(repo: Path, tmp_path: Path, review: ReviewResult):
    tracker = spine.FakeTracker(spine._sizing_ticket_id("#3"))
    manifest = Manifest(validate={"test": "true", "security": "true"}, review_mode="advisory")
    runner = spine._runner(repo, tracker, manifest, tmp_path, agent=spine.FakeAgent(),
                           reviewer=_Says(review))
    runner.run("#3")
    assert runner.forge.opened, "no pull request was opened — this guard is measuring nothing"
    ready = [c for c in tracker.comments if "ready for review" in c]
    assert ready, f"no ready-for-review announcement on the ticket: {tracker.comments}"
    return runner.forge.opened["body"], "\n".join(ready)


_VERIFIED = [AcceptanceCheck(criterion="the feature exists", status="passed",
                             evidence="gate:test — the suite ran it")]


def test_a_credential_in_a_findings_file_is_withheld_from_the_body_and_the_announcement(
        repo: Path, tmp_path: Path):
    body, said = _ran_with(repo, tmp_path, ReviewResult(
        decision="approved_with_findings", score=80, acceptance=_VERIFIED,
        # `high`, so `headline` carries the finding, `[file]` and all, into the announcement
        findings=[Finding(severity="high", description=f"{SENTINEL_FILE}: a key is committed",
                          file=f"cfg/{FILE_TOKEN}.env", line=3)],
        summary="one finding"))

    _assert_absent(body, FILE_TOKEN)
    section = _shown(_rendered("\n".join(_review_section(body))))
    assert f"cfg/{WITHHELD_CREDENTIAL}.env:3" in section, (
        f"the finding's location does not say a credential was withheld: {section}")
    assert FILE_TOKEN not in said, f"the credential reached the ticket as written: {said}"
    assert f"[cfg/{WITHHELD_CREDENTIAL}.env]" in said, (
        f"the announcement does not say the file's credential was withheld: {said}")
    assert SENTINEL_FILE in said, f"the finding did not reach the announcement: {said}"


def test_no_part_of_a_credential_in_a_would_verify_pointer_reaches_the_body_or_the_announcement(
        repo: Path, tmp_path: Path):
    body, said = _ran_with(repo, tmp_path, ReviewResult(
        decision="approved", score=90,
        # cited to no gate, so the platform settles it NOT VERIFIED and `headline` shows the pointer
        acceptance=[AcceptanceCheck(criterion="the feature exists", status="passed",
                                    evidence="read in the diff",
                                    would_verify=POINTER_WORDS + POINTER_TOKEN)],
        summary="it reads right"))

    _assert_absent(body, POINTER_PREFIX)
    assert POINTER_PREFIX not in said, f"part of the credential reached the ticket: {said}"
    # withheld, not dropped: the pointer is there, the marker where the token was (cut at 120)
    shown = POINTER_WORDS + WITHHELD_CREDENTIAL[:120 - len(POINTER_WORDS)]
    section = "\n".join(_review_section(body))
    assert f"wire `{shown}`" in section, f"the body lost the reviewer's pointer: {section}"
    assert f"wire `{shown}`" in said, f"the announcement lost the reviewer's pointer: {said}"


def test_a_credential_in_an_acceptance_criterion_is_withheld_from_the_body_and_the_announcement(
        repo: Path, tmp_path: Path):
    body, said = _ran_with(repo, tmp_path, ReviewResult(
        decision="rejected", score=40,
        acceptance=[AcceptanceCheck(
            criterion=f"{SENTINEL_CRITERION}: the key {CRITERION_TOKEN} is rotated",
            status="failed", evidence="gate:test")],
        summary="a criterion is not met"))

    _assert_absent(body, CRITERION_TOKEN)
    assert CRITERION_TOKEN not in said, f"the credential reached the ticket as written: {said}"
    assert (f"criterion NOT met: {SENTINEL_CRITERION}: the key {WITHHELD_CREDENTIAL} is rotated"
            in said), f"the announcement does not say the criterion's credential was withheld: {said}"


def test_a_key_of_this_process_spanning_a_heading_row_is_withheld_before_the_escaping(
        repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """THE ORDER (#885): withheld after `_as_text`, the key's `## ` row is escaped first, the key is
    never found whole, and both its halves are published."""
    head, tail = "PEMHEAD196" + "k" * 6, "PEMTAIL196" + "k" * 6
    monkeypatch.setenv("REVIEW_196_PRIVATE_KEY", f"{head}\n## {tail}")
    body, _ = _ran_with(repo, tmp_path, ReviewResult(
        decision="approved_with_findings", score=80, acceptance=_VERIFIED,
        findings=[Finding(severity="low",
                          description=f"{SENTINEL_FINDING}: the key is\n{head}\n## {tail}")],
        summary=f"{SENTINEL_SUMMARY}: the fixture holds\n{head}\n## {tail}"))

    section = "\n".join(_review_section(body))
    _assert_absent(section, head, tail)
    assert section.count(WITHHELD_CREDENTIAL) >= 2, (
        f"the review section does not say the key was withheld: {section}")
    assert SENTINEL_SUMMARY in section and SENTINEL_FINDING in section, section


def test_every_word_the_reviewer_writes_is_withheld_and_nothing_else_changes():
    """`_review_withheld` field by field, on the model and on the dict `headline` reads: a field
    no renderer shows today (a finding's criterion, a check's evidence) is the next renderer's
    leak, so the projection every renderer reads is held whole."""
    from beeverforge.orchestrator.machine import _review_withheld

    def token(field: str) -> str:
        return "ghp_" + "q7" + field.upper().replace("_", "") * 3 + "X" * 16

    fields = {
        "summary": token("summary"),
        "finding.description": token("description"), "finding.file": token("file"),
        "finding.criterion": token("fcriterion"),
        "check.criterion": token("criterion"), "check.evidence": token("evidence"),
        "check.would_verify": token("would_verify"), "check.executed_by": token("executed_by"),
    }
    review = ReviewResult(
        decision="approved_with_findings", score=71, evidence_checked=True, model="m-196",
        harness="h-196", summary=f"s {fields['summary']}",
        findings=[Finding(severity="medium", line=7,
                          description=f"d {fields['finding.description']}",
                          file=f"f/{fields['finding.file']}",
                          criterion=f"c {fields['finding.criterion']}")],
        acceptance=[AcceptanceCheck(status="passed",
                                    criterion=f"c {fields['check.criterion']}",
                                    evidence=f"e {fields['check.evidence']}",
                                    would_verify=f"w {fields['check.would_verify']}",
                                    executed_by=f"x {fields['check.executed_by']}")])

    for shape in (review, review.model_dump()):
        withheld = _review_withheld(shape)
        dumped = withheld.model_dump() if isinstance(withheld, ReviewResult) else withheld
        assert isinstance(withheld, type(shape)), type(withheld)
        for name, secret in fields.items():
            assert secret not in repr(dumped), f"{name} reached the renderers as written: {dumped}"
        assert repr(dumped).count(WITHHELD_CREDENTIAL) == len(fields), dumped
        assert dumped["findings"][0]["file"] == f"f/{WITHHELD_CREDENTIAL}", dumped
        assert {k: v for k, v in dumped.items() if k not in ("summary", "findings", "acceptance")
                } == {k: v for k, v in review.model_dump().items()
                      if k not in ("summary", "findings", "acceptance")}, dumped
        assert (dumped["findings"][0]["line"], dumped["findings"][0]["severity"],
                dumped["acceptance"][0]["status"]) == (7, "medium", "passed"), dumped
    # a key the dict lacks stays absent: `headline` reads `{}` as "no review"
    assert _review_withheld({}) == {}
    assert _review_withheld({"decision": "approved"}) == {"decision": "approved"}
