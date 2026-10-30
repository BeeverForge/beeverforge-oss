"""A file written with Windows line endings keeps its front matter (#67): every reader's
normalisation, cut one at a time.

WHAT THE ROWS BREAK: rows 1-5 remove the CRLF and lone-CR normalisation in each of the five
front-matter readers; row 6 keeps the CRLF replace in `parse_capability` but drops the lone-CR one;
row 7 removes the normalisation in the queue's `_opening`, so a CRLF card opens with its own
front-matter block.
"""

TEST = "tests/test_front_matter_reads_the_same_with_crlf.py"

CAPS = "beeverforge/product/capabilities.py"
NORMALISE = ('    text = text.replace("\\r\\n", "\\n").replace("\\r", "\\n")     # a CRLF file keeps its '
             'front matter\n')
BODY = ('    body = body.replace("\\r\\n", "\\n").replace("\\r", "\\n")     # a CRLF body keeps its '
        'front matter\n')

MUTATIONS = [
    ("a capability file's CRLF is matched as it is, so it reads as having no front matter", CAPS,
     '    text = (text or "").replace("\\r\\n", "\\n").replace("\\r", "\\n")\n',
     '    text = text or ""\n'),

    ("a concept's CRLF is matched as it is", "beeverforge/knowledge/okf.py", NORMALISE, ""),

    ("a decision record's CRLF is matched as it is", "beeverforge/knowledge/system/adrs.py",
     NORMALISE, ""),

    ("a document's CRLF is matched as it is", "beeverforge/adapters/extract/text.py",
     NORMALISE, ""),

    ("a ticket body's CRLF is split as it is", "beeverforge/adapters/tracker/parse.py",
     BODY, ""),

    ("a capability file's lone CR is not read as a line end", CAPS,
     '    text = (text or "").replace("\\r\\n", "\\n").replace("\\r", "\\n")\n',
     '    text = (text or "").replace("\\r\\n", "\\n")\n'),

    ("a CRLF card opens with its own front-matter block", "beeverforge/product/queue.py",
     BODY, ""),
]
