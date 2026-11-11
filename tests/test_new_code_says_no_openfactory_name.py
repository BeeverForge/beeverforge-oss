"""New code outside the compatibility layer says no OpenFactory 0.7 name (#264).

BeeverForge still reads OpenFactory 0.7's names until the release `beeverforge/deprecations.py`
names for each: the `openfactory` command and import, `OPENFACTORY_*`, the `openfactory.adapters`
group, the `openfactory.*` documents, the `.openfactory/` folders and the Temporal names. Each of
those lives somewhere in the code, and the day 1.1 removes them, every place must be found. A new
`openfactory` name written after the rename, a path, an id, a variable, an import, is one more
place nobody registered: it outlives the cut, or it is a new reader of the old name. So this guard
walks everything that ships and fails on any `openfactory` name it does not already know.

WHAT A NAME IS. A word code reads: `openfactory` or `OPENFACTORY` as a token, with the path, id
and identifier characters around it (`.openfactory/**`, `openfactory-jobs`, `OPENFACTORY_*`,
`upgrade_from_openfactory`). The product's name in a sentence, "OpenFactory 0.7", is prose: a
message may say what a deployment upgrades from, wherever it is. In Python, it is read from every
string that is not a docstring (f-string pieces included) and every identifier: a name, an
attribute, an import, a definition, an argument, a keyword. A comment is never read. In the other
shipped files, from every line that is not a comment.

WHERE IT MAY BE. `LAYER`: the modules that exist to read the old names, where any number may be;
each must still say one, or its entry is stale. `PINNED`: every other file that serves an old name,
with the exact names it says today. A new name there fails as surely as one in a new file, and a
name gone from it fails too, so the pin is updated and never outlives the code. A failure says
what to do: use the BeeverForge name, or, for a new compatibility path, register it in
`deprecations.REMOVALS` and pin it here.

WHAT IS SHIPPED. The `beeverforge` and `openfactory` packages, the images' Dockerfiles, the
installer, `pyproject.toml`, the compose file, the example environment files and `deploy/`.
Tests, docs, the changelog and the release scripts quote the old names on purpose.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.the_tree_read_once import parsed

ROOT = Path(__file__).resolve().parents[1]

#: An OpenFactory name as code says it. Case-sensitive on purpose: `OpenFactory` is the product
#: named in a sentence; `openfactory`/`OPENFACTORY` is the name a path, an id, a variable or an
#: import carries. `openfactoryx` is another word.
NAME = re.compile(r"[\w.~/*-]*(?<![A-Za-z0-9])(?:openfactory|OPENFACTORY)(?![A-Za-z0-9])[\w.~/*-]*")

#: The compatibility layer: modules whose job is the old names, so any number may appear.
LAYER = {
    "openfactory/__init__.py": "the `openfactory` import name, an alias of `beeverforge`",
    "beeverforge/deprecations.py": "the removal register: every old name and its release",
    "beeverforge/former_names.py": "reads `OPENFACTORY_*` as `BEEVERFORGE_*`",
    "beeverforge/former_command.py": "the `openfactory` command, an alias that warns",
    "beeverforge/former_in_use.py": "the doctor's list of old names a deployment still uses",
    "beeverforge/onboarding/upgrade_from_openfactory.py":
        "carries a 0.7 compose stack's volumes and settings",
    "beeverforge/onboarding/migrate_folder.py": "`beeverforge migrate`: renames `.openfactory/`",
}

#: Every other shipped file that serves an old name, with the names it says, sorted, one per use.
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

#: What ships besides the two packages, by path from the root.
SHIPPED = ("docker", "deploy", "install.sh", "pyproject.toml", "docker-compose.yml",
           ".env.example", ".env.compose.example", ".dockerignore")

#: Files the scan must reach, by name: the import alias, the command line, an image, the installer,
#: the floor. A scan that lost a kind of file would still pass with nothing to report.
MUST_SCAN = ("openfactory/__init__.py", "beeverforge/cli.py", "docker/worker.Dockerfile",
             "install.sh", "beeverforge/org_defaults/floor.yaml", "pyproject.toml")


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
    return []


def names_in_python(tree: ast.AST) -> list[str]:
    prose = _docstrings(tree)
    return sorted(name for node in ast.walk(tree) if id(node) not in prose
                  for word in _words(node) for name in NAME.findall(word))


def _code_lines(text: str, path: str) -> list[str]:
    """The lines a machine reads. Markdown and JSON have no comments: a role prompt is read by a
    model, so all of it counts. A shell script or a Dockerfile loses its comment lines only,
    since ` #` can sit inside a quoted string; YAML, TOML and environment files lose trailing
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
    return sorted(name for line in _code_lines(text, path) for name in NAME.findall(line))


def _shipped() -> Iterator[Path]:
    for top in ("beeverforge", "openfactory", *SHIPPED):
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
    return {str(path.relative_to(ROOT)): names_in(path) for path in _shipped()}


def test_the_scan_sees_every_shape_a_name_takes_in_python():
    """The positive twin: every shape an old name took in this tree, beside a docstring, a
    comment, the product named in a sentence and a longer word, which are not names."""
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
        "    return run(openfactory_mode=1)\n"
        "# a comment naming openfactory.adapters\n"
        'SAID = "upgrading from OpenFactory 0.7"\n'
        'OTHER = "openfactoryx"\n'
    )

    assert names_in_python(planted) == sorted([
        "openfactory", "openfactory.adapters", "openfactory_x", "~/.openfactory/env",
        "OPENFACTORY_", "openfactory-jobs", "openfactory_group", "upgrade_from_openfactory",
        "openfactory_dir", "openfactory_mode", "openfactory_home", "openfactory_cache",
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
])
def test_the_scan_sees_a_name_in_a_shipped_file_and_leaves_its_comments(path, text, names):
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


def test_no_shipped_file_says_an_openfactory_name_it_is_not_pinned_to():
    said = _said()

    for must in MUST_SCAN:
        assert must in said, f"the scan never reached {must}: it lost a kind of file"
    unknown_names = unknown(said)
    assert not unknown_names, (
        "these files say OpenFactory 0.7 names other than the ones pinned for them (found, "
        f"then pinned): { {p: (n, PINNED.get(p, [])) for p, n in unknown_names.items()} }. A new "
        "name: use the BeeverForge name instead, or, for a new way to keep reading 0.7's, "
        "register it in `deprecations.REMOVALS` and pin it here. A name gone: update its pin.")


@pytest.mark.parametrize("path", sorted(LAYER))
def test_every_module_of_the_layer_still_says_an_old_name(path):
    """Staleness: a module exempted whole that no longer says an old name is no longer the
    layer. Delete its entry, so a name it gains later is seen."""
    assert names_in(ROOT / path), f"{path} says no OpenFactory 0.7 name: delete it from LAYER"


def test_a_file_is_either_the_layer_or_pinned_never_both():
    assert not set(LAYER) & set(PINNED), set(LAYER) & set(PINNED)
