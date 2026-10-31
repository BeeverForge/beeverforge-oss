"""A worker whose deployment never said where its engine is ends in a sentence, not a traceback.

WHAT HAPPENED (review of #318, #73). `born()` turned `EngineNotListening` into one sentence and
exit 1 (#135), but `connect_at_birth` asks `address()` first, and with neither `TEMPORAL_ADDRESS`
nor `TEMPORAL_ENDPOINT` set that raises `EngineNotDeclared` (#163), which `born()` did not catch: the
worker ended in a traceback whose last line held the sentence a person needed. Its message is the
sentence, so `born()` catches it beside the other.

The test runs the real `born()` in a process of its own, as `beeverforge up` and the compose file
start it, and reads its exit code and stderr.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_a_worker_with_an_engine_nobody_declared_ends_in_a_SENTENCE_not_a_traceback(tmp_path):
    """Neither address variable says anything. They are set EMPTY rather than left out: an empty
    value is "nobody said" to `address()`, and `load_dotenv` never overrides a variable that is
    set, so a `.env` at the checkout's root cannot declare an engine behind this test's back. The
    timeout guards a hang only."""
    drive = ("import asyncio\n"
             "from beeverforge.runtime.temporal.worker import born\n"
             "asyncio.run(born())\n")

    done = subprocess.run(
        [sys.executable, "-c", drive], cwd=tmp_path, capture_output=True, text=True, timeout=25,
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "PYTHONPATH": str(ROOT),
             "TEMPORAL_ADDRESS": "", "TEMPORAL_ENDPOINT": "",
             "BEEVERFORGE_ENGINE_STARTS_IN": "0.01"})

    assert done.returncode == 1, done.stderr[-400:]
    assert "Traceback" not in done.stderr, done.stderr[-600:]
    last = done.stderr.strip().splitlines()[-1]
    assert last.startswith("worker: this deployment does not say where its durable engine is"), \
        f"the worker does not end on its sentence: {done.stderr[-600:]}"
    for owed in ("TEMPORAL_ADDRESS", "TEMPORAL_ENDPOINT"):
        assert owed in last, f"the refusal does not say {owed!r}: {last}"
