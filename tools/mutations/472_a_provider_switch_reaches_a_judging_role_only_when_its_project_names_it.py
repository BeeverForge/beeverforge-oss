"""A provider switch reaches a judging role only when its project's `box.env` names it (#472),
proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
          tools/mutations/472_a_provider_switch_reaches_a_judging_role_only_when_its_project_names_it.py

`_scrubbed_env` removed the AWS credentials of a project that does not name them, and left
`CLAUDE_CODE_USE_BEDROCK` / `CLAUDE_CODE_USE_VERTEX`, so a deployment-wide switch sent another
project's judging roles to a provider they had no credentials for. The claims, each a row:

  1. the worktree withholds a switch the project does not name;
  2. it keeps one the project names (retired as a row: two lines keep a named variable, below);
  3. the list is every switch the routes read: Bedrock and Vertex, and nothing the routes do not
     read (a switch they do not read is left as it is).
"""

TEST = "tests/test_a_provider_switch_reaches_a_judging_role_only_when_its_project_names_it.py"

WORKTREE = "beeverforge/adapters/sandbox/worktree.py"

MUTATIONS = [
    # 1. withheld
    ("TODAY'S DEFECT: the switches are not withheld", WORKTREE,
     " + _AGENT_CRED_VARS + _PROVIDER_SWITCH_VARS:\n",
     " + _AGENT_CRED_VARS:\n"),
    # 2. kept when named
    # RETIRED 2026-11-08: no single cut can see it, and the guard is not the reason. A name
    # `box.env` declares is kept by two lines that predate this change and serve every credential
    # too: the loop skips it (`if var not in kept:`), and the re-read through the credential store
    # below puts it back (`elif var in kept and found.value:`, where `lookup` falls back to the
    # process variable). Each cut alone stayed green (5 passed), because the other line still keeps
    # the switch; the test's "kept" assertions hold the two together.
    # 3. the list
    ("Vertex's switch is not on the list", WORKTREE,
     '_PROVIDER_SWITCH_VARS = ("CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX")\n',
     '_PROVIDER_SWITCH_VARS = ("CLAUDE_CODE_USE_BEDROCK",)\n'),
    ("Bedrock's switch is not on the list", WORKTREE,
     '_PROVIDER_SWITCH_VARS = ("CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX")\n',
     '_PROVIDER_SWITCH_VARS = ("CLAUDE_CODE_USE_VERTEX",)\n'),
    ("a switch the routes do not read is withheld", WORKTREE,
     '_PROVIDER_SWITCH_VARS = ("CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX")\n',
     '_PROVIDER_SWITCH_VARS = ("CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX",\n'
     '                         "CLAUDE_CODE_USE_FOUNDRY")\n'),
]
