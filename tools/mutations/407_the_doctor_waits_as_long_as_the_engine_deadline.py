"""#407: `doctor`'s listening check waits as long as the engine's deadline, and says so.

Run:  .venv/bin/python tools/mutate.py tools/mutations/407_the_doctor_waits_as_long_as_the_engine_deadline.py

The claims, each a row:

  1. the connect is bounded by `read_deadline()`, not by a literal and not by nothing (rows 1-3);
  2. a listener that was asked and did not answer says how long the doctor waited and which
     variable sets it (rows 4-5).
"""

TEST = "tests/test_the_doctor_waits_as_long_as_the_engine_deadline.py"

DOCTOR = "beeverforge/doctor.py"

MUTATIONS = [
    ("TODAY'S DEFECT: the fixed 1.5 s is back", DOCTOR,
     "socket.create_connection((host, port), timeout=read_deadline())",
     "socket.create_connection((host, port), timeout=1.5)"),
    ("the deadline is ignored for a fixed default", DOCTOR,
     "socket.create_connection((host, port), timeout=read_deadline())",
     "socket.create_connection((host, port), timeout=3.0)"),
    ("the connect is unbounded", DOCTOR,
     "socket.create_connection((host, port), timeout=read_deadline())",
     "socket.create_connection((host, port), timeout=None)"),

    ("the wait is not said", DOCTOR,
     '    return (f"; the doctor waited {read_deadline():g}s for each answer',
     '    return ""\n    return (f"; the doctor waited {read_deadline():g}s for each answer'),
    ("the wait is said without the variable that sets it", DOCTOR,
     'f"that answers later, raise `BEEVERFORGE_ENGINE_DEADLINE`")',
     'f"that answers later, raise the deadline")'),
]
