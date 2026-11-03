"""#407: `doctor`'s listening check waits as long as the engine's deadline, and says so.

Run:  .venv/bin/python tools/mutate.py tools/mutations/407_the_doctor_waits_as_long_as_the_engine_deadline.py

The claims, each a row:

  1. the connect is bounded by `read_deadline()`, not by a literal and not by nothing (rows 1-3);
  2. a listener that was asked and timed out says how long the doctor waited and which variable
     sets it (rows 4-5);
  3. only a listener that timed out is said to have been waited on: not one that refused at once,
     not one nobody declared and so never dialled, and, where only some timed out, not the others
     (rows 6-9).
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
     "    if not waited:\n        return \"\"",
     "    if waited:\n        return \"\""),
    ("the wait is said without the variable that sets it", DOCTOR,
     'f"a loaded machine that answers later, raise `BEEVERFORGE_ENGINE_DEADLINE`")',
     'f"a loaded machine that answers later, raise the deadline")'),

    ("THE REVIEWED DEFECT: the wait is appended unconditionally again", DOCTOR,
     "    waited = [name for name, where in asked.items() if isinstance(where, TimedOut)]",
     "    waited = list(asked)"),
    ("a refusal is folded into a timeout again", DOCTOR,
     "            except OSError:  # refused or unreachable: the deadline is not what ended it\n"
     "                return False, where",
     "            except OSError:  # refused or unreachable: the deadline is not what ended it\n"
     "                return False, TimedOut(where)"),
    ("a timeout is folded into a refusal, so nothing is said to have been waited on", DOCTOR,
     "                return False, TimedOut(where)\n            except OSError:",
     "                return False, where\n            except OSError:"),
    ("an engine nobody declared, and so never dialled, is said to have been waited on", DOCTOR,
     "                    False, f\"{NOT_DECLARED} — set `{ENGINE.reach_vars[0]}={ENGINE.local()}`\")",
     "                    False, TimedOut(\n                        f\"{NOT_DECLARED} — set "
     "`{ENGINE.reach_vars[0]}={ENGINE.local()}`\"))"),
]
