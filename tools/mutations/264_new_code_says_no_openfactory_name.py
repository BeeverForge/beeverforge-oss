"""#264: new code outside the compatibility layer says no OpenFactory 0.7 name.

The guard walks the tree and fails on an `openfactory` name a file is not pinned to, and on a file
allowed one that neither the removal register nor the names kept with no end claims. The first
rows write a new name into the code, one per shape it takes and per kind of file, or unclaim a
file in the register, and the guard must see each. The rest weaken the guard itself, and its
planted twins must see that.
"""

TEST = "tests/test_new_code_says_no_openfactory_name.py"
DOCTOR = "beeverforge/doctor.py"
PATHS = "beeverforge/paths.py"
REGISTER = "beeverforge/deprecations.py"

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

    ("a module outside the layer names a class after 0.7 in CamelCase", DOCTOR, FUTURE,
     FUTURE + "class OpenFactoryError(Exception):\n    pass\n"),

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

    ("a module of the layer stops saying an old name, and its exemption outlives it",
     "beeverforge/onboarding/migrate_folder.py",
     'FORMER_DIR = ".openfactory"', 'FORMER_DIR = "." + "open" + "factory"'),

    # ── the register stops claiming a file ─────────────────────────────────────────────────────
    ("the register's entry no longer claims the file that serves it", REGISTER,
     '''            paths=("beeverforge/plugins.py", "beeverforge/former_in_use.py")),''',
     '''            paths=("beeverforge/former_in_use.py",)),'''),

    ("the register claims a file that says no old name", REGISTER,
     '''            paths=("beeverforge/plugins.py", "beeverforge/former_in_use.py")),''',
     '''            paths=("beeverforge/plugins.py", "beeverforge/former_in_use.py",
                   "beeverforge/doctor.py")),'''),

    ("an entry of the register claims no file", REGISTER,
     '''            paths=("beeverforge/plugins.py", "beeverforge/former_in_use.py")),''',
     '''            ),'''),

    # ── the guard is weakened ──────────────────────────────────────────────────────────────────
    ("the match reads lower and upper case only", TEST,
     '''                  r"[Oo][Pp][Ee][Nn][-_]?[Ff][Aa][Cc][Tt][Oo][Rr][Yy](?![a-z0-9])'''
     '''[\\w.~/*-]*")''',
     '''                  r"(?:openfactory|OPENFACTORY)(?![A-Za-z0-9])[\\w.~/*-]*")'''),

    ("the match reads no `-` or `_` inside the word", TEST,
     "[Oo][Pp][Ee][Nn][-_]?[Ff]", "[Oo][Pp][Ee][Nn][Ff]"),

    ("the match never starts at a camelCase hump", TEST,
     "(?:(?<![A-Za-z0-9])|(?<=[a-z0-9])(?=O))", "(?<![A-Za-z0-9])"),

    ("the match reads a longer word as the name", TEST,
     "[Yy](?![a-z0-9])", "[Yy]"),

    ("the product named in a sentence counts as a name", TEST,
     '''                  if not (prose and name.strip("*.") == PROSE))''',
     '''                  )'''),

    ("anything the product's name starts is prose", TEST,
     '''                  if not (prose and name.strip("*.") == PROSE))''',
     '''                  if not (prose and name.strip("*.").startswith(PROSE)))'''),

    ("an identifier may be the product's name standing alone", TEST,
     "                                   prose=False)])",
     "                                   prose=True)])"),

    ("a module outside the layer names a class `OpenFactory`", DOCTOR, FUTURE,
     FUTURE + "class OpenFactory:\n    pass\n"),

    ("a docstring counts as code", TEST,
     "    docstrings = _docstrings(tree)\n", "    docstrings = set()\n"),

    ("a string is not read", TEST,
     "    if isinstance(node, ast.Constant) and isinstance(node.value, str):\n"
     "        return [node.value]\n",
     ""),

    ("a bytes constant is not read", TEST,
     '        return [node.value.decode("latin-1")]\n', "        return []\n"),

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

    ("an `except ... as` name is not read", TEST,
     "    if isinstance(node, ast.ExceptHandler):\n", "    if False:\n"),

    ("a `global` or `nonlocal` name is not read", TEST,
     "        return list(node.names)\n", "        return []\n"),

    ("a `match` capture is not read", TEST,
     "    if isinstance(node, (ast.MatchAs, ast.MatchStar)):\n", "    if False:\n"),

    ("a `match` mapping's rest is not read", TEST,
     '        return [node.rest or ""]\n', "        return []\n"),

    ("a comment line counts in a file", TEST,
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
     'for top in ("beeverforge", "openfactory", *SCANNED):',
     'for top in ("beeverforge", "openfactory"):'),

    ("the layer exempts every file", TEST,
     "            if path not in LAYER and names != PINNED.get(path, [])}",
     "            if False}"),

    ("a pinned file may say any name", TEST,
     "            if path not in LAYER and names != PINNED.get(path, [])}",
     "            if path not in LAYER and path not in PINNED and names}"),

    ("every file counts as claimed", TEST,
     "    return sorted(set(allowed) - claimed)\n", "    return []\n"),

    ("a claimed file needs no place in the lists", TEST,
     "    return sorted([*gone, *(claimed - allowed)])\n", "    return sorted(gone)\n"),

    ("an entry may claim no file", TEST,
     "    return sorted([*gone, *(claimed - allowed)])\n",
     "    return sorted(claimed - allowed)\n"),
]
