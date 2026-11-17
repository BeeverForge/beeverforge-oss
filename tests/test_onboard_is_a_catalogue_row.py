"""`onboard` is a catalogue row, and `beeverforge onboard` is a mapping over it (#237, ADR-0039).

The first-time setup was a CLI verb only: a screen of one's own could not ask for it, and nothing
but a shell where the factory runs could say how far it got. The row onboards a project's
repositories — read, manifest, proof, map and pull request per repository, the preview's proposal
with `with_preview`, then the context repository. The shell's own `onboard` runs it in its process
and answers every repository's steps; every other caller — the panel's route, `beeverforge act` —
starts it on the worker and answers at once with the handle of the run, or of the one already
running. Either way each step is journaled, where the panel's events route reads it.

What is real: the registry, the row, `perform`'s authorization and audit, both transports, the
journal, and `product_init` as the context step asks for it. Stood in: each repository's onboarding
(`onboard_source_repo`, a forge that remembers what it opened), the context box and the durable
engine. Nothing here waits on real time: the worker's half is driven synchronously through the
activity's own body.
"""

from __future__ import annotations

import ast
import asyncio
import contextlib
import dataclasses
import inspect
import json
import logging
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from beeverforge import actions
from beeverforge.actions import catalog
from beeverforge.onboarding import onboard as ob

STEPS = ["read", "manifest", "proof", "map", "pull_request"]


def _registry(tmp_path, monkeypatch, *, docs_repo: str = "acme/demo-context") -> None:
    reg = tmp_path / "registry.yaml"
    entry = {"name": "demo", "repo_path": "https://github.com/acme/demo.git",
             "forge": {"kind": "github", "repo": "acme/demo"},
             "tracker": {"kind": "github", "repo": "acme/demo"}}
    if docs_repo:
        entry["product"] = {"docs_repo": docs_repo}
    reg.write_text(json.dumps({"projects": {"demo": entry}}))
    monkeypatch.setenv("BEEVERFORGE_REGISTRY", str(reg))


@pytest.fixture
def demo(tmp_path, monkeypatch):
    """A registered project `demo` whose repositories onboard in no time, against a forge that
    remembers every pull request it opened: asked again, it finds the open one, as `propose` does.
    `world.asked` is every repository onboarded, `world.broken` the ones whose clone fails."""
    _registry(tmp_path, monkeypatch)
    monkeypatch.setenv("BEEVERFORGE_LOG_DIR", str(tmp_path / "logs"))
    world = SimpleNamespace(opened={}, asked=[], broken=set(), context_pr="", contexts=[])

    def source(project, repo, *, sandbox="container", stream=None):
        world.asked.append((repo, sandbox))
        if stream is not None:
            stream("start", f"{repo}: cloning")
            stream("line", "4 passed")
        if repo in world.broken:
            return ob.RepoOutcome(repo=repo, detail=f"could not clone {repo}: access denied")
        existed = repo in world.opened
        world.opened.setdefault(repo, f"https://github.com/{repo}/pull/{len(world.opened) + 1}")
        return ob.RepoOutcome(repo=repo, ok=True, pr=world.opened[repo], existed=existed,
                              proof="proven", modules=3, questions=["which port does it serve?"],
                              detail="" if not existed else "already open")

    def context(project, *, sources, stream=None):
        world.contexts.append(list(sources))
        existed = bool(world.context_pr)
        world.context_pr = world.context_pr or "https://github.com/acme/demo-context/pull/9"
        return ob.ContextOutcome(docs_repo=project.product.docs_repo, ok=True,
                                 pr=world.context_pr, backfill="deterministic",
                                 changed=not existed,
                                 detail="the context was already proposed" if existed
                                 else f"proposed — {world.context_pr}")

    monkeypatch.setattr(ob, "onboard_source_repo", source)
    monkeypatch.setattr(ob, "onboard_product_context", context)
    return world


class _Engine:
    """The durable engine as the row meets it: a workflow started under an id, refused with the
    engine's own error while one under that id is open. No `execute_workflow`: a row that waited
    for the onboarding would fail here."""

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


def _panel() -> actions.Actor:
    return actions.Actor(id="ana", display="Ana", via="panel", admin=True)


def _in_the_shell():
    """What `beeverforge onboard` sets around the row: the run happens in its process."""
    return ob.in_this_shell(lambda _kind, _text: None)


