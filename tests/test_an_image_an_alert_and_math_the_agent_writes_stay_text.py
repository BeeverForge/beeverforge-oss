"""An image, a GitHub alert and math the agent writes stay text in the quoted account (#112).

Measured through GitHub's renderer (`POST /markdown`, mode gfm) on the real `_account_lines`
output: an `![…](…)` badge came back as a camo-proxied `<img>` inside the section, a first line
`[!CAUTION]` turned the quote into a `markdown-alert` `<div>`, and `$…$`, `$$…$$` and
`` $`…`$ `` reached `<math-renderer>` — the last one turning the platform's code span around
`@ann` back into a mention.

GitHub resolves CommonMark's backslash escapes and entities BEFORE it reads an alert or pairs a
`$` (review on a2714e1: `[\\!CAUTION]` was an alert in all five types, `\\$…\\$` was typeset). So
these guards do not pin how the platform spells the text; they read each row the way GitHub
does — escapes and entities resolved, the platform's code spans kept whole — and assert the
property GitHub acts on: no row is an alert marker, no `$` is one GitHub would pair (every `$`
outside code follows a zero-width space, the one shape measured to stop all three forms), and no
`![` is left unescaped.
"""

from __future__ import annotations

import html
import re
import string

import pytest

from beeverforge.contracts import AgentRunResult
from beeverforge.orchestrator import machine

BADGE = "![review](https://img.shields.io/badge/review-APPROVED-brightgreen)"
ALERTS = ["NOTE", "note", "Tip", "IMPORTANT", "warning", "CAUTION"]
MATH = ["$$\\Huge \\text{APPROVED}$$", "$\\color{green}\\text{all gates green}$",
        "$`@ann`$ said so", "$@ann$ said so", "costs $5 and $6 more", "$$\n\\Huge x\n$$",
        "see https://example.com/$a$ and $b$", "[$x$](https://example.com/a) $y$"]
_ENTITY = re.compile(r"&(?:#[0-9]{1,7}|#[xX][0-9a-fA-F]{1,6}|[A-Za-z][A-Za-z0-9]*);")
_ZWSP = "​"


def github_reads(row: str) -> list[tuple[str, str]]:
    """A quote row as GitHub reads its text: `(kind, text)` pieces, `code` for a code span (kept
    verbatim, backticks included) and `text` for the rest, with CommonMark's backslash escapes and
    entities resolved — what GitHub's alert and math readers see."""
    body = row[2:] if row.startswith("> ") else row.lstrip(">")
    out: list[tuple[str, str]] = []
    text, i = [], 0
    while i < len(body):
        c = body[i]
        if c == "\\" and i + 1 < len(body) and body[i + 1] in string.punctuation:
            text.append(body[i + 1])
            i += 2
        elif c == "&" and (entity := _ENTITY.match(body, i)):
            text.append(html.unescape(entity[0]))
            i = entity.end()
        elif c == "`" and (end := body.find("`", i + 1)) != -1:
            out += [("text", "".join(text)), ("code", body[i:end + 1])]
            text, i = [], end + 1
        else:
            text.append(c)
            i += 1
    return [*out, ("text", "".join(text))]


def read_as_text(row: str) -> str:
    return "".join(piece for _, piece in github_reads(row))


def pairable_dollars(row: str) -> list[str]:
    """Each `$` GitHub could pair into math: outside a code span, and not after a zero-width
    space. Shown with what is around it, for the failure message."""
    return [text[max(0, k - 3):k + 4] for kind, text in github_reads(row) if kind == "text"
            for k, c in enumerate(text) if c == "$" and (k == 0 or text[k - 1] != _ZWSP)]


def is_an_alert_marker(row: str) -> bool:
    return bool(re.fullmatch(r"\s*\[!(?:note|tip|important|warning|caution)\]\s*",
                             read_as_text(row), re.IGNORECASE))


