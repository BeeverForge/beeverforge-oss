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

# REVIEW OF #434 (hermesfelipe). A gate stopped at its limit read as a bare `exited 124`: the box
# writes the limit at the head of the output and the finding keeps the tail. And the production
# wiring in `box_probes` was guarded by nothing — each cut there left the whole file green.
MUTATIONS += [
    ("a gate stopped at its limit is reported as a bare exit code again", SRC,
     '            line = (f"{name}: `{cmd}` was stopped at its limit of {stopped_at}s "\n'
     '                    f"(exit {rc}); {raise_it}\\n{_tail(out)}")',
     '            line = f"{name}: `{cmd}` exited {rc}\\n{_tail(out)}"'),

    ("a gate stopped at its limit gets the generic \"cannot reproduce your build\" remedy", SRC,
     "        if stopped and len(stopped) == len(failed_gates):\n"
     "            remedy = timeout_remedy",
     "        if False:\n"
     "            remedy = timeout_remedy"),

    ("an undeclared gate stopped at the box's limit is told to raise a setting it has none of",
     SRC,
     '            raise_it = (f"raise validate.{name}.timeout_minutes" if limit is not None else',
     '            raise_it = (f"raise validate.{name}.timeout_minutes" if True else'),

    ("the real probe set declares no gates: every gate keeps the box's limit", SRC,
     "            validation_gates=lambda: dict(manifest.validation),\n",
     "            validation_gates=dict,\n"),

    ("the real gate runner drops the limit on the way into the box", SRC,
     "            run_gate=lambda cmd, timeout, on_line: _in_box(cmd, on_line, timeout=timeout),",
     "            run_gate=lambda cmd, timeout, on_line: _in_box(cmd, on_line),"),
]
