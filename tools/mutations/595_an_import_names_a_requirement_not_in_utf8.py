"""An import that would change a requirement file that is not UTF-8 names it and lands nothing.

`land` read the requirement whose register a folder's rows join with
`read_text(encoding="utf-8")`, so a Latin-1 or UTF-16 file raised `UnicodeDecodeError` out of the
import part-way through writing its plan. It now reads the bytes through
`beeverforge/util/utf8.py::decode` and fails as `not_utf8`, the decoder's sentence (the file, the
byte offset, the remedy) kept in `Landed.unread` and put in the person's sentence by
`_land_failed`. A revision whose old requirement is not UTF-8 says the same, instead of only that
it could not be marked replaced.

Each row below puts one read back to a text read, drops a refusal, or drops the sentence, and the
guard must go red on each.
"""

TEST = "tests/test_an_import_names_a_requirement_not_in_utf8.py"

IMPORTING = "beeverforge/product/importing.py"
AUTHORING = "beeverforge/product/authoring.py"

MUTATIONS = [
    ("joining decisions reads the requirement as text again, so a Latin-1 one raises",
     IMPORTING,
     "    read, unread = utf8.decode(twin.read_bytes(), row.path)\n",
     "    read, unread = twin.read_text(encoding=\"utf-8\"), \"\"\n"),

    ("the rows are joined into a requirement the decoder refused, and the file written over",
     IMPORTING,
     "    if read is None:\n        log.error(\"BEEVERFORGE_PRODUCT_IMPORT_NOT_UTF8",
     "    if False:\n        log.error(\"BEEVERFORGE_PRODUCT_IMPORT_NOT_UTF8"),

    ("the person's sentence drops the decoder's, so it names neither the file nor the offset",
     IMPORTING,
     "\"unread\": done.unread or \"—\"}",
     "\"unread\": \"—\"}"),

    ("a revision over a requirement that is not UTF-8 stops saying why it failed",
     IMPORTING,
     "                    done.unread = _not_utf8(root, folder, failed)\n",
     "                    done.unread = \"\"\n"),

    ("the revision's lookup hands back no sentence, so a requirement that is not UTF-8 reads as "
     "one that was readable",
     AUTHORING,
     "    return _numbered(root / requirements_dir.strip(\"/\"), requirements_dir, n)[2]\n",
     "    return \"\"\n"),
]
