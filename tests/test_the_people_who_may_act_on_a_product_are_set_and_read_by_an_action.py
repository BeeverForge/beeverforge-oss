"""#528: `product_people_set` and `product_people_list` set and read who may approve or act on a
product — `product.admins` and `product.engineers` — in one registry write.

The registry is driven for real (a file under `tmp_path`) and `may_act` is asked of the project
read back from it, with nothing of `authz` mocked. Nothing waits on time: the lock's two threads
are released by an event.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from beeverforge import actions
from beeverforge.product import people as the_people

ROOT = Path(__file__).resolve().parents[1]
INSTALLATION = actions.Actor(id="rob", via="panel", admin=True)
FULL = [{"id": "ana", "role": "admin"}, {"id": "bia", "role": "admin"},
        {"id": "caio", "role": "engineer"}]


def _set(people=FULL, by=INSTALLATION, project="acme"):
    params = {} if people is None else {"people": people}
    return asyncio.run(actions.perform("product_people_set", by=by, project=project, **params))


def _list(project="acme"):
    return asyncio.run(actions.perform("product_people_list", by=INSTALLATION, project=project))


def _bytes(path: Path) -> bytes:
    return path.read_bytes()


@pytest.fixture
def registry(tmp_path, monkeypatch):
    """`acme` with a product section whose other fields must survive, and `bare` with none."""
    from beeverforge.contracts.product import ProductConfig
    from beeverforge.contracts.project import Project
    from beeverforge.registry import ProjectRegistry

    path = tmp_path / "registry.yaml"
    monkeypatch.setenv("BEEVERFORGE_REGISTRY", str(path))
    reg = ProjectRegistry()
    reg.add(Project(name="acme", repo_path=str(tmp_path / "acme"),
                    product=ProductConfig(docs_repo="acme/docs", agent_name="Bruno",
                                          timezone="America/Sao_Paulo", enabled=True,
                                          admins=["old"], engineers=["gone"])))
    reg.add(Project(name="bare", repo_path=str(tmp_path / "bare")))
    return path


def _product(path: Path, name="acme") -> dict:
    return yaml.safe_load(path.read_text())["projects"][name]["product"]


# ── in the catalogue ────────────────────────────────────────────────────────────────────────────

def test_both_rows_are_in_the_catalogue_and_run(registry):
    assert {"product_people_set", "product_people_list"} <= set(actions.names())
    assert _set().ok and _list().ok


# ── what a set writes ───────────────────────────────────────────────────────────────────────────

def test_a_set_writes_both_lists_and_keeps_the_rest_of_the_entry(registry):
    before = yaml.safe_load(registry.read_text())["projects"]
    out = _set()
    assert out.ok and out.data["changed"] is True
    after = yaml.safe_load(registry.read_text())["projects"]
    assert after["acme"]["product"]["admins"] == ["ana", "bia"]
    assert after["acme"]["product"]["engineers"] == ["caio"]  # "old" and "gone" left out: removed
    for kept in ("docs_repo", "agent_name", "timezone", "enabled"):
        assert after["acme"]["product"][kept] == before["acme"]["product"][kept]
    after["acme"]["product"].pop("admins"), after["acme"]["product"].pop("engineers")
    before["acme"]["product"].pop("admins"), before["acme"]["product"].pop("engineers")
    assert after == before


def test_may_act_follows_the_list_for_the_ids_the_provider_gives(registry):
    from beeverforge.product.module import may_act
    from beeverforge.registry import ProjectRegistry

    _set()
    project = ProjectRegistry().get("acme")
    assert may_act(project, "ana") and may_act(project, "bia")
    assert not may_act(project, "caio")  # an engineer is not an admin
    assert not may_act(project, "old") and not may_act(project, "stranger")


def test_an_empty_list_empties_both_and_a_missing_one_is_refused(registry):
    assert _set([]).ok
    assert _product(registry)["admins"] == [] and _product(registry)["engineers"] == []
    _set()
    before = _bytes(registry)
    out = _set(None)
    assert not out.ok and out.code == "invalid" and _bytes(registry) == before


# ── refusals write nothing ──────────────────────────────────────────────────────────────────────

def test_a_project_with_no_product_section_is_refused_naming_the_declaration(registry):
    before = _bytes(registry)
    out = _set(project="bare")
    assert out.code == "not_found" and "product declare" in out.message
    assert _bytes(registry) == before
    assert _list(project="bare").code == "not_found"


def test_an_unregistered_project_is_refused_naming_the_roster(registry):
    before = _bytes(registry)
    out = _set(project="ghost")
    assert out.code == "not_found" and "acme" in out.message and _bytes(registry) == before


@pytest.mark.parametrize("people, names", [
    ([{"id": "", "role": "admin"}], "entry 1"),
    ([{"id": "ok", "role": "admin"}, {"id": "   ", "role": "admin"}], "entry 2"),
    ([{"id": "x", "role": "owner"}], "entry 1"),
    ([{"id": "x", "role": "admin"}, {"id": "x", "role": "engineer"}], "entry 2"),
    ([{"id": f"p{i}", "role": "admin"} for i in range(the_people.BOUND + 1)], "at most"),
    (["ana"], "entry 1"),
    ("ana", "list"),
])
def test_a_malformed_entry_is_refused_naming_it_and_writes_nothing(registry, people, names):
    before = _bytes(registry)
    out = _set(people)
    assert out.code == "invalid" and names in out.message
    assert _bytes(registry) == before


def test_the_same_list_answers_unchanged_and_does_not_rewrite(registry, monkeypatch):
    from beeverforge.registry import ProjectRegistry

    _set()
    before = _bytes(registry)
    saves = []
    real = ProjectRegistry._save_raw
    monkeypatch.setattr(ProjectRegistry, "_save_raw",
                        lambda self, projects: (saves.append(1), real(self, projects)))
    out = _set(list(reversed(FULL)))
    assert out.ok and out.data["changed"] is False
    assert saves == [] and _bytes(registry) == before


def test_the_answer_names_what_was_added_removed_and_kept(registry):
    out = _set([{"id": "ana", "role": "admin"}, {"id": "old", "role": "admin"},
                {"id": "caio", "role": "engineer"}])
    assert out.data["admins"] == {"added": ["ana"], "removed": [], "unchanged": ["old"]}
    assert out.data["engineers"] == {"added": ["caio"], "removed": ["gone"], "unchanged": []}


def test_one_audit_record_with_counts_and_digest_and_no_ids(registry, caplog):
    with caplog.at_level(logging.INFO):
        out = _set()
    mine = [r for r in caplog.records if "product_people_set" in r.getMessage()]
    assert len(mine) == 1
    line = mine[0].getMessage()
    assert "acme" in line and "2 admins, 1 engineers" in line and out.data["digest"] in line
    assert "ana" not in line.replace("acme", "")


# ── two writers ─────────────────────────────────────────────────────────────────────────────────

def test_two_concurrent_sets_leave_one_list_whole(registry):
    from beeverforge.registry import ProjectRegistry

    one = [{"id": "a1", "role": "admin"}, {"id": "a2", "role": "engineer"}]
    two = [{"id": "b1", "role": "admin"}, {"id": "b2", "role": "engineer"}]
    go, first_in, seen = threading.Event(), threading.Event(), []
    real = ProjectRegistry._load_raw

    def slow(self):
        data = real(self)
        first_in.set()
        go.wait(5)  # released by the event, never by time passing
        return data

    ProjectRegistry._load_raw = slow
    try:
        threads = [threading.Thread(target=lambda p=p: seen.append(_set(p))) for p in (one, two)]
        for t in threads:
            t.start()
        first_in.wait(5)
        go.set()
        for t in threads:
            t.join(10)
    finally:
        ProjectRegistry._load_raw = real
    held = _product(registry)
    assert (held["admins"], held["engineers"]) in ((["a1"], ["a2"]), (["b1"], ["b2"]))
    assert all(o.ok for o in seen)


# ── who may ─────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("by", [
    actions.Actor(id="x", via="panel", admin=True, scopes=frozenset({"floor"})),
    actions.Actor(id="x", via="panel", admin=True, scopes=frozenset({"product"})),
    actions.Actor(id="ana", via="product", admin=True, scopes=frozenset({"product"})),
    actions.Actor(id="ana", via="panel", admin=True),  # unscoped, adding themselves
])
def test_a_credential_that_is_not_the_installations_is_denied(registry, by):
    before = _bytes(registry)
    out = _set(by=by)
    assert out.code == "denied" and _bytes(registry) == before


def test_a_person_may_leave_themselves_on_the_list_but_not_join_it(registry):
    me = actions.Actor(id="old", via="panel", admin=True)
    assert _set([{"id": "old", "role": "admin"}], by=me).ok


# ── the read ────────────────────────────────────────────────────────────────────────────────────

def test_the_list_answers_what_was_set_with_the_same_digest(registry):
    out = _set()
    read = _list()
    assert read.ok and read.data["digest"] == out.data["digest"]
    assert read.data["people"] == [{"id": "ana", "role": "admin"}, {"id": "bia", "role": "admin"},
                                   {"id": "caio", "role": "engineer"}]


def test_the_list_of_a_product_nobody_is_on_is_empty(registry):
    _set([])
    assert _list().data["people"] == [] and _list().data["digest"] == _set([]).data["digest"]


# ── the documents and the command ───────────────────────────────────────────────────────────────

def test_the_rows_are_documented():
    api = (ROOT / "docs/reference/the-front-end-api.md").read_text()
    cli = (ROOT / "docs/reference/cli.md").read_text()
    cfg = (ROOT / "docs/configuration.md").read_text()
    for row in ("product_people_set", "product_people_list"):
        assert f"| `{row}` |" in api
    assert "product people set" in cli and "product people list" in cli
    assert "product_people_set" in cfg
    assert list((ROOT / "changes").glob("528.*.md"))


def test_the_command_sets_and_lists(registry):
    from beeverforge.cli import app

    runner = CliRunner()
    out = runner.invoke(app, ["product", "people", "set", "acme", "--admin", "ana",
                              "--admin", "bia", "--engineer", "caio"])
    assert out.exit_code == 0, out.output
    assert _product(registry)["admins"] == ["ana", "bia"]
    listed = runner.invoke(app, ["product", "people", "list", "acme"])
    assert listed.exit_code == 0 and "ana" in listed.output and "caio" in listed.output
    refused = runner.invoke(app, ["product", "people", "set", "bare", "--admin", "ana"])
    assert refused.exit_code != 0


# ── the amended decision ────────────────────────────────────────────────────────────────────────

def test_adr_0057_names_this_row_as_the_declared_exception_to_the_grants_rule():
    text = next((ROOT / "docs/adr").glob("0057-*.md")).read_text()
    assert "product_people_set" in text


def test_only_this_row_writes_the_product_lists():
    from beeverforge.registry import ProjectRegistry

    assert hasattr(ProjectRegistry, "set_people")
    src = (ROOT / "beeverforge/actions/catalog.py").read_text()
    assert src.count(".set_people(") == 1
