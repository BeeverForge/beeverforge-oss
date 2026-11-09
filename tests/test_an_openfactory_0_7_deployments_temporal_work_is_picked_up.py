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
    #: the queue whose worker's `run` raises; every other one then waits until it is cancelled,
    #: or until `release` is set — so a worker that is never stopped fails the test, not hangs it
    failing: str | None = None
    release: asyncio.Event

    def __init__(self, client, **kwargs):
        self.client = client
        self.kwargs = kwargs
        self.ran = False
        self.cancelled = False
        _Worker.built.append(self)

    async def run(self):
        self.ran = True
        if _Worker.failing is None:
            return
        if self.kwargs.get("task_queue") == _Worker.failing:
            raise RuntimeError(f"polling {_Worker.failing} was refused")
        try:
            await _Worker.release.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise


@pytest.fixture
def booted(monkeypatch):
    """`worker.main()` driven to its end with everything around the engine faked: no `.env`, no
    registry seed, no toolbox copy, no listeners, no health port, no schedules."""
    from beeverforge.runtime.temporal import worker

    _Worker.built = []
    _Worker.failing = None

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
    if getattr(booted_with, "failing", None):
        _Worker.failing = booted_with.failing

        async def _boot():
            _Worker.release = asyncio.Event()
            boot = asyncio.ensure_future(worker.main())
            await asyncio.wait([boot], timeout=10)
            # read BEFORE the release, and before the loop's teardown cancels what is left
            stopped = [w.cancelled for w in _Worker.built
                       if w.kwargs.get("task_queue") != _Worker.failing]
            _Worker.release.set()
            # what the boot raised, read here and asserted by the test, so a boot that did not
            # raise fails the test rather than erroring its fixture
            try:
                await asyncio.wait_for(boot, timeout=10)
            except RuntimeError as exc:
                return exc, stopped
            return None, stopped

        return asyncio.run(_boot())
    asyncio.run(asyncio.wait_for(worker.main(), timeout=10))
    return _Worker.built


#: set by a test that wants one queue's worker to fail at boot (`booted`)
booted_with = type("BootedWith", (), {"failing": None})


@pytest.fixture
def one_fails(monkeypatch):
    monkeypatch.setattr(booted_with, "failing", FORMER_QUEUE)


def test_the_worker_ends_when_either_queues_worker_fails(one_fails, booted):
    """The worker exits with the failed queue's error, and the other queue's worker is stopped
    before it does — not left polling half the work."""
    error, others_cancelled = booted
    assert isinstance(error, RuntimeError) and FORMER_QUEUE in str(error), error
    assert others_cancelled == [True]


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


# ── a 0.7 workflow keeps its 0.7 id (review of #500) ─────────────────────────────────────────────
#
# Picked up from `openfactory-jobs`, a workflow 0.7 started still answers to the id 0.7 gave it:
# `openfactory-<project>-<issue>` for a job, `openfactory-coordinator-<project>` for the
# tech-lead, `openfactory-deploy-<project>-<issue>` for a deploy watch,
# `openfactory-product-breakdown-<project>-<n>` for a breakdown (read at v0.7.0). Everything that
# finds or addresses one by `beeverforge-` alone would not see it.

FORMER_JOB = f"openfactory-{PROJECT}-7"


def test_the_former_workflow_id_prefix_is_0_7s():
    from beeverforge.runtime.temporal import FORMER_WORKFLOW_ID_PREFIX

    assert FORMER_WORKFLOW_ID_PREFIX == "openfactory-"


def test_a_0_7_job_id_is_parsed_as_its_project_and_issue():
    from beeverforge.runtime.temporal import view

    assert view.parse_job_id(FORMER_JOB, known_projects=[PROJECT]) == (PROJECT, "7")
    assert view.parse_job_id(f"openfactory-{PROJECT}-web-CONT-412",
                             known_projects=[PROJECT, f"{PROJECT}-web"]) == \
        (f"{PROJECT}-web", "CONT-412")
    assert view.parse_job_id(f"beeverforge-{PROJECT}-8", known_projects=[PROJECT]) == \
        (PROJECT, "8")
    assert view.parse_job_id("someone-else-9", known_projects=[PROJECT]) == (None, None)


class _Wf:
    def __init__(self, wf_id, status=None):
        from datetime import UTC, datetime

        from temporalio.client import WorkflowExecutionStatus

        self.id = wf_id
        self.run_id = "run-1"
        self.status = status or WorkflowExecutionStatus.RUNNING
        self.start_time = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
        self.close_time = None

    async def memo(self):
        return {}


