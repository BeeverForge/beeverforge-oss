"""Kimi's MCP refusal on a planner pass names a remedy the planner can take (#173).

Run:  .venv/bin/python tools/mutate.py tools/mutations/173_kimi_s_mcp_refusal_names_the_planner_s_remedy.py

`NOT_WHILE_DECLARED` runs before every Kimi pass, the planner's included, and ended "or give this
role another harness." The planner has no harness of its own: it runs on the executor's.

Row 1 is the defect as it shipped: the parenthetical is gone. Row 2 names another role's harness.
"""

TEST = "tests/test_a_role_reaches_only_the_tools_it_is_given.py"

KIMI = "beeverforge/adapters/agent/kimi.py"

MUTATIONS = [
    ("THE DEFECT: the remedy is 'give this role another harness.' again", KIMI,
     "    'from the account that runs the harness, or give this role another harness (for the '\n"
     "    'planner, the executor\\'s, which it runs on).\"; '\n",
     "    'from the account that runs the harness, or give this role another harness.\"; '\n"),

    ("the parenthetical names the reviewer's harness, not the executor's", KIMI,
     "    'planner, the executor\\'s, which it runs on).\"; '\n",
     "    'planner, the reviewer\\'s, which it runs on).\"; '\n"),
]
