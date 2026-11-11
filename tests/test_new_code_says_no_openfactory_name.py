"""New code outside the compatibility layer says no OpenFactory 0.7 name (#264).

BeeverForge still reads OpenFactory 0.7's names until the release `beeverforge/deprecations.py`
names for each: the `openfactory` command and import, `OPENFACTORY_*`, the `openfactory.adapters`
group, the `openfactory.*` documents and the Temporal names. A few more are read with no end set:
the `.openfactory/` folders, `~/.openfactory/`, the journals and a 0.7 stack's volumes. Each of
those lives somewhere in the code, and the day 1.1 removes them, every place must be found. A new
`openfactory` name written after the rename, a path, an id, a variable, an import, is one more
place nobody registered: it outlives the cut, or it is a new reader of the old name. So this guard
walks the tree and fails on any `openfactory` name it does not already know.

WHAT A NAME IS. A word code reads: `openfactory` in any case and spelling (`open_factory`,
`Open-Factory`), with the path, id and identifier characters around it (`.openfactory/**`,
`openfactory-jobs`, `OPENFACTORY_*`, `upgrade_from_openfactory`, `OpenFactoryError`,
`openFactory`). The product's name standing alone, "OpenFactory 0.7", is prose: a message may say
what a deployment upgrades from, wherever it is. In Python, it is read from every string and bytes
constant that is not a docstring (f-string pieces included) and every identifier: a name, an
attribute, an import, a definition, an argument, a keyword, an `except ... as`, a `global` or
`nonlocal`, a capture in a `match`. A comment is never read. In the other files, from every line
that is not a comment.

WHERE IT MAY BE. `LAYER`: the modules that exist to read the old names, where any number may be;
each must still say one, or its entry is stale. `PINNED`: every other file that serves an old name,
with the exact names it says today. A new name there fails as surely as one in a new file, and a
name gone from it fails too, so the pin is updated and never outlives the code.

AND WHY. Every file of the two lists is claimed by the register, both ways: an entry of
`deprecations.REMOVALS` names its files in `paths`, and a file that serves only a name kept with no
end set is in `KEPT_WITH_NO_END`, with what it keeps. A file nothing claims fails, and so does a
claimed file that is in neither list. So removing an entry at its release fails here until its
files stop saying its names and leave the lists, and a new name passes only with a release or a
stated reason behind it.

WHAT IS READ. The `beeverforge` and `openfactory` packages, the images' Dockerfiles, the installer,
`pyproject.toml`, the compose file, the example environment files, `deploy/`, the `Makefile`, the
workflows and the release scripts. Tests, docs and the changelog quote the old names on purpose.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable, Iterator
from pathlib import Path

import pytest

from beeverforge import deprecations
from tests.the_tree_read_once import parsed

ROOT = Path(__file__).resolve().parents[1]

#: An OpenFactory name as code says it: the word in any case, joined by nothing, `-` or `_`, at a
#: word's start or a camelCase hump (`myOpenFactory`), and not running on in lower case
#: (`openfactoryx` is another word), with the path, id and identifier characters around it.
NAME = re.compile(r"[\w.~/*-]*(?:(?<![A-Za-z0-9])|(?<=[a-z0-9])(?=O))"
                  r"[Oo][Pp][Ee][Nn][-_]?[Ff][Aa][Cc][Tt][Oo][Rr][Yy](?![a-z0-9])[\w.~/*-]*")
#: The product named in a sentence: the word alone, as a sentence spells it, a full stop or
#: Markdown's emphasis around it included (`**OpenFactory 0.7's names**`).
PROSE = "OpenFactory"

#: The register itself: it names every old name, and is what claims the files below.
REGISTER = "beeverforge/deprecations.py"

#: The compatibility layer: modules whose job is the old names, so any number may appear.
LAYER = {
    "openfactory/__init__.py": "the `openfactory` import name, an alias of `beeverforge`",
    REGISTER: "the removal register: every old name and its release",
    "beeverforge/former_names.py": "reads `OPENFACTORY_*` as `BEEVERFORGE_*`",
    "beeverforge/former_command.py": "the `openfactory` command, an alias that warns",
    "beeverforge/former_in_use.py": "the doctor's list of old names a deployment still uses",
    "beeverforge/onboarding/upgrade_from_openfactory.py":
        "carries a 0.7 compose stack's volumes and settings",
    "beeverforge/onboarding/migrate_folder.py": "`beeverforge migrate`: renames `.openfactory/`",
}

#: Every other file that serves an old name, with the names it says, sorted, one per use.
PINNED = {
    "beeverforge/certify/controls.py": [".openfactory/**"],
    "beeverforge/certify/redact.py": [".openfactory/**", ".openfactory/project.yaml",
                                      "~/.openfactory/env"],
    "beeverforge/certify/schema.py": ["openfactory-documents", "openfactory.certify/1"],
    "beeverforge/certify/verify.py": ["openfactory.certify.thresholds/1"],
    "beeverforge/cli.py": [".openfactory", ".openfactory/", "OPENFACTORY_*",
                           "upgrade-from-openfactory", "upgrade_from_openfactory",
                           "upgrade_from_openfactory_cmd"],
    "beeverforge/namespace.py": [".openfactory"],
    "beeverforge/paths.py": [".openfactory-logs"],
    "beeverforge/plugins.py": ["openfactory-adapters", "openfactory.adapters"],
    "beeverforge/runtime/temporal/__init__.py": ["openfactory-", "openfactory-jobs"],
    "beeverforge/runtime/temporal/schedule.py": [
        "openfactory-card-questions", "openfactory-okf-refresh", "openfactory-poller",
        "openfactory-preview-reaper", "openfactory-product-sweep", "openfactory-techlead-watch"],
    "beeverforge/certify/pack.schema.json": ["openfactory.certify/1"],
    "beeverforge/org_defaults/floor.yaml": [".openfactory/**"],
    "docker/cli.Dockerfile": ["./openfactory", "openfactory"],
    "docker/sandbox.Dockerfile": ["./openfactory", "openfactory"],
    "docker/worker.Dockerfile": ["./openfactory", "openfactory"],
    "install.sh": ["OPENFACTORY_WORK_DIR", "openfactory", "upgrade-from-openfactory",
                   "upgrade-from-openfactory"],
    "pyproject.toml": ["openfactory", "openfactory"],
}

#: The files that serve a name read with NO END SET, so no entry of the register claims them: the
#: product's call, not a removal waiting for a release. Each says what it keeps.
KEPT_WITH_NO_END = {
    "beeverforge/certify/controls.py": "the floor protects a repository's `.openfactory/` too",
    "beeverforge/certify/redact.py": "a pack redacts `.openfactory/` and `~/.openfactory/env`",
    "beeverforge/cli.py": "`beeverforge migrate` and `upgrade-from-openfactory`",
    "beeverforge/namespace.py": "a repository's `.openfactory/` folder is read",
    "beeverforge/paths.py": "a 0.7 checkout's journals in `.openfactory-logs/`",
    "beeverforge/org_defaults/floor.yaml": "the floor protects a repository's `.openfactory/`",
    "beeverforge/former_in_use.py": "the doctor lists `~/.openfactory/` and the 0.7 journals",
    "beeverforge/onboarding/upgrade_from_openfactory.py": "a 0.7 compose stack's data is carried",
    "beeverforge/onboarding/migrate_folder.py": "a repository's `.openfactory/` is renamed",
    "install.sh": "the installer carries a 0.7 compose stack's data",
}

#: What is read besides the two packages, by path from the root.
SCANNED = ("docker", "deploy", "install.sh", "pyproject.toml", "docker-compose.yml",
           ".env.example", ".env.compose.example", ".dockerignore", "Makefile", ".github",
           "scripts")

#: Files the scan must reach, by name: the import alias, the command line, an image, the installer,
#: the floor, the build. A scan that lost a kind of file would still pass with nothing to report.
MUST_SCAN = ("openfactory/__init__.py", "beeverforge/cli.py", "docker/worker.Dockerfile",
             "install.sh", "beeverforge/org_defaults/floor.yaml", "pyproject.toml", "Makefile",
             "scripts/release_notes.py")


def _docstrings(tree: ast.AST) -> set[int]:
    found: set[int] = set()
    for node in ast.walk(tree):
        if (isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and node.body and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)):
            found.add(id(node.body[0].value))
    return found


def _words(node: ast.AST) -> list[str]:
    """What a node says as code: a string's text, or the identifier it binds or reads."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.Constant) and isinstance(node.value, bytes):
        return [node.value.decode("latin-1")]
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        return [node.attr]
    if isinstance(node, ast.alias):
        return [node.name, node.asname or ""]
    if isinstance(node, ast.ImportFrom):
        return [node.module or ""]
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return [node.name]
    if isinstance(node, ast.arg):
        return [node.arg]
    if isinstance(node, ast.keyword):
        return [node.arg or ""]
    if isinstance(node, ast.ExceptHandler):
        return [node.name or ""]
    if isinstance(node, (ast.Global, ast.Nonlocal)):
        return list(node.names)
    if isinstance(node, (ast.MatchAs, ast.MatchStar)):
        return [node.name or ""]
    if isinstance(node, ast.MatchMapping):
        return [node.rest or ""]
    return []


