"""Two statements #1 found stale, held against the code so they cannot drift back (#1).

Run:  .venv/bin/python tools/mutate.py tools/mutations/1_the_docs_say_what_the_code_does.py

Rows 1-2 move the page and the workflow apart: the page back to the 3-minute poll, and the
workflow's slow poll changed under the page. Row 3 puts an `sdlc` command into a document outside
the records. Row 4 drops the renaming note from an ADR that keeps `sdlc …`.
"""

TEST = "tests/test_the_docs_say_what_the_code_does.py"

MUTATIONS = [
    ("the page says the merge wait polls every 3 minutes again", "docs/autonomous-flow.md",
     "Durable poll of merge status every **2 min** for the first hour, then every **15 min**",
     "Durable poll of merge status every **3 min**"),

    ("the workflow's slow poll moves away from the page", "beeverforge/runtime/temporal/workflow.py",
     "_CI_SLOW_POLL = timedelta(minutes=15)",
     "_CI_SLOW_POLL = timedelta(minutes=20)"),

    ("a guide names an `sdlc` command", "CONTRIBUTING.md",
     "  CI runs the random order only, so the fixed-order run is yours to make before you push.\n",
     "  CI runs the random order only, so the fixed-order run is yours to make (`sdlc test`).\n"),

    ("an ADR that keeps `sdlc …` loses the note saying what it is called now",
     "docs/adr/0039-the-action-layer.md",
     "- **Note (2026-11-06, #1):** this record says `sdlc …`",
     "- **Note (2026-11-06, #1):** this record says the old names"),
]
