"""#73 (review of #318): a worker whose engine nobody declared ends in a sentence.

`born()` turned `EngineNotListening` into one sentence (#135) but not `EngineNotDeclared` (#163),
which `connect_at_birth` raises before it waits. It now catches both. The rows for the wait and the
`EngineNotListening` half are in `135_the_worker_waits_for_the_engine_to_listen.py`.
"""

TEST = "tests/test_the_worker_refuses_an_engine_nobody_declared.py"
SRC = "beeverforge/runtime/temporal/worker.py"

MUTATIONS = [
    ("an engine nobody declared is no longer caught, so the worker ends in a traceback", SRC,
     "    except (EngineNotListening, EngineNotDeclared) as exc:\n",
     "    except EngineNotListening as exc:\n"),

    ("the exit goes through no sentence, so what to set is gone", SRC,
     "        raise logs.exiting(log, f\"worker: {exc}\") from None\n",
     "        raise SystemExit(1) from None\n"),
]
