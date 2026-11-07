"""`env context --ask` asks in a copy of the checkout, never in the checkout itself (#167).

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/167_env_context_ask_asks_in_a_copy_of_the_checkout.py

Row 1 is the defect as it shipped: the question is asked in the person's checkout. Rows 2-3 leave the
copy behind: after an answer, and only after a failure. Rows 4-6 change what the copy holds: what
git ignores, no untracked file, and a `.git` copied where the checkout is no working tree. Row 7
copies a link that leaves the checkout. Rows 8-11 stop saying what went wrong in a sentence: no git
installed, git too slow, a checkout over the size bound, a file that cannot be read. Row 12 asks a
harness that cannot judge before saying so.
"""

TEST = "tests/test_env_context_ask_asks_in_a_copy_of_the_checkout.py"

CATALOG = "beeverforge/actions/catalog.py"

MUTATIONS = [
    ("TODAY'S DEFECT: the question is asked in the person's own checkout", CATALOG,
     '            room = _copy_into(checkout, names, Path(tmp) / (checkout.name or "checkout"))\n',
     "            room = checkout\n"),

    ("the copy is left behind after the question is answered", CATALOG,
     '        with tempfile.TemporaryDirectory(prefix="beeverforge-ask-") as tmp:\n',
     '        for tmp in [tempfile.mkdtemp(prefix="beeverforge-ask-")]:\n'),

    ("the copy is removed after an answer and left behind after a failure", CATALOG,
     '        with tempfile.TemporaryDirectory(prefix="beeverforge-ask-") as tmp:\n'
     '            room = _copy_into(checkout, names, Path(tmp) / (checkout.name or "checkout"))\n'
     "            return ctx.agent_ask(\n"
     "                asker,\n"
     "                sandbox=judging_worktree(project, root=room),\n"
     '                workspace=Workspace(path=str(room), branch="main", base_branch="main"))(prompt)\n',
     '        tmp = tempfile.mkdtemp(prefix="beeverforge-ask-")\n'
     '        room = _copy_into(checkout, names, Path(tmp) / (checkout.name or "checkout"))\n'
     "        answer = ctx.agent_ask(\n"
     "            asker,\n"
     "            sandbox=judging_worktree(project, root=room),\n"
     '            workspace=Workspace(path=str(room), branch="main", base_branch="main"))(prompt)\n'
     "        __import__(\"shutil\").rmtree(tmp)\n"
     "        return answer\n"),

    ("what git ignores is copied", CATALOG,
     '             "--exclude-standard"], capture_output=True, check=False, timeout=60)\n',
     '             "--exclude=__never__"], capture_output=True, check=False, timeout=60)\n'),

    ("an untracked file is not copied", CATALOG,
     '            ["git", "-C", str(checkout), "ls-files", "-z", "--cached", "--others",\n',
     '            ["git", "-C", str(checkout), "ls-files", "-z", "--cached",\n'),

    ("a checkout that is no working tree is copied with its .git", CATALOG,
     '            dirs[:] = sorted(d for d in dirs if d != ".git")\n',
     "            dirs[:] = sorted(dirs)\n"),

    ("a link that leaves the checkout is copied", CATALOG,
     "            if os.path.isabs(pointed) or not lands.is_relative_to(root):\n",
     "            if False:\n"),

    ("a machine with no git is refused with a traceback", CATALOG,
     "    except FileNotFoundError:\n"
     "        listed = None                    # no git on this machine: the whole tree, as for a "
     "folder\n",
     "    except FileNotFoundError:\n"
     "        raise\n"),

    ("git too slow reaches the person as a traceback", CATALOG,
     "    except subprocess.TimeoutExpired as exc:\n        raise ValueError(\n",
     "    except subprocess.TimeoutExpired as exc:\n        raise\n        raise ValueError(\n"),

    ("a checkout of any size is copied", CATALOG,
     "    if size > _ASK_COPY_LIMIT:\n",
     "    if False:\n"),

    ("a file that cannot be read reaches the person as a traceback", CATALOG,
     "        except OSError as exc:\n            raise RuntimeError(\n",
     "        except OSError as exc:\n            raise\n            raise RuntimeError(\n"),

    ("a harness that cannot judge is said only when it is asked", CATALOG,
     "    ctx.agent_ask(asker, sandbox=None, workspace=None)\n",
     ""),
]
