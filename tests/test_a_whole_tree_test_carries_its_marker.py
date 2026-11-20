"""A test that walks this repository's tree carries `whole_tree`, and only such a test does (#545).

WHY THE MARKER EXISTS. About 290 tests read the whole checkout — `rglob("*.py")` over the package,
`git ls-files` over the repository — and the guards among them each hold a parsed copy of it
(`tests/the_tree_read_once.py`: ~260 MB a worker, while the module that asked runs). A gate on a box with few CPUs and little memory
can leave them out with `-m "not whole_tree"`; CI still runs them before a human merges. A label
that nobody holds to the code is a promise, so this file holds it both ways:

  - a test that walks the tree without the marker is a test the small box would still run, and
    the next such test lands unmarked unless something says so;
  - a test that carries the marker and walks nothing is a test the small box needlessly drops.

WHAT "WALKS" MEANS is `tests/whole_tree_walks.py`: it is read from the source, never by running a
test, and a walk of a `tmp_path` or a fixture directory does not count. Nor does a glob that does
not recurse: the two guards in `test_ci_runs_every_test_exactly_once.py` that read every
`tests/test_*.py` stay unmarked on purpose (#619). They run in the unit selection and keep no tree
(`the_tree_read_once.fact`), so the small box pays ~4 s of parsing and no memory for them.
"""

from __future__ import annotations

import functools
import tomllib
from pathlib import Path

import pytest

from tests.whole_tree_walks import MARKER, analyse

ROOT = Path(__file__).resolve().parent.parent

# Fewer test modules than this means the scan could not see the suite, not that the suite is clean
# (docs/engineering-lessons.md §2). On 5e6f491, `tests/` held 1,000+ modules and 14,000+ tests.
FLOOR_MODULES = 800
# Fewer walking tests than this means the detector went blind: 290 on the same commit.
FLOOR_WALKING = 200


def _test_roots() -> list[Path]:
    """What pytest collects when it is named nothing (`testpaths`), kept to what the tree holds."""
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return sorted({p for pattern in config["tool"]["pytest"]["ini_options"]["testpaths"]
                   for p in ROOT.glob(pattern) if p.is_dir()})


@functools.cache
def _suite():
    sources = {path.relative_to(ROOT).as_posix(): path.read_text(encoding="utf-8")
               for top in _test_roots() for path in sorted(top.rglob("*.py"))}
    return analyse(sources)


def _tests():
    for path, tests in _suite().items():
        for name, facts in tests.items():
            yield path, name, facts


# ── the suite ────────────────────────────────────────────────────────────────────────────────


@pytest.mark.whole_tree
def test_the_scan_sees_the_suite():
    suite = _suite()
    assert len(suite) > FLOOR_MODULES, f"the scan read {len(suite)} modules; it could not see the suite"
    walking = [1 for _, _, facts in _tests() if facts.walk]
    assert len(walking) > FLOOR_WALKING, (
        f"{len(walking)} tests walk the tree, the floor is {FLOOR_WALKING}: the detector is blind"
    )


@pytest.mark.whole_tree
def test_a_test_that_walks_the_tree_carries_the_marker():
    offenders = [f"{path}::{name} walks the tree at {facts.walk}"
                 for path, name, facts in _tests() if facts.walk and not facts.marked]
    assert not offenders, (
        f"{len(offenders)} tests walk the repository without `@pytest.mark.{MARKER}` (a module "
        f"whose every test walks says `pytestmark = pytest.mark.{MARKER}` instead):\n  "
        + "\n  ".join(offenders)
    )


@pytest.mark.whole_tree
def test_a_test_that_carries_the_marker_walks_the_tree():
    offenders = [f"{path}::{name} (line {facts.line})"
                 for path, name, facts in _tests() if facts.marked and not facts.walk]
    assert not offenders, (
        f"{len(offenders)} tests carry `{MARKER}` and walk no part of the repository, so a small "
        "box would drop them for nothing; take the marker off:\n  " + "\n  ".join(offenders)
    )


@pytest.mark.whole_tree
def test_a_module_whose_every_test_walks_marks_the_module():
    offenders = []
    for path, tests in _suite().items():
        if tests and all(f.walk for f in tests.values()) and not all(f.marked for f in tests.values()):
            offenders.append(path)
        elif tests and all(f.walk for f in tests.values()):
            source = (ROOT / path).read_text(encoding="utf-8")
            if "pytestmark" not in source:
                offenders.append(path)
    assert not offenders, (
        f"every test of these walks the tree, so say `pytestmark = pytest.mark.{MARKER}` once at "
        "module level instead of on each test:\n  " + "\n  ".join(offenders)
    )


def test_the_marker_is_registered_with_what_it_is_for():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    markers = config["tool"]["pytest"]["ini_options"]["markers"]
    assert [m for m in markers if m.startswith(f"{MARKER}:")], f"`{MARKER}` is not registered"
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    head = text.split(f'"{MARKER}:', 1)[0].rsplit("\n    \"", 1)[-1]
    assert "CI still runs" in head, "the comment above the marker does not say CI still runs it"


# ── the detector, on the shapes the suite writes ─────────────────────────────────────────────


def _one(source: str, marked: bool = False) -> dict:
    text = (f"import pytest\n{'pytestmark = pytest.mark.whole_tree' if marked else ''}\n" + source)
    return analyse({"tests/test_planted.py": text})["tests/test_planted.py"]


