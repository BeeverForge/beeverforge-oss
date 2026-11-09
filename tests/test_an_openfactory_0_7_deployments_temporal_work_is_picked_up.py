"""An OpenFactory 0.7 deployment upgraded in place keeps its Temporal work (#264).

BeeverForge names its Temporal task queue and schedules `beeverforge-*`; OpenFactory 0.7 named
them `openfactory-*`. A 0.7 deployment upgraded against the same Temporal server has, at the
moment the new worker boots:

- workflows 0.7 started, and activities they scheduled, sitting on 0.7's task queue
  (`openfactory-jobs`). A worker that polls only `beeverforge-jobs` never picks them up: a job in
  flight, a merge gate a person answers hours later, a deploy watch — each stranded for ever.
- 0.7's schedules (`openfactory-poller`, the per-project sweeps, the previews' reaper), which keep
  firing onto `openfactory-jobs` beside the new `beeverforge-*` ones. With the worker polling
  that queue too, every board would be scanned twice per tick and every sweep reported twice.

So, until 1.0: the worker polls BOTH queues with the same workflows and activities, nothing new is
ever started on the former one, and `ensure_all` deletes 0.7's schedules — by their exact ids and
per-project prefixes only — once the new ones are ensured.

The engine is faked here: `Worker` and the client record what they were asked; no server runs.
"""

from __future__ import annotations

import ast
import asyncio
import logging
from pathlib import Path

import pytest

from tests.the_tree_read_once import parsed

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "acme"

#: OpenFactory 0.7's own names, read at its tag v0.7.0 (`openfactory/runtime/temporal/
#: __init__.py` and `schedule.py`). Written out here, not imported, so the test holds the code to
#: what 0.7 actually created rather than to whatever the code says 0.7 created.
FORMER_QUEUE = "openfactory-jobs"
FORMER_IDS = {"openfactory-poller", "openfactory-preview-reaper"}
FORMER_PREFIXES = ("openfactory-product-sweep", "openfactory-techlead-watch",
                   "openfactory-card-questions", "openfactory-okf-refresh")
FORMER_PER_PROJECT = {f"{prefix}-{PROJECT}" for prefix in FORMER_PREFIXES}
#: …and a former project the registry no longer holds: 0.7's schedule for it still fires.
FORMER_GONE_PROJECT = {f"{prefix}-gone" for prefix in FORMER_PREFIXES}
EVERY_FORMER = FORMER_IDS | FORMER_PER_PROJECT | FORMER_GONE_PROJECT

#: Schedules that are not 0.7's and must survive: names that merely START like one of 0.7's, a
#: prefix with no project after its dash, a schedule 0.7 never made, and somebody else's.
NOT_FORMER = {
    "openfactory-poller-copy",
    "openfactory-preview-reaper-2",
    "openfactory-product-sweeper",
    "openfactory-okf-refresh",
    "openfactory-metrics-purge",
    "someone-nightly-backup",
}


# ── the worker ───────────────────────────────────────────────────────────────────────────────────

class _Worker:
    """`temporalio.worker.Worker`, recorded: what each was built with, and whether it ran."""

    built: list[_Worker] = []

    def __init__(self, client, **kwargs):
        self.client = client
        self.kwargs = kwargs
        self.ran = False
        _Worker.built.append(self)

    async def run(self):
        self.ran = True


@pytest.fixture
def booted(monkeypatch):
    """`worker.main()` driven to its end with everything around the engine faked: no `.env`, no
    registry seed, no toolbox copy, no listeners, no health port, no schedules."""
    from beeverforge.runtime.temporal import worker

    _Worker.built = []

    async def _client():
        return "the client"

    async def _no_schedules():
        return []

    async def _no_health():
        return None

    # what the worker announces it is connected to: declared, as a deployment's would be
    monkeypatch.setenv("TEMPORAL_ADDRESS", "localhost:7233")
    monkeypatch.setattr(worker, "Worker", _Worker)
    monkeypatch.setattr(worker, "load_dotenv", lambda *_a, **_k: False)
    monkeypatch.setattr(worker, "connect_at_birth", _client)
    monkeypatch.setattr(worker, "start_channel_listeners", lambda _projects: [])
    monkeypatch.setattr("beeverforge.registry.seed_registry", lambda *_a, **_k: None)
    monkeypatch.setattr("beeverforge.runtime.toolbox.populate", lambda *_a, **_k: None)
    monkeypatch.setattr("beeverforge.observability.health.listen", _no_health)
    monkeypatch.setattr("beeverforge.namespace.announce_build", lambda *_a, **_k: None)
    monkeypatch.setattr("beeverforge.runtime.temporal.schedule.ensure_all", _no_schedules)
    asyncio.run(asyncio.wait_for(worker.main(), timeout=10))
    return _Worker.built


