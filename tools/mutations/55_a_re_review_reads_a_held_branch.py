"""#55, proven by breaking it — a re-review reads the tip of a branch a person has out elsewhere.

THE CLAIMS:

  1. **The worktree box checks the branch's tip out detached** (`prepare_tip`), on the local forge
     and on a hosted one, asking no holder, and the hosted read is the forge's tip, not the base.
  2. **Nothing of the person's is written**: not their branch, not on a failed forge read either.
  3. **The re-review reads that checkout and publishes, with no hold and no `publish_branch`**,
     and a box without `prepare_tip` still holds through `prepare`'s refusal.

The guards are real git in `tmp_path`, and the real machine with the worktree box.
"""

TEST = "tests/test_a_re_review_reads_a_branch_checked_out_elsewhere.py"

BOX = "beeverforge/adapters/sandbox/worktree.py"
MACHINE = "beeverforge/orchestrator/machine.py"

MUTATIONS = [
    ("`review_pr` ignores the capability and goes through `prepare`, which holds", MACHINE,
     '        checkout = getattr(self.sandbox, "prepare_tip", None)\n',
     "        checkout = None\n"),

    ("the tip's add checks the branch out instead of its tip, which git refuses while it is held",
     BOX,
     '        rc, said = _run(["git", "-C", str(repo_path), "worktree", "add", "--detach", '
     'str(tip),\n'
     "                         start], env=_in_gits_own_words())\n",
     '        rc, said = _run(["git", "-C", str(repo_path), "worktree", "add", str(tip),\n'
     "                         branch], env=_in_gits_own_words())\n"),

    ("the tip asks who holds the branch and refuses, as the doors that commit do", BOX,
     "        trees = self._clear_our_own(repo_path, tip)\n",
     "        trees = self._clear_our_own(repo_path, tip)\n"
     "        held = _holder(repo_path, branch)\n"
     "        if held is not None:\n"
     "            raise _branch_held_elsewhere(branch, held, repo_path=repo_path, rebuilt=False,\n"
     "                                         ours=tip)\n"),

    ("the re-review publishes the branch after it republishes its verdict", MACHINE,
     "            self._republish_review(pr_url, review=review)\n",
     "            self._republish_review(pr_url, review=review)\n"
     "            self.sandbox.publish_branch(workspace=ws, "
     "remote_url=self.forge.push_remote())\n"),

    ("a failed forge read on the tip deletes the person's branch on the way out", BOX,
     "                remote_url=remote_url, from_base=False, drop_branch=False)\n",
     "                remote_url=remote_url, from_base=False, drop_branch=True)\n"),

    ("on a hosted forge the review reads the base instead of the pull request's tip", BOX,
     # Re-pinned for the transport wrapper added after PR #283 met the new review door.
     '                                         f"+{branch}:refs/remotes/origin/{branch}"]), '
     'timeout=180)\n'
     "            if rc == 0:\n"
     '                start = f"origin/{branch}"\n',
     '                                         f"+{branch}:refs/remotes/origin/{branch}"]), '
     'timeout=180)\n'
     "            if rc == 0:\n"
     "                start = base_branch\n"),

    ("on the local forge the review reads the base instead of the branch", BOX,
     '                start = f"refs/heads/{branch}"\n',
     "                pass\n"),

    ("a box without `prepare_tip` lets `prepare`'s refusal escape instead of holding", MACHINE,
     "        except BranchHeldElsewhere as exc:\n"
     "            # A PERSON HAS THE BRANCH OUT (#623): nothing was read",
     "        except ZeroDivisionError as exc:\n"
     "            # A PERSON HAS THE BRANCH OUT (#623): nothing was read"),
]
