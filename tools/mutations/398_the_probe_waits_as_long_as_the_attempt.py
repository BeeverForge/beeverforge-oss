"""#398: the engine's readiness probe waits as long as the connect it guards.

`connection._listening` had a fixed 1.0 s of its own, shorter than the attempt it guards (the
caller's `within`, else `BEEVERFORGE_ENGINE_DEADLINE`), so a loaded host could report a listening
engine as `EngineNotListening`. Now it is bounded by the attempt alone, and `connect_at_birth`
hands it what is left of the birth's wait. Each row puts a shorter or a different bound back, or
says a probe that ran out of the attempt's bound as nothing listening. Every row must be red.

Run:  .venv/bin/python tools/mutate.py tools/mutations/398_the_probe_waits_as_long_as_the_attempt.py
"""

TEST = "tests/test_the_engine_probe_waits_as_long_as_the_attempt.py"

CONNECTION = "beeverforge/runtime/temporal/connection.py"

MUTATIONS = [
    ("the probe is bounded by a fixed 1.0 s again", CONNECTION,
     "timeout=within)", "timeout=1.0)"),
    ("the probe ignores the attempt's bound and takes the read deadline", CONNECTION,
     "timeout=within)", "timeout=read_deadline())"),
    ("a probe that ran out of the attempt's bound is said as nothing listening", CONNECTION,
     "    except (OSError, TimeoutError):\n        return False",
     "    except (OSError, TimeoutError, asyncio.CancelledError):\n        return False"),
    ("the birth probe is given a fixed 1.0 s again", CONNECTION,
     "    while not await _listening(host, port, within=deadline - time.monotonic()):",
     "    while not await _listening(host, port, within=1.0):"),
]