class _Workflows:
    """A client holding some workflows by id. `list_workflows` honours one clause of the query, a
    `WorkflowId STARTS_WITH "<x>"`, which is the clause that would hide a 0.7 id; a handle answers
    `describe`, `query` (None) and `signal`, and raises the engine's NOT_FOUND for an id it does
    not hold."""

    def __init__(self, *wfs):
        self.wfs = {w.id: w for w in wfs}
        self.queries: list[str] = []
        self.signals: list[tuple] = []
        self.started: list[tuple] = []
        self.terminated: list[str] = []
        #: what every query answers
        self.answer = None

    def list_workflows(self, query=""):
        import re

        self.queries.append(query)
        prefixes = re.findall(r'WorkflowId STARTS_WITH "([^"]*)"', query)
        exact = re.findall(r'WorkflowId = "([^"]*)"', query)
        listed = [w for w in self.wfs.values()
                  if (not prefixes or any(w.id.startswith(p) for p in prefixes))
                  and (not exact or w.id in exact)]

        async def _iterate():
            for w in listed:
                yield w

        return _iterate()

    def get_workflow_handle(self, wf_id, run_id=None):
        client = self

        class _Handle:
            id = wf_id

            def _held(self):
                if wf_id not in client.wfs:
                    raise _not_found(wf_id)
                return client.wfs[wf_id]

            async def describe(self):
                held = self._held()
                return type("Described", (), {"status": held.status, "run_id": held.run_id})()

            async def query(self, *_a, **_k):
                self._held()
                return client.answer

            async def signal(self, name, *args, **kwargs):
                self._held()
                client.signals.append((wf_id, name, args, kwargs))

            async def result(self):
                self._held()
                return {}

            async def terminate(self, *_a, **_k):
                self._held()
                client.terminated.append(wf_id)

        return _Handle()

    async def start_workflow(self, workflow, arg=None, *, id, **kwargs):
        self.started.append((workflow, id, kwargs))


async def test_a_0_7_job_is_listed_on_the_panel(monkeypatch):
    from beeverforge.runtime.temporal import view

    monkeypatch.setattr(view, "_registered_projects", lambda: [PROJECT])
    view.forget_jobs()
    rows = await view.list_jobs(_Workflows(_Wf(FORMER_JOB)), "default")
    assert [(r["project"], r["issue"], r["workflow_id"]) for r in rows] == \
        [(PROJECT, "7", FORMER_JOB)]


def test_the_panels_engine_link_finds_a_0_7_job_too():
    """The project's **Engine ↗** link filters by id; read off the query the panel builds."""
    from urllib.parse import unquote

    from beeverforge.api import app

    query = unquote(app.engine_jobs_query(PROJECT))
    held = _Workflows(_Wf(FORMER_JOB), _Wf(f"beeverforge-{PROJECT}-8"),
                      _Wf("beeverforge-other-1"))
    import re

    prefixes = re.findall(r'WorkflowId STARTS_WITH "([^"]*)"', query)
    found = sorted(w for w in held.wfs if any(w.startswith(p) for p in prefixes))
    assert found == sorted([FORMER_JOB, f"beeverforge-{PROJECT}-8"]), query
    assert " OR " in query, query


async def test_a_gate_on_a_0_7_job_is_answered_on_its_0_7_id():
    """A person answers the merge gate of a job 0.7 started: the panel addresses the job by
    project and issue, and the engine holds it under 0.7's id."""
    from beeverforge.runtime.temporal import view

    held = _Workflows(_Wf(FORMER_JOB))
    handle = view.job_handle(held, PROJECT, "7")
    assert (await handle.describe()).status is not None
    await handle.signal("act_on_impediment", "resume")
    assert held.signals and held.signals[0][0] == FORMER_JOB


async def test_a_0_7_jobs_gate_answer_is_sealed_over_its_0_7_id(monkeypatch):
    """The worker checks a gate's seal against the running workflow's own id, so an approval
    sealed over BeeverForge's id would be refused by the 0.7 job it was meant for."""
    from beeverforge import gate_seal
    from beeverforge.runtime.temporal import view

    monkeypatch.delenv(gate_seal.VARIABLE, raising=False)
    held = _Workflows(_Wf(FORMER_JOB))
    held.answer = True
    await view.approve_job(held, PROJECT, "7", version="1.2.0", approver="someone", comment="")
    ((to, _name, _args, kwargs),) = held.signals
    version, approver, comment, seal = kwargs["args"]
    assert to == FORMER_JOB
    assert gate_seal.refusal(seal, gate_seal.APPROVE_PROD, FORMER_JOB,
                             version, approver, comment) == ""


