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


@pytest.mark.parametrize(("row", "params", "bad"), [
    ("enable", {"project": "demo", "enabled": ["a"]}, "enabled"),
    ("enable", {"project": "demo", "enabled": "no"}, "enabled"),
    ("start", {"project": "demo", "issue": "12", "promote": {"x": 1}}, "promote"),
    ("start", {"project": "demo", "issue": "12", "durable": 1}, "durable"),
])
async def test_a_value_that_is_not_a_boolean_where_one_is_declared_is_refused(row, params, bad,
                                                                               monkeypatch):
    from beeverforge.actions import catalog

    async def runner(**_: object) -> actions.Outcome:
        raise AssertionError("the row ran")

    original = catalog.CATALOG[row]
    stub = dataclasses.replace(original, run=runner)
    monkeypatch.setitem(catalog.CATALOG, row, stub)
    # The stub carries the original runner's declared types, so the check reads those.
    monkeypatch.setattr(actions, "_declared_types",
                        lambda found, _real=actions._declared_types: _real(original))

    out = await actions.perform(row, by=actions.Actor(id="U9", via="cli", admin=True), **params)

    assert out.ok is False
    assert out.code == actions.INVALID
    assert out.data["reason"] == "bad_parameters"
    assert bad in out.message and "true or false" in out.message
    assert "\n" not in out.message and out.message.count(". ") == 0


def test_a_boolean_or_nothing_passes_where_a_boolean_is_declared():
    assert _check_params(actions.spec("enable"), {"project": "demo", "enabled": False}) == ""
    assert _check_params(actions.spec("enable"), {"project": "demo", "enabled": None}) == ""


def test_every_type_a_row_declares_is_one_the_check_knows():
    """A row that declares a type the check does not know would let any value through it again."""
    from beeverforge.actions import _ACCEPTS, _declared_types, catalog

    unknown = sorted(f"{key}.{p}: {_declared_types(row).get(p)!r}"
                     for key, row in catalog.CATALOG.items()
                     for p in row.parameters
                     if p in _declared_types(row)
                     and _declared_types(row)[p] not in _ACCEPTS)
    assert unknown == []
