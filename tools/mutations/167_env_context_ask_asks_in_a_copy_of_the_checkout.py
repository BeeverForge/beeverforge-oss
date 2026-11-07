"""`env context --ask` asks in a copy of the checkout, never in the checkout itself (#167).

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/167_env_context_ask_asks_in_a_copy_of_the_checkout.py

Row 1 is the defect as it shipped: the question is asked in the person's checkout. Row 2 leaves the
copy behind. Rows 3-5 change what the copy holds: what git ignores, no untracked file, and a `.git`
copied where the checkout is no working tree. Row 6 asks a harness that cannot judge before saying
so.
"""

TEST = "tests/test_env_context_ask_asks_in_a_copy_of_the_checkout.py"

CATALOG = "beeverforge/actions/catalog.py"

MUTATIONS = [
    ("TODAY'S DEFECT: the question is asked in the person's own checkout", CATALOG,
     '            room = _a_copy_of(checkout, Path(tmp) / (checkout.name or "checkout"))\n',
     "            room = checkout\n"),

    ("the copy is left behind after the question is answered", CATALOG,
     '        with tempfile.TemporaryDirectory(prefix="beeverforge-ask-") as tmp:\n',
     '        for tmp in [tempfile.mkdtemp(prefix="beeverforge-ask-")]:\n'),

    ("what git ignores is copied", CATALOG,
     '         "--exclude-standard"], capture_output=True, check=False, timeout=60)\n',
     '         "--exclude=__never__"], capture_output=True, check=False, timeout=60)\n'),

    ("an untracked file is not copied", CATALOG,
     '        ["git", "-C", str(checkout), "ls-files", "-z", "--cached", "--others",\n',
     '        ["git", "-C", str(checkout), "ls-files", "-z", "--cached",\n'),

    ("a checkout that is no working tree is copied with its .git", CATALOG,
     '        shutil.copytree(checkout, room, symlinks=True, ignore=shutil.ignore_patterns(".git"))\n',
     "        shutil.copytree(checkout, room, symlinks=True)\n"),

    ("a harness that cannot judge is said only when it is asked", CATALOG,
     "    ctx.agent_ask(asker, sandbox=None, workspace=None)\n",
     ""),
]
