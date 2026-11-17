"""`box_prove` is a catalogue row, and `beeverforge box prove` is a mapping over it (#237, ADR-0039).

A project's proof was a CLI verb only: a screen of one's own could not ask for one, and nothing but
a shell on the worker could say what the box proved. The row proves one project's box. The shell's
own `box prove` proves it in its process and answers the proof document: what passed, what failed,
and each finding by its name. Every other caller — the panel's route, `beeverforge act` — starts
the proof on the worker and answers at once with the handle of the proof that runs, or of the one
already running; the doctor's `box_proof` reads what it recorded afterwards, as it does today.

What is real: the registry, the row, `perform`'s authorization and audit, both transports, the
proof's record and the readiness check that reads it. "The shell" is `box prove`'s own context
(`box_prove.proving_here`), never a transport's name. Stood in: the box itself (`box_probes`,
`prove`), the image's resolution and the durable engine. Nothing here waits on real time: the
worker's half is driven synchronously through the activity's own body.
"""

from __future__ import annotations

import ast
import asyncio
import contextlib
import inspect
import json
import logging
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from beeverforge import actions
from beeverforge import box_prove as bp
from beeverforge.actions import catalog
from beeverforge.box_prove import Finding, Proof
from beeverforge.factory import resolve_box_image as _real_resolve_box_image


@pytest.fixture
def demo(tmp_path, monkeypatch):
    """A registered project `demo`, a box that proves it in no time, and the proofs directory
    under the test's own one. `world.ok` decides the verdict; `world.boxes` is every box opened."""
    from beeverforge import factory

    reg = tmp_path / "registry.yaml"
    reg.write_text(json.dumps({"projects": {"demo": {
        "name": "demo", "repo": "acme/demo",
        "repo_path": "https://github.com/acme/demo.git"}}}))
    monkeypatch.setenv("BEEVERFORGE_REGISTRY", str(reg))
    monkeypatch.setenv("BEEVERFORGE_SANDBOX", "container")
    monkeypatch.setattr(bp, "PROOF_DIR", tmp_path / "proofs")
    monkeypatch.setattr(factory, "resolve_box_image", lambda *_a, **_k: "img:1")
    world = SimpleNamespace(ok=True, boxes=[])

    @contextlib.contextmanager
    def box(project, image, **kw):
        world.boxes.append({"project": project.name, "image": image, **kw})
        yield SimpleNamespace()

    def prove(key, image, _probes, *, on_stage=None):
        if on_stage is not None:
            on_stage("start", "running your gates")
            on_stage("line", "4 passed")
        return Proof(project=key, image=image, ok=world.ok, findings=[
            Finding("image", True, "img:1 resolved"),
            Finding("validate", world.ok, "4 gate(s) green" if world.ok else "test: exited 1",
                    "" if world.ok else "fix the failing test")])

    monkeypatch.setattr(bp, "box_probes", box)
    monkeypatch.setattr(bp, "prove", prove)
    return world


class _Engine:
    """The durable engine as the row meets it: a workflow started under an id, refused with the
    engine's own error while one under that id is open. No `execute_workflow`: a row that waited
    for the proof would fail here."""

    def __init__(self) -> None:
        self.started: list[dict] = []
        self.open: set[str] = set()

    async def start_workflow(self, name, arg, *, id, task_queue, **options):
        from temporalio.exceptions import WorkflowAlreadyStartedError

        if id in self.open:
            raise WorkflowAlreadyStartedError(id, name)
        self.open.add(id)
        self.started.append({"name": name, "arg": arg, "id": id, "task_queue": task_queue,
                             **options})
        return SimpleNamespace(id=id)


@pytest.fixture
def engine(monkeypatch):
    made = _Engine()

    async def _connected():
        return made, None

    monkeypatch.setattr(catalog, "_connected", _connected)
    return made


def _shell() -> actions.Actor:
    return actions.Actor(id="ops", display="ops", via="cli", admin=True)


