"""#317: the measurement checkout's fixed path is looked at before git is asked to change it.

The dangerous reverse is the first cut: a symbolic link at the path reaches `worktree remove` and
`worktree add`, which remove or check out into the tree the link names. The others: a file at the
path reaching git, the sentence naming the wrong thing, the path's own stale registration left so
a wiped cache cannot be measured again, an emptied leftover's registration left after its rmtree,
the blanket `worktree prune` coming back, and the window between the check and the add: a link or
file planted there, a create that follows a link, and the failed add's cleanup.
"""

TEST = "tests/test_a_proof_checkout_refuses_what_is_not_its_own_at_its_path.py"
FACTORY = "beeverforge/factory.py"

MUTATIONS = [
    ("a symbolic link at the checkout path reaches git, which works through it", FACTORY,
     "    if dest.is_symlink() or (dest.exists() and not dest.is_dir()):",
     "    if dest.exists() and not dest.is_dir():"),

    ("a file at the checkout path reaches git instead of a sentence", FACTORY,
     "    if dest.is_symlink() or (dest.exists() and not dest.is_dir()):",
     "    if dest.is_symlink():"),

    ("the refusal calls a file a symbolic link", FACTORY,
     '        there = "a symbolic link" if dest.is_symlink() else "a file"',
     '        there = "a symbolic link"'),

    ("the refusal calls a symbolic link a file", FACTORY,
     '        there = "a symbolic link" if dest.is_symlink() else "a file"',
     '        there = "a file"'),

    ("the refusal stops saying nothing was changed", FACTORY,
     '            f"Nothing was changed"\n        )\n    if dest.exists():',
     '            f""\n        )\n    if dest.exists():'),

    ("a wiped checkout's registration is left, so it cannot be measured again", FACTORY,
     '    else:\n'
     '        # The directory is gone but git may still list it',
     '    elif False:\n'
     '        # The directory is gone but git may still list it'),

    ("an emptied leftover's registration outlives its rmtree, so `add` fails with git's words",
     FACTORY,
     "        # Now the directory is gone, this path's own `remove` drops it (the `else` branch's "
     "clear).\n"
     '        _git(["-C", str(repo), "worktree", "remove", "--force", str(dest)])',
     "        # Now the directory is gone, this path's own `remove` drops it (the `else` branch's "
     "clear).\n"
     "        pass"),

    ("the blanket prune comes back and drops other people's registrations", FACTORY,
     '        # momentarily missing, other people\'s included (see adapters/sandbox/worktree.py).\n'
     '        _git(["-C", str(repo), "worktree", "remove", "--force", str(dest)])',
     '        # momentarily missing, other people\'s included (see adapters/sandbox/worktree.py).\n'
     '        _git(["-C", str(repo), "worktree", "prune"])'),
    # THE WINDOW between the guard and the add (the shape #124 / PR #312 settled).
    ("the path is not made before the add, so a link planted after the check is written through",
     FACTORY,
     "        os.mkdir(dest)\n    except FileExistsError:",
     "        pass\n    except FileExistsError:"),

    ("what appeared at the path after the check is swallowed and handed to git", FACTORY,
     "        raise RuntimeError(_appeared_at(dest, ref)) from None",
     "        pass"),

    ("a following create calls a link to a directory fine and git checks out through it", FACTORY,
     "        os.mkdir(dest)\n    except FileExistsError:",
     "        os.makedirs(dest, exist_ok=True)\n    except FileExistsError:"),

    ("a path that cannot be made reaches git instead of a sentence naming the cause", FACTORY,
     "    except OSError as exc:\n        raise RuntimeError(\n            f\"could not make {dest}",
     "    except FileNotFoundError as exc:\n        raise RuntimeError(\n            f\"could not make {dest}"),

    ("a failed add leaves the empty directory it made, blocking the rerun", FACTORY,
     "            os.rmdir(dest)\n        except OSError:",
     "            pass\n        except OSError:"),

    ("a failed add's cleanup is recursive and takes what is inside with it", FACTORY,
     "            os.rmdir(dest)\n        except OSError:",
     "            shutil.rmtree(dest)\n        except OSError:"),

    ("a failed add's cleanup unlinks whatever is at the path, a link included", FACTORY,
     "            os.rmdir(dest)\n        except OSError:",
     "            os.unlink(dest) if dest.is_symlink() else os.rmdir(dest)\n        except OSError:"),

    ("a leftover rmtree could not remove goes on to git with no word", FACTORY,
     "        if dest.exists() or dest.is_symlink():\n            # `ignore_errors=True`",
     "        if False:\n            # `ignore_errors=True`"),

    ("what stands at the path is read through a link and called a directory", FACTORY,
     "        mode = os.lstat(path).st_mode",
     "        mode = os.stat(path).st_mode"),
]
