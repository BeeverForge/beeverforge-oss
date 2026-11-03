"""The engine's readiness probe waits as long as the connect it guards (#398).

With JSON lines, `connection.connect` asks the socket (`_listening`) before it builds a runtime,
and a worker being born asks it until the engine listens (`connect_at_birth`). The probe had a
fixed 1.0 s of its own, shorter than the attempt's bound (the caller's `within`, else
`BEEVERFORGE_ENGINE_DEADLINE`), so a loaded host could report a listening engine as not
listening. Now the probe is bounded by the attempt alone: an answer inside the attempt's bound is
listening, a probe that runs out of it is said as the attempt's timeout, and a port nobody listens
on is still refused before anything is built.

NO REAL WAITS. Every case runs on an event loop whose clock is a counter (`_VirtualClockLoop`):
when nothing is ready, the loop's wait for its next timer moves the counter instead of sleeping,
and the socket's answer is a stand-in that answers after a given number of those seconds. A loop
that would wait with no timer at all fails the case instead of hanging it.
"""

from __future__ import annotations

import asyncio
import selectors
import types

import pytest

from beeverforge.observability import logs
from beeverforge.runtime.temporal import connection


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0


class _VirtualSelector(selectors.DefaultSelector):
    """Asks the real selector without waiting; a wait for a timer moves the clock instead."""

    def __init__(self, clock: _Clock) -> None:
        super().__init__()
        self._clock = clock

    def select(self, timeout=None):
        ready = super().select(0)
        if ready:
            return ready
        if timeout is None:
            raise AssertionError("the loop would wait for ever: nothing bounds what it waits on")
        if timeout > 0:
            self._clock.now += timeout
        return ready


class _VirtualClockLoop(asyncio.SelectorEventLoop):
    def __init__(self, clock: _Clock) -> None:
        self._clock = clock
        super().__init__(_VirtualSelector(clock))

    def time(self) -> float:
        return self._clock.now


class _Writer:
    def close(self) -> None:
        pass

    async def wait_closed(self) -> None:
        pass


class _Engine:
    """Stand-ins for the socket's answer, the runtime and the client, with what each was asked."""

    def __init__(self, monkeypatch, clock: _Clock) -> None:
        self.clock = clock
        self.built: list = []
        self.connects: list = []
        self.asked: list[float] = []
        self.answered: list[float] = []
        self.client = object()
        monkeypatch.setenv(logs.FORMAT_VARIABLE, "json")
        monkeypatch.setenv("TEMPORAL_ADDRESS", "127.0.0.1:7233")
        monkeypatch.setattr(connection, "time", types.SimpleNamespace(monotonic=lambda: clock.now))

        def _runtime():
            self.built.append(clock.now)
            return object()

        async def _connect(*_a, **_kw):
            self.connects.append(clock.now)
            return self.client

        monkeypatch.setattr(connection, "core_runtime", _runtime)
        monkeypatch.setattr(connection.Client, "connect", _connect)
        self._monkeypatch = monkeypatch

    def answers_after(self, seconds: float) -> None:
        async def _open(_host, _port):
            self.asked.append(self.clock.now)
            await asyncio.sleep(seconds)
            self.answered.append(self.clock.now)
            return None, _Writer()

        self._monkeypatch.setattr(connection.asyncio, "open_connection", _open)

    def never_answers(self) -> None:
        async def _open(_host, _port):
            self.asked.append(self.clock.now)
            await asyncio.Event().wait()

        self._monkeypatch.setattr(connection.asyncio, "open_connection", _open)

    def refuses(self) -> None:
        async def _open(_host, _port):
            self.asked.append(self.clock.now)
            raise ConnectionRefusedError(111, "Connection refused")

        self._monkeypatch.setattr(connection.asyncio, "open_connection", _open)


@pytest.fixture
def clock() -> _Clock:
    return _Clock()


@pytest.fixture
def engine(monkeypatch, clock) -> _Engine:
    return _Engine(monkeypatch, clock)


def _run(clock: _Clock, make):
    with asyncio.Runner(loop_factory=lambda: _VirtualClockLoop(clock)) as runner:
        return runner.run(make())


@pytest.mark.parametrize(("deadline", "answer_s", "within"), [
    pytest.param("3", 4.0, 5.0, id="the-callers-within"),
    pytest.param("2.5", 1.5, None, id="the-engine-deadline"),
])
def test_a_listener_that_answers_after_the_old_second_but_inside_the_attempts_bound_is_listening(
        engine, clock, monkeypatch, deadline, answer_s, within):
    monkeypatch.setenv("BEEVERFORGE_ENGINE_DEADLINE", deadline)
    engine.answers_after(answer_s)

    got = _run(clock, lambda: connection.connect(within=within))

    assert got is engine.client
    assert len(engine.built) == 1, "a listening engine is given its one runtime"
    assert len(engine.connects) == 1
    assert engine.answered == [answer_s], "the probe waited for the listener's answer"
    assert clock.now >= answer_s


def test_a_probe_that_runs_out_of_the_attempts_bound_is_said_as_the_timeout_not_as_nothing_listening(
        engine, clock):
    engine.never_answers()

    with pytest.raises(TimeoutError) as raised:
        _run(clock, lambda: connection.connect(within=2.0))

    assert not isinstance(raised.value, connection.EngineNotListening)
    said = str(raised.value)
    assert "did not take a connection within 2s" in said
    assert "BEEVERFORGE_ENGINE_DEADLINE" in said
    assert engine.built == [], "a probe that ran out built no runtime"
    assert clock.now == pytest.approx(2.0)


def test_an_address_where_nothing_listens_is_still_refused_before_a_runtime_is_built(
        engine, clock):
    engine.refuses()

    with pytest.raises(connection.EngineNotListening) as raised:
        _run(clock, lambda: connection.connect(within=5.0))

    assert "nothing accepted a connection at 127.0.0.1:7233" in str(raised.value)
    assert engine.built == []
    assert engine.connects == []


def test_a_birth_probe_that_answers_after_the_old_second_is_listening(engine, clock):
    engine.answers_after(1.5)

    got = _run(clock, lambda: connection.connect_at_birth(within=4.0))

    assert got is engine.client
    assert engine.asked[0] == 0.0
    assert engine.answered[0] == pytest.approx(1.5), (
        "the birth's first probe was answered, not given up after the old second and retried")
    assert len(engine.built) == 1