@contextlib.contextmanager
def _in_the_shell(name: str = "demo"):
    """What `beeverforge box prove` sets around the row: its project, proven in its process."""
    from beeverforge.registry import ProjectRegistry

    with bp.proving_here(ProjectRegistry().get(name), record=bp.save):
        yield


def _panel() -> actions.Actor:
    return actions.Actor(id="ana", display="Ana", via="panel", admin=True)


# ── the row ─────────────────────────────────────────────────────────────────────────────────────

def test_box_prove_is_a_row_of_the_floor_for_one_project():
    found = actions.CATALOG["box_prove"]

    assert found.scope == actions.FLOOR and found.needs_admin
    assert found.required == ("project",)
    assert set(found.optional) == {"repo", "ref", "image", "sandbox"}
    assert not found.pending


async def test_on_the_host_it_answers_the_proof_document(demo):
    with _in_the_shell():
        out = await actions.perform("box_prove", by=_shell(), project="demo")

    assert out.ok, out.message
    proof = out.data["proof"]
    assert proof["ok"] is True and proof["project"] == "demo" and proof["image"] == "img:1"
    assert proof["passed"] == ["image", "validate"] and proof["failed"] == []
    assert [f["check"] for f in proof["findings"]] == ["image", "validate"]
    assert out.data["state"] == bp.PROVEN and out.data["key"] == "demo"
    assert out.data["recorded_at"] and bp.load("demo").ok, "the proof was not recorded"


async def test_a_proof_that_fails_is_answered_with_what_failed_and_recorded_as_failed(demo):
    demo.ok = False

    with _in_the_shell():
        out = await actions.perform("box_prove", by=_shell(), project="demo")

    assert out.ok, "the proof ran: a red box is an answer, not a refusal"
    assert out.data["state"] == bp.NOT_PROVEN
    assert out.data["proof"]["failed"] == ["validate"]
    failed = [f for f in out.data["proof"]["findings"] if f["check"] == "validate"]
    assert failed[0]["remedy"] == "fix the failing test"
    assert bp.load("demo").ok is False


async def test_a_ref_proof_is_measured_and_never_recorded(demo, monkeypatch, tmp_path):
    from beeverforge import factory, loader

    monkeypatch.setattr(factory, "resolve_repo_path", lambda *_a, **_k: tmp_path / "checkout")
    monkeypatch.setattr(loader, "load_manifest", lambda *_a, **_k: object())

    with _in_the_shell():
        out = await actions.perform("box_prove", by=_shell(), project="demo", ref="feat/x")

    assert out.ok and out.data["ref"] == "feat/x" and out.data["recorded_at"] is None
    assert bp.load("demo") is None, "a branch proof was recorded where the poller looks"


async def test_a_proof_already_running_here_is_refused_in_its_own_sentence(demo, monkeypatch):
    @contextlib.contextmanager
    def busy(*_a, **_k):
        raise bp.ProveBusy("demo")
        yield  # a generator, so `with` can enter it

    monkeypatch.setattr(bp, "box_probes", busy)

    with _in_the_shell():
        out = await actions.perform("box_prove", by=_shell(), project="demo")

    assert not out.ok and out.code == actions.CONFLICT
    assert out.message == bp.ProveBusy("demo").sentence
    assert bp.load("demo") is None, "a proof that measured nothing was recorded"


async def test_a_ref_proof_lets_its_key_go_however_it_ends_to_any_thread(demo, monkeypatch,
                                                                        tmp_path):
    """The host proves on a thread of its own (`asyncio.to_thread`), so the key is asked of
    ANOTHER thread here: `held_here` is true only in the holder's, and would miss a leak."""
    from beeverforge import factory, loader
    from beeverforge.util.filelock import FileLock

    def free() -> bool:
        lock = FileLock(bp.proof_lock_path("demo"))
        try:
            lock.acquire(timeout=0)
        except TimeoutError:
            return False
        lock.release()
        return True

    def unreadable(*_a, **_k):
        raise ValueError("no manifest on feat")

    monkeypatch.setattr(factory, "resolve_repo_path", lambda *_a, **_k: tmp_path / "checkout")
    monkeypatch.setattr(loader, "load_manifest", unreadable)
    with _in_the_shell():
        out = await actions.perform("box_prove", by=_shell(), project="demo", ref="feat")
    assert not out.ok and out.code == actions.INVALID, out.message
    assert free(), "a ref proof whose manifest could not be read kept its key"

    monkeypatch.setattr(loader, "load_manifest", lambda *_a, **_k: object())
    with _in_the_shell():
        out = await actions.perform("box_prove", by=_shell(), project="demo", ref="feat")
    assert out.ok, out.message
    assert free(), "a ref proof that ran kept its key after it ended"


