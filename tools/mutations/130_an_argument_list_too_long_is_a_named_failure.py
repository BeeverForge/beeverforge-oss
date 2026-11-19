"""An argument list too long is a named failure of the GitHub tracker, not a raw `OSError` (#130).

Run:  .venv/bin/python tools/mutate.py tools/mutations/130_an_argument_list_too_long_is_a_named_failure.py

`subprocess.run` raises `OSError: [Errno 7] Argument list too long: 'gh'` before `gh` starts when
one argv element is over `MAX_ARG_STRLEN` (131,072 bytes). `_gh` caught only `FileNotFoundError`,
so `comment`'s `--body` and `close_ticket`'s `--comment` could still end in a traceback.

Row 1 is the defect as it shipped: no catch on the first run. Row 2 catches the wrong errno. Row 3
drops the log marker. Row 4 drops the remedy from the sentence. Row 5 removes the catch on the
secondary-rate-limit retry. Row 6 re-raises instead of answering as `refused()` does. Row 7
gives `gh issue close` the comment's remedy, `--body-file -`, a flag `gh issue close` does not have.

RE-PINNED (#127): the answer itself, `argv_too_long`, moved from the tracker to
`beeverforge/adapters/github_cli.py` so the GitHub forge answers an E2BIG with the same function.
Rows 2, 3, 4, 6 and 7 cut the same lines there, with the same meaning; rows 1 and 5, the tracker's
two `except OSError` branches, stay on the tracker.
"""

TEST = "tests/test_an_argument_list_too_long_is_a_named_failure.py"

GH = "beeverforge/adapters/tracker/github.py"
CLI = "beeverforge/adapters/github_cli.py"

MUTATIONS = [
    ("THE DEFECT: the first run catches only FileNotFoundError", GH,
     '                "BEEVERFORGE_BOT_TOKEN / the GitHub App variables).") from None\n'
     '        except OSError as exc:\n'
     '            return argv_too_long(args, exc, log)\n',
     '                "BEEVERFORGE_BOT_TOKEN / the GitHub App variables).") from None\n'),

    ("the wrong errno is taken for E2BIG", CLI,
     "    if exc.errno != errno.E2BIG:\n",
     "    if exc.errno != errno.ENOENT:\n"),

    ("the bound is not logged when hit", CLI,
     '    log.warning("BEEVERFORGE_GH_ARGV_TOO_LONG %s: an argument over %s bytes (MAX_ARG_STRLEN)",\n'
     '                command, f"{MAX_ARG_STRLEN:,}")\n',
     ""),

    ("the sentence names the cause but not the remedy", CLI,
     '"so the text must go to `gh` on stdin with `--body-file -`"',
     '"so the text must go somewhere else"'),

    ("the close is given the comment's remedy, naming a flag `gh issue close` lacks", CLI,
     '    if args[:2] == ["issue", "close"]:\n',
     '    if args[:2] == ["issue", "closed"]:\n'),

    ("the rate-limit retry is not caught", GH,
     '            env=self._env(),\n'
     '            )\n'
     '        except OSError as exc:\n'
     '            return argv_too_long(args, exc, log)\n'
     '        return p\n',
     '            env=self._env(),\n'
     '            )\n'
     '        except ValueError as exc:\n'
     '            return argv_too_long(args, exc, log)\n'
     '        return p\n'),

    ("an E2BIG is re-raised instead of answered as a failed call", CLI,
     '                command, f"{MAX_ARG_STRLEN:,}")\n'
     "    return refused(args, why)\n",
     '                command, f"{MAX_ARG_STRLEN:,}")\n'
     "    raise exc\n"),
]
