"""Mutation plan for #264 — an OpenFactory 0.7 user keeps working until BeeverForge 1.1: the
`openfactory` command and the `openfactory` import name are aliases of `beeverforge` that say so.

Each row takes away one thing the alias rests on — that it is declared, that it warns once and
where a person reads it, that it leaves stdout and the exit code alone, that the old import gives
back the SAME module objects with their own specs, that the warning is one the default filters
show, and that the shim ships in the wheel and in the images. Every row must turn its test red.
"""

TEST = "tests/test_the_openfactory_command_and_import_still_work_until_1_1.py"
WHEEL = "tests/test_the_wheel_ships_what_the_platform_needs.py"
COMMAND = "beeverforge/former_command.py"
SHIM = "openfactory/__init__.py"
PYPROJECT = "pyproject.toml"

MUTATIONS = [
    # ── the command ──
    ("`openfactory` points at the app itself, so it never says it is leaving", PYPROJECT,
     'openfactory = "beeverforge.former_command:main"',
     'openfactory = "beeverforge.cli:app"'),
    ("the command runs without its warning", COMMAND,
     "    print(WARNING, file=sys.stderr, flush=True)\n",
     ""),
    ("the warning is printed on stdout, where scripts parse", COMMAND,
     "    print(WARNING, file=sys.stderr, flush=True)\n",
     "    print(WARNING, file=sys.stdout, flush=True)\n"),
    ("the warning is printed twice", COMMAND,
     "    print(WARNING, file=sys.stderr, flush=True)\n",
     "    print(WARNING, file=sys.stderr, flush=True)\n"
     "    print(WARNING, file=sys.stderr, flush=True)\n"),
    ("a deployment logging JSON lines gets the warning as a plain line in its log", COMMAND,
     "    if logs.structured():\n",
     "    if False:\n"),
    ("the JSON-mode warning is logged before the log is configured, through lastResort", COMMAND,
     "        logs.configure()\n        log.warning(WARNING)\n",
     "        log.warning(WARNING)\n"),
    ("the alias runs the app outside click's standalone mode, so exit codes change", COMMAND,
     "    return app()\n",
     "    return app(standalone_mode=False)\n"),
    # ── the import ──
    ("`import openfactory` gives back the shim, not the `beeverforge` package", SHIM,
     "sys.modules[__name__] = beeverforge\n",
     ""),
    ("the finder hands back a fresh module, a second copy of `beeverforge.<x>`", SHIM,
     "        return sys.modules[_NEW + spec.name[len(_OLD):]]\n",
     "        return None\n"),
    ("the finder queues behind the path finder, which loads the old name as a copy", SHIM,
     "    sys.meta_path.insert(0, _TheNewName())\n",
     "    sys.meta_path.append(_TheNewName())\n"),
    ("the aliased module keeps the alias's spec", SHIM,
     "        module.__spec__ = module.__spec__.loader_state\n",
     "        pass\n"),
    ("a DeprecationWarning, which the default filters hide from an add-on's import", SHIM,
     "    FutureWarning, stacklevel=2)",
     "    DeprecationWarning, stacklevel=2)"),
    ("the warning names the shim's own line, not the add-on's import", SHIM,
     "    FutureWarning, stacklevel=2)",
     "    FutureWarning, stacklevel=1)"),
    ("importing `beeverforge` registers the old name too", "beeverforge/__init__.py",
     "",
     "\nimport openfactory  # noqa: E402,F401\n"),
    # ── the register (#501's review) ──
    ("the command restates its release instead of reading the register", COMMAND,
     'REMOVED_IN = removed_in("openfactory-command")',
     'REMOVED_IN = "1.1"'),
    ("the import shim restates its release instead of reading the register", SHIM,
     'REMOVED_IN = removed_in("openfactory-import")',
     'REMOVED_IN = "1.1"'),
    ("the command alias is not in the register", "beeverforge/deprecations.py",
     '    Removal("openfactory-command", "1.1",',
     '    Removal("openfactory-command-x", "1.1",'),
    # ── the carry-over, said once though the alias loads the environment twice ──
    ("the carry-over forgets what it said, so the alias's second load says it again",
     "beeverforge/former_names.py",
     "    _REPORTED.update(new.carried + new.ignored)\n",
     ""),
    # ── the shipping ──
    ("the wheel does not ship the shim", PYPROJECT,
     'include = ["beeverforge*", "openfactory"]',
     'include = ["beeverforge*"]',
     f"{WHEEL}::test_every_runtime_data_file_is_inside_the_built_wheel"),
    ("the worker image does not copy the shim it installs", "docker/worker.Dockerfile",
     "COPY openfactory ./openfactory\n",
     "",
     f"{WHEEL}::test_every_image_that_builds_the_package_carries_what_pyproject_declares"),
]
