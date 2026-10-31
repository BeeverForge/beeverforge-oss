"""A file written with Windows line endings keeps its front matter (#67): every reader's
normalisation, cut one at a time.

WHAT THE ROWS BREAK: rows 1-5 remove the CRLF and lone-CR normalisation in each of the five
front-matter readers; row 6 keeps the CRLF replace in `parse_capability` but drops the lone-CR one;
row 7 removes the normalisation in the queue's `_opening`, so a CRLF card opens with its own
front-matter block. Rows 8-10 put plain `utf-8` back in the three readers that open a file
themselves (`read_concepts`, `confirm_in_repository`, `distilled_until`), so a file saved with a
byte-order mark reads as having no front matter.
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

    ("a concept file saved with a BOM is read with its U+FEFF", "beeverforge/knowledge/okf.py",
     'parse_concept(path.read_text(encoding="utf-8-sig"))',
     'parse_concept(path.read_text(encoding="utf-8"))'),

    ("a capability file saved with a BOM is confirmed as unreadable", CAPS,
     'parse_capability(target.read_text(encoding="utf-8-sig"), path=rel)',
     'parse_capability(target.read_text(encoding="utf-8"), path=rel)'),

    ("a distillate saved with a BOM has no `until`", "beeverforge/product/authoring.py",
     'front_matter(one.read_text(encoding="utf-8-sig"))',
     'front_matter(one.read_text(encoding="utf-8"))'),
]
