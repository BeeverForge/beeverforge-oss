"""#70: `box prove` gives each gate the same time limit a job does.

A job runs a gate with its declared `timeout_minutes` (else `_VALIDATION_TIMEOUT`). The proof ran
every gate with the box's own default, so a suite that needs longer than that passed in every job
and could never be proven — measured on a 31-minute suite stopped at 99% with exit 124, and
pickup held behind it. These tests pin the proof to the job's limit, through the probe set's own
seam, without a box and without a clock.
"""

from __future__ import annotations

from beeverforge.box_prove import Probes, prove
from beeverforge.contracts.manifest import Gate
from beeverforge.orchestrator import machine
from beeverforge.orchestrator.validation import gate_commands

GATES = {"suite": {"command": "pytest -q", "timeout_minutes": 60}, "lint": "ruff check"}


def _probes(**overrides) -> Probes:
    """A box that satisfies everything, declaring one long gate and one plain one."""
    base = dict(
        resolve_digest=lambda image: "sha256:" + "a" * 64,
        image_platform=lambda image: ("linux", "arm64", "glibc"),
        toolbox_stamp=lambda: {"variant": "linux-arm64-glibc",
                               "harnesses": ["claude", "codex", "kimi"]},
        contract=lambda image: {},
        run_in_box=lambda cmd: (0, ""),
        harness_reachable=lambda: (True, ""),
        setup_commands=lambda: ["pip install -q pytest"],
        validate_commands=lambda: gate_commands(GATES),
        validation_gates=lambda: dict(GATES),
        harness_name=lambda: "claude",
    )
    base.update(overrides)
    return Probes(**base)


def test_a_gate_declaring_sixty_minutes_is_given_3600s_and_one_without_the_job_default():
    seen: list[tuple[str, int]] = []

    def run_gate(cmd, timeout, on_line):
        seen.append((cmd, timeout))
        return 0, ""

    proof = prove("acme", "mycorp/ci:1", _probes(run_gate=run_gate))

    assert proof.ok, [f.message for f in proof.findings if not f.ok]
    assert dict(seen)["pytest -q"] == 3600
    assert dict(seen)["ruff check"] == machine._VALIDATION_TIMEOUT


def test_setup_and_the_box_probe_never_go_through_the_gate_runner():
    in_box: list[str] = []
    gated: list[str] = []

    def run_in_box(cmd):
        in_box.append(cmd)
        return 0, ""

    def run_gate(cmd, timeout, on_line):
        gated.append(cmd)
        return 0, ""

    proof = prove("acme", "mycorp/ci:1", _probes(run_in_box=run_in_box, run_gate=run_gate))

    assert proof.ok, [f.message for f in proof.findings if not f.ok]
    assert "pip install -q pytest" in in_box
    assert "true" in in_box
    assert sorted(gated) == ["pytest -q", "ruff check"]
    assert not set(gated) & {"pip install -q pytest", "true"}


def test_a_watched_gate_still_streams():
    streamed: list[str] = []
    relays: list[object] = []
    events: list[tuple[str, str]] = []

    def run_streaming(cmd, on_line):
        streamed.append(cmd)
        return 0, ""

    def run_gate(cmd, timeout, on_line):
        relays.append(on_line)
        if on_line is not None:
            on_line(f"running {cmd}")
        return 0, ""

    proof = prove("acme", "mycorp/ci:1",
                  _probes(run_streaming=run_streaming, run_gate=run_gate),
                  on_stage=lambda kind, text: events.append((kind, text)))

    assert proof.ok, [f.message for f in proof.findings if not f.ok]
    assert "pip install -q pytest" in streamed
    assert relays and all(callable(r) for r in relays)
    assert ("line", "running pytest -q") in events


def test_the_helper_gives_the_declared_minutes_in_seconds_else_the_default():
    from beeverforge.orchestrator.validation import gate_timeout

    assert gate_timeout({"command": "x", "timeout_minutes": 60}, 1800) == 3600
    assert gate_timeout(Gate(command="x"), 1234) == 1234
    assert gate_timeout("x", 1234) == 1234
