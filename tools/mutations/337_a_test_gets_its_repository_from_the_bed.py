"""A test gets its git repository from the bed, and the count of bare `git init` calls under
`tests/` does not grow back (#337, slice 4 of the suite-cost audit): every guard the bed claims,
cut one at a time.

ROWS 1-6 ARE THE BED: a changed template handed out again (the check before a copy gone), never
caught at the end of the session (`verify_all` a no-op), the template itself handed out, a shape
built again by the next worker (the manifest never read), a copy left naming the template's path,
and a binary file naming it let through.

ROWS 7-8 ARE THE SESSION: the fixture's check at the end of the session gone, and the build's
direct writes to `os.environ` left in the test that built the shape.

ROWS 9-19 ARE THE COUNT: each form the counter reads dropped (a `["git", ..., "init"]` list, a git
helper given `"init"`, a git helper given a list, a command line in a string), the subcommand read
past an option or as any argument, a docstring counted, the bed and its guard counted, the text
filter too narrow to let a command line through, and the line moved by one or turned round.
"""

TEST = "tests/test_a_test_gets_its_repository_from_the_bed.py"

BED = "tests/the_git_bed.py"

MUTATIONS = [
    # ── the bed ─────────────────────────────────────────────────────────────────────────────────
    ("a template a test changed is handed out again: the check before a copy is gone", BED,
     "            template = self._template(name, build)\n"
     "        self._verify(name, template)\n",
     "            template = self._template(name, build)\n"),

    ("a template a test changed is never caught at the end: `verify_all` checks nothing", BED,
     "        for name, template in self._shapes.items():\n"
     "            self._verify(name, template)",
     "        for name, template in self._shapes.items():\n"
     "            pass"),

    ("the template itself is handed out, so a test's commit lands in every later copy", BED,
     "            path.write_bytes(path.read_bytes().replace(old, new))\n"
     "        return dest",
     "            path.write_bytes(path.read_bytes().replace(old, new))\n"
     "        return template.root"),

    ("a shape another worker built is built again: the manifest is never read", BED,
     "            if manifest.is_file():",
     "            if False:"),

    ("a copy keeps the template's path in its remote URL and its text files", BED,
     "        for rel in template.texts:",
     "        for rel in []:"),

    ("a binary file naming the template's path is let through, unrewritable", BED,
     '                    data.decode("utf-8")',
     '                    data.decode("latin-1")'),

    # ── the session ─────────────────────────────────────────────────────────────────────────────
    ("the session's bed never verifies its templates when the session ends", BED,
     "    yield bed\n"
     "    bed.verify_all()",
     "    yield bed"),

    ("a build's direct write to `os.environ` stays in the test that built the shape", BED,
     "                os.environ.clear()\n"
     "                os.environ.update(saved)",
     "                pass"),

    # ── the count ───────────────────────────────────────────────────────────────────────────────
    ("a `[\"git\", ..., \"init\"]` list handed to a process is not counted", BED,
     "        if _is_git_init_list(node) or _is_git_helper_init(node):",
     "        if _is_git_helper_init(node):"),

    ("a git helper given `\"init\"` is not counted", BED,
     "        if _is_git_init_list(node) or _is_git_helper_init(node):",
     "        if _is_git_init_list(node):"),

    ("a git helper handed a list whose subcommand is `init` is not counted", BED,
     '    if isinstance(first, (ast.List, ast.Tuple)) and _subcommand(first.elts) == "init":',
     "    if False:"),

    ("a command line in a string is not counted", BED,
     "              and id(node) not in prose and _GIT_INIT.search(node.value)):",
     "              and id(node) not in prose and False):"),

    ("the subcommand is read as the first string, so `-C <repo> init` is not counted", BED,
     '            if not item.value.startswith("-"):',
     "            if True:"),

    ("any `\"init\"` argument is the subcommand, so a commit whose message is `init` counts", BED,
     '            if not item.value.startswith("-"):\n'
     "                return item.value",
     '            if item.value == "init":\n'
     "                return item.value"),

    ("a docstring that says `git init` is counted as one", BED,
     "              and id(node) not in prose and _GIT_INIT.search(node.value)):",
     "              and _GIT_INIT.search(node.value)):"),

    ("the bed and its guard are counted, though they build on purpose", BED,
     "        if path.name in NOT_COUNTED:\n"
     "            continue",
     "        if False:\n"
     "            continue"),

    ("the text filter lets only a quoted `init` through, so a command line is never parsed", BED,
     '''_COULD_BE_ONE = re.compile(r"""['"]init['"]|\\bgit\\s+init\\b""")''',
     '''_COULD_BE_ONE = re.compile(r"""['"]init['"]""")'''),

    ("one repository over the line is let through", BED,
     '    return refusal(count, baseline) if count > baseline else ""',
     '    return refusal(count, baseline) if count > baseline + 1 else ""'),

    ("the line is turned round: the count at the line is refused", BED,
     '    return refusal(count, baseline) if count > baseline else ""',
     '    return refusal(count, baseline) if count >= baseline else ""'),
]
