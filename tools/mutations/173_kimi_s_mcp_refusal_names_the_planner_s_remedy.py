"""Kimi's MCP refusal names the entry of the `harness` setting to change: the role its adapter was
built for, the planner's included (#173).

Run:  .venv/bin/python tools/mutate.py tools/mutations/173_kimi_s_mcp_refusal_names_the_planner_s_remedy.py

The refusal runs before every Kimi pass and ended "or give this role another harness." A pass with
no `harness:` entry of its own (the planner on `executor`, the card judge and the documents role on
`reviewer`, the context ask and the sizer on `techlead`) read a setting nobody could find.

Row 1 is the defect as it shipped. Row 2 drops the role on its way from the registry to the
adapter, so every adapter names `executor`. Row 3 names a fixed role whatever the adapter was built
for. Row 4 drops where the setting is. Row 5 lets a role name that is not a plain word into the
shell.
"""

TEST = "tests/test_a_role_reaches_only_the_tools_it_is_given.py"

KIMI = "beeverforge/adapters/agent/kimi.py"
REGISTRY = "beeverforge/adapters/agent/registry.py"

MUTATIONS = [
    ("THE DEFECT: the remedy is 'give this role another harness.' again", KIMI,
     "        'file from the account that runs the harness, or set another harness on the '\n"
     "        f'{role} entry of the project\\'s harness setting in the deployment\\'s project "
     "registry.\"; '\n",
     "        'file from the account that runs the harness, or give this role another harness.\"; '\n"),

    ("the registry drops the role: every Kimi adapter names the executor's entry", REGISTRY,
     'language=kw.get("language"), role=str(kw.get("role") or "executor"))',
     'language=kw.get("language"))'),

    ("the refusal names the executor's entry whatever role the adapter was built for", KIMI,
     "        f'{role} entry of the project", "        f'executor entry of the project"),

    ("the refusal names the entry and not where the setting is", KIMI,
     "harness setting in the deployment\\'s project registry.\"; '",
     "harness entry.\"; '"),

    ("a role name that is not a plain word reaches the shell", KIMI,
     "    if not _PLAIN_ROLE.fullmatch(role):\n", "    if False:\n"),
]
