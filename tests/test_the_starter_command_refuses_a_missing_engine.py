"""`python -m beeverforge.runtime.temporal.starter` with no engine to reach ends in a sentence (#73).

WHAT HAPPENED. The schedule command's sibling (review of #318): `main()` dialled the bare
`connect()`, so `python -m beeverforge.runtime.temporal.starter <project> <issue>` with nothing
listening on `TEMPORAL_ADDRESS` ended in a traceback closing on `RuntimeError: Failed client
connect`, and with no address declared at all, in one closing on `EngineNotDeclared`. It now dials
`connect_at_birth`, as the worker is born, and turns both refusals into the command's one sentence:
exit 1 and no traceback.

The first two tests run the real module under `__main__` in a process of its own, as a person types
it, and read its exit code and stderr. The third reads `main` off the module's syntax tree.

`BEEVERFORGE_ENGINE_STARTS_IN` is a hundredth of a second, so the wait for a port nothing will ever
bind is short; no test asserts how long anything took.
"""

from __future__ import annotations

import ast
import socket
import subprocess
import sys
from pathlib import Path

from tests.the_tree_read_once import parsed

ROOT = Path(__file__).resolve().parents[1]
MODULE = "beeverforge.runtime.temporal.starter"


def _a_free_port() -> int:
    """A port nothing listens on: bound by the system, then released."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _run(tmp_path: Path, **engine: str) -> subprocess.CompletedProcess:
    """The command as a person types it. The timeout guards a hang only."""
    return subprocess.run(
        [sys.executable, "-m", MODULE, "acme", "1"], cwd=tmp_path, capture_output=True, text=True,
        timeout=25,
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "PYTHONPATH": str(ROOT),
             "BEEVERFORGE_ENGINE_STARTS_IN": "0.01", **engine})


def test_the_starter_with_no_engine_listening_ends_in_a_SENTENCE_not_a_traceback(tmp_path):
    port = _a_free_port()

    done = _run(tmp_path, TEMPORAL_ADDRESS=f"127.0.0.1:{port}")

    assert done.returncode != 0, done.stderr[-400:]
    assert "Traceback" not in done.stderr, done.stderr[-600:]
    said = done.stderr.strip()
    for owed in (f"127.0.0.1:{port}", "TEMPORAL_ADDRESS", "beeverforge up"):
        assert owed in said, f"the refusal does not say {owed!r}: {said[-600:]}"
    assert said.startswith("starter: "), f"the refusal is not the command's sentence: {said[-600:]}"
    assert "\n" not in said, f"the refusal is more than one line: {said[-600:]}"


def test_the_starter_with_an_engine_nobody_declared_ends_in_a_SENTENCE(tmp_path):
    """Neither address variable says anything. They are set EMPTY rather than left out: an empty
    value is "nobody said" to `address()`, and `load_dotenv` never overrides a variable that is
    set, so a `.env` at the checkout's root cannot declare an engine behind this test's back."""
    done = _run(tmp_path, TEMPORAL_ADDRESS="", TEMPORAL_ENDPOINT="")

    assert done.returncode != 0, done.stderr[-400:]
    assert "Traceback" not in done.stderr, done.stderr[-600:]
    said = done.stderr.strip()
    assert said.startswith("starter: this deployment does not say where its durable engine is"), \
        f"the refusal is not the command's sentence: {said[-600:]}"
    for owed in ("TEMPORAL_ADDRESS", "TEMPORAL_ENDPOINT"):
        assert owed in said, f"the refusal does not say {owed!r}: {said[-600:]}"
    assert "\n" not in said, f"the refusal is more than one line: {said[-600:]}"


def test_the_starter_is_BORN_through_the_wait():
    """Read off the module's own syntax tree: `main` awaits `connect_at_birth`, and nothing in it
    awaits the bare `connect` that dies on the first refusal."""
    tree = parsed(ROOT / "beeverforge/runtime/temporal/starter.py")
    main = next(node for node in tree.body
                if isinstance(node, ast.AsyncFunctionDef) and node.name == "main")
    awaited = {node.value.func.id for node in ast.walk(main)
               if isinstance(node, ast.Await) and isinstance(node.value, ast.Call)
               and isinstance(node.value.func, ast.Name)}

    assert "connect_at_birth" in awaited, f"the starter's main awaits {sorted(awaited)}"
    assert "connect" not in awaited
