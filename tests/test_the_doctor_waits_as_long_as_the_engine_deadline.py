"""`doctor`'s "is anything listening" check waits as long as the engine's deadline (#407).

It gave up after a fixed 1.5 s, so on a loaded host a listener that answered late was reported as
down while the rest of the deployment waited `BEEVERFORGE_ENGINE_DEADLINE` (`read_deadline()`)
for the same engine. A robustness gap, not an observed failure: #398 measured a probe max of
6.4 ms at a load average of 3-6, #402 a max of 120 ms at load averages up to 49.

NO REAL SOCKET AND NO REAL WAIT. The stand-in for `socket.create_connection` is handed the
`timeout` the probe chose and decides by comparing it with a simulated answer time; it never
sleeps, and nothing here is bounded by elapsed or processor time.
"""

from __future__ import annotations

import socket
from types import SimpleNamespace

import pytest

from beeverforge.runtime.temporal.deadlines import read_deadline

ENGINE, UI, PANEL = 7301, 7302, 7303

_EVERY_VAR = ("TEMPORAL_ADDRESS", "TEMPORAL_ENDPOINT", "TEMPORAL_UI_URL", "BEEVERFORGE_PANEL_URL",
              "TEMPORAL_PORT", "TEMPORAL_UI_PORT", "PANEL_PORT", "BEEVERFORGE_ENGINE_DEADLINE")


@pytest.fixture(autouse=True)
def _nothing_declared(monkeypatch, tmp_path):
    for var in _EVERY_VAR:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)


class _Connected:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _a_machine(monkeypatch, answers_after: dict[int, float | None]) -> list:
    """Replace the connect with one whose listeners answer after a simulated time (None: never).
    Returns the list of `timeout` values the probe handed it."""
    handed: list = []

    def create_connection(address, timeout=None, *args, **kwargs):
        handed.append(timeout)
        if timeout is None:
            raise AssertionError(f"an unbounded connect to {address}")
        after = answers_after[address[1]]
        if after is not None and after <= timeout:
            return _Connected()
        raise TimeoutError(f"{address} did not answer within {timeout}s")

    monkeypatch.setattr(socket, "create_connection", create_connection)
    return handed


def _probe(monkeypatch, tmp_path):
    from beeverforge import doctor

    monkeypatch.setenv("BEEVERFORGE_OWN_WORK", "1")
    monkeypatch.setenv("TEMPORAL_ADDRESS", f"127.0.0.1:{ENGINE}")
    monkeypatch.setenv("TEMPORAL_UI_URL", f"http://127.0.0.1:{UI}")
    monkeypatch.setenv("PANEL_PORT", str(PANEL))
    project = SimpleNamespace(name="acme", repo_path=str(tmp_path), forge=None, tracker=None)
    probe = doctor.probes_for(project).processes
    assert probe is not None
    return probe


def test_a_listener_answering_after_the_old_bound_but_inside_the_deadline_answers(
        monkeypatch, tmp_path):
    monkeypatch.setenv("BEEVERFORGE_ENGINE_DEADLINE", "5")
    handed = _a_machine(monkeypatch, {ENGINE: 4.0, UI: 4.0, PANEL: None})

    answered = _probe(monkeypatch, tmp_path)()

    assert answered["engine"][0] is True, "an engine answering in 4 s, inside a 5 s deadline"
    assert answered["engine UI"][0] is True, "a UI answering in 4 s, inside a 5 s deadline"
    assert answered["panel"][0] is False, "a panel that never answers"
    assert handed == [5.0, 5.0, 5.0]


def test_the_connect_is_bounded_by_the_deployments_deadline(monkeypatch, tmp_path):
    """Unset, the deadline's own default is followed, not a literal of the doctor's."""
    handed = _a_machine(monkeypatch, {ENGINE: None, UI: None, PANEL: None})

    answered = _probe(monkeypatch, tmp_path)()

    assert not any(up for up, _ in answered.values())
    assert handed and all(t == read_deadline() for t in handed), handed


def _processes_finding(answered):
    from beeverforge import doctor
    from tests.pinned_probes import a_fully_pinned_probe_set

    report = doctor.diagnose(a_fully_pinned_probe_set(processes=lambda: answered))
    return next(f for f in report.findings if f.check == "processes")


@pytest.mark.parametrize("answered, already", [
    ({"engine": (True, "localhost:7233"), "engine UI": (False, "http://localhost:8080"),
      "panel": (True, "http://localhost:8787")}, "TEMPORAL_UI_URL"),
    ({"engine": (False, "localhost:7233"), "engine UI": (False, "http://localhost:8080"),
      "panel": (True, "http://localhost:8787")}, "beeverforge up"),
    ({"engine": (False, "localhost:7233"), "engine UI": (False, "http://localhost:8080"),
      "panel": (False, "http://localhost:8787")}, "beeverforge up"),
], ids=["the UI does not answer", "the engine does not answer", "neither answers"])
def test_an_unanswered_listener_says_how_long_the_doctor_waited_and_what_sets_it(
        monkeypatch, answered, already):
    monkeypatch.setenv("BEEVERFORGE_ENGINE_DEADLINE", "7")

    finding = _processes_finding(answered)

    assert not finding.ok
    assert "7s" in finding.remedy and "BEEVERFORGE_ENGINE_DEADLINE" in finding.remedy, (
        finding.remedy)
    assert already in finding.remedy, finding.remedy


@pytest.mark.parametrize("answered", [
    {"engine": (True, "localhost:7233"), "engine UI": (True, "http://localhost:8080"),
     "panel": (True, "http://localhost:8787")},
    {"engine": (True, "localhost:7233"), "engine UI": (False, ""),
     "panel": (True, "http://localhost:8787")},
], ids=["everything answers", "nobody said where the UI is"])
def test_where_nothing_was_waited_on_no_wait_is_named(monkeypatch, answered):
    monkeypatch.setenv("BEEVERFORGE_ENGINE_DEADLINE", "7")

    finding = _processes_finding(answered)

    said = f"{finding.message} {finding.remedy or ''} {getattr(finding, 'note', '') or ''}"
    assert "BEEVERFORGE_ENGINE_DEADLINE" not in said, said