def _journal() -> list[dict]:
    from beeverforge.paths import events_file
    from beeverforge.registry import ProjectRegistry

    path = events_file(ProjectRegistry().get("demo"), ob.ONBOARDING)
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] \
        if path.exists() else []


# ── the row ─────────────────────────────────────────────────────────────────────────────────────

def test_onboard_is_a_row_of_the_floor_for_one_project():
    found = actions.CATALOG["onboard"]

    assert found.scope == actions.FLOOR and found.needs_admin
    assert found.required == ("project",)
    assert set(found.optional) == {"sources", "with_preview", "sandbox", "skip_context"}
    assert not found.pending
    assert asyncio.iscoroutinefunction(found.run)


async def test_in_the_shell_it_answers_every_repository_s_steps(demo):
    with _in_the_shell():
        out = await actions.perform("onboard", by=_shell(), project="demo", sources="acme/web")

    assert out.ok, out.message
    assert [r["repo"] for r in out.data["repos"]] == ["acme/demo", "acme/web"]
    for repo in out.data["repos"]:
        assert [s["step"] for s in repo["steps"]] == STEPS, repo
        assert {s["state"] for s in repo["steps"]} == {actions.STEP_DONE}, repo["steps"]
        assert repo["pr"] and repo["questions"] == ["which port does it serve?"]
    assert out.data["context"]["pr"] == demo.context_pr
    assert demo.contexts == [["acme/demo", "acme/web"]], "the context was not told its sources"
    assert out.data["changed"] is True and out.data["ok"] is True
    assert out.data["handle"] is None and out.data["state"] == ob.ONBOARDED


async def test_each_repository_s_progress_is_journaled_as_events(demo):
    with _in_the_shell():
        await actions.perform("onboard", by=_shell(), project="demo", sources="acme/web")

    steps = [(e["data"]["repo"], e["data"]["step"], e["data"]["state"]) for e in _journal()
             if e["data"].get("step")]
    for repo in ("acme/demo", "acme/web"):
        assert [s for r, s, _ in steps if r == repo] == STEPS, steps
    assert ("acme/demo-context", "context", actions.STEP_DONE) in steps, steps
    assert {e["ticket_id"] for e in _journal()} == {ob.ONBOARDING}


async def test_running_it_twice_changes_nothing_the_second_time_and_says_so(demo):
    with _in_the_shell():
        first = await actions.perform("onboard", by=_shell(), project="demo", sources="acme/web")
        opened = dict(demo.opened)
        second = await actions.perform("onboard", by=_shell(), project="demo", sources="acme/web")

    assert first.data["changed"] is True
    assert second.ok and second.data["changed"] is False, second.data
    assert "nothing changed" in second.message, second.message
    assert demo.opened == opened, "the second run opened a pull request"
    for repo in second.data["repos"]:
        pull = next(s for s in repo["steps"] if s["step"] == "pull_request")
        assert pull["state"] == actions.STEP_ALREADY, pull
        assert repo["pr"] == opened[repo["repo"]]
    assert second.data["context"]["changed"] is False


async def test_with_preview_each_repository_proposes_its_preview_once(demo, monkeypatch):
    from beeverforge.onboarding import preview_propose

    proposed: dict[str, str] = {}

    def propose_preview(project, *, repo):
        existed = repo in proposed
        proposed.setdefault(repo, f"https://github.com/{repo}/pull/77")
        return preview_propose.Outcome(ok=True, url=proposed[repo], existed=existed)

    monkeypatch.setattr(preview_propose, "propose_preview", propose_preview)
    monkeypatch.setattr(ob, "onboard_source_repo", lambda project, repo, **_kw: ob.RepoOutcome(
        repo=repo, ok=True, proof="proven", modules=1, manifest_already_there=True,
        detail=f"{repo} already declares everything — nothing to propose (proof: proven)"))

    with _in_the_shell():
        first = await actions.perform("onboard", by=_shell(), project="demo", with_preview=True,
                                      skip_context=True)
        second = await actions.perform("onboard", by=_shell(), project="demo", with_preview=True,
                                       skip_context=True)

    def preview(out):
        (repo,) = out.data["repos"]
        return next(s for s in repo["steps"] if s["step"] == "preview")

    assert preview(first)["state"] == actions.STEP_DONE and first.data["changed"] is True
    assert preview(second)["state"] == actions.STEP_ALREADY and second.data["changed"] is False
    assert first.data["context"] is None, "skip_context ran the context"


