"""#73 (review of #318): the starter, run with no engine to reach, ends in a sentence.

`python -m beeverforge.runtime.temporal.starter` dialled the bare `connect()`, so nothing listening
ended in `RuntimeError: Failed client connect` and an undeclared engine in `EngineNotDeclared`,
each in a traceback. It now dials `connect_at_birth` and turns both into the command's sentence.
Each row takes one part of that away.
"""

TEST = "tests/test_the_starter_command_refuses_a_missing_engine.py"
SRC = "beeverforge/runtime/temporal/starter.py"

MUTATIONS = [
    ("main goes back to the bare connect, which dies on the refusal in a traceback", SRC,
     "        client = await connect_at_birth()  # dev-server or Temporal Cloud, per env\n",
     "        from beeverforge.runtime.temporal.connection import connect\n"
     "        client = await connect()\n"),

    ("both refusals are caught and re-raised bare, so the traceback is back", SRC,
     "    except (EngineNotListening, EngineNotDeclared) as exc:\n"
     "        raise logs.exiting(log, f\"starter: {exc}\") from None\n",
     "    except (EngineNotListening, EngineNotDeclared):\n"
     "        raise\n"),

    ("the exit goes through no sentence, so the address and the remedy are gone", SRC,
     "        raise logs.exiting(log, f\"starter: {exc}\") from None\n",
     "        raise SystemExit(1) from None\n"),

    ("an engine nobody declared is no longer caught, so it ends in a traceback", SRC,
     "    except (EngineNotListening, EngineNotDeclared) as exc:\n",
     "    except EngineNotListening as exc:\n"),

    ("an engine not listening is no longer caught, so it ends in a traceback", SRC,
     "    except (EngineNotListening, EngineNotDeclared) as exc:\n",
     "    except EngineNotDeclared as exc:\n"),
]
