"""Five more readers of a file a person or an operator writes name a file that is not UTF-8.

Each read used `read_text(encoding="utf-8")`, so a Latin-1 or UTF-16 file raised
`UnicodeDecodeError` out of its caller, and UTF-16 without a byte-order mark was read as text full
of NULs. Each now reads bytes through `beeverforge/util/utf8.py` (`decode`, or `text_of` with the
reader's own refusal) and turns its sentence into the path it already takes for a file it cannot
read: the preview shape of a pull request
logs it and treats the manifest as having no `preview:` block, the knowledge bundle's manifest
logs it and reads as `None`, and the thresholds file, the evaluation battery and the fixture's
product manifest are refused with their own exception.

Each row below puts one read back to a text read, drops the log that says why a manifest was
set aside, or refuses with a bare `ValueError` instead of the reader's own refusal, and the guard
must go red on each.
"""

TEST = "tests/test_five_more_readers_name_a_file_that_is_not_utf8.py"

_MACHINE = "beeverforge/orchestrator/machine.py"
_OKF = "beeverforge/knowledge/okf.py"
_VERIFY = "beeverforge/certify/verify.py"
_BATTERY = "beeverforge/product/evaluation/battery.py"
_RUN = "beeverforge/product/evaluation/run.py"
_UTF8 = "beeverforge/util/utf8.py"

MUTATIONS = [
    ("the preview shape reads the manifest as text again, so a Latin-1 one raises",
     _MACHINE,
     "    text, unread = utf8.decode((root / manifest_rel).read_bytes(), manifest_rel)\n",
     "    text, unread = (root / manifest_rel).read_text(encoding=\"utf-8\"), \"\"\n"),

    ("the preview shape drops a manifest it could not read without saying why",
     _MACHINE,
     "        log.warning(\"BEEVERFORGE_PREVIEW_SHAPE_NOT_UTF8 %s\", unread)\n",
     "        pass\n"),

    ("the knowledge manifest is read as text again",
     _OKF,
     "        text, unread = utf8.decode(path.read_bytes(), str(path))\n    except OSError:\n"
     "        return \"\"\n",
     "        text, unread = path.read_text(encoding=\"utf-8\"), \"\"\n    except OSError:\n"
     "        return \"\"\n"),

    ("the knowledge manifest drops a manifest it could not read without saying why",
     _OKF,
     "        log.warning(\"BEEVERFORGE_OKF_MANIFEST_NOT_UTF8 %s\", unread)\n",
     "        pass\n"),

    ("the thresholds file is read as text again",
     _VERIFY,
     "        data = yaml_io.load(utf8.text_of(where, str(where), ThresholdsError))\n",
     "        data = yaml_io.load(where.read_text(encoding=\"utf-8\"))\n"),

    ("the thresholds file is refused as a bare `ValueError`, not as thresholds",
     _VERIFY,
     "        data = yaml_io.load(utf8.text_of(where, str(where), ThresholdsError))\n",
     "        data = yaml_io.load(utf8.text_of(where, str(where)))\n"),

    ("the battery is read as text again",
     _BATTERY,
     "        data = yaml_io.load(utf8.text_of(path, str(path), BatteryRefused))\n",
     "        data = yaml_io.load(path.read_text(encoding=\"utf-8\"))\n"),

    ("the battery is refused as a bare `ValueError`, not as a battery",
     _BATTERY,
     "        data = yaml_io.load(utf8.text_of(path, str(path), BatteryRefused))\n",
     "        data = yaml_io.load(utf8.text_of(path, str(path)))\n"),

    ("the fixture's product manifest is read as text again",
     _RUN,
     "        data = yaml_io.load(utf8.text_of(manifest, str(manifest), FixtureRefused)) or {}\n",
     "        data = yaml_io.load(manifest.read_text(encoding=\"utf-8\")) or {}\n"),

    ("the fixture's product manifest is refused as a bare `ValueError`, not as a fixture",
     _RUN,
     "        data = yaml_io.load(utf8.text_of(manifest, str(manifest), FixtureRefused)) or {}\n",
     "        data = yaml_io.load(utf8.text_of(manifest, str(manifest))) or {}\n"),

    ("the shared reader raises a bare `ValueError` whatever refusal its reader asked for",
     _UTF8,
     "        raise refused(unread)\n",
     "        raise ValueError(unread)\n"),
]
