"""A project's rounds follow its `enabled` switch (#243).

The tech-lead watch, the knowledge refresh and the card-question sweep are per-project schedules
that `ensure_all` created for enabled projects at worker boot only. Enabling a project later
scheduled nothing until the worker restarted, and disabling one left its rounds firing for ever.

The engine is faked: a client that records the schedules it holds. No server, no clock.
"""

from __future__ import annotations

import asyncio

import pytest

PROJECT = "acme"


class _Listed:
    def __init__(self, sid):
        self.id = sid


class _Engine:
    namespace = "default"

    def __init__(self, existing=()):
        self.existing = set(existing)
        self.events: list[tuple[str, str]] = []

    async def create_schedule(self, sid, _schedule):
        from temporalio.client import ScheduleAlreadyRunningError

        if sid in self.existing:
            raise ScheduleAlreadyRunningError()
        self.events.append(("create", sid))
        self.existing.add(sid)

    async def list_schedules(self, *_a, **_k):
        listed = [_Listed(sid) for sid in sorted(self.existing)]

        async def _iterate():
            for item in listed:
                yield item

        return _iterate()

    def get_schedule_handle(self, sid):
        engine = self

        class _Handle:
            async def delete(self, *_a, **_k):
                if sid not in engine.existing:
                    from temporalio.service import RPCError, RPCStatusCode

                    raise RPCError("not found", RPCStatusCode.NOT_FOUND, b"")
                engine.events.append(("delete", sid))
                engine.existing.discard(sid)

            async def update(self, fn, *_a, **_k):
                engine.events.append(("update", sid))

        return _Handle()


def _rounds(name: str) -> set[str]:
    from beeverforge.runtime.temporal import schedule as s

    return {f"{prefix}-{name}" for prefix in (
        s.WATCH_SCHEDULE_PREFIX, s.OKF_SCHEDULE_PREFIX, s.CARD_QUESTION_SCHEDULE_PREFIX)}


def _register(tmp_path, monkeypatch, *, enabled: bool, name: str = PROJECT) -> None:
    monkeypatch.setenv("BEEVERFORGE_REGISTRY", str(tmp_path / "registry.yaml"))
    from beeverforge.contracts.project import Project, ProviderRef
    from beeverforge.registry import ProjectRegistry

    ProjectRegistry().add(Project(name=name, repo_path=str(tmp_path), language="en",
                                  tracker=ProviderRef(kind="local", repo=name, options={}),
                                  enabled=enabled))


@pytest.fixture
def engine(tmp_path, monkeypatch):
    from beeverforge.runtime.temporal import schedule

    fake = _Engine()

    async def _connect(*_a, **_k):
        return fake

    monkeypatch.setattr(schedule, "connect", _connect)
    _register(tmp_path, monkeypatch, enabled=False)
    return fake


def _run(coro):
    return asyncio.run(asyncio.wait_for(coro, timeout=10))


def _enable(enabled: bool):
    from beeverforge import actions
    from beeverforge.actions.base import Actor

    return _run(actions.perform("enable", by=Actor(id="t", via="test", admin=True), project=PROJECT,
                                enabled=enabled))


def test_enabling_a_disabled_project_creates_its_three_rounds_at_once(engine):
    assert _rounds(PROJECT).isdisjoint(engine.existing)
    outcome = _enable(True)
    assert outcome.ok, outcome.message
    assert engine.existing == _rounds(PROJECT)


def test_rounds_that_already_exist_are_updated_not_recreated(engine):
    from beeverforge.runtime.temporal import schedule

    engine.existing |= _rounds(PROJECT)
    made = _run(schedule.schedule_project_rounds(PROJECT))
    assert sorted(e for e in engine.events if e[0] == "update") == sorted(
        ("update", sid) for sid in _rounds(PROJECT))
    assert not [e for e in engine.events if e[0] == "create"]
    assert sorted(made) == sorted(f"updated {sid}" for sid in _rounds(PROJECT))


def test_enabling_one_project_schedules_nothing_for_another(engine, tmp_path, monkeypatch):
    _register(tmp_path, monkeypatch, enabled=False, name="other")
    _enable(True)
    assert engine.existing == _rounds(PROJECT)


def test_disabling_a_project_deletes_its_three_rounds(engine):
    # seeded straight into the engine: going through the enable path would make this pass on
    # code that has no disable path at all
    engine.existing |= _rounds(PROJECT) | {"beeverforge-poller"}
    outcome = _enable(False)
    assert outcome.ok, outcome.message
    assert engine.existing == {"beeverforge-poller"}


def test_disabling_a_project_whose_rounds_are_already_gone_is_not_an_error(engine):
    outcome = _enable(False)
    assert outcome.ok and "next worker boot" not in outcome.message
    assert engine.existing == set()


def test_an_engine_that_is_down_does_not_undo_the_switch_and_says_so(engine, monkeypatch):
    from beeverforge.registry import ProjectRegistry
    from beeverforge.runtime.temporal import schedule

    async def _down(*_a, **_k):
        raise ConnectionError("engine unreachable")

    monkeypatch.setattr(schedule, "connect", _down)
    outcome = _enable(True)
    assert [p.enabled for p in ProjectRegistry().list() if p.name == PROJECT] == [True]
    assert "next worker boot" in outcome.message


def test_a_boot_retires_the_rounds_of_a_registered_disabled_project(engine):
    engine.existing |= _rounds(PROJECT) | {"beeverforge-poller", "someone-else"}
    from beeverforge.runtime.temporal import schedule

    out = _run(schedule.ensure_all())
    assert engine.existing.isdisjoint(_rounds(PROJECT))
    assert {"beeverforge-poller", "someone-else"} <= engine.existing
    assert any(PROJECT in line and "disabled" in line for line in out)


def test_a_boot_keeps_the_rounds_of_an_enabled_project(engine, tmp_path, monkeypatch):
    _register(tmp_path, monkeypatch, enabled=True, name="live")
    from beeverforge.runtime.temporal import schedule

    engine.existing |= _rounds(PROJECT)
    _run(schedule.ensure_all())
    assert _rounds("live") <= engine.existing
    assert engine.existing.isdisjoint(_rounds(PROJECT))
