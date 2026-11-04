"""A staged product write the module refused, or that raised, is not `done` (#187).

WHAT WAS WRONG: `confirm.answer_staged` answered `("done", sentence)` both when the product module
refused the write (`if not result.ok: return _client_detail(...)` in `_confirm_fact` and its
siblings) and when it raised (caught and answered with `broke()`). `catalog._product_answer` then
answered `done(...)`, so `/api/act/product_answer` said `ok: true` for a write that did not happen,
`beeverforge product ask … --propose --yes` exited 0, and the panel drew the refusal as an ordinary
line.

WHAT IS PROVEN HERE, through the real panel (`TestClient(app)`), the real `/api/act` row, the real
worker activity (`product_role_answer`) and the real gate, with only the module and the engine's
transport doubled:

  · a write the module refused answers its refusal word's code (403/404/409/400), with the role's
    sentence and `data.refusal`; a refusal that names no word is a failure with a reference;
  · a write whose module raised answers 500 `failed`, with a reference its log line names, and the
    person still hears the "something broke" sentence;
  · a write that succeeded still answers `done`;
  · the CLI's `--propose --yes` exits non-zero for both, and the panel's answer route does not
    answer either with its 200 decision payload.
"""

from __future__ import annotations

import logging

import pytest

from tests.test_a_card_nobody_started_can_be_closed_and_removed import (  # noqa: F401 — fixtures
    ADMIN,
    deployment,
)
from tests.test_a_product_refusal_answers_as_a_refusal_and_never_500 import (  # noqa: F401
    _post,
    client,
)
from tests.test_a_product_write_that_failed_is_still_a_failure_logged_with_a_reference import (
    _a_reference_its_line_names,
)

KEY = "someone-t187"
SENTENCE = "That term is already written down by someone, so nothing was changed."


class _Module:
    """The product module at its boundary: `note_fact` answers what the test hands it."""

    def __init__(self, answer):
        self.answer, self.wrote = answer, []

    def note_fact(self, *, term, body, said_by, where=""):
        self.wrote.append(term)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


@pytest.fixture
def staged(deployment, monkeypatch):  # noqa: F811 — the imported fixture
    """A `fact` proposal staged by hand for the deployment, and its token — dictated by the
    product admin, whose yes the tests give."""
    from beeverforge.memory import transcript
    from beeverforge.product import staging

    monkeypatch.setattr(transcript, "record", lambda *a, **k: "")
    staging._PENDING.clear()
    try:
        staging.remember(KEY, {"kind": "fact", "term": "someone", "body": "someone said it",
                               "said_by": ADMIN, "source": "", "channel": ""},
                         lang="en", project=deployment)
        yield staging.proposal_token(KEY, staging.pending_for(KEY, project=deployment))
    finally:
        staging._PENDING.clear()


@pytest.fixture
def on_the_worker(deployment, monkeypatch):  # noqa: F811 — the imported fixture
    """The engine, doubled at its transport only: the workflow runs the REAL activity in-process,
    which builds the module the test installs here."""
    from beeverforge.actions import catalog
    from beeverforge.product import module as module_mod
    from beeverforge.registry import ProjectRegistry
    from beeverforge.runtime.temporal import activities

    class _Engine:
        async def execute_workflow(self, name, inp, **_kw):
            return await activities.product_role_answer(inp)

    async def _connected():
        return _Engine(), None

    monkeypatch.setattr(catalog, "_connected", _connected)
    monkeypatch.setattr(ProjectRegistry, "get", lambda self, name: deployment)
    installed: dict = {}

    def _install(module):
        monkeypatch.setattr(module_mod, "ProductModule",
                            lambda project, *, via="api": module)
        installed["module"] = module
        return module

    return _install


def _answer(client, token):  # noqa: F811 — the imported fixture
    return _post(client, "product_answer", who=ADMIN, token=token, answer="approve", yes=True)