async def test_a_ref_that_cannot_be_read_is_said_without_the_credential_in_its_url(
        demo, monkeypatch, caplog):
    """The sentence reaches whoever asked, and a failed clone's text carries its URL."""
    from beeverforge import factory

    def clone_failed(*_a, **_k):
        raise RuntimeError("git clone https://x-access-token:ghs_live@github.com/acme/demo.git "
                           "exited 128")

    monkeypatch.setattr(factory, "resolve_repo_path", clone_failed)
    with _in_the_shell():
        out = await actions.perform("box_prove", by=_shell(), project="demo", ref="feat")

    assert not out.ok and out.code == actions.INVALID
    assert "exited 128" in out.message and "ghs_live" not in out.message, out.message
    assert "exited 128" in caplog.text and "ghs_live" not in caplog.text


def test_a_project_before_its_code_is_refused_before_a_proof_starts(demo, monkeypatch, tmp_path):
    """The row waits for the code by its declaration (#992), so `perform` says it in the sentence
    every door says. A proof that started would read `repo_path` — empty — as the product."""
    reg = tmp_path / "codeless.yaml"
    reg.write_text(json.dumps({"projects": {"myapp": {
        "name": "myapp", "repo_path": "",
        "product": {"docs_repo": "acme/myapp-context"}}}}))
    monkeypatch.setenv("BEEVERFORGE_REGISTRY", str(reg))

    def started(*_a, **_k):
        raise AssertionError("a proof started for a project with no code")

    monkeypatch.setattr(bp, "prove_the_box", started)

    out = asyncio.run(actions.perform("box_prove", by=_shell(), project="myapp"))

    assert not out.ok and out.data["reason"] == actions.NO_CODE_YET, out.message
    assert "first-source myapp" in out.message and demo.boxes == []

    from beeverforge.cli import app as cli

    result = CliRunner().invoke(cli, ["box", "prove", "myapp"])

    assert result.exit_code == 1, result.output
    assert result.output.startswith("✗ ") and "first-source myapp" in result.output, result.output
    assert demo.boxes == []


@pytest.mark.parametrize("in_the_shell", [True, False], ids=["host", "worker"])
async def test_an_unknown_project_answers_a_reason_never_a_traceback(demo, engine, in_the_shell):
    with _in_the_shell() if in_the_shell else contextlib.nullcontext():
        out = await actions.perform("box_prove", by=_panel(), project="nope")

    assert not out.ok and out.code == actions.NOT_FOUND
    assert out.data["reason"] == actions.NOT_FOUND
    assert "nope" in out.message and "demo" in out.message, out.message
    assert engine.started == [] and demo.boxes == []


# ── the worker's half: answers at once, one proof per key ───────────────────────────────────────

async def test_away_from_the_host_it_starts_the_proof_on_the_worker_and_answers_its_handle(
        demo, engine):
    from beeverforge.runtime.temporal import TASK_QUEUE

    out = await actions.perform("box_prove", by=_panel(), project="demo")

    assert out.ok, out.message
    (started,) = engine.started
    assert started["name"] == "BoxProveWorkflow" and started["task_queue"] == TASK_QUEUE
    assert started["arg"].project == "demo"
    assert started["id"] == bp.workflow_id("demo") == out.data["handle"]
    assert started["execution_timeout"] == bp.PROOF_FLIGHT
    assert out.data["state"] == bp.RUNNING and out.data["proof"] is None
    assert demo.boxes == [], "the request proved the box itself"


