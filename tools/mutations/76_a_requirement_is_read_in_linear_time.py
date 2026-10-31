"""A requirement is read in time linear in its size (#76, and the review of #301).

The readers of `beeverforge/product` had two shapes that cost n² or worse: a gap `\\s*` under
`MULTILINE` beside a line anchor, which at every blank line ate all the blank lines after it and
backtracked; and a lazy group closed by `\\s*$` (or `<!--.*?-->`), which tried every end on a line
and scanned the rest of the line from each. Each row below puts one site back the way it was, and
the guard, which measures how each reader's processor time grows from n to 4n, must go red.
"""

TEST = "tests/test_a_requirement_is_read_in_time_linear_in_its_size.py"

_CORPUS = "beeverforge/product/corpus.py"
_DOMAIN = "beeverforge/product/domain.py"
_ITEMS = "beeverforge/product/index/items.py"
_BRIEFING = "beeverforge/product/briefing.py"

MUTATIONS = [
    ("A REQUIREMENT'S FIELD OPENS WITH `^\\s*` AGAIN: it spans the blank lines before it",
     _CORPUS,
     r'    return re.compile(rf"^[ \t]*[-*][ \t]*\**{re.escape(name)}',
     r'    return re.compile(rf"^\s*[-*][ \t]*\**{re.escape(name)}'),

    ("a domain fact's field opens with `^\\s*` again",
     _DOMAIN,
     r'    m = re.search(rf"^[ \t]*[-*][ \t]*\**{name}',
     r'    m = re.search(rf"^\s*[-*][ \t]*\**{name}'),

    ("an index item's header line opens with `^\\s*` again",
     _ITEMS,
     r'_HEADER_LINE = re.compile(r"^[ \t]*(?:#\s+REQ-\d+.*"',
     r'_HEADER_LINE = re.compile(r"^\s*(?:#\s+REQ-\d+.*"'),

    ("the briefing's heading marks are dropped with `^\\s*` again",
     _BRIEFING,
     r'    text = re.sub(r"(?m)^[ \t]*#{1,6}\s+", "", text)',
     r'    text = re.sub(r"(?m)^\s*#{1,6}\s+", "", text)'),

    ("THE TITLE IS A LAZY GROUP CLOSED BY `\\s*$` AGAIN: a title and n spaces cost n²",
     _CORPUS,
     r'(?P<title>[^\n]+)", re.MULTILINE)',
     r'(?P<title>.+?)\s*$", re.MULTILINE)'),

    ("a field's value is a lazy group closed by `[ \\t]*$` again",
     _CORPUS,
     r'                      r"(?P<value>[^\n]*)", re.MULTILINE | re.IGNORECASE)',
     r'                      r"(?P<value>.*?)[ \t]*$", re.MULTILINE | re.IGNORECASE)'),

    ("a section heading is a lazy group closed by `\\s*$` again",
     _CORPUS,
     r'_HEADING_RE = re.compile(r"^##\s+([^\n]+)", re.MULTILINE)',
     r'_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)'),

    ("a domain term is a lazy group closed by `\\s*$` again",
     _DOMAIN,
     r'_ENTRY_RE = re.compile(r"^###\s+(?P<term>[^\n]+)", re.MULTILINE)',
     r'_ENTRY_RE = re.compile(r"^###\s+(?P<term>.+?)\s*$", re.MULTILINE)'),

    ("an indexed heading is a lazy group closed by `\\s*#*\\s*$` again, which is cubic",
     _ITEMS,
     r'_HEADING = re.compile(r"^#{1,6}\s+([^\n]+)", re.MULTILINE)',
     r'_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)'),

    ("A STATUS'S COMMENT IS REMOVED WITH `<!--.*?-->` AGAIN: n openings cost n²",
     _CORPUS,
     "    raw = _without_comments(raw).strip().lower()",
     '    raw = re.sub(r"<!--.*?-->", "", raw).strip().lower()'),

    ("a cleaned field's comment is removed with `<!--.*?-->` again",
     _CORPUS,
     '    return _without_comments(value or "").strip().strip("<>").strip()',
     '    return re.sub(r"<!--.*?-->", "", value or "").strip().strip("<>").strip()'),

    ("a domain field's comment is removed with `<!--.*?-->` again",
     _DOMAIN,
     '    return _without_comments(m.group("v")).strip() if m else ""',
     '    return re.sub(r"<!--.*?-->", "", m.group("v")).strip() if m else ""'),

    ("the scan looks for the end of the line from every comment, so a line of n comments costs n²",
     _CORPUS,
     "        if eol < start:\n",
     "        if True:\n"),
]
