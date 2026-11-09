"""The requirement writers strip comments in time linear in a value's size (#322, after #76).

WHAT WAS WRONG: #76 replaced `re.sub(r"<!--.*?-->", "", value)` in the readers with
`corpus._without_comments`, one left-to-right scan, but the writers in `authoring.py` that check,
drop and accept a requirement kept the old pattern on its Status, Asked by and Date values. The
pattern searched for a close from every `<!--` to the end of the value, so a value of n unclosed
openings cost n² steps there while the reader of the same file took linear time.

WHAT IS HELD HERE: each writer passes the value it reads through `corpus._without_comments`, the
reader's own one-pass helper, whose linearity #76's test already measures. That is checked by
recording the helper's arguments, with no clock, so the result depends on the code alone (#322 AC 1:
not by a fixed time bound). On ordinary values (the template's own comments, and a value with none)
the shared helper and the writers give exactly what the old pattern gave.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from beeverforge.product import authoring
from beeverforge.product.authoring import (
    _is_dropped,
    _set_status_accepted,
    _set_status_dropped,
)
from beeverforge.product.corpus import _without_comments

DAY = "2026-01-01"
TEMPLATE = (Path(__file__).resolve().parents[1]
            / "beeverforge/org_defaults/requirements/0000-template.md")


@pytest.fixture
def stripped(monkeypatch) -> list[str]:
    """Every value a writer hands to `_without_comments`, which still does the real work."""
    seen: list[str] = []
    real = authoring._without_comments

    def recording(value: str) -> str:
        seen.append(value)
        return real(value)

    monkeypatch.setattr(authoring, "_without_comments", recording)
    return seen


def _status(value: str) -> str:
    return f"# REQ-0001 — t\n\n- **Status:** {value}\n"


def test_the_dropped_check_strips_the_status_with_the_readers_helper(stripped):
    assert _is_dropped(_status("dropped <!-- c1 -->")) is True
    assert any("<!-- c1 -->" in v for v in stripped), stripped


def test_the_drop_strips_the_status_with_the_readers_helper(stripped):
    text = _status("dropped <!-- c2 -->")
    assert _set_status_dropped(text, dropped_by="someone", day=DAY) == (text, "already")
    assert any("<!-- c2 -->" in v for v in stripped), stripped


def test_the_accept_strips_the_status_with_the_readers_helper(stripped):
    text = _status("accepted <!-- c3 -->")
    assert _set_status_accepted(text, accepted_by="someone", day=DAY) == (text, "already")
    assert any("<!-- c3 -->" in v for v in stripped), stripped


def test_the_accept_strips_an_existing_asker_and_date_with_the_readers_helper(stripped):
    text = ("- **Status:** proposed\n- **Asked by:** someone <!-- c4 -->\n"
            f"- **Date:** {DAY} <!-- c5 -->\n")
    new, outcome = _set_status_accepted(text, accepted_by="someone", day=DAY)
    assert outcome == "flipped"
    assert new == text.replace("proposed", "accepted")
    assert any("<!-- c4 -->" in v for v in stripped), stripped
    assert any("<!-- c5 -->" in v for v in stripped), stripped


def _template_values() -> list[str]:
    values = [m.group(1) for m in re.finditer(r"(?m)^- \*\*[^*]+:\*\*(.*)$",
                                              TEMPLATE.read_text(encoding="utf-8"))]
    assert any("<!--" in v for v in values), "the template carries no field comment to compare"
    return values


def test_the_template_comment_and_a_plain_value_strip_as_before():
    # the old pattern, kept here only as the oracle the shared helper must agree with
    for value in [*_template_values(), " accepted", " someone", "", " a <!-- b --> c <!-- d"]:
        assert _without_comments(value) == re.sub(r"<!--.*?-->", "", value), value


TEMPLATE_HEAD = (
    "# REQ-0000 — t\n\n"
    "- **Status:** proposed        <!-- proposed · accepted · superseded-by NNNN -->\n"
    "- **Asked by:** <who>          <!-- the person, not the agent that transcribed it -->\n"
    "- **Date:** YYYY-MM-DD\n"
)


def test_the_writers_rewrite_the_template_as_before():
    assert _is_dropped(TEMPLATE_HEAD) is False
    assert _set_status_accepted(TEMPLATE_HEAD, accepted_by="someone", day=DAY) == (
        "# REQ-0000 — t\n\n"
        "- **Status:** accepted        <!-- proposed · accepted · superseded-by NNNN -->\n"
        "- **Asked by:** <who>          <!-- the person, not the agent that transcribed it -->\n"
        "- **Date:** YYYY-MM-DD\n", "flipped")
    assert _set_status_dropped(TEMPLATE_HEAD, dropped_by="someone", day=DAY) == (
        "# REQ-0000 — t\n\n"
        "- **Status:** dropped\n"
        f"- **Dropped by:** someone on {DAY}\n"
        "- **Asked by:** <who>          <!-- the person, not the agent that transcribed it -->\n"
        "- **Date:** YYYY-MM-DD\n", "flipped")


def test_the_writers_rewrite_a_value_without_a_comment_as_before():
    plain = "- **Status:** proposed\n- **Asked by:** someone\n"
    assert _is_dropped(plain) is False
    assert _is_dropped("- **Status:** dropped\n") is True
    assert _set_status_accepted(plain, accepted_by="someone", day=DAY) == (
        f"- **Status:** accepted\n- **Date:** {DAY}\n- **Asked by:** someone\n", "flipped")
    assert _set_status_dropped(plain, dropped_by="someone", day=DAY) == (
        f"- **Status:** dropped\n- **Dropped by:** someone on {DAY}\n- **Asked by:** someone\n",
        "flipped")