async def test_a_shell_s_act_away_from_box_prove_proves_on_the_worker_too(demo, engine):
    """WHERE IT PROVES IS NOT THE TRANSPORT'S NAME. `beeverforge act box_prove` from an operator's
    laptop is `via="cli"` too; proven there, its record would land in a PROOF_DIR no worker reads,
    and the doctor would hold the next pickup as if it never ran."""
    out = await actions.perform("box_prove", by=_shell(), project="demo")

    assert out.ok and out.data["handle"] == bp.workflow_id("demo"), out.message
    assert len(engine.started) == 1 and demo.boxes == []
    assert bp.load("demo") is None, "a proof was recorded by the process that asked"


async def test_away_from_the_shell_a_ref_is_refused_before_anything_starts(demo, engine):
    """A ref is measured and never recorded, so on the worker its answer would reach nobody."""
    out = await actions.perform("box_prove", by=_panel(), project="demo", ref="feat/x")

    assert not out.ok and out.code == actions.INVALID
    assert "beeverforge box prove demo --ref feat/x" in out.message, out.message
    assert engine.started == [] and demo.boxes == []


async def test_a_second_ask_while_a_proof_runs_answers_the_same_handle(demo, engine):
    first = await actions.perform("box_prove", by=_panel(), project="demo")
    second = await actions.perform("box_prove", by=_panel(), project="demo")

    assert first.data["handle"] == second.data["handle"]
    assert (first.data["joined"], second.data["joined"]) == (False, True)
    assert len(engine.started) == 1


async def test_away_from_the_shell_an_unknown_sandbox_is_refused_before_anything_starts(demo,
                                                                                         engine):
    """The worker could not open a box it does not know: answering `running` would be a proof
    that never runs, said as one that does."""
    out = await actions.perform("box_prove", by=_panel(), project="demo", sandbox="nonsuch")

    assert not out.ok and out.code == actions.INVALID and out.data["reason"]
    assert "nonsuch" in out.message and "Nothing was started" in out.message, out.message
    assert engine.started == [] and demo.boxes == []


async def test_away_from_the_shell_an_image_the_box_cannot_honour_is_refused(demo, engine,
                                                                            monkeypatch, tmp_path):
    """A project that declares `box.image`, asked to prove in a `worktree` box, which runs none —
    refused as `_start` refuses it, before the worker is asked."""
    from beeverforge import factory

    reg = tmp_path / "imaged.yaml"
    reg.write_text(json.dumps({"projects": {"demo": {
        "name": "demo", "repo": "acme/demo", "repo_path": "https://github.com/acme/demo.git",
        "box": {"image": "acme/demo-ci:3"}}}}))
    monkeypatch.setenv("BEEVERFORGE_REGISTRY", str(reg))
    monkeypatch.setattr(factory, "resolve_box_image", _real_resolve_box_image)

    out = await actions.perform("box_prove", by=_panel(), project="demo", sandbox="worktree")

    assert not out.ok and out.code == actions.INVALID and out.data["reason"]
    assert "box.image" in out.message and "worktree" in out.message, out.message
    assert engine.started == [] and demo.boxes == []


@pytest.mark.parametrize("kind", ["fargate", "worktree"])
async def test_away_from_the_shell_a_box_the_worker_may_not_prove_in_is_refused(demo, engine,
                                                                               monkeypatch, kind):
    """`fargate` has no local box to build, so the worker's proof raises after `running` was
    answered; `worktree` bounds nothing on a worker that is not its operator's (ADR-0049 D9)."""
    monkeypatch.delenv("BEEVERFORGE_OWN_WORK", raising=False)

    out = await actions.perform("box_prove", by=_panel(), project="demo", sandbox=kind)

    assert not out.ok and out.code == actions.INVALID and kind in out.message, out.message
    assert "Nothing was started" in out.message and engine.started == [] and demo.boxes == []


async def test_a_worker_that_is_its_operator_s_own_proves_in_the_worktree_box(demo, engine,
                                                                             monkeypatch):
    monkeypatch.setenv("BEEVERFORGE_OWN_WORK", "1")

    out = await actions.perform("box_prove", by=_panel(), project="demo", sandbox="worktree")

    assert out.ok and engine.started[0]["arg"].sandbox == "worktree", out.message


