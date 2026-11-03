"""A document saved with a byte-order mark keeps its summary in the brief (#321).

WHAT THE ROWS BREAK: row 1 puts plain `utf-8` back in `_doc_summary`, so a leading U+FEFF stands
in front of `---` and `#`: the document is named by its heading instead of its front-matter
`summary`, or by its file name when it has no front matter.
"""

TEST = "tests/test_a_document_summary_reads_the_same_with_a_bom.py"

MUTATIONS = [
    ("a document saved with a BOM loses its summary", "beeverforge/orchestrator/context.py",
     '    text = path.read_text(encoding="utf-8-sig")\n',
     '    text = path.read_text(encoding="utf-8")\n'),
]
