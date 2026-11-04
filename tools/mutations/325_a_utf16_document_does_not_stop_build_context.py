"""A document that is not UTF-8 is named in the log and indexed by its file name (#325).

WHAT THE ROWS BREAK: row 1 narrows the `except UnicodeDecodeError` in `_doc_summary` to an
exception the read cannot raise, so a UTF-16 or Latin-1 document stops `build_context` with a raw
`UnicodeDecodeError` again. Row 2 drops the warning, so the document is skipped silently and the
log no longer names the file, the cause and the remedy.
"""

TEST = "tests/test_a_utf16_document_does_not_stop_build_context.py"

MUTATIONS = [
    ("a document that is not UTF-8 raises again", "beeverforge/orchestrator/context.py",
     "    except UnicodeDecodeError as exc:\n",
     "    except LookupError as exc:\n"),
    ("a document that is not UTF-8 is skipped without a word", "beeverforge/orchestrator/context.py",
     '        _log.warning("%s is not UTF-8 (%s) — it is indexed by its file name; save it as UTF-8",\n'
     "                     path.name, exc.reason)\n",
     "        del exc\n"),
]
