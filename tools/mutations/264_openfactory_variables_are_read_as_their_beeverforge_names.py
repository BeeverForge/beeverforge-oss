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
     "    (logger or log).warning(done.sentence())\n",
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
