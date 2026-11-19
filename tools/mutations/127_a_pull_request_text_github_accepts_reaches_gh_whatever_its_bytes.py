"""A pull-request text GitHub would accept reaches `gh` on stdin, whatever its bytes (#127).

Run:  .venv/bin/python tools/mutate.py tools/mutations/127_a_pull_request_text_github_accepts_reaches_gh_whatever_its_bytes.py

The GitHub forge put every pull-request text in argv as `--body <body>`. Linux refuses one argv
element of `MAX_ARG_STRLEN` bytes or more with `E2BIG`, raised by `subprocess.run` as `OSError`
before `gh` starts, while GitHub accepts 65,536 characters: a 3-byte script failed from about
43,690 characters.

Rows 1-4 are the defect as it shipped, one per write: the text back in argv as `--body`, nothing
on stdin. Row 5 drops `input=stdin` from the forge's one `subprocess.run`, so every write sends
`--body-file -` with nothing behind it. Row 6 removes the forge's catch of an E2BIG, so a refusal
escapes as a raw `OSError`. Row 7 catches it and re-raises instead of answering a named failed
call. Row 8 widens the catch the other way, in the shared helper: every `OSError` is answered as a
failed call, so a denied `gh` (EACCES) or a missing one (ENOENT) reaching the forge is swallowed.

RE-PINNED (review of 6079738): the four writes now reach `gh` through one helper, `_write`, so
rows 1-4 put each write back on `_gh` with the text in argv, the same defect as before. Rows 9-14
are the review's three findings, each check removed: a title holding a NUL reaches
`subprocess.run` (row 9), a title over GitHub's limit is sent (row 10), a text over GitHub's limit
is sent (row 11), and a lone surrogate is no longer marked, in both texts (row 12), in the title
alone (row 13) or in the body alone (row 14).
"""

TEST = "tests/test_a_pull_request_text_github_accepts_reaches_gh_whatever_its_bytes.py"

FORGE = "beeverforge/adapters/forge/github.py"

CLI = "beeverforge/adapters/github_cli.py"

MUTATIONS = [
    ("THE DEFECT, `open_pr`: `gh pr create` carries the text in argv", FORGE,
     '        p = self._write(\n'
     '            ["pr", "create", "--repo", target, "--head", head, "--base", base],\n'
     '            title=title, body=body,\n'
     '        )\n',
     '        p = self._gh(\n'
     '            ["pr", "create", "--repo", target, "--head", head, "--base", base,\n'
     '             "--title", title, "--body", body],\n'
     '        )\n'),

    ("THE DEFECT, `_bring_up_to_date`: `gh pr edit --title` carries the text in argv", FORGE,
     '            done = self._write(["pr", "edit", pr, "--repo", repo], title=title, body=body)\n',
     '            done = self._gh(["pr", "edit", pr, "--repo", repo, "--title", title,\n'
     '                             "--body", body])\n'),

    ("THE DEFECT, `review_pr`: `gh pr review` carries the text in argv", FORGE,
     '        self._write(["pr", "review", pr, "--repo", self.repo, _EVENT_FLAG[event]], '
     'body=body)\n',
     '        self._gh(["pr", "review", pr, "--repo", self.repo, _EVENT_FLAG[event],\n'
     '                  "--body", body])\n'),

    ("THE DEFECT, `set_pr_body`: `gh pr edit` carries the text in argv", FORGE,
     '        done = self._write(["pr", "edit", pr, "--repo", repo or self.repo], body=body)\n',
     '        done = self._gh(["pr", "edit", pr, "--repo", repo or self.repo, "--body", body])\n'),

    ("the forge's `_gh` takes `stdin` and never hands it to `gh`", FORGE,
     '                ["gh", *args], input=stdin, capture_output=True, text=True, timeout=timeout,\n'
     '                env=env,\n',
     '                ["gh", *args], capture_output=True, text=True, timeout=timeout,\n'
     '                env=env,\n'),

    ("an E2BIG reaching the forge escapes as a raw OSError", FORGE,
     '        except OSError as exc:\n'
     '            return argv_too_long(args, exc, log)\n',
     '        except ValueError as exc:\n'
     '            return argv_too_long(args, exc, log)\n'),

    ("the forge re-raises an E2BIG instead of answering a named failed call", FORGE,
     '        except OSError as exc:\n'
     '            return argv_too_long(args, exc, log)\n',
     '        except OSError as exc:\n'
     '            raise exc\n'),

    ("every OSError reaching the forge is answered as a failed call, not only E2BIG", CLI,
     "    if exc.errno != errno.E2BIG:\n"
     "        raise exc\n",
     "    if False:\n"
     "        raise exc\n"),

    ("a title holding a NUL reaches `subprocess.run`, which raises `ValueError`", FORGE,
     '    if title is not None and "\\x00" in title:\n',
     "    if False:\n"),

    ("a title over GitHub's limit is sent as is", FORGE,
     "    if title is not None and len(title) > TITLE_LIMIT:\n",
     "    if False:\n"),

    ("a text over GitHub's limit is sent, and only GitHub refuses it", FORGE,
     "    if len(body) > BODY_LIMIT:\n",
     "    if False:\n"),

    ("a lone surrogate is not marked, so `subprocess.run` raises `UnicodeEncodeError`", FORGE,
     '    return _SURROGATE.sub("\\ufffd", text)\n',
     "    return text\n"),

    ("the title's lone surrogates are not marked, only the text's", FORGE,
     "            title = _marked(title)\n",
     "            title = str(title)\n"),

    ("the text's lone surrogates are not marked, only the title's", FORGE,
     "        body = _marked(body)\n",
     "        body = str(body)\n"),
]
