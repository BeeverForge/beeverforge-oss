"""`doctor`'s "is anything listening" check waits as long as the engine's deadline (#407).

It gave up after a fixed 1.5 s, so on a loaded host a listener that answered late was reported as
down while the rest of the deployment waited `BEEVERFORGE_ENGINE_DEADLINE` (`read_deadline()`)
for the same engine. A robustness gap, not an observed failure: #398 measured a probe max of
6.4 ms at a load average of 3-6, #402 a max of 120 ms at load averages up to 49.

A REFUSAL IS NOT A WAIT. A port nothing listens on refuses in milliseconds, so a remedy that
says the doctor waited the deadline for it, and points at the variable that raises it, names a
cause that did not happen and a lever that cannot help. Only a listener that timed out is said to
have been waited on.

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


REFUSES = "refuses"


def _a_machine(monkeypatch, answers_after: dict[int, float | None | str]) -> list:
    """Replace the connect with one whose listeners answer after a simulated time (None: never,
    so the connect times out; `REFUSES`: nothing listens, so it is refused at once). Returns the
    list of `timeout` values the probe handed it."""
    handed: list = []

    def create_connection(address, timeout=None, *args, **kwargs):
        handed.append(timeout)
        if timeout is None:
            raise AssertionError(f"an unbounded connect to {address}")
        after = answers_after[address[1]]
        if after == REFUSES:
            raise ConnectionRefusedError(111, "Connection refused")
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


_WHO = {ENGINE: "durable engine", UI: "UI", PANEL: "panel"}


@pytest.mark.parametrize("answers_after, already", [
    ({ENGINE: 0.0, UI: None, PANEL: 0.0}, "TEMPORAL_UI_URL"),
    ({ENGINE: None, UI: None, PANEL: 0.0}, "beeverforge up"),
    ({ENGINE: None, UI: None, PANEL: None}, "beeverforge up"),
], ids=["the UI does not answer", "the engine does not answer", "neither answers"])
def test_an_unanswered_listener_says_how_long_the_doctor_waited_and_what_sets_it(
        monkeypatch, tmp_path, answers_after, already):
    monkeypatch.setenv("BEEVERFORGE_ENGINE_DEADLINE", "7")
    _a_machine(monkeypatch, answers_after)

    finding = _processes_finding(_probe(monkeypatch, tmp_path)())

    assert not finding.ok
    assert "7s" in finding.remedy and "BEEVERFORGE_ENGINE_DEADLINE" in finding.remedy, (
        finding.remedy)
    assert already in finding.remedy, finding.remedy


@pytest.mark.parametrize("answers_after, already", [
    ({ENGINE: 0.0, UI: REFUSES, PANEL: 0.0}, "TEMPORAL_UI_URL"),
    ({ENGINE: REFUSES, UI: REFUSES, PANEL: 0.0}, "beeverforge up"),
    ({ENGINE: REFUSES, UI: REFUSES, PANEL: REFUSES}, "beeverforge up"),
], ids=["the UI refuses", "the engine refuses", "both refuse"])
def test_a_listener_that_refused_at_once_names_no_wait(
        monkeypatch, tmp_path, answers_after, already):
    """The common case: nothing was started on this machine, every port refuses in milliseconds,
    and raising the deadline would change nothing."""
    monkeypatch.setenv("BEEVERFORGE_ENGINE_DEADLINE", "7")
    _a_machine(monkeypatch, answers_after)

    finding = _processes_finding(_probe(monkeypatch, tmp_path)())

    assert not finding.ok
    assert "waited" not in finding.remedy and "BEEVERFORGE_ENGINE_DEADLINE" not in finding.remedy, (
        finding.remedy)
    assert already in finding.remedy, finding.remedy


@pytest.mark.parametrize("answers_after, waited_on, not_waited_on", [
    ({ENGINE: REFUSES, UI: REFUSES, PANEL: None}, PANEL, ENGINE),
    ({ENGINE: None, UI: REFUSES, PANEL: REFUSES}, ENGINE, PANEL),
], ids=["the engine refuses and the panel times out", "the engine times out and the panel refuses"])
def test_where_only_some_timed_out_the_wait_is_said_of_those_alone(
        monkeypatch, tmp_path, answers_after, waited_on, not_waited_on):
    monkeypatch.setenv("BEEVERFORGE_ENGINE_DEADLINE", "7")
    _a_machine(monkeypatch, answers_after)

    finding = _processes_finding(_probe(monkeypatch, tmp_path)())

    assert not finding.ok and "beeverforge up" in finding.remedy, finding.remedy
    _, said, wait = finding.remedy.partition("; the doctor waited 7s")
    assert said and "BEEVERFORGE_ENGINE_DEADLINE" in wait, finding.remedy
    assert _WHO[waited_on] in wait and _WHO[not_waited_on] not in wait, finding.remedy


@pytest.mark.parametrize("answered", [
    {"engine": (True, "localhost:7233"), "engine UI": (True, "http://localhost:8080"),
     "panel": (True, "http://localhost:8787")},
    {"engine": (True, "localhost:7233"), "engine UI": (False, ""),
     "panel": (True, "http://localhost:8787")},
    {"engine": (False, "not declared — set `TEMPORAL_ADDRESS=localhost:7233`"),
     "panel": (True, "http://localhost:8787")},
], ids=["everything answers", "nobody said where the UI is", "the engine is not declared"])
def test_where_nothing_was_waited_on_no_wait_is_named(monkeypatch, answered):
    monkeypatch.setenv("BEEVERFORGE_ENGINE_DEADLINE", "7")

    finding = _processes_finding(answered)

    said = f"{finding.message} {finding.remedy or ''} {getattr(finding, 'note', '') or ''}"
    assert "BEEVERFORGE_ENGINE_DEADLINE" not in said, said


def test_an_engine_nobody_declared_is_not_said_to_have_been_waited_on(monkeypatch, tmp_path):
    """Through the probe itself: an undeclared engine is never dialled, so the panel that answers
    beside it leaves nothing that was waited on."""
    monkeypatch.setenv("BEEVERFORGE_ENGINE_DEADLINE", "7")
    _a_machine(monkeypatch, {UI: None, PANEL: 0.0})
    probe = _probe(monkeypatch, tmp_path)
    monkeypatch.delenv("TEMPORAL_ADDRESS")

    finding = _processes_finding(probe())

    assert not finding.ok and "not declared" in finding.message, finding.message
    assert "BEEVERFORGE_ENGINE_DEADLINE" not in finding.remedy, finding.remedy
