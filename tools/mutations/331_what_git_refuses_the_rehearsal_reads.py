"""What git refuses, the environment rehearsal reads (#331).

The diff step committed the agent's work with `git add -A && ... git commit -m ... || true`, so a
commit git REFUSED (exit 128: dubious ownership, a lock it could not take) read as "nothing to
commit". `diff_paths` then hit the same refusal, and the person was told to check that the box has
git and that the base branch is present — git was there, the branch was there, git's own words
never reached anybody.

The claims, each held by a test in `tests/test_onboarding_firstrun.py`:

  - a commit git refuses fails the diff step with git's exit code and words, and the remedy
    "make git usable on this workspace in the box", before `diff_paths` is asked;
  - exit 1 on a clean tree is nothing to commit, and the round goes on quietly;
  - exit 1 on a dirty tree (a refusing hook) is a refusal, not nothing to commit;
  - after an empty diff, a `git status --porcelain` that git refused is not an agent that wrote
    nothing (the sibling at the old firstrun.py:1166).

The `FakeBox` answers a commit command that still ends in `|| true` with exit 0, as the shell
would, so the first row really does swallow the code.
"""

TEST = "tests/test_onboarding_firstrun.py"
FIRSTRUN = "beeverforge/onboarding/firstrun.py"

MUTATIONS = [
    ("`|| true` comes back on the commit, and a refusal reads as nothing to commit", FIRSTRUN,
     'command=f"git add -A && {author}git commit -m {msg}",',
     'command=f"git add -A && {author}git commit -m {msg} || true",'),

    ("exit 1 alone is read as nothing to commit, and a refusing hook on a dirty tree goes on",
     FIRSTRUN,
     "        if rc != 0 and not (rc == 1 and self._tree_is_clean()):\n",
     "        if rc != 0 and not (rc == 1):\n"),

    ("exit 1 on a clean tree is read as a refusal, and nothing to commit fails the round",
     FIRSTRUN,
     "        return rc == 0 and not (dirty or \"\").strip()\n",
     "        return False\n"),

    ("the commit's refusal branch falls through to `diff_paths`, and the old remedy comes back",
     FIRSTRUN,
     "                _GIT_REFUSED_REMEDY, on=self.on), started)\n"
     "            return False\n"
     "        read = box.diff_paths(workspace=ws)\n",
     "                _GIT_REFUSED_REMEDY, on=self.on), started)\n"
     "        read = box.diff_paths(workspace=ws)\n"),

    ("the commit's refusal is not told at all, and the round carries on past it", FIRSTRUN,
     "        if rc != 0 and not (rc == 1 and self._tree_is_clean()):\n",
     "        if False:\n"),

    ("the remedy loses the way out the person can act on", FIRSTRUN,
     '_GIT_REFUSED_REMEDY = ("make git usable on this workspace in the box — git itself refused '
     'it, "\n',
     '_GIT_REFUSED_REMEDY = ("check the box — git itself refused it, "\n'),

    ("git's own words are dropped from the commit's refusal", FIRSTRUN,
     "                \"diff\", f\"`git add -A && git commit` exited {rc} in the workspace\\n\"\n"
     "                        f\"{_tail(out, 8)}\",\n",
     "                \"diff\", f\"`git add -A && git commit` exited {rc} in the workspace\",\n"),

    ("git's exit code is dropped from the commit's refusal", FIRSTRUN,
     "`git add -A && git commit` exited {rc} in the workspace",
     "`git add -A && git commit` failed in the workspace"),

    ("a status git refused after an empty diff reads as an agent that wrote nothing", FIRSTRUN,
     "            if rc != 0:\n"
     "                # A status git refused is not an agent that wrote nothing (#331's sweep).\n",
     "            if False:\n"),
]
