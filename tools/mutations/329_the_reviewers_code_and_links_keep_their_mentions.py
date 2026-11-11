"""#329: the reviewer's code and links reach the pull request as written, mentions and all.

#315's rewrites (`#1` as `card 1`, a zero-width space after a name's `@` and inside `GH-1`) ran
inside closed code spans, closed fences and the links GitHub makes of bare ones, so they changed
the code the reviewer quoted and where a link pointed. `_quieted` now runs outside those spans
only, on the split the `&` escaping uses (`_quieted_outside_code_and_links`). Each row rewrites
inside one of them again, or stops rewriting outside them.
"""

TEST = "tests/test_the_reviewers_code_and_links_keep_their_mentions.py"
MACHINE = "beeverforge/orchestrator/machine.py"

MUTATIONS = [
    ("a closed code span is rewritten", MACHINE,
     "            out += [_outside_links(text[start:i], text[start - 1:start]), text[i:span.end()]]",
     "            out += [_outside_links(text[start:i], text[start - 1:start]),"
     " _quieted(text[i:span.end()])]"),

    ("a closed fence is rewritten", MACHINE,
     "                out, paragraph, i = out + ended() + rows[i:end + 1], [], end + 1",
     "                out, paragraph, i = out + ended() + [_quieted(r) for r in rows[i:end + 1]], [], end + 1"),

    ("a bare link is rewritten", MACHINE,
     "            piece = link[0]",
     "            piece = _quieted(link[0])"),

    ("an angle autolink GitHub keeps is rewritten", MACHINE,
     "            piece = kept if kept == link[0] else _quieted(kept)",
     "            piece = _quieted(kept)"),

    ("the whole text is rewritten after the split, as before", MACHINE,
     "    return _closing_references_broken(_quieted_outside_code_and_links(words))",
     "    return _closing_references_broken(_quieted(_quieted_outside_code_and_links(words)))"),

    ("text before a link is left as written", MACHINE,
     "        out += [_quieted(text[start:link.start()]), piece]",
     "        out += [_escaped_ampersands(text[start:link.start()]), piece]"),

    ("text after the last link is left as written", MACHINE,
     '    return "".join(out) + _quieted(text[start:])',
     '    return "".join(out) + _escaped_ampersands(text[start:])'),

    ("a backtick that never closes protects what follows it", MACHINE,
     "            if span is None:\n                break",
     "            if span is None:\n                return \"\".join(out) + _outside_links(text[start:i]) + text[i:]"),

    # review of #521: a table's cell may end a span at its `|`
    ("a table's paragraph is read span by span", MACHINE,
     "        if _A_TABLE_DELIMITER.search(text):",
     "        if False:"),

    ("a delimiter row needs no `|`, so a heading's `---` reads as one", MACHINE,
     '''_A_TABLE_DELIMITER = re.compile(r"^[ \\t>]*(?=[^\\n]*\\|)\\|?[ \\t]*:?-+:?[ \\t]*"''',
     '''_A_TABLE_DELIMITER = re.compile(r"^[ \\t>]*\\|?[ \\t]*:?-+:?[ \\t]*"'''),

    ("a table in a quote is read span by span", MACHINE,
     '''_A_TABLE_DELIMITER = re.compile(r"^[ \\t>]*(?=[^\\n]*\\|)\\|?[ \\t]*:?-+:?[ \\t]*"''',
     '''_A_TABLE_DELIMITER = re.compile(r"^[ \\t]*(?=[^\\n]*\\|)\\|?[ \\t]*:?-+:?[ \\t]*"'''),

    # review of #521: a squash commit message reads a closing keyword with no code around it
    ("a closing keyword in kept code still closes", MACHINE,
     "    return _closing_references_broken(_quieted_outside_code_and_links(words))",
     "    return _quieted_outside_code_and_links(words)"),

    ("only `closes` is a closing keyword", MACHINE,
     '''    r"\\b((?:close[sd]?|fix(?:e[sd])?|resolve[sd]?):?\\s+)"''',
     '''    r"\\b((?:close[sd]?):?\\s+)"'''),

    ("a closing keyword is read in lower case only", MACHINE,
     "    re.IGNORECASE)\n#: A row that may open an HTML block",
     "    )\n#: A row that may open an HTML block"),

    ("a cross-repository reference after a closing keyword is kept", MACHINE,
     '''    r"(?:([\\w.-]+/[\\w.-]+)?#|GH-|https?://[^/\\s]+/([\\w.-]+/[\\w.-]+)/(?:issues|pull)/)(?=\\d)",''',
     '''    r"(?:()#|GH-|https?://[^/\\s]+/([\\w.-]+/[\\w.-]+)/(?:issues|pull)/)(?=\\d)",'''),

    ("`GH-<number>` after a closing keyword is kept", MACHINE,
     '''    r"(?:([\\w.-]+/[\\w.-]+)?#|GH-|https?://[^/\\s]+/([\\w.-]+/[\\w.-]+)/(?:issues|pull)/)(?=\\d)",''',
     '''    r"(?:([\\w.-]+/[\\w.-]+)?#|https?://[^/\\s]+/([\\w.-]+/[\\w.-]+)/(?:issues|pull)/)(?=\\d)",'''),

    ("a link to the issue after a closing keyword is kept", MACHINE,
     '''    r"(?:([\\w.-]+/[\\w.-]+)?#|GH-|https?://[^/\\s]+/([\\w.-]+/[\\w.-]+)/(?:issues|pull)/)(?=\\d)",''',
     '''    r"(?:([\\w.-]+/[\\w.-]+)?#|GH-|(?!)())(?=\\d)",'''),

    ("a link's repository is dropped from its card", MACHINE,
     "    repository = reference[2] or reference[3]",
     "    repository = reference[2]"),

    ("a link to an issue is rewritten with no closing keyword before it", MACHINE,
     '''    r"\\b((?:close[sd]?|fix(?:e[sd])?|resolve[sd]?):?\\s+)"''',
     '''    r"\\b((?:close[sd]?|fix(?:e[sd])?|resolve[sd]?):?\\s+|see )"'''),

    ("every `#<number>` in kept code is rewritten", MACHINE,
     '''    r"\\b((?:close[sd]?|fix(?:e[sd])?|resolve[sd]?):?\\s+)"''',
     '''    r"()"'''),

    ("a name is left live outside code", MACHINE,
     '''    words = _A_HANDLE.sub(lambda m: f"@\\u200b{m.group(1)}", without_mentions(words))''',
     '''    words = without_mentions(words)'''),

    ("`#<number>` is left live outside code", MACHINE,
     '''    words = _A_HANDLE.sub(lambda m: f"@\\u200b{m.group(1)}", without_mentions(words))''',
     '''    words = _A_HANDLE.sub(lambda m: f"@\\u200b{m.group(1)}", words)'''),
]
