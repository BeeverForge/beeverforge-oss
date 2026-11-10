"""#266: the doctor on an upgraded deployment lists every OpenFactory 0.7 name still in use, each
with the new name to use.

Each row drops one source from the list, or one part of how the doctor says it.
"""

IN_USE = "beeverforge/former_in_use.py"
FORMER_NAMES = "beeverforge/former_names.py"
DOCTOR = "beeverforge/doctor.py"

TEST = "tests/test_the_doctor_lists_every_former_name_still_in_use.py"

MUTATIONS = [
    ("THE FINDING: the doctor has no former-names line", DOCTOR,
     "    if former is not None and former.message:\n        findings.append(former)\n",
     "    pass\n", TEST),

    ("an environment name is said without its new name", IN_USE,
     'f"`{PREFIX}{name[len(FORMER_PREFIX):]}`"', 'f"`{name}`"', TEST),

    ("an environment name is said without the release that stops reading it", IN_USE,
     '"the environment", environ))', '"the environment"))', TEST),

    ("an ignored environment name is told to be renamed", IN_USE,
     "        if name in skipped:\n", "        if False:\n", TEST),

    ("the process forgets which environment names it ignored", FORMER_NAMES,
     "    _IGNORED.update(new.ignored)\n", "", TEST),

    ("the probe reads no ignored names", IN_USE, "ignored=former_names.ignored()", "ignored=()",
     TEST),

    ("the 0.7 operator directory in use is not listed", IN_USE,
     "        if namespace.dir_in(home) == namespace.FORMER_DIR:\n",
     "        if False:\n", TEST),

    ("a stale 0.7 operator directory is not listed", IN_USE,
     "        elif namespace.stale_former_dir(home):\n", "        elif False:\n", TEST),

    ("a repository on the 0.7 folder is not listed", IN_USE,
     "    if checkout is not None and namespace.dir_in(checkout) == namespace.FORMER_DIR:\n",
     "    if False:\n", TEST),

    ("a repository with both folders is listed beside the folder line", IN_USE,
     "    if checkout is not None and namespace.dir_in(checkout) == namespace.FORMER_DIR:\n",
     "    if checkout is not None and (checkout / namespace.FORMER_DIR).is_dir():\n", TEST),

    ("the 0.7 journals are not listed", IN_USE,
     "    if journals is not None and journals.parent.name == FORMER_LOGS_BESIDE:\n",
     "    if False:\n", TEST),

    ("the current journals are listed as 0.7's", IN_USE,
     "    if journals is not None and journals.parent.name == FORMER_LOGS_BESIDE:\n",
     "    if journals is not None:\n", TEST),

    ("stale 0.7 journals are not listed", IN_USE,
     "        if stale.is_dir():\n", "        if False:\n", TEST),

    ("add-ons that could not be read are read as none", IN_USE,
     "    if add_ons is None:\n", "    if False:\n", TEST),

    ("the add-on listing answers an unreadable store with an empty list", "beeverforge/plugins.py",
     '''        log.warning("could not read the %s entry points", FORMER_GROUP, exc_info=True)
        return None
''', '''        log.warning("could not read the %s entry points", FORMER_GROUP, exc_info=True)
        return []
''', TEST),

    ("an add-on on the former group is not listed", IN_USE,
     "    for row in add_ons or ():\n", "    for row in ():\n", TEST),

    ("the `openfactory` import is not listed", IN_USE,
     "    if imported:\n", "    if False:\n", TEST),

    ("the `openfactory` command is not listed", IN_USE,
     '    if command == "openfactory":\n', "    if False:\n", TEST),

    ("the process forgets which environment names it found", FORMER_NAMES,
     "    return tuple(sorted(_REPORTED))\n", "    return ()\n", TEST),

    ("the probe reads no environment names", IN_USE,
     "environment=former_names.found()", "environment=()", TEST),

    ("the probe reads no home", IN_USE, "home=Path.home()", "home=None", TEST),

    ("the probe reads no add-on", IN_USE,
     "add_ons=plugins.on_the_former_group()", "add_ons=[]", TEST),

    ("the probe never sees the import", IN_USE,
     'imported="openfactory" in sys.modules', "imported=False", TEST),

    ("the probe never sees the command", IN_USE,
     "command=Path(sys.argv[0]).name if sys.argv else \"\"", 'command=""', TEST),

    ("the probe is not handed the project's journals", DOCTOR,
     "journals=project_log_dir(project))", "journals=None)", TEST),

    ("the line is not handed the checkout", DOCTOR,
     "    found = p.former_names(p.checkout() if p.checkout else None)\n",
     "    found = p.former_names(None)\n", TEST),

    ("the line fails, making an upgraded deployment not ready", DOCTOR,
     '        "former_names", True,\n        f"OpenFactory 0.7 names still in use',
     '        "former_names", False,\n        f"OpenFactory 0.7 names still in use', TEST),

    ("a deployment with no former name gets an empty line", DOCTOR,
     '        return Finding("former_names", True, "")\n',
     '        return Finding("former_names", True, "no OpenFactory 0.7 name is in use")\n',
     TEST),
]