async def test_a_repository_whose_manifest_is_not_merged_has_its_preview_waiting(demo):
    with _in_the_shell():
        out = await actions.perform("onboard", by=_shell(), project="demo", with_preview=True,
                                    skip_context=True)

    (repo,) = out.data["repos"]
    step = next(s for s in repo["steps"] if s["step"] == "preview")
    assert step["state"] == actions.STEP_SKIPPED and "once the manifest merges" in step["said"]


async def test_a_repository_that_fails_is_said_by_its_step_and_the_others_still_run(demo):
    demo.broken = {"acme/web"}

    with _in_the_shell():
        out = await actions.perform("onboard", by=_shell(), project="demo", sources="acme/web")

    assert out.ok, "the row ran: a repository that failed is an answer, not a refusal"
    assert out.data["ok"] is False
    web = next(r for r in out.data["repos"] if r["repo"] == "acme/web")
    read = next(s for s in web["steps"] if s["step"] == "read")
    assert read["state"] == actions.STEP_FAILED and "access denied" in read["said"]
    assert [r for r, _ in demo.asked] == ["acme/demo", "acme/web"]
    assert "acme/web" in out.message, out.message


async def test_a_context_repository_nobody_declared_is_created_through_product_init(
        demo, tmp_path, monkeypatch):
    """The installation is changed by `product_init`'s row, asked by whoever asked for this one —
    a credential that may not change the installation is refused it there, not here."""
    _registry(tmp_path, monkeypatch, docs_repo="")
    seen: list[tuple[actions.Actor, dict]] = []

    async def recorder(by=None, **params):
        seen.append((by, params))
        return actions.done("recorded", steps=[{"step": "context", "state": "failed",
                                                 "said": "the forge refused to create it"}])

    monkeypatch.setattr(catalog, "CATALOG", {**catalog.CATALOG, "product_init": dataclasses.replace(
        catalog.CATALOG["product_init"], run=recorder)})

    with _in_the_shell():
        out = await actions.perform("onboard", by=_shell(), project="demo")

    assert [(by.id, params) for by, params in seen] == [
        ("ops", {"project": "demo", "create_context": True})]
    assert out.data["context"]["ok"] is False
    assert out.data["context"]["detail"] == "the forge refused to create it"
    assert demo.contexts == [], "the context box ran on a repository that was never made"


@pytest.mark.parametrize("in_the_shell", [True, False], ids=["shell", "worker"])
async def test_an_unknown_project_answers_a_reason_never_a_traceback(demo, engine, in_the_shell):
    with _in_the_shell() if in_the_shell else contextlib.nullcontext():
        out = await actions.perform("onboard", by=_panel(), project="nope")

    assert not out.ok and out.code == actions.NOT_FOUND
    assert out.data["reason"] == actions.NOT_FOUND
    assert "nope" in out.message and "demo" in out.message, out.message
    assert engine.started == [] and demo.asked == []


@pytest.mark.parametrize("in_the_shell", [True, False], ids=["shell", "worker"])
@pytest.mark.parametrize("source", ["../../etc", "not a repository"])
async def test_a_source_that_is_not_one_of_the_project_s_answers_a_reason(demo, engine,
                                                                         in_the_shell, source):
    with _in_the_shell() if in_the_shell else contextlib.nullcontext():
        out = await actions.perform("onboard", by=_panel(), project="demo",
                                    sources=f"acme/web,{source}")

    assert not out.ok and out.code == actions.INVALID
    assert out.data["reason"] == actions.INVALID and out.data["unreadable"] == [source]
    assert "Nothing was done" in out.message, out.message
    assert engine.started == [] and demo.asked == []


async def test_a_project_that_names_no_repository_has_nothing_to_onboard(demo, engine, tmp_path,
                                                                         monkeypatch):
    reg = tmp_path / "bare.yaml"
    reg.write_text(json.dumps({"projects": {"demo": {
        "name": "demo", "repo_path": "https://github.com/acme/demo.git"}}}))
    monkeypatch.setenv("BEEVERFORGE_REGISTRY", str(reg))

    out = await actions.perform("onboard", by=_panel(), project="demo")

    assert not out.ok and out.code == actions.INVALID and out.data["reason"] == actions.INVALID
    assert "nothing to onboard" in out.message, out.message
    assert engine.started == [] and demo.asked == []


# ── the worker's half: answers at once, one run per project ─────────────────────────────────────