async def test_the_box_the_row_checked_is_the_box_the_worker_is_asked_to_prove(demo, engine):
    await actions.perform("box_prove", by=_panel(), project="demo", sandbox=" Container ")
    await actions.perform("box_prove", by=_panel(), project="demo", repo="acme/web")

    assert [s["arg"].sandbox for s in engine.started] == ["container", "container"]


async def test_a_repository_s_proof_on_the_worker_is_its_own_flight(demo, engine):
    from beeverforge.registry import ProjectRegistry
    from beeverforge.runtime.card_repo import _runner_view

    _view, key = _runner_view(ProjectRegistry().get("demo"), "acme/web#0")
    assert key != "demo", "the stand-in repository resolved to the default one"

    default = await actions.perform("box_prove", by=_panel(), project="demo")
    other = await actions.perform("box_prove", by=_panel(), project="demo", repo="acme/web")

    assert default.ok and other.ok, (default.message, other.message)
    assert other.data["key"] == key and other.data["handle"] == bp.workflow_id(key)
    assert other.data["handle"] != default.data["handle"] and other.data["joined"] is False
    assert [s["id"] for s in engine.started] == [bp.workflow_id("demo"), bp.workflow_id(key)]
    assert engine.started[1]["arg"].repo == "acme/web"


def test_a_ref_and_a_repository_are_their_own_proofs():
    ids = {bp.workflow_id("demo"), bp.workflow_id("demo", "feat/x"),
           bp.workflow_id("demo--org--web"), bp.workflow_id("demo", "feat/y")}

    assert len(ids) == 4


async def test_with_no_engine_it_is_refused_as_unavailable(demo, monkeypatch):
    from beeverforge.actions.base import refused

    async def _connected():
        return None, refused(actions.UNAVAILABLE, "the durable engine is not answering")

    monkeypatch.setattr(catalog, "_connected", _connected)
    out = await actions.perform("box_prove", by=_panel(), project="demo")

    assert not out.ok and out.code == actions.UNAVAILABLE


async def test_a_start_the_engine_refuses_for_another_reason_is_said_with_a_reference(
        demo, monkeypatch, caplog):
    class _Broken:
        async def start_workflow(self, *_a, **_k):
            raise RuntimeError("namespace not found")

    async def _connected():
        return _Broken(), None

    monkeypatch.setattr(catalog, "_connected", _connected)
    out = await actions.perform("box_prove", by=_panel(), project="demo")

    assert not out.ok and out.code == actions.FAILED
    assert out.data["reference"] and out.data["reference"] in caplog.text


def test_the_worker_proves_and_records_it_driven_synchronously(demo):
    from beeverforge.runtime.temporal import activities as acts
    from beeverforge.runtime.temporal.io import BoxProveInput

    said = acts._do_prove_box(BoxProveInput(project="demo"))

    assert said.startswith("PROVEN"), said
    assert bp.load("demo").ok and demo.boxes[0]["key"] == "demo"


def test_the_worker_says_an_unknown_project_and_raises_nothing(demo):
    from beeverforge.runtime.temporal import activities as acts
    from beeverforge.runtime.temporal.io import BoxProveInput

    said = acts._do_prove_box(BoxProveInput(project="nope"))

    assert "nope" in said and demo.boxes == []


def test_the_workflow_runs_its_one_activity_bounded_and_heartbeating():
    from beeverforge.runtime.temporal import workflow as wf

    tree = ast.parse(inspect.getsource(wf.BoxProveWorkflow))
    (call,) = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
               and getattr(n.func, "attr", "") == "execute_activity"]
    given = {k.arg: ast.unparse(k.value) for k in call.keywords}

    assert ast.unparse(call.args[0]) == "prove_box"
    assert given == {"start_to_close_timeout": "BOX_PROOF_CEILING",
                     "heartbeat_timeout": "BOX_PROOF_HEARTBEAT", "retry_policy": "_ONCE"}
    assert bp.PROOF_HEARTBEAT < bp.PROOF_CEILING < bp.PROOF_FLIGHT


