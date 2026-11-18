"""Nine more reads of a file a person writes name a file that is not UTF-8, never raise.

Each read used `read_text(encoding="utf-8")`, so a Latin-1 or UTF-16 file raised
`UnicodeDecodeError` out of the command, and UTF-16 without a byte-order mark was read as text full
of NULs. Each now reads bytes through `beeverforge/util/utf8.py::decode` and turns its sentence
into the refusal its function already gives: proposing a preview, the three requirement writers,
superseding, the facts pack's README, the refresh record, the requirement template, the upgrade
from a 0.7 stack (in `carry` and in the command's early check), and the project's manifest as
`load_manifest` and `explain` read it, through one `utf8.text_of`.

Each row below puts one read back to a text read, or drops its refusal, and the guard must go red
on each.
"""

TEST = "tests/test_nine_more_reads_name_a_file_that_is_not_utf8.py"

_PROPOSE = "beeverforge/onboarding/preview_propose.py"
_AUTHORING = "beeverforge/product/authoring.py"
_FACTS = "beeverforge/product/facts.py"
_REFRESH = "beeverforge/product/refresh.py"
_TEMPLATE = "beeverforge/product/template.py"
_UPGRADE = "beeverforge/onboarding/upgrade_from_openfactory.py"
_CLI = "beeverforge/cli.py"
_LOADER = "beeverforge/loader.py"
_EXPLAIN = "beeverforge/orchestrator/explain.py"
_UTF8 = "beeverforge/util/utf8.py"

_REFUSED = ("        if refused:\n"
            "            return refused\n")


def _writer(label: str, call: str) -> tuple[str, str, str, str]:
    """A row in which one requirement writer reads the requirement as text again, past
    `_requirement_text`."""
    return (label, _AUTHORING, call + _REFUSED,
            "        text = target.read_text(encoding=\"utf-8\")\n")


