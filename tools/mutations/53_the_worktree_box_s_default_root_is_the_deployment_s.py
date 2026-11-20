"""The worktree box's default root is the deployment's, not the directory the process started in.

Run:
    .venv/bin/python tools/mutate.py \
      tools/mutations/53_the_worktree_box_s_default_root_is_the_deployment_s.py

`_worktree` in the sandbox registry builds a box with no `root` (as `box prove` and `doctor` do)
under `default_root() / ".beeverforge-worktrees"`: beside the repository cache, the root a job's
box gets from `factory.py`, asked when the box is built. A given `root` is used as given. Each row
breaks one of those and the guard must go red.
"""

TEST = "tests/test_the_worktree_box_s_default_root_is_the_deployment_s.py"

REGISTRY = "beeverforge/adapters/sandbox/registry.py"

MUTATIONS = [
    ("the default is back on the directory the command started in", REGISTRY,
     '        root = default_root() / ".beeverforge-worktrees"\n',
     '        root = Path.cwd() / ".beeverforge-worktrees"\n'),

    # The module still imports: the frozen value is the expression `default_root()` answers,
    # computed once when the registry is imported, with no new import that could cycle.
    ("the cache is read once at import, so a changed BEEVERFORGE_REPO_CACHE is ignored", REGISTRY,
     'def _worktree(**kw):\n'
     '    from beeverforge.adapters.sandbox import WorktreeSandbox\n\n'
     '    root = kw.get("root")\n'
     '    if not root:\n',
     '_IMPORT_TIME_ROOT = Path(__import__("os").environ.get("BEEVERFORGE_REPO_CACHE")\n'
     '                         or "/tmp/beeverforge-repo-cache") / ".beeverforge-worktrees"\n\n\n'
     'def _worktree(**kw):\n'
     '    from beeverforge.adapters.sandbox import WorktreeSandbox\n\n'
     '    root = kw.get("root") or _IMPORT_TIME_ROOT\n'
     '    if not root:\n'),

    ("the subdirectory is renamed, so a proof's tree is not where a job looks", REGISTRY,
     '        root = default_root() / ".beeverforge-worktrees"\n',
     '        root = default_root() / ".beeverforge-trees"\n'),

    ("a given root is ignored", REGISTRY,
     '    root = kw.get("root")\n    if not root:\n',
     '    root = kw.get("root")\n    if True:\n'),
]
