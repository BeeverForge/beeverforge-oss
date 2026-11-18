"""A `product.yaml`, or a compose file a preview reads, that is not UTF-8 is named, never raised.

Both readers of `.beeverforge/product.yaml` read it as UTF-8 text and caught only `OSError`, or
nothing, so a file saved as Latin-1 or UTF-16 raised `UnicodeDecodeError` out of the product
module and the preview. `beeverforge/util/utf8.py::decode` now turns the bytes into text or into
one sentence naming the file, the offset of the first byte that is not UTF-8 text (a NUL counts,
for UTF-16 without a byte-order mark) and the remedy; the loader reads bytes through it, and the
preview's `_read_inside` returns `NotUtf8`, which each caller turns into its own refusal.

Each row below is one way that could come undone, and the guard must go red on each.
"""

TEST = "tests/test_a_product_yaml_that_is_not_utf8_is_named.py"

_DECODE = "beeverforge/util/utf8.py"
_LOADER = "beeverforge/product/loader.py"
_READ = "beeverforge/preview/read.py"
_PRODUCT = "beeverforge/preview/product.py"

MUTATIONS = [
    ("THE DEFECT: the decoder decodes blindly, so Latin-1, UTF-16 with a mark and invalid bytes "
     "raise out of both readers again",
     _DECODE, "    except UnicodeDecodeError as exc:\n        return None, _refusal(raw, shown, "
     "exc.start)\n",
     "    except ZeroDivisionError as exc:\n        return None, _refusal(raw, shown, "
     "exc.start)\n"),

    ("a NUL is read as text, so UTF-16 without a byte-order mark fails as YAML, naming neither "
     "the offset nor the remedy",
     _DECODE, "    if \"\\x00\" in text:\n", "    if False:\n"),

    ("the product module reads the file as text again",
     _LOADER, "        raw = manifest.read_bytes()\n",
     "        raw = manifest.read_text(encoding=\"utf-8\").encode()\n"),

    ("the preview's reader decodes the file itself, past the decoder",
     _READ, "    text, refused = utf8.decode(raw, shown or ",
     "    text, refused = raw.decode(\"utf-8\"), \"\"\n    (shown or "),

    ("the preview's reader of `product.yaml` passes a refusal on as text",
     _PRODUCT, "    if isinstance(text, NotUtf8):\n        return None, text.reason\n",
     "    if False:\n        return None, text.reason\n"),

    ("a compose file `preview.compose` names is refused as nothing",
     _READ, "        elif isinstance(text, NotUtf8):\n            unread.append(text.reason)\n",
     "        elif False:\n            unread.append(text.reason)\n"),

    ("a file an `extends:` names is kept as text when it is not",
     _READ, "        if isinstance(text, NotUtf8):\n            found = found + Prescan(",
     "        if False:\n            found = found + Prescan("),

    ("the product's compose files are read past a refusal",
     _PRODUCT,
     "    if isinstance(text, NotUtf8):\n        return Refused(reasons=(text.reason,))\n",
     "    if False:\n        return Refused(reasons=(text.reason,))\n"),

    ("a source's own manifest that is not UTF-8 is handed to the YAML loader",
     _PRODUCT, "    if not isinstance(text, str):\n        return False\n",
     "    if text is None:\n        return False\n"),

    ("the remedy is dropped from the sentence",
     _DECODE, "f\"read{hint} — save it as UTF-8.\")", "f\"read{hint}.\")"),

    ("the offset is counted from one",
     _DECODE, "the byte at offset {at} (", "the byte at offset {at + 1} ("),
]
