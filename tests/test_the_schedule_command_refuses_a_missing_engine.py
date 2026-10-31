"""`python -m beeverforge.runtime.temporal.schedule` with no engine listening ends in a sentence (#73).

WHAT HAPPENED. Measured with temporalio 1.34.0 and nothing listening on `TEMPORAL_ADDRESS`, the
command exited 1 with a 34-line traceback ending in `RuntimeError: Failed client connect: Server
connection error: ... Connection refused`. Nothing named the cause or the remedy: `main()` dialled
the bare `connect()`, while the worker is born through `connect_at_birth`, which waits a bounded
time for the engine to listen and then refuses in one sentence naming the address and the remedy.

The first test runs the real module under `__main__` in a process of its own, as a person types it,
and reads its exit code and stderr. The second reads `main` off the module's syntax tree.
"""

from __future__ import annotations

import ast
import socket
import subprocess
import sys
from pathlib import Path

from tests.the_tree_read_once import parsed

ROOT = Path(__file__).resolve().parents[1]
MODULE = "beeverforge.runtime.temporal.schedule"


def _a_free_port() -> int:
    """A port nothing listens on: bound by the system, then released."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_the_schedule_command_with_no_engine_ends_in_a_SENTENCE_not_a_traceback(tmp_path):
    """The real command, the real exit code, the real stderr. The timeout guards a hang only."""
    port = _a_free_port()

    done = subprocess.run(
        [sys.executable, "-m", MODULE], cwd=tmp_path, capture_output=True, text=True, timeout=25,
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "PYTHONPATH": str(ROOT),
             "TEMPORAL_ADDRESS": f"127.0.0.1:{port}", "BEEVERFORGE_ENGINE_STARTS_IN": "1"})

    assert done.returncode != 0, done.stderr[-400:]
    assert "Traceback" not in done.stderr, done.stderr[-600:]
    said = done.stderr.strip()
    for owed in (f"127.0.0.1:{port}", "TEMPORAL_ADDRESS", "beeverforge up"):
        assert owed in said, f"the refusal does not say {owed!r}: {said[-600:]}"
    assert said.startswith("schedule: "), f"the refusal is not the command's sentence: {said[-600:]}"


def test_the_schedule_command_is_BORN_through_the_wait():
    """Read off the module's own syntax tree: `main` awaits `connect_at_birth`, and nothing in it
    awaits the bare `connect` that dies on the first refusal."""
    tree = parsed(ROOT / "beeverforge/runtime/temporal/schedule.py")
    main = next(node for node in tree.body
                if isinstance(node, ast.AsyncFunctionDef) and node.name == "main")
    awaited = {node.value.func.id for node in ast.walk(main)
               if isinstance(node, ast.Await) and isinstance(node.value, ast.Call)
               and isinstance(node.value.func, ast.Name)}

    assert "connect_at_birth" in awaited, f"the schedule command's main awaits {sorted(awaited)}"
    assert "connect" not in awaited