async def test_beeverforges_own_job_is_addressed_first():
    from beeverforge.runtime.temporal import view

    held = _Workflows(_Wf(FORMER_JOB), _Wf(f"beeverforge-{PROJECT}-7"))
    await view.job_handle(held, PROJECT, "7").signal("act_on_impediment", "resume")
    assert [s[0] for s in held.signals] == [f"beeverforge-{PROJECT}-7"]


async def test_a_job_under_neither_id_is_said_under_beeverforges():
    from temporalio.service import RPCError

    from beeverforge.runtime.temporal import view

    with pytest.raises(RPCError) as raised:
        await view.job_handle(_Workflows(), PROJECT, "7").describe()
    assert f"beeverforge-{PROJECT}-7" in str(raised.value)


async def test_an_engine_failure_other_than_not_found_is_not_retried_on_0_7s_id():
    from temporalio.service import RPCError, RPCStatusCode

    from beeverforge.runtime.temporal import view

    held = _Workflows(_Wf(FORMER_JOB))
    asked: list[str] = []
    real = held.get_workflow_handle

    def _handle(wf_id, run_id=None):
        asked.append(wf_id)
        handle = real(wf_id)
        if wf_id.startswith("beeverforge-"):
            async def _refused(*_a, **_k):
                raise RPCError("unavailable", RPCStatusCode.UNAVAILABLE, b"")
            handle.describe = _refused
        return handle

    held.get_workflow_handle = _handle
    with pytest.raises(RPCError):
        await view.job_handle(held, PROJECT, "7").describe()
    assert FORMER_JOB not in asked


def test_no_job_is_addressed_by_beeverforges_id_alone():
    """Every handle on an existing job goes through `job_handle`: a `get_workflow_handle` given
    `job_id(...)`, or an f-string spelling `beeverforge-{project}-{issue}`, would miss a 0.7 job."""
    found = []
    for path in sorted((ROOT / "beeverforge").rglob("*.py")):
        for node in ast.walk(parsed(path)):
            if not (isinstance(node, ast.Call)
                    and getattr(node.func, "attr", "") == "get_workflow_handle" and node.args):
                continue
            arg = node.args[0]
            named = arg.func if isinstance(arg, ast.Call) else None
            if named is not None and (getattr(named, "attr", "") in ("job_id", "_job_id")
                                      or getattr(named, "id", "") in ("job_id", "_job_id")):
                found.append(f"{path.relative_to(ROOT)}:{node.lineno}")
            if isinstance(arg, ast.JoinedStr) and arg.values and isinstance(
                    arg.values[0], ast.Constant) and arg.values[0].value == "beeverforge-":
                found.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not found, f"a job addressed by BeeverForge's id alone: {found}"


async def test_a_0_7_deploy_watch_is_read_for_the_panel():
    from beeverforge.runtime.temporal import view

    held = _Workflows(_Wf(f"openfactory-deploy-{PROJECT}-7"))
    view._deploy_cache.clear()
    assert await view._deploy_state(held, PROJECT, "7") == "deploying"


async def test_the_floor_counts_a_running_0_7_job(monkeypatch):
    """No job runs twice for one card because a running 0.7 job holds the floor: with one slot,
    the poller starts nothing while it runs."""
    from beeverforge.runtime.temporal import activities

    held = _Workflows(_Wf(FORMER_JOB))
    monkeypatch.setattr(activities, "engine_client", lambda: held)
    monkeypatch.setenv("BEEVERFORGE_MAX_CONCURRENT_JOBS", "1")
    assert await activities.available_slots() == 0
    monkeypatch.setenv("BEEVERFORGE_MAX_CONCURRENT_JOBS", "2")
    assert await activities.available_slots() == 1


def _coordinating(monkeypatch, *wfs):
    from beeverforge.runtime.temporal import activities

    held = _Workflows(*wfs)
    monkeypatch.setattr(activities, "engine_client", lambda: held)
    return held


async def test_a_running_0_7_coordinator_is_signalled_and_no_second_is_started(monkeypatch):
    from beeverforge.runtime.temporal import activities
    from beeverforge.runtime.temporal.io import CoordinatorItem, CoordinatorSayInput

    former = f"openfactory-coordinator-{PROJECT}"
    held = _coordinating(monkeypatch, _Wf(former))
    item = CoordinatorItem(project=PROJECT, issue="7", job_id=FORMER_JOB)
    await activities.notify_coordinator(item)
    await activities.notify_coordinator_say(CoordinatorSayInput(project=PROJECT, text="hi"))

    assert held.started == [], held.started
    assert [(s[0], s[1]) for s in held.signals] == [(former, "on_decision"), (former, "say")]


