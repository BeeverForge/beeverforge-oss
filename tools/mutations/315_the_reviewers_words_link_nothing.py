"""#315: the reviewer's summary and findings link no issue and notify no one.

`_review_lines` wrote the reviewer's `summary` and each finding's `description` into the pull
request body as written, and `format_review` posted them the same way, so a `#1`, `GH-2`,
`owner/repo#3` or `@someone` in them linked an unrelated issue or notified a stranger. Both now
pass that text through `_without_reviewer_mentions`: main's `without_mentions`, then a zero-width
space after a name's `@` and between `GH` and `-<number>`.
"""

TEST = "tests/test_the_reviewers_words_link_nothing.py"
MACHINE = "beeverforge/orchestrator/machine.py"
POLICY = "beeverforge/orchestrator/merge_policy.py"

MUTATIONS = [
    # ── every path the reviewer's text takes into the pull request ──────────────────────────────
    ("the summary is written without the helper", MACHINE,
     "        out = [first, _as_text(_without_reviewer_mentions(r.summary))]",
     "        out = [first, _as_text(r.summary)]"),

    ("a finding is written without the helper", MACHINE,
     "            words = _as_text(_without_reviewer_mentions(f.description))",
     "            words = _as_text(f.description)"),

    ("the posted review's summary is raw", POLICY,
     '''    lines = [f"**{review.decision}** — score {review.score}", "", quiet(review.summary)]''',
     '''    lines = [f"**{review.decision}** — score {review.score}", "", review.summary]'''),

    ("the posted review's finding is raw", POLICY,
     '''        lines.append(f"- **{f.severity}**{loc}: {quiet(f.description)}")''',
     '''        lines.append(f"- **{f.severity}**{loc}: {f.description}")'''),

    # ── what the helper does ────────────────────────────────────────────────────────────────────
    ("the helper leaves `#<number>` live", MACHINE,
     '''    words = _A_HANDLE.sub(lambda m: f"@\\u200b{m.group(1)}", without_mentions(words))''',
     '''    words = _A_HANDLE.sub(lambda m: f"@\\u200b{m.group(1)}", words)'''),

    ("the helper leaves a name live", MACHINE,
     '''    words = _A_HANDLE.sub(lambda m: f"@\\u200b{m.group(1)}", without_mentions(words))''',
     '''    words = without_mentions(words)'''),

    ("the helper leaves `GH-<number>` live", MACHINE,
     '''    return _A_GH_REFERENCE.sub("\\\\1\\u200b", words)''',
     '''    return words'''),

    ("`gh-<number>` is left live", MACHINE,
     '''_A_GH_REFERENCE = re.compile(r"(?<![A-Za-z0-9])(GH)(?=-\\d)", re.IGNORECASE)''',
     '''_A_GH_REFERENCE = re.compile(r"(?<![A-Za-z0-9])(GH)(?=-\\d)")'''),

    ("a `GH` glued to a word is broken too", MACHINE,
     '''_A_GH_REFERENCE = re.compile(r"(?<![A-Za-z0-9])(GH)(?=-\\d)", re.IGNORECASE)''',
     '''_A_GH_REFERENCE = re.compile(r"(GH)(?=-\\d)", re.IGNORECASE)'''),

    ("an address's `@` is broken too", MACHINE,
     '''    words = _A_HANDLE.sub(lambda m: f"@\\u200b{m.group(1)}", without_mentions(words))''',
     '''    words = re.sub(r"@(\\w)", lambda m: f"@\\u200b{m.group(1)}", without_mentions(words))'''),

    ("the summary loses its `## ` escaping while its mentions are broken", MACHINE,
     "        out = [first, _as_text(_without_reviewer_mentions(r.summary))]",
     "        out = [first, _without_reviewer_mentions(r.summary)]"),
]