def names_in_words(words: Iterable[str]) -> list[str]:
    return sorted(name for word in words for name in NAME.findall(word)
                  if name.strip("*.") != PROSE)


def names_in_python(tree: ast.AST) -> list[str]:
    prose = _docstrings(tree)
    return names_in_words(word for node in ast.walk(tree) if id(node) not in prose
                          for word in _words(node))


def _code_lines(text: str, path: str) -> list[str]:
    """The lines a machine reads. Markdown and JSON have no comments: a role prompt is read by a
    model, so all of it counts. A shell script, a Dockerfile or a Makefile loses its comment lines
    only, since ` #` can sit inside a quoted string; YAML, TOML and environment files lose trailing
    comments too. The panel loses its HTML and script comments."""
    lines = text.splitlines()
    if path.endswith((".md", ".json")):
        return lines
    if path.endswith(".html"):
        text = re.sub(r"<!--.*?-->|/\*.*?\*/", "", text, flags=re.S)
        return [line for line in text.splitlines() if not line.lstrip().startswith("//")]
    kept = [line for line in lines if not line.lstrip().startswith("#")]
    if path.endswith((".yaml", ".yml", ".toml", ".example")):
        kept = [line.split(" #", 1)[0] for line in kept]
    return kept


def names_in_text(text: str, path: str) -> list[str]:
    return names_in_words(_code_lines(text, path))