@pytest.mark.parametrize("word, status, code", [
    ("not_yours", 403, "denied"),
    ("not_found", 404, "not_found"),
    ("not_waiting", 409, "conflict"),
    ("not_valid", 400, "invalid"),
])
def test_a_staged_write_the_module_refused_answers_its_refusal_code(
        client, staged, on_the_worker, word, status, code):  # noqa: F811 — fixtures
    """Criterion 1. On the old code this answered 200 `ok: true`, `outcome: done`."""
    from beeverforge.product.authoring import WriteResult

    module = on_the_worker(_Module(WriteResult(ok=False, refusal=word, detail=SENTENCE)))

    r = _answer(client, staged)

    said = r.json()
    assert module.wrote == ["someone"], "the staged write was never tried"
    assert said["ok"] is False, said
    assert (r.status_code, said["code"]) == (status, code), (r.status_code, said)
    assert said["message"] == SENTENCE, said
    assert said["data"]["refusal"] == word, said


def test_a_staged_write_refused_with_no_word_is_a_failure_with_a_reference(
        client, staged, on_the_worker, caplog):  # noqa: F811 — fixtures
    """Criterion 1's other half: a not-ok result that names no refusal is nobody's decision."""
    from beeverforge.product.authoring import WriteResult

    on_the_worker(_Module(WriteResult(ok=False, refusal="", detail=SENTENCE)))

    with caplog.at_level(logging.INFO):
        r = _answer(client, staged)

    assert r.json()["ok"] is False, r.json()
    _a_reference_its_line_names(r, caplog)
    assert r.json()["message"] == SENTENCE, r.json()


def test_a_staged_write_whose_module_raised_answers_500_failed_with_a_reference(
        client, staged, on_the_worker, deployment, caplog):  # noqa: F811 — fixtures
    """Criterion 2. On the old code this answered 200 `ok: true` with the "something broke"
    sentence. The person is still answered with it — silence is the worst answer."""
    from beeverforge.product import voice

    on_the_worker(_Module(RuntimeError("the corpus checkout died")))

    with caplog.at_level(logging.INFO):
        r = _answer(client, staged)

    said = r.json()
    assert said["ok"] is False, said
    _a_reference_its_line_names(r, caplog)
    assert said["message"] == voice.strip_markup(voice.broke(language=deployment.language)), said
    assert any("BEEVERFORGE_PRODUCT_MUTE" in rec.getMessage() for rec in caplog.records), (
        "the crash is no longer logged as a mute")


def test_a_staged_write_that_succeeded_still_answers_done(
        client, staged, on_the_worker):  # noqa: F811 — fixtures
    """Criterion 3: the write that happened is unchanged."""
    from beeverforge.product.authoring import WriteResult

    module = on_the_worker(_Module(WriteResult(ok=True)))

    r = _answer(client, staged)

    said = r.json()
    assert (r.status_code, said["ok"]) == (200, True), said
    assert said["data"]["outcome"] == "done", said
    assert module.wrote == ["someone"]


def test_product_answer_declares_every_code_a_staged_write_can_answer():
    """Criterion 4: the row's `refuses=` names each code the new outcomes answer."""
    from beeverforge.actions import catalog

    spec = catalog.CATALOG["product_answer"]
    assert {catalog.DENIED, catalog.NOT_FOUND, catalog.CONFLICT, catalog.INVALID,
            catalog.FAILED} <= set(spec.refuses), spec.refuses


