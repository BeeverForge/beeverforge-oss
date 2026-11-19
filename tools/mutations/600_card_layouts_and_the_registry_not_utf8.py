"""A product's card template and rubric, the operator's registry and its seed name a file that is
not UTF-8.

Each read used a bare `read_text()`, so a Latin-1 or UTF-16 file raised `UnicodeDecodeError` (or
decoded by the machine's locale), and UTF-16 without a byte-order mark was read as text full of
NULs. Each now reads bytes through `beeverforge/util/utf8.py` (`decode` for the template, whose
refusal is a value; `text_of` for the others, whose refusal is a `ValueError` already handled) and
takes the path it already takes for a file it cannot use: the template and the rubric are refused
by name and the next candidate or the shipped one is used, the registry raises its `ValueError`,
and the seed is not seeded and says why. The shipped layouts are read as explicit UTF-8.

Each row below puts one read back to a text read, drops the decoder's sentence from the template
refusal, or drops the explicit encoding of the shipped read, and the guard must go red on each.
"""

TEST = "tests/test_card_layouts_and_the_registry_name_a_file_that_is_not_utf8.py"

_CARDS = "beeverforge/product/cards.py"
_REGISTRY = "beeverforge/registry.py"

MUTATIONS = [
    ("the product's template is read as text again, so a Latin-1 one raises",
     _CARDS,
     "    text, unread = utf8.decode(own.read_bytes(), str(own))\n",
     "    text, unread = own.read_text(encoding=\"utf-8\"), \"\"\n"),

    ("the product's template is refused without the decoder's sentence",
     _CARDS,
     "    if text is None:\n        return \"\", unread\n",
     "    if text is None:\n        return \"\", \"unreadable\"\n"),

    ("the product's rubric is read as text again",
     _CARDS,
     "            return Rubric.parse(utf8.text_of(own, str(own)), "
     "source=f\"{OVERRIDE_DIR}/{RUBRIC_FILE}\")\n",
     "            return Rubric.parse(own.read_text(encoding=\"utf-8\"), "
     "source=f\"{OVERRIDE_DIR}/{RUBRIC_FILE}\")\n"),

    ("the shipped layouts are read in the machine's locale again",
     _CARDS,
     "    return (_DEFAULTS / name).read_text(encoding=\"utf-8\")\n",
     "    return (_DEFAULTS / name).read_text()\n"),

    ("the registry is read as text again, so a Latin-1 one raises a codec error",
     _REGISTRY,
     "            data = yaml_io.load(utf8.text_of(self.path, str(self.path))) or {}\n",
     "            data = yaml_io.load(self.path.read_text(encoding=\"utf-8\")) or {}\n"),

    ("the seed is read as text again, so its warning carries a codec error",
     _REGISTRY,
     "        seeded = yaml_io.load(utf8.text_of(seed_path, str(seed_path))) or {}\n",
     "        seeded = yaml_io.load(seed_path.read_text(encoding=\"utf-8\")) or {}\n"),
]
