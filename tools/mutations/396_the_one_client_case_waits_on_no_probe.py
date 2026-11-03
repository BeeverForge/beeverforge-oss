"""The one-engine-client case still catches what it caught once it waits on no probe (#396).

#396: under load, `test_with_json_lines_the_one_engine_client_has_a_runtime_whose_core_writes_
through_the_log` raised `EngineNotListening` from the probe a JSON-lines connect asks first
(`connection._listening`, with a 1.0 s of its own that no `within` reaches). The case, and the
other `listening` users that read the connect rather than the probe, now stand in for that probe
with one that answers at once and records each address it was asked about. A stand-in can hide
what the case guards, so each row here breaks a claim the case makes and runs THAT case alone.
Every row must be red.

Run:  .venv/bin/python tools/mutate.py tools/mutations/396_the_one_client_case_waits_on_no_probe.py

The probe itself keeps its own guards, on the real socket: plan 681's "a port nobody listens on
is given a runtime" (`test_a_port_nobody_listens_on_costs_no_runtime_and_no_collection`, the
`refusing` fixture) and the `_listening` rows of plans 135 and 362.
"""

LOGS = "tests/test_the_logs_can_be_json_lines_that_say_the_project.py"
ONE_CLIENT = (LOGS + "::test_with_json_lines_the_one_engine_client_has_a_runtime_whose_core_"
              "writes_through_the_log")
TEST = ONE_CLIENT

CONNECTION = "beeverforge/runtime/temporal/connection.py"

MUTATIONS = [
    ("a client is made for every caller", CONNECTION,
     "            if held is not None:\n                return held",
     "            if False:\n                return held", ONE_CLIENT),
    ("the core does not forward through the log", CONNECTION,
     "        forwarding=LogForwardingConfig(logger=logging.getLogger(CORE_LOGGER))))",
     "        forwarding=None))", ONE_CLIENT),
    ("the core is asked for more than it says by default", CONNECTION,
     "        filter=LoggingConfig.default.filter,", '        filter="TRACE",', ONE_CLIENT),
    ("every client is made on the library's default runtime", CONNECTION,
     '                **({"runtime": runtime} if runtime is not None else {}), **_auth())',
     "                **_auth())", ONE_CLIENT),
    ("a changed target is served the old target's client", CONNECTION,
     "    return address(), namespace(), digest", '    return address(), "default", digest',
     ONE_CLIENT),
    # The stand-in is on the path the case reads: a connect that no longer asks the probe before
    # it builds a runtime is red here, by the probe's own count, not only in the `refusing` case.
    ("a runtime is built before the socket is asked", CONNECTION,
     "            if logs.structured() and not await _listening(*_host_and_port(where)):",
     "            if False:", ONE_CLIENT),
]
