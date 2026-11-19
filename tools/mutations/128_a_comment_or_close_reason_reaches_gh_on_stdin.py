"""A comment or close reason GitHub would accept reaches `gh` on stdin, whatever its bytes (#128).

Run:  .venv/bin/python tools/mutate.py tools/mutations/128_a_comment_or_close_reason_reaches_gh_on_stdin.py

The GitHub tracker's `comment` put its text in argv as `--body <text>`, and `close_ticket` its
reason as `--comment <reason>`. Linux refuses one argv element of `MAX_ARG_STRLEN` bytes or more
with `E2BIG`, while GitHub accepts 65,536 characters: a 3-byte script failed from about 43,690
characters. Both texts now go on stdin through one `gh issue comment --body-file -`, and the close
runs with `--reason` alone, after the comment.

Row 1 is the defect as it shipped for `comment`: the text back in argv. Row 2 is the close's: the
reason back on `--comment`. Row 3 closes before it comments, and row 4 never posts the reason.
Rows 5 and 6 drop the surrogate marking, at the tracker's call site and in the shared helper.
Rows 7-9 remove the limit: the tracker's raise, the limit turned into a cut, and the shared check.
Row 10 is `_write` dropping `stdin`, so every comment is sent empty. Row 11 posts a blank reason.
Rows 12 and 13 break the "posted but still open" sentence: dropped after a posted comment, or said
when nothing was posted.
"""

TEST = "tests/test_a_comment_or_close_reason_github_accepts_reaches_gh_whatever_its_bytes.py"

GH = "beeverforge/adapters/tracker/github.py"

CLI = "beeverforge/adapters/github_cli.py"

_COMMENT = ('        self._write(["issue", "comment", num, "--repo", repo, "--body-file", "-"],\n'
            '                    stdin=marked(text))\n')

_POST = ('        if posted:\n'
         '            self._post_comment(repo, num, reason, what="the close reason")\n')

_BARE = '        self._close_bare(repo, num, delivered=delivered, posted=posted)\n'

MUTATIONS = [
    ("THE DEFECT, `comment`: the text goes back into argv as `--body`", GH,
     _COMMENT,
     '        self._write(["issue", "comment", num, "--repo", repo, "--body", text])\n'),

    ("THE DEFECT, `close_ticket`: the reason goes back on the close's `--comment`", GH,
     '"--reason", "completed" if delivered else "not planned"])\n',
     '"--reason", "completed" if delivered else "not planned",\n'
     '                         "--comment", reason])\n'),

    ("the issue is closed before its reason is posted", GH,
     _POST + _BARE,
     _BARE + _POST),

    ("the close reason is never posted", GH,
     _POST,
     '        if False:\n'
     '            self._post_comment(repo, num, reason, what="the close reason")\n'),

    ("the tracker sends a lone surrogate unmarked", GH,
     '                    stdin=marked(text))\n',
     '                    stdin=str(text))\n'),

    ("the shared `marked` leaves a lone surrogate in place", CLI,
     '    return _SURROGATE.sub("\\ufffd", text)\n',
     "    return text\n"),

    ("a text over GitHub's limit is sent, and only GitHub refuses it", GH,
     "        if why:\n"
     "            raise RuntimeError(why)\n",
     "        if False:\n"
     "            raise RuntimeError(why)\n"),

    ("a text over GitHub's limit is cut to fit instead of refused", GH,
     "        why = body_too_long(text, what)\n",
     '        text, why = text[:BODY_LIMIT], ""\n'),

    ("the shared limit check never fires", CLI,
     "    if len(text) > BODY_LIMIT:\n",
     "    if False:\n"),

    ("`_write` takes `stdin` and never hands it to `_gh`", GH,
     "        p = self._gh(args, timeout=timeout, stdin=stdin)\n",
     "        p = self._gh(args, timeout=timeout)\n"),

    ("a blank reason is posted as an empty comment", GH,
     "        posted = bool(reason.strip())\n",
     "        posted = True\n"),

    ("a refused close after the comment raises gh's bare error", GH,
     "            if not posted:\n"
     "                raise\n",
     "            if True:\n"
     "                raise\n"),

    ("a refused close with nothing posted says a reason was posted", GH,
     "            if not posted:\n"
     "                raise\n",
     "            if False:\n"
     "                raise\n"),
]