def test_an_image_the_agent_writes_is_not_an_image():
    for rows in (machine._quoted(BADGE),
                 [machine._pass_words(AgentRunResult(ok=True, summary=BADGE))]):
        for row in rows:
            assert not re.search(r"(?<!\\)(?:\\\\)*!\[", row), row  # an unescaped `![` opens one
            assert "review" in read_as_text(row), row


def test_an_image_the_agent_writes_renders_no_img():
    markdown_it = pytest.importorskip("markdown_it", reason="markdown-it-py renders the body")
    html_ = markdown_it.MarkdownIt("commonmark").render("\n".join(machine._quoted(BADGE)))
    assert "<img" not in html_, html_  # CommonMark and GFM read an image alike


@pytest.mark.parametrize("kind", ALERTS)
@pytest.mark.parametrize("shape", ["[!{}]", "  [!{}]  ", "\t[!{}]"])
def test_an_alert_the_agent_writes_is_not_an_alert(kind: str, shape: str):
    said = shape.format(kind)
    rows = machine._quoted(f"{said}\nall gates green")
    assert [is_an_alert_marker(row) for row in rows] == [False, False], rows
    assert read_as_text(rows[0]).strip() == f"`{said.strip()}`"  # shown as the agent wrote it


def test_an_alert_marker_after_an_empty_row_is_not_an_alert():
    rows = machine._quoted("\n[!CAUTION]\nall gates green")
    assert not any(map(is_an_alert_marker, rows)), rows


def test_an_alert_marker_in_a_sentence_is_left_as_text():
    (row,) = machine._quoted("[!NOTE] the gates ran")
    assert read_as_text(row) == "[!NOTE] the gates ran", row  # GitHub reads no alert here


@pytest.mark.parametrize("said", MATH)
def test_math_the_agent_writes_is_not_typeset(said: str):
    rows = machine._quoted(said)
    assert [pairable_dollars(row) for row in rows] == [[] for _ in rows], rows
    shown = "\n".join(read_as_text(row).replace(_ZWSP, "") for row in rows)
    assert shown.count("$") == said.count("$"), rows  # every `$` still shown


def test_math_in_a_later_pass_line_is_not_typeset():
    words = machine._pass_words(AgentRunResult(ok=True, summary=MATH[1]))
    assert pairable_dollars(words) == [], words


def test_a_dollar_beside_a_wrapped_name_leaves_the_name_in_the_platforms_span():
    """GitHub reads `` $`…`$ `` as inline math, which renders the span's `@ann` as a mention: on
    the base the row was `\\$`@ann`\\$` and came back `<math-renderer>$<a class="user-mention"…`."""
    (row,) = machine._quoted("$@ann$ said so")
    pieces = github_reads(row)
    assert ("code", "`@ann`") in pieces, pieces
    assert all("@ann" not in text for kind, text in pieces if kind == "text"), pieces
    assert pairable_dollars(row) == [], row
    assert [row[s:e] for s, e in machine._spans(row)] == ["`@ann`"]


@pytest.mark.parametrize("said", ["$@ann$ said so", "costs $5 and $6 more", "a$`b`$c $$d$$"])
def test_a_cut_never_opens_a_dollar_or_a_span(said: str):
    (row,) = machine._quoted(said)
    for room in range(3, len(row)):
        (kept,) = machine._cut_quote([row], room) or [""]
        assert row.startswith(kept)
        assert pairable_dollars(kept) == [], (room, kept)
        assert "&" not in read_as_text(kept), (room, kept)  # no entity cut open
        assert len(re.findall(r"(?<!\\)`", kept.replace("\\\\", ""))) % 2 == 0, (room, kept)


@pytest.mark.parametrize(("said", "shown"), [("$5", 2), ("$$x$$", 5), ("$`@ann`$", 8),
                                             ("[!NOTE]", 7)])
def test_the_cut_line_counts_a_dollar_and_an_alert_marker_as_the_agent_wrote_them(said, shown):
    assert machine._quote_chars(machine._quoted(said)) == shown