def _scanned() -> Iterator[Path]:
    for top in ("beeverforge", "openfactory", *SCANNED):
        start = ROOT / top
        for path in sorted(start.rglob("*")) if start.is_dir() else [start]:
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
                yield path


def names_in(path: Path) -> list[str]:
    if path.suffix == ".py":
        return names_in_python(parsed(path))
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []
    return names_in_text(text, path.name)


def _said() -> dict[str, list[str]]:
    return {str(path.relative_to(ROOT)): names_in(path) for path in _scanned()}


def test_the_scan_sees_every_shape_a_name_takes_in_python():
    """The positive twin: every shape an old name takes, beside a docstring, a comment, the
    product named in a sentence and a longer word, which are not names."""
    planted = ast.parse(
        '"""a module docstring naming `.openfactory/` freely"""\n'
        "import openfactory\n"
        "from openfactory.adapters import x as openfactory_x\n"
        'PATH = "~/.openfactory/env"\n'
        'ENV = f"OPENFACTORY_{name}"\n'
        'QUEUE = "openfactory-jobs"\n'
        "openfactory_home = openfactory_cache\n"
        "beeverforge.openfactory_group = 1\n"
        "def upgrade_from_openfactory(openfactory_dir, *, keep=0):\n"
        '    """a function docstring naming openfactory-jobs"""\n'
        "    global openfactory_g\n"
        "    return run(openfactory_mode=1)\n"
        "def outer():\n"
        "    def inner():\n"
        "        nonlocal openfactory_n\n"
        "class OpenFactoryError(Exception):\n"
        "    pass\n"
        "client = openFactory()\n"
        "mine = myOpenFactory\n"
        "try:\n"
        "    pass\n"
        "except OSError as openfactory_e:\n"
        "    pass\n"
        "match thing:\n"
        "    case {'a': openfactory_v, **openfactory_r}:\n"
        "        pass\n"
        "    case [*openfactory_s]:\n"
        "        pass\n"
        "RAW = b'openfactory-raw'\n"
        "SPELLINGS = ('Open-Factory', 'open_factory', 'Openfactory')\n"
        "# a comment naming openfactory.adapters\n"
        'SAID = "upgrading from OpenFactory 0.7, or from OpenFactory. **OpenFactory 0.7**"\n'
        'OTHER = "openfactoryx reopenfactory"\n'
    )

    assert names_in_python(planted) == sorted([
        "openfactory", "openfactory.adapters", "openfactory_x", "~/.openfactory/env",
        "OPENFACTORY_", "openfactory-jobs", "openfactory_group", "upgrade_from_openfactory",
        "openfactory_dir", "openfactory_mode", "openfactory_home", "openfactory_cache",
        "openfactory_g", "openfactory_n", "OpenFactoryError", "openFactory", "myOpenFactory",
        "openfactory_e", "openfactory_v", "openfactory_r", "openfactory_s", "openfactory-raw",
        "Open-Factory", "open_factory", "Openfactory",
    ]), names_in_python(planted)


