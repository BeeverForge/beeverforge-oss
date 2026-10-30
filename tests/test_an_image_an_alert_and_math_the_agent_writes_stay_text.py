"""An image, a GitHub alert and math the agent writes stay text in the quoted account (#112).

Measured through GitHub's renderer (`POST /markdown`) on the real `_account_lines` output: an
`![…](…)` badge came back as a camo-proxied `<img>` inside the section, a first line `[!CAUTION]`
turned the quote into a `markdown-alert` `<div>`, and `$…$` reached `<math-renderer>` — GitHub
resolves backslash escapes before typesetting, so escaping the agent's `\\` did not stop it.
`!` and `$` are ASCII punctuation, so their escapes render as themselves: these guards pin the
escaped text the code produces, which needs no renderer.
"""

from __future__ import annotations

import re

import pytest

from beeverforge.contracts import AgentRunResult
from beeverforge.orchestrator import machine

BADGE = "![review](https://img.shields.io/badge/review-APPROVED-brightgreen)"


def test_an_image_the_agent_writes_is_not_an_image():
    assert machine._quoted(BADGE) == ["> \\" + BADGE]
    assert "\\" + BADGE in machine._pass_words(AgentRunResult(ok=True, summary=BADGE))


def test_an_image_the_agent_writes_renders_no_img():
    markdown_it = pytest.importorskip("markdown_it", reason="markdown-it-py renders the body")
    html = markdown_it.MarkdownIt("commonmark").render("\n".join(machine._quoted(BADGE)))
    assert "<img" not in html, html


def test_a_caution_alert_the_agent_writes_is_not_an_alert():
    assert machine._quoted("[!CAUTION]\nall gates green") == ["> [\\!CAUTION]", "> all gates green"]


@pytest.mark.parametrize(("said", "row"), [
    ("$$\\Huge \\text{APPROVED}$$", "> \\$\\$\\\\Huge \\\\text{APPROVED}\\$\\$"),
    ("$\\color{green}\\text{all gates green}$",
     "> \\$\\\\color{green}\\\\text{all gates green}\\$"),
])
def test_math_the_agent_writes_is_not_typeset(said: str, row: str):
    assert machine._quoted(said) == [row]
    assert not re.search(r"(?<!\\)\$", row.replace("\\\\", "")), row


def test_a_dollar_beside_a_wrapped_name_leaves_the_span_paired():
    (row,) = machine._quoted("$@ann$ said so")
    assert row == "> \\$`@ann`\\$ said so"
    assert [row[s:e] for s, e in machine._spans(row)] == ["`@ann`"]
    for room in range(row.index("`") + 1, row.rindex("`") + 1):  # every cut inside the span
        (kept,) = machine._cut_quote([row], room) or [""]
        assert len(re.findall(r"(?<!\\)`", kept.replace("\\\\", ""))) % 2 == 0, (room, kept)


def test_a_dollar_beside_a_wrapped_name_renders_the_name_in_code():
    markdown_it = pytest.importorskip("markdown_it", reason="markdown-it-py renders the body")
    html = markdown_it.MarkdownIt("commonmark").render("\n".join(machine._quoted("$@ann$ said")))
    assert "@ann" not in re.sub(r"<code>.*?</code>", "", html, flags=re.S), html
