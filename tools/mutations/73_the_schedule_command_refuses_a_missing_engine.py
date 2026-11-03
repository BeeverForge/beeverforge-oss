"""#73: the schedule command, run with no engine to reach, ends in a sentence, not a traceback.

`main()` dialled the bare `connect()`, so an unreachable engine ended the documented command in a
34-line traceback. It now dials `connect_at_birth`, as the worker is born, and turns its
`EngineNotListening` into the same one-sentence exit, and its `EngineNotDeclared` too (review of
#318): an engine nobody declared was refused by `address()` before the wait, in a traceback. Each
row takes one part of that away.
"""

TEST = "tests/test_the_schedule_command_refuses_a_missing_engine.py"
SRC = "beeverforge/runtime/temporal/schedule.py"

MUTATIONS = [
    ("main goes back to the bare connect, which dies on the refusal in a traceback", SRC,
     "        client = await connect_at_birth()\n",
     "        client = await connect()\n"),

    ("the refusal is caught and re-raised bare, so the traceback is back", SRC,
     "    except (EngineNotListening, EngineNotDeclared) as exc:\n"
     "        raise logs.exiting(log, f\"schedule: {exc}\") from None\n",
     "    except (EngineNotListening, EngineNotDeclared):\n"
     "        raise\n"),

    ("the exit goes through no sentence, so the address and the remedy are gone", SRC,
     "        raise logs.exiting(log, f\"schedule: {exc}\") from None\n",
     "        raise SystemExit(1) from None\n"),

    ("an engine nobody declared is no longer caught, so it ends in a traceback", SRC,
     "    except (EngineNotListening, EngineNotDeclared) as exc:\n",
     "    except EngineNotListening as exc:\n"),
]
