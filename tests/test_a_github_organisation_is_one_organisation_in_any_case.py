"""A GitHub organisation is one organisation however the registry spells it (#150).

GitHub logins are case-insensitive: `Acme/api` and `acme/web` are two repositories of ONE
organisation. The registry grouped its projects by the spelling, so such a registry read as
spanning two organisations: `project add` refused the second project, `ProjectRegistry.list`
logged a false `BEEVERFORGE_REGISTRY_SPANS_INSTALLATIONS`, and `beeverforge doctor`'s
`installation_scope` line failed a correct deployment. The comparison with the App installation's
account already ignored case (`registry.installation_scope_line`); the grouping now does too, and
keeps the first spelling the registry holds for the sentence.
"""

from __future__ import annotations

import dataclasses

import pytest
import yaml

from beeverforge import doctor, registry
from beeverforge.registry import ProjectRegistry
from tests.pinned_probes import a_fully_pinned_probe_set


def _hand_written(tmp_path, monkeypatch, projects: dict[str, str]):
    """`{name: "owner/repo"}` written as YAML, named by `BEEVERFORGE_REGISTRY`; returns the path.
    `yaml.safe_dump` sorts the names, so registry order is alphabetical."""
    path = tmp_path / "registry.yaml"
    path.write_text(yaml.safe_dump({"projects": {
        name: {"name": name, "repo_path": f"/tmp/{name}",
               "tracker": {"kind": "github", "repo": repo}}
        for name, repo in projects.items()}}))
    monkeypatch.setenv("BEEVERFORGE_REGISTRY", str(path))
    return path


def _line_from_the_live_probe(path) -> doctor.Finding:
    project = ProjectRegistry(path).list()[0]
    probes = dataclasses.replace(
        a_fully_pinned_probe_set(),
        installation_scope=doctor.probes_for(project).installation_scope)
    return next(f for f in doctor.diagnose(probes).findings
                if f.check == doctor.INSTALLATION_SCOPE)


def _github(name: str, owner: str = "acme", **kw):
    from beeverforge.contracts.project import Project, ProviderRef

    return Project(name=name, repo_path=f"/tmp/{name}",
                   tracker=ProviderRef(kind="github", repo=f"{owner}/{name}"), **kw)


def test_two_spellings_of_one_organisation_do_not_span(tmp_path, monkeypatch):
    path = _hand_written(tmp_path, monkeypatch, {"api": "Acme/api", "web": "acme/web"})
    projects = ProjectRegistry(path).list()

    assert registry.spanning_installations(projects) == {}
    assert registry.owners_by_project(projects) == {"Acme": ["api", "web"]}


def test_one_project_spelling_its_organisation_two_ways_is_listed_once():
    from beeverforge.contracts.project import Project, ProviderRef

    project = Project(name="api", repo_path="/tmp/api",
                      tracker=ProviderRef(kind="github", repo="acme/api",
                                          options={"board_owner": "Acme"}))

    assert registry.owners_by_project([project]) == {"Acme": ["api"]}


def test_list_logs_no_spanning_warning_for_two_spellings(tmp_path, monkeypatch, caplog):
    path = _hand_written(tmp_path, monkeypatch, {"api": "Acme/api", "web": "acme/web"})

    caplog.clear()
    with caplog.at_level("ERROR"):
        ProjectRegistry(path).list()

    assert "BEEVERFORGE_REGISTRY_SPANS_INSTALLATIONS" not in caplog.text, caplog.text


def test_project_add_accepts_the_same_organisation_spelled_differently(tmp_path):
    reg = ProjectRegistry(tmp_path / "r.yaml")
    reg.add(_github("api", owner="Acme"))
    reg.add(_github("web", owner="acme"))

    assert sorted(p.name for p in reg.list()) == ["api", "web"]


def test_project_add_still_refuses_another_organisation(tmp_path):
    """The red twin: ignoring case must not turn into accepting everything."""
    reg = ProjectRegistry(tmp_path / "r.yaml")
    reg.add(_github("api", owner="Acme"))

    with pytest.raises(ValueError):
        reg.add(_github("web", owner="othercorp"))


def test_doctor_installation_scope_does_not_fail_two_spellings(tmp_path, monkeypatch):
    path = _hand_written(tmp_path, monkeypatch, {"api": "Acme/api", "web": "acme/web"})

    finding = _line_from_the_live_probe(path)

    assert finding.ok is True, finding.message
    assert "spans" not in finding.message, finding.message


def test_the_sentence_names_the_organisation_by_its_first_spelling(tmp_path, monkeypatch):
    path = _hand_written(tmp_path, monkeypatch,
                         {"api": "Acme/api", "web": "acme/web", "x": "othercorp/x"})
    projects = ProjectRegistry(path).list()

    said = registry.spanning_message(registry.spanning_installations(projects))
    assert "Acme (api, web)" in said, said
    assert "othercorp (x)" in said, said
    assert "acme (" not in said, said

    ok, message, _ = registry.installation_scope_line(
        registry.owners_by_project(projects[:2]), ("someone-else", ""))
    assert ok is False
    assert "Acme (api, web)" in message, message


def _with_a_factory_board(board_repo: str):
    from beeverforge.contracts.project import FactoryBoard, Project, ProviderRef

    return Project(
        name="api", repo_path="/tmp/api",
        tracker=ProviderRef(kind="github", repo="Acme/api"),
        factory_board=FactoryBoard(
            tracker=ProviderRef(kind="github", repo=board_repo), supervisor="someone"))


def test_a_factory_board_in_the_same_organisation_spelled_differently_is_not_foreign(
        tmp_path, caplog):
    reg = ProjectRegistry(tmp_path / "r.yaml")

    with caplog.at_level("WARNING"):
        reg.add(_with_a_factory_board("acme/beeverforge"))

    assert "different GitHub organisation" not in caplog.text, caplog.text


def test_a_factory_board_in_another_organisation_still_warns(tmp_path, caplog):
    reg = ProjectRegistry(tmp_path / "r.yaml")

    with caplog.at_level("WARNING"):
        reg.add(_with_a_factory_board("othercorp/beeverforge"))

    assert "different GitHub organisation" in caplog.text
