"""Every release's notes say what is still read under an OpenFactory 0.7 name, and until when (#264).

#264 promises that the old names are removed in 1.1 "and every release's notes up to then say
so". The removal register (`beeverforge/deprecations.py`) already stops the release that removes
one from being cut with it still in, but the notes said it once: in the fragment of the pull
request that kept the name readable, and never again. So `scripts/release_notes.py` adds one
item to every version's "Upgrade notes", made from the register: each name still read, as a
reader says it (`Removal.said`), and the release that stops reading it. The register is READ
(`ast`), never imported: the script runs on a bare runner's `python3`, with the standard library
only. A register it cannot read fails the preview and the assembly, so a version is never
published silently without the item; it never fails a release page.
"""

from __future__ import annotations

import ast
import re
import shutil
from pathlib import Path

import pytest
from test_a_release_is_noted_by_its_pull_requests import (
    NOTES,
    ROOT,
    TYPES,
    _declare,
    _fragment,
    _run,
)

from beeverforge import deprecations
from tests.the_tree_read_once import parsed

REGISTER = ROOT / "beeverforge" / "deprecations.py"
HEADING = "### " + dict(TYPES)["upgrade"]


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """A checkout's root as the script reads one, with this tree's own removal register."""
    (tmp_path / "changes").mkdir()
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\nWhat changed in each release.\n")
    _declare(tmp_path, "0.7.0.dev0")
    (tmp_path / "beeverforge").mkdir()
    shutil.copy(REGISTER, tmp_path / "beeverforge" / "deprecations.py")
    return tmp_path


def _upgrade_group(notes: str) -> str:
    start = notes.index(HEADING)
    following = notes.find("\n### ", start + 1)
    return notes[start:] if following < 0 else notes[start:following]


def _expected_rows() -> list[str]:
    return [f"  - {entry.said}: until {entry.removed_in}" for entry in deprecations.REMOVALS]


def test_every_name_the_register_holds_is_said_with_its_release(tree):
    _fragment(tree, "12.upgrade.md", "An upgrade line.")

    group = _upgrade_group(_run(tree, "preview", "0.7.0").stdout)

    assert "- An upgrade line (#12)." in group
    for row in _expected_rows():
        assert row in group.splitlines(), f"{row!r} not in {group!r}"
    assert group.index("An upgrade line") < group.index("OpenFactory 0.7"), "the item comes last"


def test_a_version_without_an_upgrade_line_still_says_it_in_its_own_group(tree):
    _fragment(tree, "12.fix.md", "A fix.")
    _fragment(tree, "13.limitation.md", "A limitation.")

    notes = _run(tree, "preview", "0.7.0").stdout

    headings = re.findall(r"^### (.+)$", notes, re.M)
    assert headings == [dict(TYPES)[t] for t in ("fix", "upgrade", "limitation")], headings
    assert all(row in notes.splitlines() for row in _expected_rows()), notes


def test_the_assembly_writes_it_into_the_version_s_section(tree):
    _fragment(tree, "12.fix.md", "A fix.")

    done = _run(tree, "assemble", "0.7.0", "--date", "2026-11-10")

    assert done.returncode == 0, done.stderr
    changelog = (tree / "CHANGELOG.md").read_text()
    section = NOTES.section_of(changelog, "0.7.0")
    assert all(row in section.splitlines() for row in _expected_rows()), section


def test_a_candidate_page_says_it_too(tree):
    _fragment(tree, "12.fix.md", "A fix.")

    page = _run(tree, "page", "v0.7.0-rc.1")

    assert page.returncode == 0, page.stderr
    assert all(row in page.stdout.splitlines() for row in _expected_rows()), page.stdout


def test_with_nothing_left_in_the_register_the_notes_say_nothing_of_it(tree):
    register = tree / "beeverforge" / "deprecations.py"
    text = register.read_text()
    start = text.index("REMOVALS: tuple[Removal, ...] = (")
    end = text.index("\n)\n", start) + 3
    register.write_text(text[:start] + "REMOVALS: tuple[Removal, ...] = ()\n" + text[end:])
    _fragment(tree, "12.fix.md", "A fix.")

    notes = _run(tree, "preview", "0.7.0").stdout

    assert HEADING not in notes and "OpenFactory 0.7" not in notes, notes


def test_the_register_is_read_never_run(tree):
    register = tree / "beeverforge" / "deprecations.py"
    register.write_text("raise SystemExit('the register ran')\n" + register.read_text())
    _fragment(tree, "12.fix.md", "A fix.")

    preview = _run(tree, "preview", "0.7.0")

    assert preview.returncode == 0, preview.stderr
    assert all(row in preview.stdout.splitlines() for row in _expected_rows()), preview.stdout


@pytest.mark.parametrize("breakage", [
    lambda text: text.replace("REMOVALS: tuple[Removal, ...] = (", "REMOVALS = (", 1)
    .replace("REMOVALS = (", "REMOVALS = (\n    nothing_literal(),", 1),
    lambda text: text + "\n(\n",
    # an entry that says nothing a reader of the notes can read
    lambda text: text.replace("said=", "unsaid=", 1),
    # a keyword `Removal` has no field for: Python refuses it when the package imports the register
    lambda text: text.replace("said=", 'whom="someone", said=', 1),
    lambda text: re.sub(r'said="[^"]*"', 'said=""', text, count=1),
])
def test_a_register_it_cannot_read_fails_the_preview_and_the_assembly_never_the_page(tree,
                                                                                      breakage):
    register = tree / "beeverforge" / "deprecations.py"
    register.write_text(breakage(register.read_text()))
    _fragment(tree, "12.fix.md", "A fix.")

    preview = _run(tree, "preview", "0.7.0")
    assembled = _run(tree, "assemble", "0.7.0", "--date", "2026-11-10")
    page = _run(tree, "page", "v0.7.0-rc.1")

    for refused in (preview, assembled):
        assert refused.returncode == 1, refused.stdout
        assert "beeverforge/deprecations.py" in refused.stderr, refused.stderr
    assert "## 0.7.0" not in (tree / "CHANGELOG.md").read_text()
    assert page.returncode == 0 and "A fix (#12)." in page.stdout, page.stdout
    assert "::warning::" in page.stderr and "deprecations.py" in page.stderr, page.stderr


def test_every_entry_says_what_a_reader_of_the_notes_reads():
    for entry in deprecations.REMOVALS:
        assert entry.said and entry.said == entry.said.strip(), entry
        assert not entry.said.endswith("."), f"{entry.key}: the row adds its own ending"
        assert "beeverforge/" not in entry.said, f"{entry.key}: a reader is told no source path"


def test_the_script_reads_the_register_as_python_reads_it():
    entries, problem = NOTES.still_read(REGISTER)

    assert problem is None
    assert entries == [(e.said, e.removed_in) for e in deprecations.REMOVALS]


def test_the_script_still_imports_the_standard_library_only():
    imported = set()
    for node in ast.walk(parsed(Path(NOTES.__file__))):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    import sys

    assert imported <= set(sys.stdlib_module_names) | {"__future__"}, imported