@pytest.mark.parametrize("raw", [
    {"outcome": "refused", "refusal": "not_found", "message": SENTENCE},
    {"outcome": "failed", "refusal": "", "message": "Something broke on my side."},
], ids=["refused", "failed"])
def test_product_ask_propose_yes_exits_non_zero_for_a_refused_and_a_crashed_staged_write(
        monkeypatch, raw):
    """Criterion 5: the CLI's yes reads the row's answer, so a write that did not happen is not
    an exit 0. On the old catalog both answered `done` and the command exited 0."""
    from typer.testing import CliRunner

    from beeverforge import cli
    from beeverforge.actions import catalog
    from beeverforge.actions.base import done
    from beeverforge.contracts.product import ProductConfig
    from beeverforge.contracts.project import Project, ProviderRef

    project = Project(name="acme", repo_path="/t", tracker=ProviderRef(kind="local", repo="acme"),
                      product=ProductConfig(docs_repo="acme/docs", admins=["someone"]))
    monkeypatch.setattr(catalog, "_product_module", lambda _name, **_kw: (object(), project, None))

    class _Engine:
        async def execute_workflow(self, name, inp, **_kw):
            return raw

    async def _connected():
        return _Engine(), None

    monkeypatch.setattr(catalog, "_connected", _connected)
    real = cli._perform

    def _perform(name, **params):
        if name == "product_say":
            return done("I will write that down.", project="acme", token=f"{KEY}|abc")
        return real(name, **params)

    monkeypatch.setattr(cli, "_perform", _perform)

    result = CliRunner().invoke(cli.app, ["product", "ask", "acme", "someone says so",
                                          "--propose", "--yes"])

    assert result.exit_code != 0, result.output


def _panel_route(monkeypatch, route, sink, answered):
    """The panel's own answer route, with the gate's answer handed in."""
    from beeverforge.product import channel as pc
    from beeverforge.product import confirm as gate
    from beeverforge.registry import ProjectRegistry
    from tests.test_the_panel_is_a_channel import _stage_in_the_worker, _staged_project

    token = _stage_in_the_worker(sink)
    pc._PENDING.clear()
    monkeypatch.setattr(ProjectRegistry, "get",
                        lambda self, name: _staged_project(admins=["someone"]))
    monkeypatch.setattr(gate, "answer_staged", lambda project, **kw: answered)
    monkeypatch.setenv("BEEVERFORGE_PANEL_TOKENS", "mine:someone")
    return route.post("/api/messages/demo/answer",
                      json={"token": token, "answer": "approve"},
                      headers={"Authorization": "Bearer mine"})


@pytest.fixture
def panel(tmp_path, monkeypatch):
    """The panel and its in-memory message store, as `test_the_panel_is_a_channel` sets them up."""
    from fastapi.testclient import TestClient

    from beeverforge.api.app import app
    from tests.test_the_panel_is_a_channel import _Sink
    from tests.the_sink_door import SINK_DOOR

    monkeypatch.setenv("BEEVERFORGE_REGISTRY", str(tmp_path / "registry.yaml"))
    monkeypatch.delenv("BEEVERFORGE_PANEL_TOKEN", raising=False)
    monkeypatch.delenv("BEEVERFORGE_PANEL_TOKENS", raising=False)
    monkeypatch.delenv("BEEVERFORGE_IDENTITY", raising=False)
    s = _Sink()
    monkeypatch.setattr(SINK_DOOR, lambda: s)
    monkeypatch.setattr("beeverforge.observability.query.records_of_kind",
                        lambda project, kind, limit=500, **kw: s.of_kind(project, kind, limit))
    from beeverforge.product import channel as pc

    pc._PENDING.clear()
    yield TestClient(app), s
    pc._PENDING.clear()


def test_the_panels_answer_route_answers_a_refused_staged_write_with_its_refusal_status(
        monkeypatch, panel):
    """The panel route maps `refused` onto the refusal word's status, never onto its 200 decision
    payload — on the old route an unknown outcome fell through to 200."""
    from beeverforge.product.confirm import Refused

    route, sink = panel
    r = _panel_route(monkeypatch, route, sink, ("refused", Refused(SENTENCE, refusal="not_yours")))

    assert r.status_code == 403, r.text
    assert r.json()["detail"] == SENTENCE, r.json()


def test_the_panels_answer_route_answers_a_crashed_staged_write_500(monkeypatch, panel):
    route, sink = panel
    r = _panel_route(monkeypatch, route, sink, ("failed", "Something broke on my side."))

    assert r.status_code == 500, r.text
    assert r.json()["detail"] == "Something broke on my side.", r.json()
