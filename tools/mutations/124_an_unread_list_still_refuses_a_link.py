"""#124, proven by breaking it — on an unread working-tree list, a symbolic link or a regular file
at the box's path is still refused by name before anything is written, and a directory still goes
to git.

TWO CLAIMS:

  1. **A link or a file at the path is refused whether or not the list was read** (`prepare`,
     the `taken = _what_is_at(wt)` line): neither check depends on the list, and unread, git used
     to check the card out through a link to an empty directory.
  2. **Only the directory checks wait for the list**: unread, a directory at the path is left to
     git, which refuses it as before (`worktree add failed`), and a forgotten tree is kept.

The guards are real git with real linked worktrees, with `_working_trees` answering `None`.
"""

TEST = "tests/test_an_unread_worktree_list_still_refuses_a_symlink_or_file_at_the_box_s_path.py"

BOX = "beeverforge/adapters/sandbox/worktree.py"
FORGOTTEN = ("tests/test_a_rerun_over_a_tree_git_has_forgotten_starts.py::"
             "test_a_forgotten_tree_is_kept_when_the_working_tree_list_cannot_be_read")

MUTATIONS = [
    # ── claim 1: a link or a file is refused on an unread list ──────────────────────────────────
    ("THE DEFECT ITSELF: on an unread list nothing at the path is asked, a link or a file "
     "included", BOX,
     "        taken = _what_is_at(wt)\n",
     "        taken = _what_is_at(wt) if trees is not None else None\n"),

    ("only a link is refused on an unread list, and a file goes to git after `branch -D`", BOX,
     '        if trees is None and taken is not None and taken[0] not in ("symlink", "file"):\n',
     '        if trees is None and taken is not None and taken[0] not in ("symlink",):\n'),

    # ── claim 2: only the directory checks wait for the list ────────────────────────────────────
    ("every kind is refused on an unread list, a directory git would judge included", BOX,
     '        if trees is None and taken is not None and taken[0] not in ("symlink", "file"):\n',
     '        if False:\n'),

    ("every kind is refused on an unread list, so a forgotten tree is named, not kept for git",
     BOX,
     '        if trees is None and taken is not None and taken[0] not in ("symlink", "file"):\n',
     '        if False:\n',
     FORGOTTEN),
]
