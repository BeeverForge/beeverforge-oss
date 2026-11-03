"""#117, proven by breaking it — a `git rev-parse` that times out in `mark_as_job` lets the job start.

Run:  .venv/bin/python tools/mutate.py tools/mutations/117_a_rev_parse_that_times_out_lets_the_job_start.py

THE CLAIM: `mark_as_job` raises `OSError` when `git rev-parse --absolute-git-dir` times out (a
`SubprocessError`), so `prepare` says the marker was not written and the job still starts.

The guard is real git: a real repository and the real `WorktreeSandbox.prepare`, with
`subprocess.run` patched to raise `TimeoutExpired` at once for that one command.
"""

TEST = "tests/test_a_rev_parse_that_times_out_does_not_fail_the_job.py"

MARKS = "beeverforge/adapters/gitworktrees.py"

MUTATIONS = [
    ("M1 THE DEFECT ITSELF: the catch narrowed, so `TimeoutExpired` escapes `prepare`", MARKS,
     "    except subprocess.SubprocessError as exc:\n"
     "        # a hung git raises",
     "    except subprocess.CalledProcessError as exc:\n"
     "        # a hung git raises"),
    ("M2 the timeout re-raised as something that is not an `OSError`", MARKS,
     '        raise OSError(f"git did not name the admin directory of {worktree}: {exc}") from exc\n',
     '        raise RuntimeError(f"git did not name the admin directory of {worktree}: {exc}") '
     'from exc\n'),
]