MUTATIONS = [
    ("proposing a preview reads the manifest as text again, so a Latin-1 one raises",
     _PROPOSE,
     "    text, unread = utf8.decode(manifest.read_bytes(), "
     "manifest.relative_to(checkout).as_posix())\n",
     "    text, unread = manifest.read_text(encoding=\"utf-8\"), \"\"\n"),

    ("proposing a preview drafts over a manifest it could not read instead of refusing it",
     _PROPOSE,
     "    if text is None:\n        return Outcome(repo=repo, detail=unread + \" Nothing was "
     "written.\")\n",
     "    if False:\n        return Outcome(repo=repo, detail=unread + \" Nothing was "
     "written.\")\n"),

    ("proposing a preview drafts past the refusal its manifest's reader gave",
     _PROPOSE, "    if isinstance(text, Outcome):\n        return text\n",
     "    if False:\n        return text\n"),

    ("superseding reads a retired requirement as text again",
     _AUTHORING,
     "    text, unread = utf8.decode(matches[0].read_bytes(),\n",
     "    text, unread = matches[0].read_text(encoding=\"utf-8\"), \"\"\n    (\n"),

    ("superseding passes over a requirement it could not read instead of counting it as failed",
     _AUTHORING,
     "        if found is None:\n            failed.append(n)\n",
     "        if found is None:\n            pass\n"),

    ("the requirement writers read the file as text again, past the decoder",
     _AUTHORING,
     "    text, unread = utf8.decode(target.read_bytes(), path)\n",
     "    text, unread = target.read_text(encoding=\"utf-8\"), \"\"\n"),

    ("the requirement writers write over a file they could not read",
     _AUTHORING,
     "    if text is None:\n        return \"\", _unread(path, unread)\n",
     "    if False:\n        return \"\", _unread(path, unread)\n"),

    _writer("recording a decision reads the requirement as text again",
            "        text, refused = _requirement_text(target, path, missing=WriteResult(\n"
            "            ok=False, refusal=NOT_FOUND, detail=_w(language, \"decision_not_found\", "
            "number=number)))\n"),
    _writer("accepting reads the requirement as text again",
            "        text, refused = _requirement_text(target, path, missing=WriteResult(\n"
            "            ok=False, detail=_w(language, \"accept_not_found\", number=number), "
            "refusal=NOT_FOUND))\n"),
    _writer("dropping reads the requirement as text again",
            "        text, refused = _requirement_text(target, path, missing=WriteResult(\n"
            "            ok=False, refusal=NOT_FOUND, detail=_w(language, \"drop_not_found\", "
            "number=number)))\n"),

    ("the facts pack reads its README as text again",
     _FACTS,
     "    text, unread = utf8.decode(readme.read_bytes(), f\"{into.name}/README.md\")\n",
     "    text, unread = readme.read_text(encoding=\"utf-8\"), \"\"\n"),

    ("the facts pack adds the file and rewrites a README it could not read, saying it was added",
     _FACTS,
     "    if text is None:\n        log.warning(\"could not add %s to the product facts: %s "
     "Nothing was written.\"",
     "    if False:\n        log.warning(\"could not add %s to the product facts: %s "
     "Nothing was written.\""),

    ("the facts pack writes the file before it decides the README, so a refused file is on disk",
     _FACTS,
     "    readme = into / \"README.md\"\n    text, unread = utf8.decode(readme.read_bytes(), ",
     "    (into / name).parent.mkdir(parents=True, exist_ok=True)\n    write(into / name)\n"
     "    readme = into / \"README.md\"\n    text, unread = utf8.decode(readme.read_bytes(), "),

    ("the refresh record is decoded blindly again, so the state says only \"could not be read\"",
     _REFRESH, "    text, unread = utf8.decode(raw, str(path))\n",
     "    text, unread = raw.decode(\"utf-8\"), \"\"\n"),

    ("the refresh record's state drops the decoder's sentence for the generic line",
     _REFRESH, "str(exc) if isinstance(exc, _NotUtf8) else",
     "str(exc) if isinstance(exc, ZeroDivisionError) else"),

    ("a record that is not UTF-8 is refused as a plain ValueError, its sentence lost to the state",
     _REFRESH, "        raise _NotUtf8(unread)\n", "        raise ValueError(\"not UTF-8\")\n"),

    ("the template is decoded blindly again, refused in the codec's words or raised as YAML",
     _TEMPLATE, "    return utf8.decode(raw, TEMPLATE_FILE)\n",
     "    return raw.decode(\"utf-8\", errors=\"replace\"), \"\"\n"),

    ("THE UPGRADE: a 0.7 file that is not UTF-8 is read as not 0.7, so the installer rewrites it",
     _UPGRADE, "    if text is None:\n        raise Refused(",
     "    if False:\n        raise Refused("),

    ("the upgrade reads the 0.7 file as text again, so a Latin-1 one raises out of the carry",
     _UPGRADE, "    text, unread = utf8.decode(raw, str(path))\n",
     "    text, unread = raw.decode(\"utf-8\"), \"\"\n"),

    ("the command's early check is made outside the `try`, so its refusal is a traceback",
     _CLI,
     "    try:\n        # the early check refuses as the carry does: a file that is not UTF-8 "
     "text is said here\n        if not chosen and up.is_a_0_7_file(Path(env_file)):\n",
     "    if not chosen and up.is_a_0_7_file(Path(env_file)):\n        pass\n    try:\n"
     "        if False:\n"),

    ("loading a manifest reads it as text in the machine's locale again, so a Latin-1 one raises",
     _LOADER, "yaml_io.load(utf8.text_of(manifest_file, str(manifest_file)))",
     "yaml_io.load(manifest_file.read_text())"),

    ("explaining a project reads its manifest as text again, refused in the codec's words",
     _EXPLAIN, "yaml_io.load(utf8.text_of(manifest_file, shown))",
     "yaml_io.load(manifest_file.read_text())"),

    ("the manifest's one reader parses a manifest it could not read instead of refusing it by name",
     _UTF8, "    if text is None:\n        raise ValueError(unread)\n",
     "    if False:\n        raise ValueError(unread)\n"),
]