async def test_away_from_the_shell_it_starts_the_run_on_the_worker_and_answers_its_handle(
        demo, engine):
    from beeverforge.runtime.temporal import TASK_QUEUE

    out = await actions.perform("onboard", by=_panel(), project="demo", sources="acme/web",
                                with_preview=True)

    assert out.ok, out.message
    (started,) = engine.started
    assert started["name"] == "OnboardWorkflow" and started["task_queue"] == TASK_QUEUE
    assert started["id"] == ob.workflow_id("demo") == out.data["handle"]
    assert started["execution_timeout"] == ob.ONBOARD_FLIGHT
    arg = started["arg"]
    assert (arg.project, arg.sources, arg.with_preview) == ("demo", ["acme/demo", "acme/web"],
                                                            True)
    assert (arg.asked_by, arg.via) == ("ana", "panel")
    assert out.data["state"] == ob.RUNNING and out.data["repos"] is None
    assert out.data["repositories"] == ["acme/demo", "acme/web"]
    assert demo.asked == [], "the request onboarded the repositories itself"


async def test_a_second_ask_while_a_run_is_going_answers_the_same_handle(demo, engine):
    first = await actions.perform("onboard", by=_panel(), project="demo")
    second = await actions.perform("onboard", by=_panel(), project="demo")

    assert first.data["handle"] == second.data["handle"]
    assert (first.data["joined"], second.data["joined"]) == (False, True)
    assert "already running" in second.message, second.message
    assert len(engine.started) == 1


def test_one_run_per_project_and_never_two_projects_on_one():
    assert ob.workflow_id("demo") == ob.workflow_id("demo")
    assert ob.workflow_id("demo") != ob.workflow_id("demo2")


async def test_with_no_engine_it_is_refused_as_unavailable(demo, monkeypatch):
    from beeverforge.actions.base import refused

    async def _connected():
        return None, refused(actions.UNAVAILABLE, "the durable engine is not answering")

    monkeypatch.setattr(catalog, "_connected", _connected)
    out = await actions.perform("onboard", by=_panel(), project="demo")

    assert not out.ok and out.code == actions.UNAVAILABLE and demo.asked == []


async def test_a_start_the_engine_refuses_for_another_reason_is_said_with_a_reference(
        demo, monkeypatch, caplog):
    class _Broken:
        async def start_workflow(self, *_a, **_k):
            raise RuntimeError("namespace not found")

    async def _connected():
        return _Broken(), None

    monkeypatch.setattr(catalog, "_connected", _connected)
    out = await actions.perform("onboard", by=_panel(), project="demo")

    assert not out.ok and out.code == actions.FAILED
    assert out.data["reference"] and out.data["reference"] in caplog.text


def test_the_worker_onboards_and_journals_it_driven_synchronously(demo):
    from beeverforge.runtime.temporal import activities as acts
    from beeverforge.runtime.temporal.io import OnboardInput

    said = acts._do_onboard(OnboardInput(project="demo", sources=["acme/demo", "acme/web"],
                                         asked_by="ana", via="panel"))

    assert said["project"] == "demo" and said["changed"] is True, said
    assert [r for r, _ in demo.asked] == ["acme/demo", "acme/web"]
    assert {e["job_id"] for e in _journal()} == {ob.workflow_id("demo")}


def test_the_worker_asks_product_init_as_whoever_asked(demo, tmp_path, monkeypatch):
    _registry(tmp_path, monkeypatch, docs_repo="")
    seen: list[actions.Actor] = []

    async def recorder(by=None, **params):
        seen.append(by)
        return actions.done("recorded", steps=[])

    monkeypatch.setattr(catalog, "CATALOG", {**catalog.CATALOG, "product_init": dataclasses.replace(
        catalog.CATALOG["product_init"], run=recorder)})
    from beeverforge.runtime.temporal import activities as acts
    from beeverforge.runtime.temporal.io import OnboardInput

    acts._do_onboard(OnboardInput(project="demo", sources=["acme/demo"], asked_by="ana",
                                  via="panel"))

    (by,) = seen
    assert (by.id, by.via, by.scopes) == ("ana", "panel", None)

    # A SCOPED ASKER IS REFUSED THERE, by `product_init`'s own rule: the installation is the
    # administrator's, and the worker does not widen who asked
    said = acts._do_onboard(OnboardInput(project="demo", sources=["acme/demo"], asked_by="bia",
                                         via="panel", scopes=[actions.FLOOR]))

    assert len(seen) == 1, "a floor-scoped asker changed the installation on the worker"
    assert said["context"]["ok"] is False
    assert "changes this installation" in said["context"]["detail"], said["context"]


