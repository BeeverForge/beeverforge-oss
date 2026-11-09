"""#368, proven by breaking it — a `git diff --name-only` git refused is not a change with no paths.

`_pr_diff_paths` answered a failed read with `[]`, and both callers read that as "nothing reached
the verifier": the CI-repair pass left an armed auto-merge standing on a push nobody checked, and
the knowledge gate judged an empty change. Git's words reached nobody.

ROWS 1-3 ARE THE DEFECT AND ITS HALF-FIXES: the fallback itself, and a refusal that is raised but
loses git's words or its exit code on the way to the person. ROWS 4-5 ARE THE CALLERS dropping it:
the CI-repair disarm not reading it, and the knowledge gate cutting the sentence (and its remedy) at
120 characters in the generic handler. ROW 6 CUTS THE OTHER WAY: an empty diff git answered with
exit 0 read as a failure, which would hold every repair that changed nothing.
"""

TEST = "tests/test_a_diff_git_refused_is_not_a_change_with_no_paths.py"

MACHINE = "beeverforge/orchestrator/machine.py"

MUTATIONS = [
    ("THE DEFECT ITSELF: a diff git refused falls back to `[]`, read as no paths changed", MACHINE,
     "        if rc != 0:\n            raise DiffPathsUnread(rc, out)\n",
     "        if rc != 0:\n            return []\n"),

    ("git's words are dropped from the refusal, so the person is told it failed but not why",
     MACHINE,
     '            + (f": {self.words}" if self.words else "")\n',
     '            + ""\n'),

    ("git's exit code is dropped from the refusal", MACHINE,
     '            f"`git diff --name-only` exited {rc} in the box"\n',
     '            "`git diff --name-only` failed in the box"\n'),

    ("the CI-repair disarm stops reading the refusal, so the armed auto-merge stands on a push "
     "whose paths nobody checked", MACHINE,
     "            if supp or hits or unread or unreadable or lost_tests:",
     "            if supp or hits or unreadable or lost_tests:"),

    ("the knowledge gate's own handler is gone, so the generic one cuts the sentence at 120 "
     "characters and the remedy never reaches the person", MACHINE,
     "        except DiffPathsUnread as exc:\n"
     "            # WHOLE, NOT CUT AT 120 CHARACTERS",
     "        except ZeroDivisionError as exc:\n"
     "            # WHOLE, NOT CUT AT 120 CHARACTERS"),

    ("THE REVERSE CUT: an empty diff git answered with exit 0 is read as a failure", MACHINE,
     "        if rc != 0:\n            raise DiffPathsUnread(rc, out)\n",
     "        if rc != 0 or not out.strip():\n            raise DiffPathsUnread(rc, out)\n"),
]
