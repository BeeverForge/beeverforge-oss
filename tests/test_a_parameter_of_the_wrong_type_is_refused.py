"""A parameter whose value is not of the type the row declares is refused before the row runs (#211).

`POST /api/act/product_status` with a list for `project` reached the registry and was answered
with an ERROR and a traceback. The row's runner declares `project: str`; the action layer now reads
that annotation and refuses anything that is not a scalar, as `bad_parameters`, by name.
"""

from __future__ import annotations

import dataclasses
import logging

import pytest

from beeverforge import actions
from beeverforge.actions import _check_params


@pytest.mark.parametrize("value", [["a"], {"x": 1}])
async def test_a_list_where_a_string_is_declared_is_refused_before_the_row_runs(monkeypatch, value):
    from beeverforge.actions import catalog

    calls: list[object] = []

    async def runner(*, project: str, by: actions.Actor) -> actions.Outcome:
        calls.append(project)
        raise AssertionError("the row ran")

    row = dataclasses.replace(catalog.CATALOG["product_status"], run=runner)
    monkeypatch.setitem(catalog.CATALOG, "product_status", row)

    out = await actions.perform("product_status",
                                by=actions.Actor(id="U9", via="cli", admin=True), project=value)

    assert out.ok is False
    assert out.code == actions.INVALID
    assert out.data["reason"] == "bad_parameters"
    assert "project" in out.message and "string" in out.message
    assert "\n" not in out.message
    assert out.message.endswith(".") and not out.message.endswith("..")
    assert out.message.count(". ") == 0
    assert calls == []


def test_a_string_or_scalar_value_passes_the_type_check():
    assert _check_params(actions.spec("product_status"), {"project": "demo"}) == ""
    assert _check_params(actions.spec("start"), {"project": "demo", "issue": "12",
                                                 "promote": True, "sandbox": True}) == ""
    assert _check_params(actions.spec("skip"), {"project": "demo", "issue": 12}) == ""


def test_a_list_project_answers_400_naming_it_and_logs_no_traceback(caplog):
    from fastapi.testclient import TestClient

    from beeverforge.api.app import app

    with caplog.at_level(logging.DEBUG):
        r = TestClient(app).post("/api/act/product_status", json={"params": {"project": ["a"]}})

    assert r.status_code == 400
    assert "project" in r.json()["detail"]
    assert r.json()["data"]["reason"] == "bad_parameters"
    assert not [rec for rec in caplog.records if rec.levelno >= logging.ERROR or rec.exc_info]