def test_the_worker_says_an_unknown_project_and_raises_nothing(demo):
    from beeverforge.runtime.temporal import activities as acts
    from beeverforge.runtime.temporal.io import OnboardInput

    said = acts._do_onboard(OnboardInput(project="nope", sources=["acme/nope"]))

    assert said["ok"] is False and "nope" in said["detail"] and demo.asked == []


def test_the_workflow_runs_its_one_activity_bounded_and_heartbeating():
    from beeverforge.runtime.temporal import workflow as wf

    tree = ast.parse(inspect.getsource(wf.OnboardWorkflow))
    (call,) = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
               and getattr(n.func, "attr", "") == "execute_activity"]
    given = {k.arg: ast.unparse(k.value) for k in call.keywords}

    assert ast.unparse(call.args[0]) == "onboard_product"
    assert given == {"start_to_close_timeout": "ONBOARD_CEILING",
                     "heartbeat_timeout": "ONBOARD_HEARTBEAT", "retry_policy": "_ONCE"}
    assert ob.ONBOARD_HEARTBEAT < ob.ONBOARD_CEILING < ob.ONBOARD_FLIGHT


async def test_the_worker_s_run_heartbeats_while_it_goes(monkeypatch):
    """Driven by the beats, not by a clock: the run ends only once three beats have been heard,
    so an activity that ran it without heartbeating never lets it end (bounded, and then red)."""
    import threading

    from beeverforge.runtime.temporal import activities as acts
    from beeverforge.runtime.temporal.io import OnboardInput

    beats: list[str] = []
    heard = threading.Event()

    def beat(*details):
        beats.append(details[0] if details else "")
        if len(beats) >= 3:
            heard.set()

    def onboarding(inp):
        heard.wait(timeout=5)
        return {"project": inp.project}

    monkeypatch.setattr(acts.activity, "heartbeat", beat)
    monkeypatch.setattr(acts, "_TURN_PULSE", 0)
    monkeypatch.setattr(acts, "_do_onboard", onboarding)

    said = await acts.onboard_product(OnboardInput(project="demo"))

    assert said == {"project": "demo"}
    assert len(beats) >= 3 and all("demo" in b for b in beats), beats


class _Worker:
    """`temporalio.worker.Worker`, recorded: what each was built with. Runs nothing."""

    built: list[dict] = []

    def __init__(self, _client, **kwargs):
        _Worker.built.append(kwargs)

    async def run(self):
        return None


def test_the_worker_serves_the_onboarding(monkeypatch):
    """`worker.main()` booted with the engine faked: every worker it builds serves the workflow,
    and the activity the workflow runs."""
    from beeverforge.runtime.temporal import worker
    from beeverforge.runtime.temporal.activities import onboard_product
    from beeverforge.runtime.temporal.workflow import OnboardWorkflow

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
        assert OnboardWorkflow in built["workflows"], built["task_queue"]
        assert onboard_product in built["activities"], built["task_queue"]


# ── both transports, with the catalogue's authorization ────────────────────────────────────────

def test_through_the_panel_s_route_it_answers_the_handle(demo, engine, monkeypatch, caplog):
    monkeypatch.delenv("BEEVERFORGE_PANEL_TOKEN", raising=False)
    from fastapi.testclient import TestClient

    from beeverforge.api.app import app

    caplog.set_level(logging.INFO, logger="beeverforge.actions")
    r = TestClient(app).post("/api/act/onboard", json={"params": {
        "project": "demo", "sources": ["acme/web"], "with_preview": True}})

    assert r.status_code == 200, r.text
    assert r.json()["data"]["handle"] == ob.workflow_id("demo")
    assert engine.started[0]["arg"].sources == ["acme/demo", "acme/web"]
    assert "action=onboard" in caplog.text, "the audit line was not written"


def test_through_the_panel_s_route_an_unknown_project_is_a_404_with_its_reason(demo, engine,
                                                                               monkeypatch):
    monkeypatch.delenv("BEEVERFORGE_PANEL_TOKEN", raising=False)
    from fastapi.testclient import TestClient

    from beeverforge.api.app import app

    r = TestClient(app).post("/api/act/onboard", json={"params": {"project": "nope"}})

    assert r.status_code == 404, r.text
    assert r.json()["data"]["reason"] == actions.NOT_FOUND and "Traceback" not in r.text
    assert engine.started == []


