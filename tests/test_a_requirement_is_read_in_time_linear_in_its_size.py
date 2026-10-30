"""A requirement is read in time linear in its size, however many blank lines it holds (#76).

WHAT WAS WRONG: the field patterns of the product readers opened with `^\\s*` under `MULTILINE`.
`\\s` matches a line break, so at the start of every blank line the pattern ate every blank line
after it, failed, and backtracked: a requirement with n blank lines cost n² steps (10,000 blank
lines took 3.5 s of processor time to read, 50,000 well over a minute). Only a text where the
pattern finds nothing after the blank lines pays it: a match there ends the backtracking early.

WHAT IS HELD HERE: the field patterns (`corpus._field_re`, `domain._field`) never span a line
break, and neither do the other patterns of the product readers that open at a line anchor
(`index.items._HEADER_LINE`, `briefing._flat`). Each is fed 50,000 blank lines and must finish in
well under a second of processor time (`_processor_seconds`), so those tests are marked `alone`.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from beeverforge.product import briefing, domain
from beeverforge.product.corpus import ACCEPTED, _field_re, parse_requirement
from beeverforge.product.index.items import _HEADER_LINE

BLANK_LINES = 50_000
BOUND_SECONDS = 1.0


def _processor_seconds(since: os.times_result) -> float:
    """The processor time spent since `since`, a reading of `os.times()`: this process's and that
    of the children it waited for, user and system."""
    now = os.times()
    return (now.user + now.system + now.children_user + now.children_system
            - since.user - since.system - since.children_user - since.children_system)


# ── a match stays within its own line ──────────────────────────────────────────────────────────


def test_a_field_is_matched_within_its_own_line():
    m = _field_re("Status").search("\n\n\n  - **Status:** accepted\n\n")
    assert m is not None
    assert m.group("value") == "accepted"
    assert "\n" not in m.group(0)


def test_an_empty_field_does_not_read_the_next_line():
    m = _field_re("Status").search("- **Status:**\n\n- **Date:** 2026-01-01\n")
    assert m is not None
    assert m.group("value") == ""
    assert "\n" not in m.group(0)


def test_domain_index_and_briefing_patterns_never_span_a_line_break():
    assert domain._field("\n\n\n- **Source:** x\n", "Source") == "x"
    assert domain._field("- **Source:**\n\n- **Owner:** y\n", "Source") == ""
    matches = list(_HEADER_LINE.finditer("\n\n\n- Status: accepted\n\n# REQ-0001 — t\n\nbody\n"))
    assert [m.group(0) for m in matches] == ["- Status: accepted", "# REQ-0001 — t"]
    flat = briefing._flat("\n\n\n# Title\nbody")
    assert flat == "Title body"


# ── in time linear in the size ─────────────────────────────────────────────────────────────────


@pytest.mark.alone
def test_a_requirement_with_fifty_thousand_blank_lines_is_read_in_under_a_second():
    text = ("# REQ-0001 — t\n" + "\n" * BLANK_LINES
            + "- **Status:** accepted\n\n## Affects\n\n- the checkout\n")
    since = os.times()
    req, _ = parse_requirement(Path("0001-x.md"), text)
    spent = _processor_seconds(since)
    assert req is not None and req.status == ACCEPTED
    assert req.affects == ["the checkout"]
    assert spent < BOUND_SECONDS, f"{spent:.2f} s of processor time"


@pytest.mark.alone
def test_a_requirement_of_blank_lines_and_no_field_is_read_in_under_a_second():
    text = "# REQ-0001 — t\n" + "\n" * BLANK_LINES + "only text\n"
    since = os.times()
    req, findings = parse_requirement(Path("0001-x.md"), text)
    spent = _processor_seconds(since)
    assert req is not None
    assert "status-missing" in {f.code for f in findings}
    assert spent < BOUND_SECONDS, f"{spent:.2f} s of processor time"


@pytest.mark.alone
def test_a_domain_fact_of_blank_lines_is_read_in_under_a_second():
    since = os.times()
    value = domain._field("\n" * BLANK_LINES + "no field here\n", "Source")
    spent = _processor_seconds(since)
    assert value == ""
    assert spent < BOUND_SECONDS, f"{spent:.2f} s of processor time"


@pytest.mark.alone
def test_an_index_item_of_blank_lines_is_stripped_of_its_header_in_under_a_second():
    since = os.times()
    out = _HEADER_LINE.sub("", "\n" * BLANK_LINES + "text")
    spent = _processor_seconds(since)
    assert out.endswith("text")
    assert spent < BOUND_SECONDS, f"{spent:.2f} s of processor time"


@pytest.mark.alone
def test_a_briefing_of_blank_lines_is_flattened_in_under_a_second():
    since = os.times()
    flat = briefing._flat("\n" * BLANK_LINES + "no heading, only body")
    spent = _processor_seconds(since)
    assert flat == "no heading, only body"
    assert spent < BOUND_SECONDS, f"{spent:.2f} s of processor time"
