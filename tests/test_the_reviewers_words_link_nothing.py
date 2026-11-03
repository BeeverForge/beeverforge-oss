"""The reviewer's summary and findings link no issue and notify no one (#315).

`_review_lines` wrote the reviewer's `summary` and each finding's `description` into the pull
request body as the reviewer wrote them, so a `#12`, `GH-12`, `owner/repo#12` or `@someone` in
them linked an unrelated issue or notified a stranger. The agent's own prose already went through
`without_mentions`; the reviewer's text now does too (`#12` and `GH-12` read `card 12`, #111), and
its `@name` gets a zero-width space that keeps it readable and makes it nothing a forge links. `format_review`, the review
the platform posts on the same pull request, writes the same text and is held to the same rule.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import test_walking_skeleton as spine

from beeverforge.contracts import Manifest, ReviewResult, RunResult, ValidationResult
from beeverforge.contracts.review import Finding
from beeverforge.orchestrator.machine import _REVIEW_HEADING, JobRunner
from beeverforge.orchestrator.merge_policy import format_review

#: GitHub decodes an entity before it links, so `&#x40;someone` and `&commat;someone` mention and
#: `&#x23;1` and `GH&#x2D;1` link, as `@someone` and `#1` do (review of #323, measured on
#: `POST /markdown`). `\\&commat;dee` is one the reviewer already escaped: a second backslash
#: before it would escape the first instead and leave the entity live. A backtick that never
#: closes opens no code span, so the entity after it still mentions and is escaped too.
ENTITIES = "&#x40;someone &commat;someone &#x23;1 GH&#x2D;1 \\&commat;dee see `x &#x40;github"
#: What `_A_URL` finds but GitHub does not autolink, so its `&` is text and the entity is live
#: (reviews of #323 at 8bf6101 and 41956ed, measured on `POST /markdown`): a scheme with no host
#: after it, a host that starts with `-` or has `_` in its last two labels, a scheme link glued to
#: a letter or after a `[`, and a `www.` link after a `<`, which is no autolink (it needs a scheme).
NOT_LINKS = ["https://&#x40;someone", "http://&#x40;someone x", "(https://&#x40;someone)",
             "see:https://&#x40;someone", "https://a_b.c_d/&#x40;someone",
             "http://a_b/&#x40;someone", "http://-x/&#x40;someone",
             "xhttps://ex.com/&#x40;someone", "[https://ex.com/&#x40;someone", "https://&#x23;1",
             "see <www.&#x40;someone> x", "see <www.ex.com/&#x40;someone> x", "see <www.&#x23;1> x"]
#: An autolink whose scheme is not `http(s)`: no backslash inside one is an escape, so `\&` left
#: the entity live (review of #323 at 208035c, measured on `POST /markdown`). Its `<` is escaped,
#: so it is no autolink and `\&` is an escape again.
NOT_AUTOLINKS = ["see <ftp://ex.com/&#x40;someone> x", "see <irc://&#x40;someone> x",
                 "see <ftp://ex.com/&commat;someone> x", "see <ftp://ex.com/&#x23;1> x",
                 "see <ftp://ex.com/&num;1> x", "see <a+b:&#x23;1> x"]
WORDS = (f"Fixes #1, GH-2, gh-4, owner/repo#3, cc @someone {ENTITIES} {' '.join(NOT_LINKS)} "
         f"{' '.join(NOT_AUTOLINKS)}")
ZWSP = "​"

#: What a forge would link or notify: an issue number, a `GH-N`, a cross-repository reference
#: (`owner/repo#3` is caught by the first) and a handle.
LIVE = [re.compile(r"#(?=\d)"),
        re.compile(r"(?<![A-Za-z0-9])GH-\d", re.IGNORECASE),
        re.compile(r"(?<![A-Za-z0-9])@[A-Za-z0-9]"),
        # an `&` no backslash escapes: one after an even run of them (none, or escaped pairs)
        re.compile(r"(?<!\\)(?:\\\\)*&")]


def _review_rows(review: ReviewResult) -> list[str]:
    ticket = spine._sizing_ticket_id("#9")
    result = RunResult(
        ticket_id="#9", state="validating", branch="beeverforge/9",
        validations=[ValidationResult(name="test", command="true", exit_code=0, passed=True)],
        review=review, total_cost_usd=0.05)
    holder = SimpleNamespace(manifest=Manifest(validate={"test": "true"}), _profile=None)
    rows = JobRunner._pr_body(holder, ticket, result).split("\n")
    start = next(i for i, row in enumerate(rows) if row.startswith(_REVIEW_HEADING))
    return rows[start + 1:]


def _assert_dead(text: str) -> None:
    for live in LIVE:
        assert not live.search(text), f"{live.pattern!r} still matches in {text!r}"
    # Still readable: the words are there; a zero-width space is the only change to the name.
    for kept in ("card 1", "owner/repo card 3", f"@{ZWSP}someone", "card 2", "card 4",
                 "\\&#x40;someone", "\\&commat;someone", "\\&#x23;1", "GH\\&#x2D;1",
                 " \\&commat;dee", "see `x \\&#x40;github",
                 *(link.replace("&", "\\&") for link in NOT_LINKS),
                 *(link.replace("<", "\\<").replace("&", "\\&") for link in NOT_AUTOLINKS)):
        assert kept in text, f"{kept!r} not in {text!r}"


def test_a_reviewer_summary_links_and_mentions_nothing() -> None:
    rows = _review_rows(ReviewResult(decision="approved", score=90, summary=WORDS))
    summary = next(row for row in rows if row.startswith("Fixes "))
    _assert_dead(summary)


def test_a_finding_description_links_and_mentions_nothing() -> None:
    review = ReviewResult(decision="approved_with_findings", score=80, summary="fine",
                          findings=[Finding(severity="high", description=WORDS)])
    row = next(row for row in _review_rows(review) if row.startswith("- **high**"))
    _assert_dead(row)


def test_the_review_posted_on_the_pull_request_links_and_mentions_nothing() -> None:
    review = ReviewResult(decision="approved_with_findings", score=80, summary=WORDS,
                          findings=[Finding(severity="low", description=f"also {WORDS}")])
    rows = format_review(review).split("\n")
    _assert_dead(next(row for row in rows if row.startswith("Fixes ")))
    _assert_dead(next(row for row in rows if row.startswith("- **low**")))


def test_an_address_and_a_card_key_are_left_as_written() -> None:
    words = "mail a@b.com about PROJ-12 and AGH-3"
    review = ReviewResult(decision="approved_with_findings", score=80, summary=words,
                          findings=[Finding(severity="low", description=words)])
    rows = _review_rows(review)
    assert words in rows
    assert f"- **low**: {words}" in rows
    assert words in format_review(review).split("\n")


def test_a_heading_row_in_the_reviewer_text_is_still_escaped() -> None:
    rows = _review_rows(ReviewResult(decision="approved", score=90,
                                     summary="said\n## Review — x &#x40;ann\n"
                                             "### Summary heading @ann"))
    assert "\\## Review — x \\&#x40;ann" in rows
    assert f"### Summary heading @{ZWSP}ann" in rows


#: Where a backslash is not an escape, so `\\&` would show it or move a link: a CLOSED code span, a
#: closed fence, a bare link and its angle form (review of #323, measured on `POST /markdown`).
#: An entity there renders literally or as part of the address, and mentions no one.
VERBATIM = ["use `a && b` here", "x && y", "see https://ex.com/?a=1&b=2 now",
            "or <https://ex.com/?a=1&b=2> too", "an ``a ` && b`` span",
            "<https://ex.com/?c=3&d=4> opens a row",
            # links GitHub does make, so the entity is part of the address and mentions no one
            "see https://ex.com/a&#x40;github, (https://ex.com/&#x23;1) *www.&#x40;github*",
            # a scheme link follows any character but an ASCII letter or `[`, and one label is a
            # host (review of #323 at 41956ed, measured on `POST /markdown`)
            '"https://ex.com/?a=1&b=2"', "http://localhost:8080/?a=1&b=2",
            "see:https://ex.com/?a=1&b=2", "éhttps://ex.com/?a=1&b=2",
            "`a`https://ex.com/&#x40;x", "`a`https://ex.com/&#x40;x `b`",
            "'https://ex.com/?a=1&b=2'", "=https://ex.com/?a=1&b=2", "/https://ex.com/?a=1&b=2",
            "!https://ex.com/?a=1&b=2", "1https://ex.com/?a=1&b=2", "`a`https://ex.com/?a=1&b=2",
            "http://x/y?a=1&b=2",
            # GitHub decodes no entity inside an autolink: it is part of the address
            '"https://ex.com/&#x40;someone"', "http://localhost:8080/&#x40;someone",
            # an angle autolink takes any host after its scheme (CommonMark), in any case
            "or <http://a_b/?a=1&b=2> too", "see <HTTPS://ex.com/?a=1&b=2> x"]
FENCED = "\n".join([VERBATIM[0], "```sh", VERBATIM[1], "```", *VERBATIM[2:]])


def test_code_and_links_keep_their_ampersands() -> None:
    review = ReviewResult(decision="approved_with_findings", score=80, summary=FENCED,
                          findings=[Finding(severity="low", description=VERBATIM[0])])
    rows = _review_rows(review)
    posted = format_review(review).split("\n")
    for kept in VERBATIM:
        assert kept in rows, f"{kept!r} not in {rows!r}"
        assert kept in posted, f"{kept!r} not in {posted!r}"
    assert f"- **low**: {VERBATIM[0]}" in rows


def test_outside_the_closed_span_an_ampersand_is_still_escaped() -> None:
    words = "`a && b` & then &#x40;x"
    rows = _review_rows(ReviewResult(decision="approved", score=90, summary=words))
    assert "`a && b` \\& then \\&#x40;x" in rows


def test_where_the_code_is_in_doubt_an_ampersand_is_escaped() -> None:
    # A fence that never closes, a `<` whose tag reaches over a backtick, and an HTML block, where
    # GitHub decodes an entity even between backticks: none is skipped.
    for words, kept in [("```\n&#x40;x", "\\&#x40;x"),
                        ("see <a title='`'> &#x40;x `y`", "see <a title='`'> \\&#x40;x `y`"),
                        ("see <a\ntitle='`'> &#x40;x `y`", "title='`'> \\&#x40;x `y`"),
                        ("<div>\n`&#x40;x`", "`\\&#x40;x`"),
                        # GitHub closes this span on the next row: the `&` after it is text
                        ("`a\nb` &#x40;x `c`", "b` \\&#x40;x `c`"),
                        # a `www.` link glued to a closed span's backtick is not one GFM makes
                        ("`a`www.ex.com/&#x40;x", "`a`www.ex.com/\\&#x40;x"),
                        ("`a`www.ex.com/&#x40;x `b`", "`a`www.ex.com/\\&#x40;x `b`"),
                        # an empty label is no domain GFM describes
                        ("see https://.ex.com/&#x40;x", "see https://.ex.com/\\&#x40;x"),
                        ("see https://ex..com/&#x40;x", "see https://ex..com/\\&#x40;x"),
                        ("see www..ex.com/&#x40;x", "see www..ex.com/\\&#x40;x"),
                        # where a row may open an HTML block, a later paragraph's autolink is
                        # still broken, or its `\&` is no escape
                        ("<div>\n\nsee <ftp://ex.com/&#x40;x> y", "see \\<ftp://ex.com/\\&#x40;x> y")]:
        rows = _review_rows(ReviewResult(decision="approved", score=90, summary=words))
        assert kept in rows, f"{kept!r} not in {rows!r}"
