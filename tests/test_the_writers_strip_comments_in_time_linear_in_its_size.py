"""The requirement writers strip comments in time linear in a value's size (#322, after #76).

WHAT WAS WRONG: #76 replaced `re.sub(r"<!--.*?-->", "", value)` in the readers with
`corpus._without_comments`, one left-to-right scan, but the writers in `authoring.py` that check,
drop and accept a requirement kept the old pattern on its Status, Asked by and Date values. The
pattern searched for a close from every `<!--` to the end of the value, so a value of n unclosed
openings cost n² steps there while the reader of the same file took linear time.

WHAT IS HELD HERE: each writer grows linearly on a value of many `<!--`, MEASURED, NOT BOUNDED,
with the n against 4n processor-time ratio of #76's own test; and on ordinary values (the
template's own comments, and a value with none) the shared helper and the writers give exactly
what the old pattern gave.
"""

from __future__ import annotations

import re
from pathlib import Path

from beeverforge.product.authoring import (
    _is_dropped,
    _set_status_accepted,
    _set_status_dropped,
)
from beeverforge.product.corpus import _without_comments
from tests.test_a_requirement_is_read_in_time_linear_in_its_size import N, _linear

DAY = "2026-01-01"
TEMPLATE = (Path(__file__).resolve().parents[1]
            / "beeverforge/org_defaults/requirements/0000-template.md")


def _many_openings_in_status(n: int) -> str:
    return "# REQ-0001 — t\n\n- **Status:** " + "<!--" * n + "\n"


def test_a_status_of_many_comment_openings_is_checked_for_dropped_linearly():
    assert _is_dropped(_many_openings_in_status(N)) is False
    _linear(_is_dropped, _many_openings_in_status)


def test_a_status_of_many_comment_openings_is_dropped_linearly():
    text = _many_openings_in_status(N)
    new, outcome = _set_status_dropped(text, dropped_by="someone", day=DAY)
    assert new == text
    assert outcome.endswith("which is not a state anything can be dropped from")
    _linear(lambda t: _set_status_dropped(t, dropped_by="someone", day=DAY),
            _many_openings_in_status)


def test_a_status_of_many_comment_openings_is_accepted_linearly():
    text = _many_openings_in_status(N)
    new, outcome = _set_status_accepted(text, accepted_by="someone", day=DAY)
    assert new == text
    assert outcome.endswith("which is not a pre-promise state")
    _linear(lambda t: _set_status_accepted(t, accepted_by="someone", day=DAY),
            _many_openings_in_status)


def test_an_asker_of_many_comment_openings_is_kept_on_accept_linearly():
    def make(n: int) -> str:
        return ("- **Status:** proposed\n- **Asked by:** " + "<!--" * n
                + f"\n- **Date:** {DAY}\n")
    new, outcome = _set_status_accepted(make(N), accepted_by="someone", day=DAY)
    assert outcome == "flipped"
    assert new == ("- **Status:** accepted\n- **Asked by:** " + "<!--" * N
                   + f"\n- **Date:** {DAY}\n")
    _linear(lambda t: _set_status_accepted(t, accepted_by="someone", day=DAY), make)


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