async def test_the_worker_s_proof_heartbeats_while_it_runs(monkeypatch):
    """Driven by the beats, not by a clock: the proof ends only once three beats have been heard,
    so an activity that ran it without heartbeating never lets it end (bounded, and then red)."""
    import threading

    from beeverforge.runtime.temporal import activities as acts
    from beeverforge.runtime.temporal.io import BoxProveInput

    beats: list[str] = []
    heard = threading.Event()

    def beat(*details):
        beats.append(details[0] if details else "")
        if len(beats) >= 3:
            heard.set()

    def proving(inp):
        heard.wait(timeout=5)
        return f"PROVEN — {inp.project}"

    monkeypatch.setattr(acts.activity, "heartbeat", beat)
    monkeypatch.setattr(acts, "_TURN_PULSE", 0)
    monkeypatch.setattr(acts, "_do_prove_box", proving)

    said = await acts.prove_box(BoxProveInput(project="demo"))

    assert said == "PROVEN — demo"
    assert len(beats) >= 3 and all("demo" in b for b in beats), beats


class _Worker:
    """`temporalio.worker.Worker`, recorded: what each was built with. Runs nothing."""

    built: list[dict] = []

    def __init__(self, _client, **kwargs):
        _Worker.built.append(kwargs)

    async def run(self):
        return None


def test_the_worker_serves_the_box_proof(monkeypatch):
    """`worker.main()` booted with the engine faked: every worker it builds serves the workflow,
    and the activity the workflow runs."""
    from beeverforge.runtime.temporal import worker
    from beeverforge.runtime.temporal.activities import prove_box
    from beeverforge.runtime.temporal.workflow import BoxProveWorkflow

    async def _client():
        return "the client"

    async def _nothing(*_a, **_k):
        return []

    _Worker.built = []
    monkeypatch.setenv("TEMPORAL_ADDRESS", "localhost:7233")
    monkeypatch.setattr(worker, "Worker", _Worker)
    monkeypatch.setattr(worker, "load_dotenv", lambda *_a, **_k: False)
    monkeypatch.setattr(worker, "connect_at_birth", _client)
    monkeypatch.setattr(worker, "start_channel_listeners", lambda _projects: [])
    monkeypatch.setattr("beeverforge.registry.seed_registry", lambda *_a, **_k: None)
    monkeypatch.setattr("beeverforge.runtime.toolbox.populate", lambda *_a, **_k: None)
    monkeypatch.setattr("beeverforge.observability.health.listen", _nothing)
    monkeypatch.setattr("beeverforge.namespace.announce_build", lambda *_a, **_k: None)
    monkeypatch.setattr("beeverforge.runtime.temporal.schedule.ensure_all", _nothing)

    asyncio.run(asyncio.wait_for(worker.main(), timeout=10))

    assert _Worker.built, "the worker built no worker"
    for built in _Worker.built:
        assert BoxProveWorkflow in built["workflows"], built["task_queue"]
        assert prove_box in built["activities"], built["task_queue"]


# ── both transports, with the catalogue's authorization ────────────────────────────────────────

def test_through_the_panel_s_route_it_answers_the_handle(demo, engine, monkeypatch, caplog):
    monkeypatch.delenv("BEEVERFORGE_PANEL_TOKEN", raising=False)
    from fastapi.testclient import TestClient

    from beeverforge.api.app import app

    caplog.set_level(logging.INFO, logger="beeverforge.actions")
    r = TestClient(app).post("/api/act/box_prove", json={"params": {"project": "demo"}})

    assert r.status_code == 200, r.text
    assert r.json()["data"]["handle"] == bp.workflow_id("demo")
    assert len(engine.started) == 1
    assert "action=box_prove" in caplog.text, "the audit line was not written"