@pytest.mark.parametrize("path, text, names", [
    ("floor.yaml", "# `.openfactory/` in a comment\n- '.openfactory/**'  # trailing remark\n",
     [".openfactory/**"]),
    ("x.yaml", "key: value  # names openfactory in a remark\n", []),
    ("install.sh", "# OPENFACTORY_WORK_DIR in a comment\n"
                   'say "step #2: carry the openfactory stack"\n',
     ["openfactory"]),
    ("worker.Dockerfile", "# openfactory in a comment\nCOPY openfactory ./openfactory\n",
     ["./openfactory", "openfactory"]),
    ("panel.html", "<!-- openfactory -->\n<script>\n/* openfactory */\n// openfactory\n"
                   "const k = 'openfactory_token';\n</script>\n", ["openfactory_token"]),
    ("role.md", "# Write `.openfactory/project.yaml`\n", [".openfactory/project.yaml"]),
    (".env.example", "#OPENFACTORY_X=1\nBEEVERFORGE_X=1 # was OPENFACTORY_X\n", []),
    ("Makefile", "# openfactory in a comment\nimage:\n\tdocker build -t openFactory-cli .\n",
     ["openFactory-cli"]),
])
def test_the_scan_sees_a_name_in_a_file_and_leaves_its_comments(path, text, names):
    assert names_in_text(text, path) == names


def unknown(said: dict[str, list[str]]) -> dict[str, list[str]]:
    """The files whose names are not the ones pinned for them: outside the layer, any name in a
    file with no pin, or a list that differs from its pin, by a name more, less or used again."""
    return {path: names for path, names in said.items()
            if path not in LAYER and names != PINNED.get(path, [])}


def test_a_new_name_is_unknown_wherever_it_is_said_outside_the_layer():
    """The positive twin of the comparison, over planted findings: the real tree has none."""
    layer = next(iter(LAYER))
    paths = "beeverforge/paths.py"
    said = {
        "beeverforge/doctor.py": [".openfactory/project.yaml"],
        paths: sorted([*PINNED[paths], ".openfactory-state"]),
        "beeverforge/certify/controls.py": [],
        "beeverforge/plugins.py": sorted([*PINNED["beeverforge/plugins.py"], "openfactory.adapters"]),
        layer: ["openfactory", "openfactory-anything-new"],
        "beeverforge/namespace.py": PINNED["beeverforge/namespace.py"],
        "beeverforge/config.py": [],
    }

    assert sorted(unknown(said)) == sorted(["beeverforge/doctor.py", paths,
                                            "beeverforge/certify/controls.py",
                                            "beeverforge/plugins.py"]), unknown(said)