def test_the_former_queue_is_the_one_openfactory_0_7_polled():
    from beeverforge.runtime.temporal import FORMER_TASK_QUEUE, TASK_QUEUE

    assert FORMER_TASK_QUEUE == FORMER_QUEUE
    assert TASK_QUEUE != FORMER_TASK_QUEUE


def test_the_worker_polls_its_own_queue_and_0_7s(booted):
    """One worker per queue, both run: work 0.7 left on `openfactory-jobs` is picked up."""
    from beeverforge.runtime.temporal import FORMER_TASK_QUEUE, TASK_QUEUE

    queues = sorted(w.kwargs.get("task_queue") for w in booted)
    assert queues == sorted([TASK_QUEUE, FORMER_TASK_QUEUE]), queues
    assert all(w.ran for w in booted), [w.kwargs.get("task_queue") for w in booted if not w.ran]
    assert all(w.client == "the client" for w in booted)


def test_the_former_queue_is_served_by_the_same_workflows_and_activities(booted):
    """A workflow 0.7 started replays on the former queue and schedules its activities there, so
    that worker must know every workflow and activity the new one does — one missing is an
    unknown-type failure at the moment the stranded work is finally polled."""
    from beeverforge.runtime.temporal import FORMER_TASK_QUEUE, TASK_QUEUE
    from beeverforge.runtime.temporal.worker import WORKER_ACTIVITIES

    by_queue = {w.kwargs["task_queue"]: w.kwargs for w in booted}
    own, former = by_queue[TASK_QUEUE], by_queue[FORMER_TASK_QUEUE]
    assert list(former["workflows"]) == list(own["workflows"])
    assert list(own["activities"]) == list(WORKER_ACTIVITIES)
    assert list(former["activities"]) == list(own["activities"])
    assert [type(i) for i in former.get("interceptors", [])] == \
        [type(i) for i in own.get("interceptors", [])]
    assert former.get("max_concurrent_activities") == own.get("max_concurrent_activities")


def test_nothing_new_is_started_on_the_former_queue():
    """The former queue is POLLED, never a destination: no module but the one that defines it and
    the worker that polls it names it, and its spelling appears nowhere else in the package. A
    start or a schedule aimed at it would keep 0.7's name alive past 1.0."""
    from beeverforge.runtime.temporal import FORMER_TASK_QUEUE

    allowed = {ROOT / "beeverforge/runtime/temporal/__init__.py",
               ROOT / "beeverforge/runtime/temporal/worker.py"}
    named, spelled = [], []
    for path in sorted((ROOT / "beeverforge").rglob("*.py")):
        if path in allowed:
            continue
        for node in ast.walk(parsed(path)):
            if isinstance(node, ast.Name) and node.id == "FORMER_TASK_QUEUE" or (
                    isinstance(node, ast.Attribute) and node.attr == "FORMER_TASK_QUEUE") or (
                    isinstance(node, ast.alias) and node.name == "FORMER_TASK_QUEUE"):
                named.append(f"{path.relative_to(ROOT)}:{getattr(node, 'lineno', '?')}")
            if isinstance(node, ast.Constant) and node.value == FORMER_TASK_QUEUE:
                spelled.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not named, f"the former queue is named outside its poller: {named}"
    assert not spelled, f"the former queue is spelled outside its definition: {spelled}"
    # …and the worker hands it to `Worker` and to nothing else that could start work.
    worker = parsed(ROOT / "beeverforge/runtime/temporal/worker.py")
    for node in ast.walk(worker):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") in (
                "start_workflow", "execute_workflow", "create_schedule"):
            raise AssertionError(f"worker.py starts work at line {node.lineno}")


