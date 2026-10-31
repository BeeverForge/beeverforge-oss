"""An argument list too long is a named failure of the GitHub tracker, not a raw `OSError` (#130).

Run:  .venv/bin/python tools/mutate.py tools/mutations/130_an_argument_list_too_long_is_a_named_failure.py

`subprocess.run` raises `OSError: [Errno 7] Argument list too long: 'gh'` before `gh` starts when
one argv element is over `MAX_ARG_STRLEN` (131,072 bytes). `_gh` caught only `FileNotFoundError`,
so `comment`'s `--body` and `close_ticket`'s `--comment` could still end in a traceback.

Row 1 is the defect as it shipped: no catch on the first run. Row 2 catches the wrong errno. Row 3
drops the log marker. Row 4 drops the remedy from the sentence. Row 5 removes the catch on the
secondary-rate-limit retry. Row 6 re-raises instead of answering as `refused()` does.
"""

TEST = "tests/test_an_argument_list_too_long_is_a_named_failure.py"

GH = "beeverforge/adapters/tracker/github.py"

MUTATIONS = [
    ("THE DEFECT: the first run catches only FileNotFoundError", GH,
     '                "BEEVERFORGE_BOT_TOKEN / the GitHub App variables).") from None\n'
     '        except OSError as exc:\n'
     '            return _argv_too_long(args, exc)\n',
     '                "BEEVERFORGE_BOT_TOKEN / the GitHub App variables).") from None\n'),

    ("the wrong errno is taken for E2BIG", GH,
     "    if exc.errno != errno.E2BIG:\n",
     "    if exc.errno != errno.ENOENT:\n"),

    ("the bound is not logged when hit", GH,
     '    log.warning("BEEVERFORGE_GH_ARGV_TOO_LONG %s: an argument over %s bytes (MAX_ARG_STRLEN)",\n'
     '                command, f"{MAX_ARG_STRLEN:,}")\n',
     ""),

    ("the sentence names the cause but not the remedy", GH,
     '"with `--body-file -`.")',
     '"somehow.")'),

    ("the rate-limit retry is not caught", GH,
     '            env=self._env(),\n'
     '            )\n'
     '        except OSError as exc:\n'
     '            return _argv_too_long(args, exc)\n'
     '        return p\n',
     '            env=self._env(),\n'
     '            )\n'
     '        except ValueError as exc:\n'
     '            return _argv_too_long(args, exc)\n'
     '        return p\n'),

    ("an E2BIG is re-raised instead of answered as a failed call", GH,
     "    return refused(args, why)\n\n\nclass GitHubIssuesTracker",
     "    raise exc\n\n\nclass GitHubIssuesTracker"),
]
