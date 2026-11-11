"""#264: new code outside the compatibility layer says no OpenFactory 0.7 name.

The guard walks everything that ships and fails on an `openfactory` name a file is not pinned to.
The first rows write a new name into the code, one per shape it takes and per kind of file, and
the guard must see each. The rest weaken the guard itself, and its planted twins must see that.
"""

TEST = "tests/test_new_code_says_no_openfactory_name.py"
DOCTOR = "beeverforge/doctor.py"
PATHS = "beeverforge/paths.py"

FUTURE = "from __future__ import annotations\n"

MUTATIONS = [
    # ── new code says a name ───────────────────────────────────────────────────────────────────
    ("a module outside the layer reads a 0.7 path", DOCTOR, FUTURE,
     FUTURE + '_OLD_MANIFEST = ".openfactory/project.yaml"\n'),

    ("a module outside the layer reads a 0.7 variable through an f-string", DOCTOR, FUTURE,
     FUTURE + 'def _old(name):\n    return f"OPENFACTORY_{name}"\n'),

    ("a module outside the layer imports the 0.7 package", DOCTOR, FUTURE,
     FUTURE + "def _old():\n    import openfactory\n    return openfactory\n"),

    ("a module outside the layer names a function after 0.7", DOCTOR, FUTURE,
     FUTURE + "def _openfactory_home():\n    return None\n"),

    ("a pinned module says one name more", PATHS,
     'FORMER_LOGS_BESIDE = ".openfactory-logs"',
     'FORMER_LOGS_BESIDE = ".openfactory-logs"\nFORMER_STATE = ".openfactory-state"'),

    ("a pinned module stops saying its name, and the pin outlives it", PATHS,
     'FORMER_LOGS_BESIDE = ".openfactory-logs"',
     'FORMER_LOGS_BESIDE = ".beeverforge-logs"'),

    ("the floor protects one more 0.7 path", "beeverforge/org_defaults/floor.yaml",
     '  - ".openfactory/**"\n',
     '  - ".openfactory/**"\n  - ".openfactory-logs/**"\n'),

    ("the installer reads one more 0.7 variable", "install.sh",
     "set -eu\n", "set -eu\nOLD_HOME=${OPENFACTORY_HOME:-}\n"),

    ("the compose file names a 0.7 volume", "docker-compose.yml",
     "services:\n", "volumes:\n  openfactory_state: {}\nservices:\n"),

    # ── the guard is weakened ──────────────────────────────────────────────────────────────────
    ("the product named in a sentence counts as a name", TEST,
     "(?:openfactory|OPENFACTORY)", "(?i:openfactory)"),

    ("a docstring counts as code", TEST,
     "    prose = _docstrings(tree)\n", "    prose = set()\n"),

    ("a string is not read", TEST,
     "    if isinstance(node, ast.Constant) and isinstance(node.value, str):\n        return [node.value]\n",
     ""),

    ("a name read or bound is not read", TEST,
     "    if isinstance(node, ast.Name):\n        return [node.id]\n", ""),

    ("an attribute is not read", TEST,
     "    if isinstance(node, ast.Attribute):\n        return [node.attr]\n", ""),

    ("an import is not read", TEST,
     '        return [node.name, node.asname or ""]\n', '        return [node.asname or ""]\n'),

    ("a module imported from is not read", TEST,
     '        return [node.module or ""]\n', "        return []\n"),

    ("a definition's name is not read", TEST,
     "        return [node.name]\n", "        return []\n"),

    ("an argument is not read", TEST,
     "        return [node.arg]\n", "        return []\n"),

    ("a keyword is not read", TEST,
     '        return [node.arg or ""]\n', "        return []\n"),

    ("a comment line counts in a shipped file", TEST,
     '    kept = [line for line in lines if not line.lstrip().startswith("#")]\n',
     "    kept = lines\n"),

    ("a trailing comment counts in YAML", TEST,
     '        kept = [line.split(" #", 1)[0] for line in kept]\n', "        pass\n"),

    ("a shell line is cut at its first ` #`", TEST,
     'if path.endswith((".yaml", ".yml", ".toml", ".example")):',
     'if True:'),

    ("the panel's comments count", TEST,
     '        text = re.sub(r"<!--.*?-->|/\\*.*?\\*/", "", text, flags=re.S)\n', ""),

    ("the scan reads the two packages only", TEST,
     'for top in ("beeverforge", "openfactory", *SHIPPED):',
     'for top in ("beeverforge", "openfactory"):'),

    ("the layer exempts every file", TEST,
     "            if path not in LAYER and names != PINNED.get(path, [])}",
     "            if False}"),

    ("a pinned file may say any name", TEST,
     "            if path not in LAYER and names != PINNED.get(path, [])}",
     "            if path not in LAYER and path not in PINNED and names}"),

    ("a module of the layer stops saying an old name, and its exemption outlives it",
     "beeverforge/onboarding/migrate_folder.py",
     'FORMER_DIR = ".openfactory"', 'FORMER_DIR = "." + "open" + "factory"'),
]
