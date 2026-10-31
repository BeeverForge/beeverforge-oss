"""#115, proven by breaking it — a relative `gitdir` under a symlinked cache root holds the job.

Run:  .venv/bin/python tools/mutate.py tools/mutations/115_a_relative_gitdir_under_a_symlinked_root_holds_the_job.py

THE CLAIMS, each held by a row:
  1. **A relative `gitdir` is asked of the filesystem as written**, so the kernel follows the
     cache root's symlink before it applies `..`; normalised as text, it names a directory that
     does not exist, the mark reads as gone and the sync swaps the job's tree.
  2. **The mark names the worktree by its resolved path**, not by the admin directory's spelling
     with `..` in it.

The guards are real git: the real `RepoCache` over a local origin and the real
`WorktreeSandbox.prepare`, with the `gitdir` written relative by git 2.48+ or, on every git, by
hand as git computes it.
"""

TEST = "tests/test_a_relative_gitdir_under_a_symlinked_cache_root_holds_the_job.py"

MARKS = "beeverforge/adapters/gitworktrees.py"

MUTATIONS = [
    ("M1 THE DEFECT ITSELF: the gitdir is normalised as text, the `..` applied to the symlink's "
     "spelling, and the sync swaps the tree under the job", MARKS,
     "            where = admin / gitdir  #",
     "            where = Path(os.path.normpath(admin / gitdir))  #"),
    ("M2 the existence check alone goes back to the lexical path", MARKS,
     "            if not where.exists():\n                continue\n",
     "            if not Path(os.path.normpath(where)).exists():\n                continue\n"),
    ("M3 the worktree is named from the unresolved path", MARKS,
     "            mark = JobMark(worktree=str(where.resolve().parent),",
     "            mark = JobMark(worktree=str(where.parent),"),
]
