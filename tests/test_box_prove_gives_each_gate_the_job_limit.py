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


# ── a gate stopped at its limit says so (review of #434, finding 1) ─────────────────────────────

#: Longer than the tail the finding keeps, so the `BEEVERFORGE_TIMEOUT:` head the box writes is cut
#: off — the case the finding has to name the limit for itself.
_LONG_RUN = "".join(f"tests/test_{i:02d}.py ........\n" for i in range(50))


def _stopped_suite(cmd, timeout, on_line):
    from beeverforge.adapters.sandbox.timeouts import timeout_result

    if cmd == "pytest -q":
        return timeout_result(cmd, timeout, _LONG_RUN)
    return 0, ""


def test_a_gate_stopped_at_its_limit_names_the_limit_and_the_setting_to_raise():
    proof = prove("acme", "mycorp/ci:1", _probes(run_gate=_stopped_suite))

    (finding,) = [f for f in proof.findings if f.check == "validate"]
    assert not finding.ok
    assert "3600s" in finding.message, finding.message
    assert "validate.suite.timeout_minutes" in finding.message, finding.message
    assert "timeout_minutes" in finding.remedy, finding.remedy
    assert "cannot reproduce your build" not in finding.remedy, finding.remedy


def test_a_gate_no_declaration_covers_does_not_offer_a_setting_it_does_not_have():
    def run_in_box(cmd):
        from beeverforge.adapters.sandbox.timeouts import timeout_result

        if cmd == "pytest -q":
            return timeout_result(cmd, 1800, _LONG_RUN)
        return 0, ""

    # an older probe set: no declared gates, no gate runner — the box's own limit applies
    proof = prove("acme", "mycorp/ci:1", _probes(run_in_box=run_in_box,
                                                 validation_gates=dict))

    (finding,) = [f for f in proof.findings if f.check == "validate"]
    assert not finding.ok
    assert "1800s" in finding.message, finding.message
    assert "validate.suite.timeout_minutes" not in finding.message, finding.message
    assert "cannot reproduce your build" not in finding.remedy, finding.remedy


def test_an_advisory_gate_that_ran_out_of_time_leaves_a_blocking_failure_its_own_remedy():
    """An ADVISORY gate stopped at its limit is reported with the advisory finding; it is not
    what the blocking finding is about. So a blocking gate that failed outright beside it keeps
    the generic remedy, with no talk of time limits it did not hit."""
    def run_gate(cmd, timeout, on_line):
        from beeverforge.adapters.sandbox.timeouts import timeout_result

        if cmd == "pytest -q":
            return timeout_result(cmd, timeout, _LONG_RUN)
        return 1, "lint: 3 errors"

    proof = prove("acme", "mycorp/ci:1", _probes(run_gate=run_gate,
                                                 advisory_gates=lambda: frozenset({"suite"})))

    (blocking,) = [f for f in proof.findings if f.check == "validate" and not f.advisory]
    assert "ruff check" in blocking.message, blocking.message
    assert "cannot reproduce your build" in blocking.remedy, blocking.remedy
    assert "timeout_minutes" not in blocking.remedy, blocking.remedy


# ── the production probe set is wired to the manifest and the box (finding 2) ───────────────────

def _box_probes_over_a_fake_box(tmp_path, monkeypatch):
    """The REAL `box_probes`, over a box that records the limit each `run` was given."""
    from types import SimpleNamespace

    from beeverforge import box_prove
    from beeverforge.adapters.sandbox import registry as sandboxes

    limits: list[tuple[str, int]] = []

    class _Box:
        def prepare(self, **_kw):
            return SimpleNamespace(path=str(tmp_path))

        def cleanup(self, **_kw):
            pass

        def harness_path(self, name):
            return name

        def run(self, workspace, command, timeout, on_output=None):
            limits.append((command, timeout))
            return 0, ""

    monkeypatch.setattr(box_prove, "PROOF_DIR", tmp_path / "proofs")
    monkeypatch.setattr(sandboxes, "installed_box_traits",
                        lambda _kind: SimpleNamespace(honours_image=True))
    monkeypatch.setattr(sandboxes, "build_sandbox", lambda *_a, **_kw: _Box())
    manifest = SimpleNamespace(base_branch="main", setup=[],
                               validation={"suite": Gate(command="pytest -q", timeout_minutes=60)})
    probes = box_prove.box_probes(SimpleNamespace(name="someone", box=None), "img",
                                  repo_path=tmp_path, manifest=manifest, key="someone",
                                  sandbox="container")
    return probes, manifest, limits


def test_the_real_probe_set_reads_the_declared_gates_off_the_manifest(tmp_path, monkeypatch):
    held, manifest, _ = _box_probes_over_a_fake_box(tmp_path, monkeypatch)

    with held as probes:
        assert probes.validation_gates() == manifest.validation


def test_the_real_probe_set_hands_the_gate_limit_to_the_box(tmp_path, monkeypatch):
    from beeverforge.orchestrator.validation import gate_timeout

    held, manifest, limits = _box_probes_over_a_fake_box(tmp_path, monkeypatch)

    with held as probes:
        limit = gate_timeout(manifest.validation["suite"], machine._VALIDATION_TIMEOUT)
        assert probes.run_gate("pytest -q", limit, None) == (0, "")

    assert limits == [("pytest -q", 3600)]
