"""Two statements #1 found stale, held against the code so they cannot drift back (#1).

WHAT WAS WRONG (two of the issue's items, the two a later change is most likely to break again):
  · `docs/autonomous-flow.md` said the merge wait polls every 3 minutes; the workflow polls every
    2 minutes for the first hour, then every 15;
  · ADRs used the command `sdlc …`, which no longer exists; the command is `beeverforge`.

WHAT IS HELD HERE:
  · the cadence the page states is the one `workflow.py`'s constants set;
  · no document outside `docs/adr/` names an `sdlc` command, and an ADR that keeps one, as a record
    of what was decided when, carries the note that says what it is called now.
"""

from __future__ import annotations

import re
from pathlib import Path

from beeverforge.runtime.temporal import workflow

ROOT = Path(__file__).resolve().parent.parent
FLOW = ROOT / "docs" / "autonomous-flow.md"
SDLC_COMMAND = re.compile(r"`sdlc [a-z]|^\s*sdlc [a-z]", re.MULTILINE)
RENAMED = "this record says `sdlc …`"


def _minutes(delta) -> int:
    return int(delta.total_seconds() // 60)


def test_the_merge_wait_cadence_on_the_page_is_the_workflows():
    row = next(line for line in FLOW.read_text(encoding="utf-8").splitlines()
               if "**Wait-for-merge**" in line)
    fast, window, slow = (_minutes(workflow._CI_POLL), _minutes(workflow._CI_FAST_WINDOW) // 60,
                          _minutes(workflow._CI_SLOW_POLL))

    said = (f"every **{fast} min** for the first hour, then every **{slow} min**"
            if window == 1 else None)
    assert said, f"the fast window is {window} h; the page's sentence says the first hour"
    assert said in row, f"the page says {row!r}; the workflow polls {fast} min, then {slow} min"
    assert f"poll {fast} min for {window} h then {slow} min" in FLOW.read_text(encoding="utf-8")


def test_no_document_outside_the_records_names_an_sdlc_command():
    named = [str(p.relative_to(ROOT)) for p in [*(ROOT / "docs").rglob("*.md"),
                                                 ROOT / "README.md", ROOT / "CONTRIBUTING.md"]
             if "adr" not in p.relative_to(ROOT).parts and SDLC_COMMAND.search(p.read_text(
                 encoding="utf-8"))]

    assert named == [], f"these name an `sdlc` command; the command is `beeverforge`: {named}"


def test_a_record_that_keeps_an_sdlc_command_says_what_it_is_called_now():
    unmarked = [p.name for p in sorted((ROOT / "docs" / "adr").glob("[0-9]*.md"))
                if SDLC_COMMAND.search(p.read_text(encoding="utf-8"))
                and RENAMED not in p.read_text(encoding="utf-8")]

    assert unmarked == [], f"these ADRs name `sdlc …` with no note saying it is `beeverforge` now: " \
                           f"{unmarked}"
