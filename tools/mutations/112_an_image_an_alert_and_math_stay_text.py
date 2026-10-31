"""#112: an image, a GitHub alert and math the agent writes stay text in the quoted account.

Each reverse undoes one measured guard. Without `!` in `_MARKUP`, an `![…](…)` badge renders as an
image inside the platform's section. With the agent's `$` only escaped (`\\$`, the shape review on
a2714e1 measured typeset), or not escaped at all, `$…$`, `$$…$$` and `` $`…`$ `` reach GitHub's
math renderer. Without the alert pass, or with it narrowed to one case or to an unindented
marker, `[!CAUTION]` and the other four open the quote as a `markdown-alert` box. And the two
readers of `_NO_MATH`: the cut line counting it as the eight characters it is in the source, and
a cut opening it.
"""

TEST = "tests/test_an_image_an_alert_and_math_the_agent_writes_stay_text.py"
MACHINE = "beeverforge/orchestrator/machine.py"

MUTATIONS = [
    ("`!` is not escaped: an image badge renders inside the quote", MACHINE,
     '_MARKUP = re.compile(r"([\\\\`<&*_~!$])")', '_MARKUP = re.compile(r"([\\\\`<&*_~$])")'),

    ("`$` is not escaped: math the agent writes is typeset inside the quote", MACHINE,
     '_MARKUP = re.compile(r"([\\\\`<&*_~!$])")', '_MARKUP = re.compile(r"([\\\\`<&*_~!])")'),

    ("`$` is only escaped, `\\$`, which GitHub resolves before it typesets", MACHINE,
     '    return _NO_MATH if markup[1] == "$" else "\\\\" + markup[1]\n',
     '    return "\\\\" + markup[1]\n'),

    ("an alert marker is left escaped, `[\\!CAUTION]`, which GitHub still reads as an alert",
     MACHINE,
     '    return _AN_ALERT.sub(r"\\1`[!\\2]`\\3",\n',
     '    return (lambda f, t: t)(r"",\n'),

    ("only an upper-case alert marker is put in a span: `[!note]` and `[!Tip]` open alerts",
     MACHINE,
     "                       re.IGNORECASE | re.MULTILINE)\n",
     "                       re.MULTILINE)\n"),

    ("an indented alert marker is left escaped, and GitHub reads it as an alert", MACHINE,
     r'_AN_ALERT = re.compile(r"^([ \t]*)\[',
     r'_AN_ALERT = re.compile(r"^()\['),

    ("an alert marker followed by spaces is left escaped, and GitHub reads it as an alert",
     MACHINE,
     r'\]([ \t]*)$",',
     r'\]()$",'),

    ("the cut line counts an agent's `$` as the eight characters of its source", MACHINE,
     "        if text.startswith(_NO_MATH, i):\n",
     "        if False:\n"),

    ("a cut may stop inside an agent's `$`, showing `&#82` and losing the `$`", MACHINE,
     '            i += len(_NO_MATH) if row.startswith(_NO_MATH, i) else 2 if row[i] == "\\\\" '
     'else 1\n',
     '            i += 2 if row[i] == "\\\\" else 1\n'),

    ("a cut straddling an agent's `$` steps back one character, into it", MACHINE,
     "        if i > cut:\n            cut = at\n",
     "        if i > cut:\n            cut -= 1\n"),
]
