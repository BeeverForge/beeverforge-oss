"""#317: the measurement checkout's fixed path is looked at before git is asked to change it.

The dangerous reverse is the first cut: a symbolic link at the path reaches `worktree remove` and
`worktree add`, which remove or check out into the tree the link names. The others: a file at the
path reaching git, the sentence naming the wrong thing, the path's own stale registration left so
a wiped cache cannot be measured again, and the blanket `worktree prune` coming back.
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

    ("the blanket prune comes back and drops other people's registrations", FACTORY,
     '        # momentarily missing, other people\'s included (see adapters/sandbox/worktree.py).\n'
     '        _git(["-C", str(repo), "worktree", "remove", "--force", str(dest)])',
     '        # momentarily missing, other people\'s included (see adapters/sandbox/worktree.py).\n'
     '        _git(["-C", str(repo), "worktree", "prune"])'),
]