async def test_without_a_0_7_coordinator_beeverforges_is_started(monkeypatch):
    from temporalio.client import WorkflowExecutionStatus

    from beeverforge.runtime.temporal import activities
    from beeverforge.runtime.temporal.io import CoordinatorItem, CoordinatorSayInput

    held = _coordinating(monkeypatch, _Wf(f"openfactory-coordinator-{PROJECT}",
                                          WorkflowExecutionStatus.COMPLETED))
    await activities.notify_coordinator(
        CoordinatorItem(project=PROJECT, issue="7", job_id=f"beeverforge-{PROJECT}-7"))
    await activities.notify_coordinator_say(CoordinatorSayInput(project=PROJECT, text="hi"))

    assert [s[1] for s in held.started] == [f"beeverforge-coordinator-{PROJECT}"] * 2
    assert held.signals == []


async def test_forgetting_a_project_closes_its_0_7_coordinator_too():
    from types import SimpleNamespace

    from beeverforge.product import forget

    held = _Workflows(_Wf(f"openfactory-coordinator-{PROJECT}"),
                      _Wf(f"beeverforge-coordinator-{PROJECT}"))
    await forget.close_runs(SimpleNamespace(key=PROJECT),
                            coordinator=forget.coordinator_id(PROJECT), client=held)
    assert sorted(held.terminated) == sorted([f"openfactory-coordinator-{PROJECT}",
                                              f"beeverforge-coordinator-{PROJECT}"])


async def test_a_0_7_coordinators_messages_are_filed_under_its_project():
    from beeverforge.runtime.temporal import view

    held = _Workflows(_Wf(f"openfactory-coordinator-{PROJECT}"))

    class _Speaks:
        async def query(self, *_a, **_k):
            return [{"id": 1, "text": "picked up #7"}]

    held.get_workflow_handle = lambda *_a, **_k: _Speaks()
    said = await view.coordinator_messages(held)
    assert [m["project"] for m in said] == [PROJECT]


async def test_a_running_0_7_breakdown_is_read_as_running(monkeypatch):
    from beeverforge.product import breaking

    held = _Workflows(_Wf(f"openfactory-product-breakdown-{PROJECT}-3"),
                      _Wf(f"beeverforge-product-breakdown-{PROJECT}-4"))
    assert await breaking.running_numbers(PROJECT, client=held) == {3, 4}


# ── the two workers end together ─────────────────────────────────────────────────────────────────

class _Runs:
    """A worker whose `run` returns, raises, or waits — until it is cancelled, or until the test
    RELEASES it. The release is what keeps a broken pairing from hanging the test: a pair that never
    cancels its other worker is let go after the wait, and the test fails on what it saw instead."""

    def __init__(self, *, raises: BaseException | None = None, returns: bool = False):
        self.raises, self.returns = raises, returns
        self.cancelled = False
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def run(self):
        self.started.set()
        if self.raises is not None:
            raise self.raises
        if self.returns:
            return
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise


async def _settled(pair, runs, *, within=5.0):
    """Wait `within` for `pair` to end by itself, say whether it did, then release every worker so
    it ends either way — and hand back what it raised (None when it returned)."""
    done, _ = await asyncio.wait([pair], timeout=within)
    for run in runs:
        run.release.set()
    try:
        await asyncio.wait_for(pair, within)
    except BaseException as exc:  # noqa: BLE001 — what it raised is what the test reads
        return bool(done), exc
    return bool(done), None


async def test_a_worker_that_fails_ends_the_other_and_its_error_is_raised():
    from beeverforge.runtime.temporal import worker

    failing, waiting = _Runs(raises=RuntimeError("the poll was refused")), _Runs()
    pair = asyncio.ensure_future(worker.run_together([waiting, failing]))
    ended, raised = await _settled(pair, [waiting, failing])
    assert ended and waiting.cancelled
    assert isinstance(raised, RuntimeError) and "the poll was refused" in str(raised)


async def test_a_worker_that_returns_ends_the_other():
    from beeverforge.runtime.temporal import worker

    returned, waiting = _Runs(returns=True), _Runs()
    pair = asyncio.ensure_future(worker.run_together([returned, waiting]))
    ended, raised = await _settled(pair, [returned, waiting])
    assert ended and waiting.cancelled and raised is None


async def test_cancelling_the_pair_cancels_both():
    from beeverforge.runtime.temporal import worker

    first, second = _Runs(), _Runs()
    pair = asyncio.ensure_future(worker.run_together([first, second]))
    await asyncio.wait_for(asyncio.gather(first.started.wait(), second.started.wait()), 5)
    pair.cancel()
    ended, raised = await _settled(pair, [first, second])
    assert ended and isinstance(raised, asyncio.CancelledError)
    assert first.cancelled and second.cancelled