WALKS = {
    "rglob over the package": (
        'from pathlib import Path\nROOT = Path(__file__).resolve().parent.parent\n'
        'def test_it():\n    for p in (ROOT / "beeverforge").rglob("*.py"):\n        pass\n'),
    "rglob over a relative directory": (
        'from pathlib import Path\ndef test_it():\n    list(Path("beeverforge").rglob("*.py"))\n'),
    "os.walk over the root": (
        'import os\nfrom pathlib import Path\nROOT = Path(__file__).parent\n'
        'def test_it():\n    list(os.walk(ROOT))\n'),
    "git ls-files in the working directory": (
        'import subprocess\ndef test_it():\n'
        '    subprocess.run(["git", "ls-files"], capture_output=True)\n'),
    "git ls-files in the checkout": (
        'import subprocess\nfrom pathlib import Path\nROOT = Path(__file__).parent\n'
        'def test_it():\n    subprocess.run(["git", "ls-files"], cwd=ROOT)\n'),
    "a helper that walks": (
        'from pathlib import Path\nROOT = Path(__file__).parent\n'
        'def _files():\n    return sorted(ROOT.rglob("*.py"))\n'
        'def test_it():\n    assert _files()\n'),
    "a helper handed the root": (
        'from pathlib import Path\nROOT = Path(__file__).parent\n'
        'def _files(top):\n    return sorted(top.rglob("*.py"))\n'
        'def test_it():\n    assert _files(ROOT)\n'),
    "a module constant that walks": (
        'from pathlib import Path\nFILES = sorted(Path("beeverforge").rglob("*.py"))\n'
        'def test_it():\n    assert FILES\n'),
    "a fixture that walks": (
        'from pathlib import Path\n@pytest.fixture\ndef files():\n'
        '    return sorted(Path("beeverforge").rglob("*.py"))\n'
        'def test_it(files):\n    assert files\n'),
    "a recursive glob": (
        'from pathlib import Path\nROOT = Path(__file__).parent\n'
        'def test_it():\n    list(ROOT.glob("docs/**/*.md"))\n'),
    "a package found from an imported module": (
        'import inspect\nimport os\nfrom pathlib import Path\n'
        'def test_it():\n    list(Path(inspect.getfile(os)).parent.rglob("*.py"))\n'),
    "a method of a test class": (
        'from pathlib import Path\nclass TestIt:\n    def test_it(self):\n'
        '        list(Path("beeverforge").rglob("*.py"))\n'),
}

WALKS_NOTHING = {
    "a tmp_path": 'def test_it(tmp_path):\n    list(tmp_path.rglob("*"))\n',
    "a directory under a tmp_path": (
        'def test_it(tmp_path):\n    list((tmp_path / "beeverforge").rglob("*.py"))\n'),
    "a helper handed a tmp_path": (
        'def _files(top):\n    return sorted(top.rglob("*"))\n'
        'def test_it(tmp_path):\n    assert not _files(tmp_path)\n'),
    "a fixture directory": (
        'from pathlib import Path\nFIXTURES = Path(__file__).parent / "fixtures"\n'
        'def test_it():\n    list((FIXTURES / "one").rglob("*"))\n'),
    "git ls-files in a tmp_path": (
        'import subprocess\ndef test_it(tmp_path):\n'
        '    subprocess.run(["git", "ls-files"], cwd=tmp_path)\n'),
    "a non-recursive glob": (
        'from pathlib import Path\nROOT = Path(__file__).parent\n'
        'def test_it():\n    list(ROOT.glob("*.md"))\n'),
    "no walk at all": 'def test_it():\n    assert 1 + 1 == 2\n',
    "a helper that is never used": (
        'from pathlib import Path\ndef _files():\n    return sorted(Path("beeverforge").rglob("*"))\n'
        'def test_it():\n    assert 1\n'),
}


@pytest.mark.parametrize("shape", sorted(WALKS))
def test_the_detector_sees_every_shape_of_a_walk(shape):
    facts = _one(WALKS[shape])["test_it" if "class" not in shape else "TestIt.test_it"]
    assert facts.walk is not None, f"the detector does not see: {shape}"


@pytest.mark.parametrize("shape", sorted(WALKS_NOTHING))
def test_the_detector_leaves_a_walk_of_somebody_elses_directory_alone(shape):
    facts = _one(WALKS_NOTHING[shape])["test_it"]
    assert facts.walk is None, f"the detector flags {shape}: {facts.walk}"


def test_the_site_names_the_file_and_the_call():
    facts = _one(WALKS["rglob over the package"])["test_it"]
    assert str(facts.walk).startswith("tests/test_planted.py:")
    assert ".rglob" in str(facts.walk)


@pytest.mark.parametrize("how", ["module", "decorator", "class"])
def test_the_detector_reads_each_way_to_carry_the_marker(how):
    body = 'from pathlib import Path\ndef {name}():\n    list(Path("beeverforge").rglob("*"))\n'
    plain = body.format(name="test_it")
    if how == "module":
        facts = _one(plain, marked=True)["test_it"]
    elif how == "decorator":
        facts = _one(plain.replace("def test_it", "@pytest.mark.whole_tree\ndef test_it"))["test_it"]
    else:
        facts = _one("@pytest.mark.whole_tree\nclass TestIt:\n    def test_it(self):\n"
                     '        list(__import__("pathlib").Path("beeverforge").rglob("*"))\n'
                     )["TestIt.test_it"]
    assert facts.marked
    assert not _one(plain)["test_it"].marked
