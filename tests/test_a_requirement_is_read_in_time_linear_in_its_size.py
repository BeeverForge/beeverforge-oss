"""A requirement is read in time linear in its size, however many blank lines it holds (#76).

WHAT WAS WRONG: the field patterns of the product readers opened with `^\\s*` under `MULTILINE`.
`\\s` matches a line break, so at the start of every blank line the pattern ate every blank line
after it, failed, and backtracked: a requirement with n blank lines cost n² steps (10,000 blank
lines took 3.5 s of processor time to read, 50,000 well over a minute). Only a text where the
pattern finds nothing after the blank lines pays it: a match there ends the backtracking early.

THE SAME SHAPE WITHIN ONE LINE (review of #301): a lazy group closed by `\\s*$` (the title, a
field's value, a section heading, a domain term, an indexed heading) tried every end on the line
and scanned the rest of it from each, so `# REQ-0001 — t` and 20,000 spaces took 2.65 s; and
`<!--.*?-->` scanned to the end of the value from every `<!--` it met, so 20,000 of them took 23 s.

WHAT IS HELD HERE: no pattern of the product readers spans a line break where it should not, and
every reader grows linearly. The growth is MEASURED, NOT BOUNDED: each reader is run on n and on 4n
and the ratio of their processor times must stay below 8, where linear work gives about 4 and the
old patterns gave 16 or more. A ratio of two readings in the same process at the same moment is
what machine load cannot move, so these tests run in the unit gate, with neighbours.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from beeverforge.product import briefing, domain
from beeverforge.product.corpus import (
    _HEADING_RE,
    _TITLE_RE,
    ACCEPTED,
    _field_re,
    _without_comments,
    parse_requirement,
)
from beeverforge.product.index import items
from beeverforge.product.index.items import _HEADER_LINE

#: the smaller size; the larger is four times it. The old patterns took 5–15 ms at this size and
#: 60–200 ms at four times it, so a regression fails in well under a second of reading.
N = 1_000
#: linear work grows about 4×, quadratic about 16×
LINEAR_AT_MOST = 8.0
#: a reading shorter than this is mostly the clock; the small size is repeated until it is longer
CALIBRATED = 0.02


def _seconds(read: Callable[[str], object], text: str, reps: int) -> float:
    """The processor time `reps` reads of `text` took."""
    since = time.process_time()
    for _ in range(reps):
        read(text)
    return time.process_time() - since


def _growth(read: Callable[[str], object], make: Callable[[int], str], n: int) -> float:
    """How many times longer `read` takes on `make(4 * n)` than on `make(n)`: the least of three
    tries each, the larger stopping at its first try under `LINEAR_AT_MOST`, since a reading is
    only ever made longer by what else the machine does, never shorter."""
    small, large = make(n), make(4 * n)
    reps = 1
    while _seconds(read, small, reps) < CALIBRATED:
        reps *= 2
    base = max(min(_seconds(read, small, reps) for _ in range(3)), 1e-9)
    ratio = float("inf")
    for _ in range(3):
        ratio = min(ratio, _seconds(read, large, reps) / base)
        if ratio < LINEAR_AT_MOST:
            break
    return ratio


def _linear(read: Callable[[str], object], make: Callable[[int], str], n: int = N) -> None:
    ratio = _growth(read, make, n)
    assert ratio < LINEAR_AT_MOST, (
        f"4× the input took {ratio:.1f}× the processor time; linear is about 4, quadratic 16")


def _requirement(text: str):
    return parse_requirement(Path("0001-x.md"), text)


# ── a match stays within its own line ──────────────────────────────────────────────────────────


def test_a_field_is_matched_within_its_own_line():
    m = _field_re("Status").search("\n\n\n  - **Status:** accepted\n\n")
    assert m is not None
    assert m.group("value").strip() == "accepted"
    assert "\n" not in m.group(0)


def test_an_empty_field_does_not_read_the_next_line():
    m = _field_re("Status").search("- **Status:**\n\n- **Date:** 2026-01-01\n")
    assert m is not None
    assert m.group("value").strip() == ""
    assert "\n" not in m.group(0)


def test_domain_index_and_briefing_patterns_never_span_a_line_break():
    assert domain._field("\n\n\n- **Source:** x\n", "Source") == "x"
    assert domain._field("- **Source:**\n\n- **Owner:** y\n", "Source") == ""
    matches = list(_HEADER_LINE.finditer("\n\n\n- Status: accepted\n\n# REQ-0001 — t\n\nbody\n"))
    assert [m.group(0) for m in matches] == ["- Status: accepted", "# REQ-0001 — t"]
    flat = briefing._flat("\n\n\n# Title\nbody")
    assert flat == "Title body"


def test_titles_values_and_headings_are_read_without_their_trailing_space():
    req, _ = _requirement("# REQ-0001 — the title   \n\n- **Status:** accepted   \n"
                          "- **Asked by:** Ana <!-- who -->  \n\n## Affects\n\n- the checkout\n")
    assert req is not None
    assert (req.title, req.status, req.asked_by) == ("the title", ACCEPTED, "Ana")
    assert [m.group(1).strip() for m in _HEADING_RE.finditer("## Affects  \n## Why\n")] == [
        "Affects", "Why"]
    facts, _ = domain.parse_facts("### the term   \n- **Source:** x\n")
    assert [f.term for f in facts] == ["the term"]
    assert items.chunks("## A heading ##  \n\nbody")[0][0] == "§ A heading"


def test_a_comment_is_removed_from_a_value_and_only_within_its_line():
    assert _without_comments("a <!-- b --> c <!-- d -->") == "a  c "
    assert _without_comments("a <!-- open") == "a <!-- open"
    assert _without_comments("a <!-- b\n --> c") == "a <!-- b\n --> c"
    assert _without_comments("<!-- x --><!-- unclosed\n<!-- y -->z") == "<!-- unclosed\nz"


# ── in time linear in the size ─────────────────────────────────────────────────────────────────


def test_a_requirement_read_grows_linearly_in_its_blank_lines():
    def make(n: int) -> str:
        return ("# REQ-0001 — t\n" + "\n" * n
                + "- **Status:** accepted\n\n## Affects\n\n- the checkout\n")
    req, _ = _requirement(make(N))
    assert req is not None and req.status == ACCEPTED and req.affects == ["the checkout"]
    _linear(_requirement, make)


def test_a_requirement_of_blank_lines_and_no_field_grows_linearly():
    def make(n: int) -> str:
        return "# REQ-0001 — t\n" + "\n" * n + "only text\n"
    req, findings = _requirement(make(N))
    assert req is not None and "status-missing" in {f.code for f in findings}
    _linear(_requirement, make)


def test_a_domain_fact_of_blank_lines_grows_linearly():
    assert domain._field("\n" * N + "no field here\n", "Source") == ""
    _linear(lambda t: domain._field(t, "Source"), lambda n: "\n" * n + "no field here\n")


def test_an_index_item_of_blank_lines_is_stripped_of_its_header_linearly():
    assert _HEADER_LINE.sub("", "\n" * N + "text").endswith("text")
    _linear(lambda t: _HEADER_LINE.sub("", t), lambda n: "\n" * n + "text")


def test_a_briefing_of_blank_lines_is_flattened_linearly():
    assert briefing._flat("\n" * N + "no heading, only body") == "no heading, only body"
    _linear(briefing._flat, lambda n: "\n" * n + "no heading, only body")


def test_a_title_of_many_spaces_is_read_linearly():
    def make(n: int) -> str:
        return "# REQ-0001 — t" + " " * n + "x\n"
    req, _ = _requirement(make(N))
    assert req is not None and req.title == "t" + " " * N + "x"
    _linear(lambda t: _TITLE_RE.search(t), make)


def test_a_field_value_of_many_spaces_is_read_linearly():
    def make(n: int) -> str:
        return "- **Status:** a" + " " * n + "x\n"
    assert _field_re("Status").search(make(N)).group("value").strip() == "a" + " " * N + "x"
    _linear(_requirement, make)


def test_a_status_of_many_comment_openings_is_read_linearly():
    def make(n: int) -> str:
        return "# REQ-0001 — t\n\n- **Status:** " + "<!--" * n + "\n"
    req, _ = _requirement(make(N))
    assert req is not None
    _linear(_requirement, make)


def test_an_asker_of_many_comment_openings_is_read_linearly():
    def make(n: int) -> str:
        return "# REQ-0001 — t\n\n- **Status:** accepted\n- **Asked by:** " + "<!--" * n + "\n"
    req, _ = _requirement(make(N))
    assert req is not None and req.asked_by == "!--" + "<!--" * (N - 1)  # `_clean` strips `<`
    _linear(_requirement, make)


def test_a_domain_field_of_many_comment_openings_is_read_linearly():
    def make(n: int) -> str:
        return "- **Source:** " + "<!--" * n + "\n"
    assert domain._field(make(N), "Source") == "<!--" * N
    _linear(lambda t: domain._field(t, "Source"), make)


def test_a_domain_term_of_many_spaces_is_read_linearly():
    def make(n: int) -> str:
        return "### t" + " " * n + "x\n- **Source:** s\n"
    facts, _ = domain.parse_facts(make(N))
    assert [f.term for f in facts] == ["t" + " " * N + "x"]
    _linear(domain.parse_facts, make)


def test_a_section_heading_of_many_spaces_is_read_linearly():
    def make(n: int) -> str:
        return "## t" + " " * n + "x\n"
    _linear(lambda t: list(_HEADING_RE.finditer(t)), make)


#: `(.+?)\s*#*\s*$` has two `\s*` side by side, so the old indexed heading was CUBIC: 0.39 s at 800
#: spaces. A smaller size keeps a regression's failure short.
HEADING_SPACES = 200


def test_an_indexed_heading_of_many_spaces_is_read_linearly():
    def make(n: int) -> str:
        return "# t" + " " * n + "x\n\nbody"
    assert items.chunks(make(N))[0][0] == "§ " + ("t" + " " * N + "x")[:80]
    _linear(items.chunks, make, HEADING_SPACES)


#: the scan's own work is `str.find`, a C loop, so a scan that looked for the end of the line from
#: every comment showed its n² only past ~10,000 comments: 12× at this size, against 4× as written
CLOSED_COMMENTS = 20_000


def test_a_line_of_many_closed_comments_is_cleared_linearly():
    assert _without_comments("<!---->" * N + "x") == "x"
    _linear(_without_comments, lambda n: "<!---->" * n + "x\n", CLOSED_COMMENTS)