def test_no_file_says_an_openfactory_name_it_is_not_pinned_to():
    said = _said()

    for must in MUST_SCAN:
        assert must in said, f"the scan never reached {must}: it lost a kind of file"
    unknown_names = unknown(said)
    assert not unknown_names, (
        "these files say OpenFactory 0.7 names other than the ones pinned for them (found, "
        f"then pinned): { {p: (n, PINNED.get(p, [])) for p, n in unknown_names.items()} }. A new "
        "name: use the BeeverForge name instead, or, for a new way to keep reading 0.7's, add "
        "the file to its entry's `paths` in `deprecations.REMOVALS` and pin it here. A name "
        "gone: update its pin.")


def unclaimed(allowed: Iterable[str], removals: Iterable[deprecations.Removal],
              kept: Iterable[str]) -> list[str]:
    """The files allowed an old name that no entry of the register and no kept name claims."""
    claimed = {path for entry in removals for path in entry.paths} | set(kept) | {REGISTER}
    return sorted(set(allowed) - claimed)


def unlisted(allowed: Iterable[str], removals: Iterable[deprecations.Removal],
             kept: Iterable[str]) -> list[str]:
    """The files the register or the kept names claim that are neither layer nor pinned, and the
    entries that claim no file at all."""
    allowed = set(allowed)
    gone = [f"{entry.key}: no paths" for entry in removals if not entry.paths]
    claimed = {path for entry in removals for path in entry.paths} | set(kept)
    return sorted([*gone, *(claimed - allowed)])


def test_the_register_and_the_lists_are_compared_both_ways():
    """The positive twin of the claim, over a planted register."""
    one = deprecations.Removal("one", "1.1", "x", said="x", paths=("a.py", "b.py"))
    none = deprecations.Removal("none", "1.1", "x", said="x")

    assert unclaimed(["a.py", "c.py", "k.py", REGISTER], [one], ["k.py"]) == ["c.py"]
    assert unlisted(["a.py"], [one, none], ["k.py"]) == ["b.py", "k.py", "none: no paths"]


def test_every_file_allowed_an_old_name_is_claimed_by_the_register_or_kept_with_no_end():
    allowed = [*LAYER, *PINNED]

    assert unclaimed(allowed, deprecations.REMOVALS, KEPT_WITH_NO_END) == [], (
        "these files may say an OpenFactory 0.7 name, and no entry of `deprecations.REMOVALS` "
        "names them in its `paths`, nor `KEPT_WITH_NO_END`: name the release that removes "
        "their name, or the reason it is kept, or take them out of LAYER/PINNED")


def test_every_file_the_register_claims_is_allowed_its_names():
    allowed = [*LAYER, *PINNED]

    assert unlisted(allowed, deprecations.REMOVALS, KEPT_WITH_NO_END) == [], (
        "these files are claimed by `deprecations.REMOVALS` or `KEPT_WITH_NO_END` and are in "
        "neither LAYER nor PINNED, or an entry claims no file: a claim that outlived the names, "
        "or a register entry nobody can find in the code")


@pytest.mark.parametrize("path", sorted(LAYER))
def test_every_module_of_the_layer_still_says_an_old_name(path):
    """Staleness: a module exempted whole that no longer says an old name is no longer the
    layer. Delete its entry, so a name it gains later is seen."""
    assert names_in(ROOT / path), f"{path} says no OpenFactory 0.7 name: delete it from LAYER"


def test_a_file_is_either_the_layer_or_pinned_never_both():
    assert not set(LAYER) & set(PINNED), set(LAYER) & set(PINNED)
