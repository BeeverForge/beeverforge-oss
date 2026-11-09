"""#91, proven by breaking it — a worktree the box adds while a sync stages keeps its `.git`.

Run:  .venv/bin/python tools/mutate.py tools/mutations/91_a_worktree_added_while_a_sync_stages_keeps_its_git.py

THE CLAIMS, each held by a row:
  1. **`prepare` adds and marks under the cache key's lock** on a served checkout, so a publish
     that staged its snapshot ends before the add, and the worktree lands in the new tree.
  2. **`_publish` asks for the job marks again just before the rename**, so an add the lock let
     through (the sync's own thread) keeps the tree it stands on.
  3. **`prepare_tip` takes the same lock** around its fetch, add and mark.
  4. **A repository registered by path takes no lock** and leaves nothing beside it.
  5. **A lock held past the wait refuses the add by name**, never runs it unlocked.
  6. **One sync says an expired hold once**, though it asks for the marks twice.

The guards are real git: the real `RepoCache` over a local bare origin and the real
`WorktreeSandbox`, with the interleave placed by a patched `copytree`, never by a clock.
"""

TEST = "tests/test_a_worktree_the_box_adds_while_a_sync_stages_keeps_its_git.py"

BOX = "beeverforge/adapters/sandbox/worktree.py"
CACHE = "beeverforge/runtime/repo_cache.py"

MUTATIONS = [
    ("M1 prepare adds and marks without the cache key's lock", BOX,
     "        with _cache_key_held(repo_path):\n            mark = _write_mark(repo_path, wt)\n",
     "        if True:\n            mark = _write_mark(repo_path, wt)\n",
     f"{TEST}::test_a_worktree_added_while_the_snapshot_is_staged_keeps_its_git_and_its_push"),
    ("M2 _publish no longer asks for the job marks again before the rename", CACHE,
     "            if RepoCache._held_by_a_job(served, \"a newer snapshot was staged to replace it\",\n"
     "                                     again=True):\n",
     "            if False:\n",
     f"{TEST}::test_a_worktree_added_just_before_the_rename_keeps_its_git_and_its_push"),
    ("M3 prepare_tip fetches, adds and marks without the cache key's lock", BOX,
     "        with _cache_key_held(repo_path):\n            start = base_branch\n",
     "        if True:\n            start = base_branch\n",
     f"{TEST}::test_a_review_tree_added_while_the_snapshot_is_staged_keeps_its_git"),
    ("M4 every repository is taken for a cache checkout and asked for a lock", BOX,
     "    except (FileNotFoundError, NotADirectoryError):\n        yield\n        return\n",
     "    except (FileNotFoundError, NotADirectoryError):\n        pass\n",
     f"{TEST}::test_a_repository_registered_by_path_takes_no_cache_lock"),
    ("M5 a lock held past the wait lets the add run unlocked instead of refusing it", BOX,
     "        raise refusal from exc\n",
     "        yield\n        return\n",
     f"{TEST}::test_a_cache_key_held_past_the_wait_refuses_the_add_and_says_why"),
    ("M6 the re-check before the rename says each expired hold a second time", CACHE,
     "        if again:\n",
     "        if False:\n",
     "tests/test_a_crashed_jobs_marker_stops_holding_the_cache_after_a_day.py"),
    ("M7 a lock that cannot be checked is taken for no lock, and the add runs unlocked", BOX,
     "    except (FileNotFoundError, NotADirectoryError):\n        yield\n",
     "    except OSError:\n        yield\n",
     f"{TEST}::test_a_lock_that_cannot_be_checked_refuses_the_add_rather_than_run_it_unlocked"),
]
