"""The reviewer's code and links reach the pull request as written, mentions and all (#329).

#315 rewrites the reviewer's `#1` as `card 1` and puts a zero-width space after the `@` of a name
and between `GH` and `-1`, so its summary and findings link no issue and notify no one. Those
rewrites ran inside closed code spans, closed fences and the links GitHub makes of bare ones too:
`` `a#1` `` reached the pull request as `` `a card 1` ``, and a link holding `/@user` or `#123`
pointed somewhere else. Nothing links or mentions inside a closed span, and a link's own text is
not a mention, so there they protected nothing and changed what the reviewer quoted. They now run
outside those spans only, on the same split the `&` escaping uses; a backtick that never closes
still protects nothing, as GitHub renders a live mention after it.
"""

from __future__ import annotations

import pytest
from test_the_reviewers_words_link_nothing import LIVE, ZWSP, _review_rows

from beeverforge.contracts import ReviewResult
from beeverforge.contracts.review import Finding
from beeverforge.orchestrator.merge_policy import format_review

#: Rows that are code or a link GitHub makes, whole: each must reach the pull request unchanged.
VERBATIM = [
    # closed code spans, of one backtick and of two
    "see `a#1` and `@someone` and `GH-1` and ``owner/repo#2 @someone`` x",
    # bare links, a scheme one and a `www.` one, holding a name after `/@` and a numeric anchor
    "see https://ex.com/@someone/x#123 y",
    "see www.ex.com/@someone#123 y",
    # the same, in angle form
    "see <https://ex.com/@someone/x#123> y",
]
#: Rows of a closed fence: code, kept as written.
FENCE = ["```sh", "fixes #1 for @someone, GH-1", "```"]
SUMMARY = "\n".join([VERBATIM[0], "", *FENCE, "", *VERBATIM[1:]])


def _both(summary: str, finding: str = "") -> list[tuple[str, list[str]]]:
    review = ReviewResult(decision="approved_with_findings", score=80, summary=summary,
                          findings=[Finding(severity="low", description=finding or summary)])
    return [("pull request body", _review_rows(review)),
            ("posted review", format_review(review).split("\n"))]


def test_a_closed_code_span_and_a_closed_fence_keep_what_the_reviewer_wrote() -> None:
    for where, rows in _both(SUMMARY, VERBATIM[0]):
        for kept in [VERBATIM[0], *FENCE]:
            assert kept in rows, f"{where}: {kept!r} not in {rows!r}"
        assert any(row.endswith(f": {VERBATIM[0]}") for row in rows), f"{where}: {rows!r}"


@pytest.mark.parametrize("link", VERBATIM[1:])
def test_a_link_github_makes_keeps_its_name_and_its_anchor(link: str) -> None:
    for where, rows in _both(link):
        assert link in rows, f"{where}: {link!r} not in {rows!r}"
        assert any(row.endswith(f": {link}") for row in rows), f"{where}: {rows!r}"


@pytest.mark.parametrize("words, kept", [
    # beside code and links, the same words still link and mention nothing
    ("`a#1` #2 @someone GH-3 `b`", f"`a#1` card 2 @{ZWSP}someone card 3 `b`"),
    ("see https://ex.com/@someone #2 @someone", f"see https://ex.com/@someone card 2 @{ZWSP}someone"),
    ("@someone #1 see https://ex.com/@someone", f"@{ZWSP}someone card 1 see https://ex.com/@someone"),
    ("`a`#1 `b`@someone", f"`a`card 1 `b`@{ZWSP}someone"),
    # a backtick that never closes opens no span: what follows it is rewritten
    ("see `x #1 @someone GH-2", f"see `x card 1 @{ZWSP}someone card 2"),
    # a link GitHub does not make: its text is text, and is rewritten
    ("xhttps://ex.com/@someone#1", f"xhttps://ex.com/@{ZWSP}someone card 1"),
])
def test_outside_code_and_links_the_reviewers_words_still_link_nothing(words: str,
                                                                        kept: str) -> None:
    for where, rows in _both(words):
        assert kept in rows, f"{where}: {kept!r} not in {rows!r}"


def test_an_unclosed_backtick_protects_no_mention_it_is_followed_by() -> None:
    for where, rows in _both("see `x #1 @someone GH-2"):
        text = "\n".join(rows)
        for live in LIVE:
            assert not live.search(text), f"{where}: {live.pattern!r} still matches in {text!r}"
