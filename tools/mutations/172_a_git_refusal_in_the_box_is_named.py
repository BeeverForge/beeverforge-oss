"""#172: a git refusal in the box is named, not swallowed.

Two guards: `ContainerSandbox.prepare` checks its `safe.directory` write, and `JobRunner._commit`
tells "nothing to commit" (exit 1, clean tree) from a refusal by exit code. The reverses matter:
a check that always fires refuses every good box, and one that never reads the tree again turns
every exit 1 into silence.
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

    ("the refused box is left running", BOX,
     '            _host(["docker", "rm", "-f", cname])\n'
     "            shutil.rmtree(host_clone, ignore_errors=True)\n",
     "            shutil.rmtree(host_clone, ignore_errors=True)\n"),

    ("_commit swallows every exit again with `|| true`", MACHINE,
     'command=f"{strip_workflows}git add -A && {author}git commit -m {msg}",',
     'command=f"{strip_workflows}git add -A && {author}git commit -m {msg} || true",'),

    ("every exit 1 is nothing to commit, dirty tree or not", MACHINE,
     "            if status_rc == 0 and not (status or \"\").strip():",
     "            if True:"),

    ("the clean-tree read is inverted - a dirty tree is quiet, a clean one fails", MACHINE,
     "            if status_rc == 0 and not (status or \"\").strip():",
     "            if status_rc == 0 and (status or \"\").strip():"),

    ("the failure drops git's words", MACHINE,
     'f"git refused to commit the job\'s work in the box (exit {rc}: {words}), so nothing "',
     'f"git refused to commit the job\'s work in the box (exit {rc}), so nothing "'),
]
