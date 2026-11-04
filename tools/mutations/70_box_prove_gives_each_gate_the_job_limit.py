"""#70: `box prove` gives each gate the same time limit a job does.

Row 1 is the shipped defect restored — the gate loop passes no limit, so every gate runs with the
box's own default and a long suite can never be proven. The rest hold what the fix is built on:
the minutes are converted to seconds, a gate with none gets the job's default, the limit reaches
the box through the gate runner, setup keeps its own limit, and a watched gate still streams.
"""

SRC = "beeverforge/box_prove.py"
HELPER = "beeverforge/orchestrator/validation.py"
TEST = "tests/test_box_prove_gives_each_gate_the_job_limit.py"

MUTATIONS = [
    ("the shipped defect: the gate loop gives no gate a limit", SRC,
     '        rc, out = _run(cmd, label=f"{name}: {cmd}", timeout=limit)',
     '        rc, out = _run(cmd, label=f"{name}: {cmd}")'),

    ("the declared minutes are read as seconds", HELPER,
     "    return minutes * 60 if minutes else default",
     "    return minutes * 1 if minutes else default"),

    ("a gate declaring no minutes is given no default", HELPER,
     "    return minutes * 60 if minutes else default",
     "    return minutes * 60 if minutes else 0"),

    ("`_run` ignores the gate runner and always uses the box's own limit", SRC,
     "        if timeout is not None and p.run_gate is not None:",
     "        if False:"),

    ("setup is given a gate's limit and goes through the gate runner", SRC,
     '        rc, out = _run(cmd, label=f"setup: {cmd}")',
     '        rc, out = _run(cmd, label=f"setup: {cmd}", timeout=1800)'),

    ("a watched gate is run blind: the gate runner never gets the line relay", SRC,
     '            relay = (lambda line: _say("line", line)) if watched else None',
     "            relay = None"),
]
