"""#315: the reviewer's summary and findings link no issue and notify no one.

`_review_lines` wrote the reviewer's `summary` and each finding's `description` into the pull
request body as written, and `format_review` posted them the same way, so a `#1`, `GH-2`,
`owner/repo#3` or `@someone` in them linked an unrelated issue or notified a stranger. Both now
pass that text through `_without_reviewer_mentions`: every bare `&` escaped outside closed code
and the links GitHub makes of bare ones (so no entity spells the others), main's
`without_mentions` (which writes `#1` and `GH-2` as `card 1` and `card 2`, #111), then a
zero-width space after a name's `@`, and between `GH` and `-<number>` where that rewrite missed
one (`_GH-1_`, `éGH-1`).
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

    # RE-PINNED 2026-11-09 (#323): main's #131 gave the posted review its own heading line
    ("the posted review's summary is raw", POLICY,
     '''    lines = [heading, "", quiet(review.summary)]''',
     '''    lines = [heading, "", review.summary]'''),

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

    # restored (review of #323 at 12c5242): main's `\b`-bounded rewrite misses `_GH-1_` and `éGH-1`
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

    ("an entity is left live: `&` is not escaped", MACHINE,
     '''    words = _ampersands_escaped(words)''',
     '''    words = words'''),

    ("an `&` the reviewer escaped gets a second backslash, which frees it", MACHINE,
     '''_A_BARE_AMPERSAND = re.compile(r"(?<!\\\\)((?:\\\\\\\\)*)&")''',
     '''_A_BARE_AMPERSAND = re.compile(r"()&")'''),

    # ── where a backslash is not an escape, and where that is in doubt ──────────────────────────
    ("an `&` in a closed code span is escaped", MACHINE,
     "            out += [_outside_links(text[start:i], text[start - 1:start]), text[i:span.end()]]",
     "            out += [_outside_links(text[start:i], text[start - 1:start]),"
     " _escaped_ampersands(text[i:span.end()])]"),

    ("an `&` in a closed fence is escaped", MACHINE,
     "                out, paragraph, i = out + ended() + rows[i:end + 1], [], end + 1",
     "                out, paragraph, i = out + ended() + [_escaped_ampersands(r) for r in rows[i:end + 1]], [], end + 1"),

    ("an `&` in a bare link is escaped", MACHINE,  # re-pinned: an `elif` after the autolink's branch
     "        elif _autolinked(link[0], prior, text[link.end():link.end() + 1]):",
     "        elif False:"),

    # ── which bare links GitHub makes, and so keep their `&` (reviews of #323) ─────────────────
    ("the reviewer's bare link takes a lower-case scheme only", MACHINE,
     r'''_A_BARE_LINK = re.compile(r"(?<!\]\()((?:(?i:https?)://|www\.)''',
     r'''_A_BARE_LINK = re.compile(r"(?<!\]\()((?:https?://|www\.)'''),

    ("a bare link's domain is read after a lower-case scheme only", MACHINE,
     r'''_A_LINK_DOMAIN = re.compile(r"((?i:https?)://|www\.)([A-Za-z0-9_.-]*)")''',
     r'''_A_LINK_DOMAIN = re.compile(r"(https?://|www\.)([A-Za-z0-9_.-]*)")'''),

    ("`WWW.` is read as a `www.` link", MACHINE,
     r'''_A_BARE_LINK = re.compile(r"(?<!\]\()((?:(?i:https?)://|www\.)''',
     r'''_A_BARE_LINK = re.compile(r"(?<!\]\()((?i:https?://|www\.)'''),

    ("a bare link keeps its `&` whatever its domain", MACHINE,
     "    return all(labels[:-1]) and not any(\"_\" in label for label in labels[-2:])",
     "    return True"),

    ("a scheme link keeps its `&` after any character", MACHINE,
     '''    elif before == "[" or (before.isascii() and before.isalpha()):''',
     '''    elif False:'''),

    ("a host that starts with neither a letter nor a digit is a host", MACHINE,
     "    elif not domain[:1].isalnum():",
     "    elif not domain:"),

    ("a scheme with nothing after it is a host", MACHINE,
     "    elif not domain[:1].isalnum():",
     "    elif False:"),

    ("a `www.` link keeps its `&` after any character", MACHINE,
     '''        if before and not before.isspace() and before not in "*_~(":''',
     '''        if False:'''),

    ("a bare link keeps its `&` with `_` in its last two labels", MACHINE,
     "    return all(labels[:-1]) and not any(\"_\" in label for label in labels[-2:])",
     "    return all(labels[:-1])"),

    ("an empty label is a domain's", MACHINE,
     "    return all(labels[:-1]) and not any(\"_\" in label for label in labels[-2:])",
     "    return not any(\"_\" in label for label in labels[-2:])"),

    ("a scheme link's single-label host is refused", MACHINE,
     "    return all(labels[:-1]) and not any(\"_\" in label for label in labels[-2:])",
     "    return len(labels) > 1 and all(labels[:-1]) and not any(\"_\" in label for label in labels[-2:])"),

    ("a scheme link follows the `www.` rule again", MACHINE,
     '''    if scheme == "www.":''',
     '''    if True:'''),

    ("a `www.` link after `<` is read by the scheme rule", MACHINE,
     '''    if scheme == "www.":''',
     '''    if scheme == "www." and not (before == "<" and after == ">"):'''),

    # RETIRED 2026-11-03: "an angle autolink's `&` is escaped when its host is not one" pinned
    # `_autolinked`'s `<…>` shortcut, which `_AN_AUTOLINK` replaced (review of #323 at 208035c);
    # "an http autolink's `&` is escaped" below holds the same claim.

    # ── an autolink, `<scheme:…>`, where no backslash is an escape (review of #323 at 208035c) ──
    ("an autolink not `http(s)` is left an autolink, so its `\\&` is no escape", MACHINE,
     '''    return f"{autolink[0][:colon]}\\\\{autolink[0][colon:]}"''',
     '''    return autolink[0].replace("&", "\\\\&")'''),

    ("an autolink after a reviewer's backslash is taken for no autolink", MACHINE,
     r'''_AN_AUTOLINK = re.compile(r"(\\*)<([A-Za-z][A-Za-z0-9+.-]{1,31}):[^\s<>\x00-\x1f]*>")''',
     r'''_AN_AUTOLINK = re.compile(r"(?<!\\)((?:\\\\)*)<([A-Za-z][A-Za-z0-9+.-]{1,31}):[^\s<>\x00-\x1f]*>")'''),

    ("an `http(s)` autolink after an odd run of backslashes is kept as one", MACHINE,
     "        if link.re is _AN_AUTOLINK and len(link[1]) % 2 and link[2].lower() in _LINKED_SCHEMES:",
     "        if False:"),

    ("the autolink is broken at its `<`, which a bare link glued before it takes", MACHINE,
     '''    return f"{autolink[0][:colon]}\\\\{autolink[0][colon:]}"''',
     '''    return f"{autolink[1]}\\\\{autolink[0][len(autolink[1]):]}"'''),

    ("every scheme's autolink is kept as written", MACHINE,
     "    if autolink[2].lower() in _LINKED_SCHEMES:",
     "    if True:"),

    ("the `http(s)` autolink is matched in lower case only", MACHINE,
     "    if autolink[2].lower() in _LINKED_SCHEMES:",
     "    if autolink[2] in _LINKED_SCHEMES:"),

    ("an http autolink's `&` is escaped", MACHINE,
     "            piece = kept if kept == link[0] else _escaped_ampersands(kept)",
     "            piece = _escaped_ampersands(kept)"),

    ("a bare link inside an autolink is read again on its own", MACHINE,
     "        if link.start() < start:\n            continue",
     "        if False:\n            continue"),

    ("where a row may open an HTML block, an autolink is left whole", MACHINE,
     "        return _escaped_ampersands(_AN_AUTOLINK.sub(_unlinked, words))",
     "        return _escaped_ampersands(words)"),

    ("a `[` no longer blocks a scheme link", MACHINE,
     '''    elif before == "[" or (before.isascii() and before.isalpha()):''',
     '''    elif before.isascii() and before.isalpha():'''),

    ("a scheme link glued to a letter keeps its `&`", MACHINE,
     '''    elif before == "[" or (before.isascii() and before.isalpha()):''',
     '''    elif before == "[":'''),

    ("a scheme link after a non-ASCII letter is refused", MACHINE,
     '''    elif before == "[" or (before.isascii() and before.isalpha()):''',
     '''    elif before == "[" or before.isalpha():'''),

    ("a bare link after a closed span is read as at the start", MACHINE,
     "            out += [_outside_links(text[start:i], text[start - 1:start]), text[i:span.end()]]",
     "            out += [_outside_links(text[start:i]), text[i:span.end()]]"),

    ("the text after the last span is read as at the start", MACHINE,
     "    return \"\".join(out) + _outside_links(text[start:], text[start - 1:start])",
     "    return \"\".join(out) + _outside_links(text[start:])"),

    ("a backtick that does not close on its row is skipped, and a later one opens a span", MACHINE,
     "            if span is None:\n                break",
     "            if span is None:\n                i += run\n                continue"),

    ("a tag that reaches over a backtick is ignored", MACHINE,
     '''            if close < 0 or "`" in text[i:close]:''',
     '''            if close < 0:'''),

    ("a tag that reaches past its row is ignored", MACHINE,
     '''            if close < 0 or "`" in text[i:close]:''',
     '''            if close >= 0 and "`" in text[i:close]:'''),

    ("an HTML block's backticks are trusted", MACHINE,
     "    if _AN_HTML_ROW.search(words):",
     "    if False:"),

    ("an autolink opening a row is taken for an HTML block", MACHINE,
     '''_AN_HTML_ROW = re.compile(r"^ {0,3}<(?![A-Za-z][A-Za-z0-9+.-]{1,31}:)[A-Za-z/!?]", re.MULTILINE)''',
     '''_AN_HTML_ROW = re.compile(r"^ {0,3}<[A-Za-z/!?]", re.MULTILINE)'''),

    ("the summary loses its `## ` escaping while its mentions are broken", MACHINE,
     "        out = [first, _as_text(_without_reviewer_mentions(r.summary))]",
     "        out = [first, _without_reviewer_mentions(r.summary)]"),

    # review of #323 with #196: withheld on the raw words before `quiet` rewrites them
    ("the posted review is quieted before its credentials are withheld", POLICY,
     "    review = _review_withheld(review)\n",
     ""),
]
