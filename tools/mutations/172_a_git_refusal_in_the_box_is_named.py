"""#172: a git refusal in the box is named, not swallowed.

Two guards: `ContainerSandbox.prepare` checks its `safe.directory` write, and `JobRunner._commit`
tells "nothing to commit" (exit 1, nothing staged) from a refusal by exit code. The reverses
matter: a check that always fires refuses every good box, and one that never reads what is staged
turns every exit 1 into silence. The refusal names HOME only when git said its config could not be
written; a box with no git, or one that stopped, is told what it is.
"""

TEST = "tests/test_a_git_refusal_in_the_box_is_named.py"
BOX = "beeverforge/adapters/sandbox/container.py"
MACHINE = "beeverforge/orchestrator/machine.py"

MUTATIONS = [
    ("the safe.directory write is not checked - the box starts with git refused in it", BOX,
     '                         "--add", "safe.directory", _WORKDIR])\n'
     "        if rc != 0:",
     '                         "--add", "safe.directory", _WORKDIR])\n'
     "        if False:"),

    ("...and the reverse: every box refuses, a good one too", BOX,
     '                         "--add", "safe.directory", _WORKDIR])\n'
     "        if rc != 0:",
     '                         "--add", "safe.directory", _WORKDIR])\n'
     "        if True:"),

    ("the refusal does not name the box's HOME", BOX,
     '(f"its HOME {home!r}" if home else "an unreadable HOME")',
     '"its HOME"'),

    ("a box that stopped is blamed on its HOME", BOX,
     '        if "is not running" in (out or ""):',
     "        if False:"),

    ("an image with no git is blamed on its HOME", BOX,
     "        if rc in (126, 127):",
     "        if False:"),

    ("every failure of the write is blamed on its HOME, whatever git said", BOX,
     "        if not any(w in (out or \"\") for w in self._HOME_WRITE_FAILURES):",
     "        if False:"),

    ("...and the reverse: a HOME that cannot hold the config is never named", BOX,
     "        if not any(w in (out or \"\") for w in self._HOME_WRITE_FAILURES):",
     "        if True:"),

    ("the refused box is left running", BOX,
     '            _host(["docker", "rm", "-f", cname])\n'
     "            shutil.rmtree(host_clone, ignore_errors=True)\n",
     "            shutil.rmtree(host_clone, ignore_errors=True)\n"),

    ("_commit swallows every exit again with `|| true`", MACHINE,
     'command=f"{strip_workflows}git add -A && {author}git commit -m {msg}",',
     'command=f"{strip_workflows}git add -A && {author}git commit -m {msg} || true",'),

    ("every exit 1 is nothing to commit, staged changes or not", MACHINE,
     "            if staged_rc == 0:",
     "            if True:"),

    ("the staged read is inverted - staged work is quiet, nothing staged fails", MACHINE,
     "            if staged_rc == 0:",
     "            if staged_rc != 0:"),

    ("the read is the tree's status again, not what is staged - a dirty submodule fails the job",
     MACHINE,
     '            staged_rc, _ = self.sandbox.run(\n'
     '                workspace=ws, command="git diff --cached --quiet", timeout=60)\n'
     "            if staged_rc == 0:",
     '            status_rc, status = self.sandbox.run(\n'
     '                workspace=ws, command="git status --porcelain", timeout=60)\n'
     '            if status_rc == 0 and not (status or "").strip():'),

    ("the failure drops git's words", MACHINE,
     'f"git refused to commit the job\'s work in the box (exit {rc}: {words}), so nothing "',
     'f"git refused to commit the job\'s work in the box (exit {rc}), so nothing "'),
]