def test_through_the_panel_s_route_an_unknown_project_is_a_404_with_its_reason(demo, engine,
                                                                               monkeypatch):
    monkeypatch.delenv("BEEVERFORGE_PANEL_TOKEN", raising=False)
    from fastapi.testclient import TestClient

    from beeverforge.api.app import app

    r = TestClient(app).post("/api/act/box_prove", json={"params": {"project": "nope"}})

    assert r.status_code == 404, r.text
    assert r.json()["data"]["reason"] == actions.NOT_FOUND and "Traceback" not in r.text
    assert engine.started == []


async def test_the_layer_refuses_a_credential_without_the_floor_by_its_reason(demo, engine):
    ba = actions.Actor(id="bia", display="Bia", via="panel", admin=True,
                       scopes=frozenset({actions.PRODUCT}))

    out = await actions.perform("box_prove", by=ba, project="demo")

    assert not out.ok and out.code == actions.DENIED and out.data["reason"] == "out_of_scope"
    assert engine.started == [] and demo.boxes == []


def test_through_the_shell_s_act_it_answers_the_handle(demo, engine, caplog):
    from beeverforge.cli import app as cli

    caplog.set_level(logging.INFO, logger="beeverforge.actions")
    result = CliRunner().invoke(cli, ["act", "box_prove", "-p", "demo", "--json"])

    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert body["data"]["handle"] == bp.workflow_id("demo") and body["data"]["proof"] is None
    assert len(engine.started) == 1 and demo.boxes == []
    assert "action=box_prove" in caplog.text, "the audit line was not written"


def test_through_the_shell_s_act_a_caller_without_the_floor_is_refused(demo, engine, monkeypatch,
                                                                       caplog):
    """The shell's actor is unscoped today (ADR-0039 §2); this is the day it is not — a shell whose
    identity holds only the product's area. `act` hands the refusal on, it does not decide it."""
    from beeverforge.cli import app as cli

    real = actions.Actor
    monkeypatch.setattr(actions, "Actor", lambda **kw: real(**kw, scopes=frozenset({
        actions.PRODUCT})))
    caplog.set_level(logging.INFO, logger="beeverforge.actions")

    result = CliRunner().invoke(cli, ["act", "box_prove", "-p", "demo", "--json"])

    assert result.exit_code == 1, result.output
    body = json.loads(result.output)
    assert body["code"] == actions.DENIED and body["data"]["reason"] == "out_of_scope"
    assert engine.started == [] and demo.boxes == [] and bp.load("demo") is None
    assert "DENIED_SCOPE box_prove" in caplog.text, "the refusal was not audited"


# ── the verb is a mapping over the row ──────────────────────────────────────────────────────────

def test_the_box_prove_verb_goes_through_the_row(demo, monkeypatch):
    from beeverforge.cli import app as cli

    seen: list[tuple[str, dict]] = []
    real = actions.perform

    async def spy(name, *, by, **params):
        seen.append((name, dict(params)))
        return await real(name, by=by, **params)

    monkeypatch.setattr(actions, "perform", spy)
    result = CliRunner().invoke(cli, ["box", "prove", "demo"])

    assert result.exit_code == 0, result.output
    assert [name for name, _ in seen] == ["box_prove"]
    assert seen[0][1]["project"] == "demo"
    assert "PROVEN — demo can build and test in this box (recorded at" in result.output
    assert "  ok    validate  4 gate(s) green" in result.output
    assert "running your gates" in result.output, "the progress no longer reaches the terminal"


# ── the doctor's read is the one it was ─────────────────────────────────────────────────────────

async def test_the_doctor_s_box_proof_reads_what_the_row_recorded(demo):
    from beeverforge.onboarding import readiness

    def check():
        found, _ = readiness._box_proof(SimpleNamespace(
            proof=lambda: bp.load("demo"), box_honours_image=lambda _s: True,
            sandbox=lambda: "container", proof_dir=lambda: str(bp._proof_dir()),
            project_name="demo"), "demo")
        return found

    assert not check().ok, "a proof was there before the row ran"
    with _in_the_shell():
        await actions.perform("box_prove", by=_shell(), project="demo")

    found = check()
    assert found.check == "box_proof" and found.ok and "img:1" in found.message
    assert asyncio.iscoroutinefunction(catalog.CATALOG["box_prove"].run)
