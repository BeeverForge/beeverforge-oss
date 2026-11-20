"""A git call the repo cache or the worktree box makes never asks for a password at the terminal,
proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/45_a_git_call_never_asks_for_a_password.py

The claims, each a row:

  1. both runners switch off git's own prompt and Git Credential Manager's;
  2. the prompt entries are merged last, so neither a caller's env nor the process's turns them
     back on, and the box keeps a caller's env as the whole environment;
  3. the box's runner adds them to git commands only.
"""

TEST = "tests/test_a_git_call_never_asks_for_a_password.py"
CACHE = "beeverforge/runtime/repo_cache.py"
WORKTREE = "beeverforge/adapters/sandbox/worktree.py"

MUTATIONS = [
    # 1. the prompt entries
    ("the cache's `_git` leaves git's own prompt on", CACHE,
     '**(env or {}),\n'
     '                                                  "GIT_TERMINAL_PROMPT": "0",\n',
     '**(env or {}),\n'),
    ("the box's `_run` leaves git's own prompt on", WORKTREE,
     '    return {**base, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}',
     '    return {**base, "GCM_INTERACTIVE": "never"}'),
    ("the cache's `_git` leaves Git Credential Manager's prompt on", CACHE,
     '                                                  "GCM_INTERACTIVE": "never"})',
     '                                                  })'),
    ("the box's `_run` leaves Git Credential Manager's prompt on", WORKTREE,
     '    return {**base, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}',
     '    return {**base, "GIT_TERMINAL_PROMPT": "0"}'),

    # 2. the merge order
    ("the cache's `_git` lets the process and the caller turn the prompt back on", CACHE,
     'env={**os.environ, **(env or {}),\n'
     '                                                  "GIT_TERMINAL_PROMPT": "0",\n'
     '                                                  "GCM_INTERACTIVE": "never"})',
     'env={"GIT_TERMINAL_PROMPT": "0",\n'
     '                                                  "GCM_INTERACTIVE": "never",\n'
     '                                                  **os.environ, **(env or {})})'),
    ("the box's `_run` lets the caller or the process turn the prompt back on", WORKTREE,
     '    return {**base, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}',
     '    return {"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never", **base}'),
    ("the box's `_run` widens a caller's whole env with the process's, restoring what was "
     "scrubbed", WORKTREE,
     '    base = os.environ if env is None else env\n',
     '    base = {**os.environ, **(env or {})}\n'),

    # 3. git only
    ("the box's `_run` sets the prompt entries for every command, not git alone", WORKTREE,
     '        cmd = ["git", *gitpin.HOOKLESS, *cmd[1:]]\n'
     '        env = _prompt_off(env)\n',
     '        cmd = ["git", *gitpin.HOOKLESS, *cmd[1:]]\n'
     '    env = _prompt_off(env)\n'),
]
