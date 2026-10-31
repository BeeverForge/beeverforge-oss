"""#113: a card objective that holds a section heading on its own line is not that section.

Both headings were found by their FIRST matching row, and the objective is written before either
section, so the next pass spliced its line or a fresh review into the objective.
"""

TEST = "tests/test_a_heading_in_the_objective_is_not_the_section.py"
MACHINE = "beeverforge/orchestrator/machine.py"

MUTATIONS = [
    ("the agent's section is found by its first heading row again", MACHINE,
     '''    start = next((i for i, row in reversed(list(enumerate(rows)))
                  if row == AGENT_ACCOUNT_HEADING), None)''',
     '''    start = next((i for i, row in enumerate(rows) if row == AGENT_ACCOUNT_HEADING), None)'''),

    ("the review section is found by its first heading row again", MACHINE,
     '''        start = next((i for i, row in reversed(list(enumerate(rows)))
                      if row.startswith(_REVIEW_HEADING)), None)''',
     '''        start = next((i for i, row in enumerate(rows)
                      if row.startswith(_REVIEW_HEADING)), None)'''),
]
