"""An exception raised in `perform` outside a row's own guard is an outcome, not a raise (#207).

`perform` caught a row's exception and answered `failed`/`raised` with a reference, but anything
that broke BEFORE the row ran (the catalog failing to import, a parameter check that breaks) went
straight to the caller, so the panel answered an unhandled 500 where every other failure answers a
named refusal. Now that path gets the same answer and the same one audit line, and a cancellation
still passes through.

THE AUDIT RECORD ON THIS BRANCH is the one `log.exception` line carrying the answer's reference:
no durable record exists until #43 lands. When #43 merges, its
`tests/test_every_action_leaves_one_audit_record.py::
test_a_call_that_raises_outside_the_rows_guard_leaves_one_record_and_raises` should expect this
outcome (one record, then the `failed`/`raised` answer) instead of the raise.

Mutation plan: `tools/mutations/207_an_exception_outside_the_rows_guard_is_an_outcome.py`.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging

import pytest
from fastapi.testclient import TestClient

from beeverforge import actions
from beeverforge.actions import base, catalog


def _breaks(exc: BaseException):
    def broken(*_a, **_kw):
        raise exc
    return broken


def _records_with(caplog, reference: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if reference in r.getMessage()]


@pytest.mark.parametrize("where, exc", [
    ("_check_params", RuntimeError("the check broke")),
    ("_catalog", ImportError("No module named 'x'")),
], ids=["a parameter check that breaks", "the catalog failing to import"])
async def test_a_call_that_raises_outside_the_rows_guard_leaves_one_record_and_answers(
        monkeypatch, caplog, where, exc):
    """Replaces #43's `..._leaves_one_record_and_raises`: the record stays, the raise does not."""
    monkeypatch.setattr(actions, where, _breaks(exc))
    with caplog.at_level("INFO"):
        out = await actions.perform("product_status", by=actions.SYSTEM, project="demo")

    assert out.ok is False
    assert out.code == actions.FAILED
    assert out.data["reason"] == base.RAISED
    reference = out.data["reference"]
    assert reference
    assert out.message.startswith("could not product_status:")
    assert str(exc) in out.message

    records = _records_with(caplog, reference)
    assert len(records) == 1, [r.getMessage() for r in records]
    assert records[0].levelno == logging.ERROR
    assert records[0].exc_info is not None


async def test_a_row_that_raises_still_leaves_one_record(monkeypatch, caplog):
    async def explodes(**_kw):
        raise RuntimeError("the row broke")

    monkeypatch.setattr(catalog, "CATALOG", {
        "product_status": dataclasses.replace(catalog.CATALOG["product_status"], run=explodes)})
    with caplog.at_level("INFO"):
        out = await actions.perform("product_status", by=actions.SYSTEM, project="demo")

    assert (out.ok, out.code, out.data["reason"]) == (False, actions.FAILED, base.RAISED)
    assert "the row broke" in out.message
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(errors) == 1, [r.getMessage() for r in errors]
    assert out.data["reference"] in errors[0].getMessage()


async def test_a_cancellation_outside_the_rows_guard_is_still_raised(monkeypatch):
    monkeypatch.setattr(actions, "_check_params", _breaks(asyncio.CancelledError()))
    with pytest.raises(asyncio.CancelledError):
        await actions.perform("product_status", by=actions.SYSTEM, project="demo")


async def test_a_cancellation_inside_the_row_is_still_raised(monkeypatch):
    async def cancelled(**_kw):
        raise asyncio.CancelledError()

    monkeypatch.setattr(catalog, "CATALOG", {
        "product_status": dataclasses.replace(catalog.CATALOG["product_status"], run=cancelled)})
    with pytest.raises(asyncio.CancelledError):
        await actions.perform("product_status", by=actions.SYSTEM, project="demo")


@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    from beeverforge.api.app import app

    monkeypatch.setenv("BEEVERFORGE_REGISTRY", str(tmp_path / "registry.yaml"))
    monkeypatch.delenv("BEEVERFORGE_PANEL_TOKEN", raising=False)
    return TestClient(app)


def test_the_panel_answers_an_exception_outside_the_guard_as_the_named_outcome(
        client, monkeypatch):
    from beeverforge.api import app as app_module

    monkeypatch.setattr(actions, "_check_params", _breaks(RuntimeError("the check broke")))
    r = client.post("/api/act/product_status", json={"params": {"project": "demo"}})

    assert r.status_code == app_module._STATUS[actions.FAILED]
    body = r.json()
    assert body["code"] == "failed"
    assert body["data"]["reason"] == "raised"
    assert body["data"]["reference"]
    assert body["detail"] == body["message"]
    assert "the check broke" in body["message"]
