"""#276: a rebase before merge runs as the bot, and only an unmerged path is a conflict."""

TEST = "tests/test_a_rebase_before_merge_runs_as_the_bot_and_names_its_failure.py"
SRC = "beeverforge/adapters/sandbox/worktree.py"
MACHINE = "beeverforge/orchestrator/machine.py"
HOLD = "tests/test_walking_skeleton.py"

MUTATIONS = [
    ("the rebase runs with the host's own identity again", SRC,
     'rc, out = _run(["git", "-C", wp, "rebase", "FETCH_HEAD"], env=as_the_bot)',
     'rc, out = _run(["git", "-C", wp, "rebase", "FETCH_HEAD"])'),

    ("the bot is only the author, so the committer is still nobody", SRC,
     '"GIT_AUTHOR_NAME": bot.name, "GIT_AUTHOR_EMAIL": bot.email,\n'
     '                      "GIT_COMMITTER_NAME": bot.name, "GIT_COMMITTER_EMAIL": bot.email}',
     '"GIT_AUTHOR_NAME": bot.name, "GIT_AUTHOR_EMAIL": bot.email}'),

    ("any failed rebase is a conflict again", SRC,
     'if unmerged_rc == 0 and unmerged.strip():\n                return "conflict"',
     'if True:\n                return "conflict"'),

    ("a real conflict is reported as a failure", SRC,
     'if unmerged_rc == 0 and unmerged.strip():',
     'if False:'),

    ("the failure is reported without git's sentence", SRC,
     'raise RuntimeError(f"rebase failed: {_redact(out)}")',
     'raise RuntimeError("rebase failed")'),

    ("the failure is reported unredacted", SRC,
     'raise RuntimeError(f"rebase failed: {_redact(out)}")',
     'raise RuntimeError(f"rebase failed: {out}")'),

    ("the machine lets the failure crash the job instead of parking it", MACHINE,
     'except RuntimeError as exc:  # git\'s own sentence, redacted by the box (#276)',
     'except KeyError as exc:  # git\'s own sentence, redacted by the box (#276)', HOLD),

    ("the park calls it a conflict", MACHINE,
     'f"could not rebase: {exc}"',
     'f"PR {pr} conflicts with {base} and cannot be auto-rebased: {exc}"', HOLD),
]