# ── 0.7's schedules ──────────────────────────────────────────────────────────────────────────────

class _Listed:
    def __init__(self, sid):
        self.id = sid


class _Engine:
    """A client on which some schedules already exist. It records, in order, every schedule it
    was asked to create and every one it deleted; `refuse` maps an id to what its delete raises,
    and `unlistable` makes the next listing itself fail."""

    #: no `service_client`: the retention read fails and says so, as on a namespace this
    #: credential may not read — the retention is not what this file is about
    namespace = "default"

    def __init__(self, existing):
        self.existing = set(existing)
        self.events: list[tuple[str, str]] = []
        self.refuse: dict[str, BaseException] = {}
        self.unlistable: BaseException | None = None
        self.uncreatable: BaseException | None = None

    async def create_schedule(self, sid, _schedule):
        if self.uncreatable is not None:
            raise self.uncreatable
        self.events.append(("create", sid))
        self.existing.add(sid)

    async def list_schedules(self, *_a, **_k):
        if self.unlistable is not None:
            # ONCE: the first listing at boot is 0.7's retirement. The orphan retirement lists
            # again after it, and what it does with a failed listing is not this file's case.
            failure, self.unlistable = self.unlistable, None
            raise failure
        listed = [_Listed(sid) for sid in sorted(self.existing)]

        async def _iterate():
            for item in listed:
                yield item

        return _iterate()

    def get_schedule_handle(self, sid):
        engine = self

        class _Handle:
            async def delete(self, *_a, **_k):
                if sid in engine.refuse:
                    raise engine.refuse[sid]
                engine.events.append(("delete", sid))
                engine.existing.discard(sid)

            async def update(self, fn, *_a, **_k):
                engine.events.append(("update", sid))

        return _Handle()

    @property
    def deleted(self) -> set[str]:
        return {sid for kind, sid in self.events if kind == "delete"}

    @property
    def ensured(self) -> set[str]:
        return {sid for kind, sid in self.events if kind in ("create", "update")}


def _not_found(sid: str):
    from temporalio.service import RPCError, RPCStatusCode

    return RPCError(f"schedule {sid} not found", RPCStatusCode.NOT_FOUND, b"")


@pytest.fixture
def engine(tmp_path, monkeypatch):
    """One registered project with the product module, and an engine holding every one of 0.7's
    schedules, schedules that only look like 0.7's, and none of BeeverForge's yet."""
    monkeypatch.setenv("BEEVERFORGE_REGISTRY", str(tmp_path / "registry.yaml"))
    from beeverforge.contracts.product import ProductConfig
    from beeverforge.contracts.project import Project, ProviderRef
    from beeverforge.registry import ProjectRegistry
    from beeverforge.runtime.temporal import schedule

    ProjectRegistry().add(Project(name=PROJECT, repo_path=str(tmp_path), language="en",
                                  tracker=ProviderRef(kind="local", repo=PROJECT, options={}),
                                  product=ProductConfig(docs_repo="acme/docs")))
    fake = _Engine(EVERY_FORMER | NOT_FORMER)

    async def _connect(*_a, **_k):
        return fake

    monkeypatch.setattr(schedule, "connect", _connect)
    return fake


def _ensure_all():
    from beeverforge.runtime.temporal import schedule

    return asyncio.run(asyncio.wait_for(schedule.ensure_all(), timeout=10))


def _beeverforge_ids() -> set[str]:
    from beeverforge.runtime.temporal import schedule as s

    return {s.SCHEDULE_ID, s.PREVIEW_REAP_SCHEDULE_ID, s.METRICS_PURGE_SCHEDULE_ID} | {
        f"{prefix}-{PROJECT}" for prefix in (s.PRODUCT_SCHEDULE_PREFIX, s.WATCH_SCHEDULE_PREFIX,
                                             s.CARD_QUESTION_SCHEDULE_PREFIX,
                                             s.OKF_SCHEDULE_PREFIX)}


