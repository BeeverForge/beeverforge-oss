"""An OpenFactory 0.7 deployment's `OPENFACTORY_*` is read under its `BEEVERFORGE_*` name (#264):
the cuts that break the rule, the warning, the box and each entry point."""

TEST = "tests/test_an_openfactory_environment_is_read_under_its_new_names.py"

_FORMER = "beeverforge/former_names.py"
_WORKER = "beeverforge/runtime/temporal/worker.py"

MUTATIONS = [
    # ── the rule ──
    ("the old name overwrites the new one when both are set",
     _FORMER,
     "        if new not in env:\n",
     "        if True:\n"),

    ("an old name alone is not read under the new one",
     _FORMER,
     "            env[new] = value\n",
     "            pass\n"),

    ("the old name stays in the environment, where a box's deny list does not name it",
     _FORMER,
     "        value = env.pop(old)\n",
     "        value = env[old]\n"),

    ("any name holding the old prefix is read, not only one that starts with it",
     _FORMER,
     "k.startswith(FORMER_PREFIX) and k != FORMER_PREFIX",
     "FORMER_PREFIX in k and k != FORMER_PREFIX"),

    # ── the warning ──
    ("nothing is said",
     _FORMER,
     # RE-PINNED 2026-11-09 (review of #499): the line says only what is new to the process.
     "    (logger or log).warning(new.sentence())\n",
     "    pass\n"),

    ("the warning prints the value beside the name",
     _FORMER,
     "            carried.append(old)\n",
     "            carried.append(f\"{old}={value}\")\n"),

    ("an old name ignored because the new one is set is not said",
     _FORMER,
     "        elif env[new] != value:\n",
     "        elif False:\n"),

    ("the same value under both names is said as ignored",
     _FORMER,
     "        elif env[new] != value:\n",
     "        else:\n"),

    ("the warning is a bare line among a deployment's JSON lines",
     _FORMER,
     "    if logs.structured():\n        logs.configure()\n",
     "    pass\n"),

    # ── once per process (review of #499) ──
    ("the process forgets what it said, so every load warns again",
     _FORMER,
     "    _REPORTED.update(new.carried + new.ignored)\n",
     ""),

    ("a carried name already said is said again",
     _FORMER,
     "    new = CarriedOver(carried=tuple(n for n in done.carried if n not in _REPORTED),\n",
     "    new = CarriedOver(carried=done.carried,\n"),

    ("an ignored name already said is said again (serve's second load)",
     _FORMER,
     "                      ignored=tuple(n for n in done.ignored if n not in _REPORTED))\n",
     "                      ignored=done.ignored)\n"),

    ("after the first warning, a new old name is never said",
     _FORMER,
     "    if not new:\n        return\n",
     "    if not new or _REPORTED:\n        return\n"),

    ("a name already said is no longer carried on the next load",
     _FORMER,
     "    for old in former:\n",
     "    for old in [k for k in former if k not in _REPORTED]:\n"),

    # ── the register (review of #499) ──
    ("the register never finds an entry due",
     "beeverforge/deprecations.py",
     "    return [e for e in REMOVALS if _release(version) >= _release(e.removed_in)]\n",
     "    return []\n",
     "tests/test_what_a_release_removes_is_registered.py"),

    ("the removing release itself is not due, only the ones after it",
     "beeverforge/deprecations.py",
     "_release(version) >= _release(e.removed_in)",
     "_release(version) > _release(e.removed_in)",
     "tests/test_what_a_release_removes_is_registered.py"),

    ("the register says the old names go in the release this tree already is",
     "beeverforge/deprecations.py",
     '    Removal("openfactory-environment", "1.1",\n',
     '    Removal("openfactory-environment", "0.2",\n',
     "tests/test_what_a_release_removes_is_registered.py"),

    ("`1.1.0` reads as a release after `1.1`",
     "beeverforge/deprecations.py",
     "    while len(parts) > 1 and parts[-1] == 0:\n        parts.pop()\n",
     "",
     "tests/test_what_a_release_removes_is_registered.py"),

    # ── every entry ──
    ("the command line does not carry the old names",
     "beeverforge/cli.py",
     "    former_names.warn(former_names.carry_over())\n",
     ""),

    ("the panel's own `.env` load does not carry the old names",
     "beeverforge/api/app.py",
     "    former_names.warn(former_names.carry_over())\n",
     ""),

    ("the worker does not carry the container's old names",
     _WORKER,
     "    carried = former_names.carry_over()\n",
     "    carried = former_names.CarriedOver()\n"),

    ("the worker sets up its log before it reads `OPENFACTORY_LOG_FORMAT`",
     _WORKER,
     "    carried = former_names.carry_over()\n    logs.configure()\n",
     "    logs.configure()\n    carried = former_names.carry_over()\n"),

    ("the worker does not say what it carried",
     _WORKER,
     "    former_names.warn(carried)\n",
     ""),

    ("the worker does not carry its `.env`'s old names",
     _WORKER,
     "    former_names.warn(former_names.carry_over())\n",
     ""),

    ("the boxed job does not carry the old names",
     "beeverforge/runtime/boxed_job.py",
     "    former_names.warn(former_names.carry_over())\n",
     ""),

    ("the schedule script does not carry its `.env`'s old names",
     "beeverforge/runtime/temporal/schedule.py",
     "    former_names.warn(former_names.carry_over())  # an OpenFactory 0.7 `.env` too (#264)\n",
     ""),

    ("the starter script does not carry its `.env`'s old names",
     "beeverforge/runtime/temporal/starter.py",
     "    former_names.warn(former_names.carry_over())  # an OpenFactory 0.7 `.env` too (#264)\n",
     ""),

    # ── the add-on reservation ──
    ("an add-on may name its variable under the old prefix",
     "beeverforge/environ.py",
     "                          (FORMER_PREFIX, \"OpenFactory's spelling of this platform's "
     "namespace, \"\n"
     "                                          f\"read as {ENV_PREFIX}* until 1.1\")):\n",
     "                          ):\n"),

    # ── the reference table, held to what is read ──
    ("an old spelling is read and the table still says it is not",
     _FORMER,
     "        new = PREFIX + old[len(FORMER_PREFIX):]\n",
     "        new = PREFIX + \"X_\" + old[len(FORMER_PREFIX):]\n",
     "tests/test_the_floor_the_limits_and_the_state_directory_are_documented.py"),
]