def test_through_the_panel_s_route_a_credential_without_the_floor_is_refused(demo, engine,
                                                                            monkeypatch):
    from fastapi.testclient import TestClient

    from beeverforge.api.app import app
    from beeverforge.identity.local import (
        PEOPLE_ENV,
        PRODUCT_PEOPLE_ENV,
        PRODUCT_SHARED_ENV,
        SHARED_ENV,
    )

    monkeypatch.setenv(PEOPLE_ENV, "op-secret:rob:Rob")
    monkeypatch.setenv(PRODUCT_PEOPLE_ENV, "ba-secret:bia:Bia Rocha")
    monkeypatch.delenv(SHARED_ENV, raising=False)
    monkeypatch.delenv(PRODUCT_SHARED_ENV, raising=False)

    r = TestClient(app).post("/api/act/onboard", json={"params": {"project": "demo"}},
                             headers={"authorization": "Bearer ba-secret"})

    assert r.status_code == 403, r.text
    assert engine.started == [] and demo.asked == []


async def test_the_layer_refuses_a_credential_without_the_floor_by_its_reason(demo, engine):
    ba = actions.Actor(id="bia", display="Bia", via="panel", admin=True,
                       scopes=frozenset({actions.PRODUCT}))

    out = await actions.perform("onboard", by=ba, project="demo")

    assert not out.ok and out.code == actions.DENIED and out.data["reason"] == "out_of_scope"
    assert engine.started == [] and demo.asked == []


def test_through_the_shell_s_act_it_answers_the_handle(demo, engine, caplog):
    from beeverforge.cli import app as cli

    caplog.set_level(logging.INFO, logger="beeverforge.actions")
    result = CliRunner().invoke(cli, ["act", "onboard", "-p", "demo", "--param",
                                      "sources=acme/web", "--json"])

    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert body["data"]["handle"] == ob.workflow_id("demo") and body["data"]["repos"] is None
    assert len(engine.started) == 1 and demo.asked == []
    assert "action=onboard" in caplog.text, "the audit line was not written"


def test_through_the_shell_s_act_a_caller_without_the_floor_is_refused(demo, engine, monkeypatch,
                                                                       caplog):
    """The shell's actor is unscoped today (ADR-0039 §2); this is the day it is not — a shell whose
    identity holds only the product's area. `act` hands the refusal on, it does not decide it."""
    from beeverforge.cli import app as cli

    real = actions.Actor
    monkeypatch.setattr(actions, "Actor", lambda **kw: real(**kw, scopes=frozenset({
        actions.PRODUCT})))
    caplog.set_level(logging.INFO, logger="beeverforge.actions")

    result = CliRunner().invoke(cli, ["act", "onboard", "-p", "demo", "--json"])

    assert result.exit_code == 1, result.output
    body = json.loads(result.output)
    assert body["code"] == actions.DENIED and body["data"]["reason"] == "out_of_scope"
    assert engine.started == [] and demo.asked == []
    assert "DENIED_SCOPE onboard" in caplog.text, "the refusal was not audited"


# ── the verb is a mapping over the row ──────────────────────────────────────────────────────────

def test_the_onboard_verb_goes_through_the_row(demo, monkeypatch):
    from beeverforge.cli import app as cli

    seen: list[tuple[str, dict]] = []
    real = actions.perform

    async def spy(name, *, by, **params):
        seen.append((name, dict(params)))
        return await real(name, by=by, **params)

    monkeypatch.setattr(actions, "perform", spy)
    result = CliRunner().invoke(cli, ["onboard", "demo", "--source", "acme/web", "--yes"])

    assert result.exit_code == 0, result.output
    assert [name for name, _ in seen] == ["onboard"]
    assert seen[0][1]["project"] == "demo" and seen[0][1]["sources"] == ["acme/web"]
    assert "\n── acme/demo\n" in result.output and "\n── acme/web\n" in result.output
    assert "acme/demo: cloning" in result.output, "the progress no longer reaches the terminal"
    assert "── the product, repository by repository" in result.output
    assert "https://github.com/acme/web/pull/2" in result.output
    assert "── YOUR STEP: review and merge the pull request(s) above" in result.output


def test_the_verb_says_a_failed_repository_and_exits_1(demo):
    from beeverforge.cli import app as cli

    demo.broken = {"acme/demo"}
    result = CliRunner().invoke(cli, ["onboard", "demo", "--yes", "--skip-context"])

    assert result.exit_code == 1, result.output
    assert "✗ acme/demo" in result.output and "access denied" in result.output