def test_ensure_all_retires_every_one_of_0_7s_schedules_and_nothing_else(engine):
    _ensure_all()

    assert engine.deleted == EVERY_FORMER, (
        f"left {sorted(EVERY_FORMER - engine.deleted)}, "
        f"deleted what is not 0.7's {sorted(engine.deleted - EVERY_FORMER)}")
    assert NOT_FORMER <= engine.existing


def test_0_7s_schedules_are_retired_only_after_beeverforges_are_ensured(engine):
    """Deleted first, a boot that then failed to create the new ones would leave the deployment
    with no poller at all."""
    _ensure_all()

    assert _beeverforge_ids() <= engine.ensured, sorted(_beeverforge_ids() - engine.ensured)
    last_ensure = max(i for i, (kind, _sid) in enumerate(engine.events) if kind != "delete")
    first_delete = min(i for i, (kind, _sid) in enumerate(engine.events) if kind == "delete")
    assert first_delete > last_ensure, engine.events


def test_a_boot_that_could_not_ensure_the_new_schedules_retires_none_of_0_7s(engine):
    """0.7's poller is the only one there is until BeeverForge's exists."""
    engine.uncreatable = RuntimeError("the engine refused the create")
    with pytest.raises(RuntimeError):
        _ensure_all()
    assert engine.deleted == set()


def test_what_was_retired_is_said_in_one_line_naming_each(engine):
    lines = _ensure_all()

    naming = [line for line in lines if any(sid in line for sid in EVERY_FORMER)]
    assert len(naming) == 1, naming
    assert all(sid in naming[0] for sid in EVERY_FORMER), naming[0]


def test_a_schedule_already_gone_is_not_a_failure(engine, caplog):
    """Deleted by somebody between the listing and the delete — or by a second worker booting
    beside this one — is the state retirement wants."""
    engine.refuse["openfactory-poller"] = _not_found("openfactory-poller")
    with caplog.at_level(logging.WARNING, logger="beeverforge.schedule"):
        _ensure_all()

    assert engine.deleted == EVERY_FORMER - {"openfactory-poller"}
    assert not [r for r in caplog.records if "openfactory-poller" in r.getMessage()
                and r.levelno >= logging.ERROR], caplog.text


@pytest.mark.parametrize("refusal", [
    pytest.param(lambda: __import__("temporalio.service", fromlist=["RPCError"]).RPCError(
        "not allowed", __import__("temporalio.service", fromlist=["RPCStatusCode"])
        .RPCStatusCode.PERMISSION_DENIED, b""), id="the-engine-refuses"),
    pytest.param(lambda: RuntimeError("the connection dropped"), id="anything-else"),
])
def test_a_schedule_that_could_not_be_retired_is_said_by_name_and_the_rest_go_on(
        engine, caplog, refusal):
    sid = f"openfactory-techlead-watch-{PROJECT}"
    engine.refuse[sid] = refusal()
    with caplog.at_level(logging.WARNING, logger="beeverforge.schedule"):
        lines = _ensure_all()

    assert engine.deleted == EVERY_FORMER - {sid}
    assert _beeverforge_ids() <= engine.ensured
    errors = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert [m for m in errors if sid in m and str(engine.refuse[sid]) in m], caplog.text
    retired = [line for line in lines if "openfactory-poller" in line]
    assert retired and sid not in retired[0], lines


def test_an_engine_whose_schedules_cannot_be_listed_is_said_and_the_boot_goes_on(engine, caplog):
    engine.unlistable = RuntimeError("the listing timed out")
    with caplog.at_level(logging.WARNING, logger="beeverforge.schedule"):
        _ensure_all()

    assert engine.deleted == set()
    assert _beeverforge_ids() <= engine.ensured
    errors = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert [m for m in errors if "0.7" in m and "the listing timed out" in m], caplog.text


def test_an_engine_without_any_of_0_7s_schedules_says_nothing_about_them(engine):
    engine.existing -= EVERY_FORMER
    lines = _ensure_all()

    assert engine.deleted == set()
    assert not [line for line in lines if "0.7" in line], lines
