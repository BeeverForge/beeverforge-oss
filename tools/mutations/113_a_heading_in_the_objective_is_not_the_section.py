"""#113: a section heading the platform did not write is not that section.

Both headings were found by their FIRST matching row, and the objective is written before either
section, so the next pass spliced its line or a fresh review into the objective. The review's own
summary and findings could carry a heading row too, and a fresh verdict then left the stale one
standing as the first review heading (#187's case). Two defences: every row the platform did not
write is escaped as it is written (`_as_text`), and both searches read only the rows below the
platform's last `## Validations` row, from the end — so a body published before the escaping,
whose objective rows are raw, is never searched in its objective either.
"""

TEST = "tests/test_a_heading_in_the_objective_is_not_the_section.py"
MACHINE = "beeverforge/orchestrator/machine.py"

MUTATIONS = [
    # ── a body published before the escaping: only the rows below `## Validations` are searched ─
    # RE-PINNED 2026-10-31: both searches are now bounded below `## Validations`; each cut puts
    # back main's first-match search over the whole body.
    ("the agent's section is found by its first heading row again", MACHINE,
     '''    start = next((floor + i for i, row in reversed(list(enumerate(rows[floor:])))
                  if row == AGENT_ACCOUNT_HEADING), None)''',
     '''    start = next((i for i, row in enumerate(rows) if row == AGENT_ACCOUNT_HEADING), None)'''),

    ("the review section is found by its first heading row again", MACHINE,
     '''        start = next((floor + i for i, row in reversed(list(enumerate(rows[floor:])))
                      if row.startswith(_REVIEW_HEADING)), None)''',
     '''        start = next((i for i, row in enumerate(rows)
                      if row.startswith(_REVIEW_HEADING)), None)'''),

    ("the agent's section is searched for above `## Validations` too, so a raw objective is it",
     MACHINE,
     '''    start = next((floor + i for i, row in reversed(list(enumerate(rows[floor:])))
                  if row == AGENT_ACCOUNT_HEADING), None)''',
     '''    start = next((i for i, row in reversed(list(enumerate(rows)))
                  if row == AGENT_ACCOUNT_HEADING), None)'''),

    ("the review section is searched for above `## Validations` too, so a raw objective is it",
     MACHINE,
     '''        start = next((floor + i for i, row in reversed(list(enumerate(rows[floor:])))
                      if row.startswith(_REVIEW_HEADING)), None)''',
     '''        start = next((i for i, row in reversed(list(enumerate(rows)))
                      if row.startswith(_REVIEW_HEADING)), None)'''),

    # ── only the platform writes a section heading ──────────────────────────────────────────────
    ("the objective is written raw, so its heading row reads as a section", MACHINE,
     '''            "", "## Objective", _as_text(card.text(ticket.objective)), "", "## Validations",''',
     '''            "", "## Objective", card.text(ticket.objective), "", "## Validations",'''),

    ("the reviewer's summary is written raw, so a stale verdict outlives a fresh one", MACHINE,
     "        out = [first, _as_text(r.summary)]",
     "        out = [first, r.summary]"),

    ("a finding is written raw, so a stale verdict outlives a fresh one", MACHINE,
     '            out.append(f"- **{f.severity}**{loc}: {_as_text(f.description)}")',
     '            out.append(f"- **{f.severity}**{loc}: {f.description}")'),

    ("the escaping escapes nothing", MACHINE,
     '''    return "\\n".join(f"\\\\{row}" if row.startswith("## ") else row for row in words.split("\\n"))''',
     '''    return words'''),
]
