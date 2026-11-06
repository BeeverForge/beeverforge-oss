"""A GitHub repository typed in another case is one repository at every site that compares it (#385).

#380 made the Projects board compare repositories without case. Four more sites compared a
registry's spelling with a typed or minted one by spelling:

  · the product page (`page.card_of`) refused the project's own card typed `Acme/api#42` as a
    card of another repository;
  · the card checkout (`card_repo._is_default_repo`, and its Azure DevOps branch) filed the
    project's own repository under a foreign key;
  · `project add` (`catalog._differs`) reported the tracker as different and refused a re-add;
  · the product module (`ProductModule.mounts`) did not label a `sources:` entry spelling the
    project's own repository otherwise as its own mount.

Each site has a twin where the registry holds the capitals, so a fold of one side only goes red,
and a twin where the repository really is another, so a site that matched every repository goes
red. The casefold is for the comparison only: what is shown or written keeps its spelling.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from beeverforge import actions
from beeverforge.contracts.project import Project, ProviderRef
from beeverforge.product import page
from beeverforge.product.module import ProductModule
from beeverforge.runtime.card_repo import _checkout_key, _is_default_repo, _runner_view

ADMIN = actions.Actor(id="rob", via="panel", admin=True)


def _github(repo: str) -> Project:
    return Project(name="dsk", repo_path="/tmp/dsk",
                   tracker=ProviderRef(kind="github", repo=repo,
                                       options={"board_owner": "acme", "board_number": "1"}),
                   forge=ProviderRef(kind="github", repo=repo))


def _ado(*, repo: str = "fx-ado", ado_project: str = "Deskline") -> Project:
    return Project(name="fx", repo_path="https://dev.azure.com/org/Deskline/_git/fx-ado",
                   tracker=ProviderRef(kind="azure_devops", repo=ado_project),
                   forge=ProviderRef(kind="azure_devops", repo=repo,
                                     options={"organization": "org", "project": ado_project}))


# ── 1. the product page ──────────────────────────────────────────────────────────────────────────

def test_a_card_of_the_projects_repository_typed_otherwise_is_its_own():
    project = _github("acme/api")

    assert page.card_of(project, "Acme/api#42") == ("42", "")
    context, why = page.admit(project, {"page": "card", "card": "Acme/api#42"},
                              may_read_board=True)
    assert why == "" and context == {"page": "card", "card": "42"}, (context, why)


def test_a_registry_in_capitals_takes_its_own_card_typed_in_lowercase():
    assert page.card_of(_github("Acme/API"), "acme/api#42") == ("42", "")


def test_a_card_of_another_repository_is_still_refused():
    project = _github("acme/api")

    for typed, repo in (("acme/web#42", "acme/web"), ("other/api#42", "other/api")):
        ref, why = page.card_of(project, typed)
        assert ref == "", (typed, ref)
        assert f"lives in {repo}" in why and "dsk's board" in why, why
        assert "ask about it from the project that registers" in why, why


# ── 2. the card checkout ─────────────────────────────────────────────────────────────────────────

def test_a_card_of_the_default_repository_typed_otherwise_checks_out_under_the_projects_key():
    project = _github("acme/api")

    assert _is_default_repo(project, "Acme/API") is True
    assert _checkout_key(project, "Acme/API") == "dsk"
    assert _runner_view(project, "Acme/API#3") == (project, "dsk")


def test_a_registry_in_capitals_checks_out_its_own_card_typed_in_lowercase():
    project = _github("Acme/API")

    assert _is_default_repo(project, "acme/api") is True
    assert _checkout_key(project, "acme/api") == "dsk"
    assert _runner_view(project, "acme/api#3") == (project, "dsk")


def test_a_card_of_another_repository_is_still_foreign_in_any_case():
    project = _github("acme/api")

    assert _is_default_repo(project, "Acme/web") is False
    assert _checkout_key(project, "Acme/web") == "dsk--Acme--web"
    assert _is_default_repo(project, "Other/api") is False


def test_an_ado_qualified_default_typed_otherwise_keys_to_the_project_name():
    assert _checkout_key(_ado(), "DeskLine/FX-ADO") == "fx"


def test_an_ado_registry_in_capitals_keys_its_own_lowercase_ref_to_the_project_name():
    assert _checkout_key(_ado(repo="FX-Ado", ado_project="DeskLine"), "deskline/fx-ado") == "fx"


def test_an_ado_repository_of_another_project_or_name_is_still_foreign():
    ado = _ado()

    assert _checkout_key(ado, "OtherProject/fx-ado") == "fx--OtherProject--fx-ado"
    assert _checkout_key(ado, "Deskline/other-repo") == "fx--Deskline--other-repo"


# ── 3. project add, again ────────────────────────────────────────────────────────────────────────

def _add(**params):
    return asyncio.run(actions.perform("project_add", by=ADMIN, project="acme",
                                       repo_path="https://github.com/acme/api.git", **params))


def _registry(tmp_path, monkeypatch):
    registry = tmp_path / "registry.yaml"
    monkeypatch.setenv("BEEVERFORGE_REGISTRY", str(registry))
    return registry


def test_adding_again_with_the_repository_typed_otherwise_changes_nothing(tmp_path, monkeypatch):
    from beeverforge.registry import ProjectRegistry

    registry = _registry(tmp_path, monkeypatch)
    assert _add().data["changed"] is True
    before = registry.read_bytes()

    again = _add(repo="Acme/api")

    assert again.ok and again.data["changed"] is False, again
    assert registry.read_bytes() == before, "adding again wrote over what was registered"
    assert ProjectRegistry().get("acme").tracker.repo == "acme/api"


def test_a_registry_in_capitals_is_not_different_from_its_lowercase_address(tmp_path,
                                                                            monkeypatch):
    from beeverforge.registry import ProjectRegistry

    registry = _registry(tmp_path, monkeypatch)
    assert _add(repo="Acme/API").data["changed"] is True
    before = registry.read_bytes()

    again = _add()

    assert again.ok and again.data["changed"] is False, again
    assert registry.read_bytes() == before
    assert ProjectRegistry().get("acme").tracker.repo == "Acme/API"


def test_adding_again_with_another_repository_is_still_refused(tmp_path, monkeypatch):
    registry = _registry(tmp_path, monkeypatch)
    assert _add().data["changed"] is True
    before = registry.read_bytes()

    elsewhere = _add(repo="acme/web")

    assert elsewhere.code == actions.CONFLICT and "tracker" in elsewhere.data["differs"], (
        elsewhere)
    assert registry.read_bytes() == before


# ── 4. the product module's own mount ────────────────────────────────────────────────────────────

def _view(tmp_path, *, own: str, mounted: dict[str, str], missing: dict[str, str]):
    for name in mounted.values():
        (tmp_path / name).mkdir(exist_ok=True)
    return SimpleNamespace(_workspace=lambda: None, _combined=str(tmp_path), _docs_at=".",
                           _left_out={}, _own_source=own,
                           _mounted_sources={r: str(tmp_path / n) for r, n in mounted.items()},
                           _missing_sources=missing)


def test_a_source_spelling_the_projects_own_repository_otherwise_is_its_own_mount(tmp_path):
    mounted = ProductModule.mounts(_view(tmp_path, own="acme/api",
                                         mounted={"acme/web": "web", "Acme/API": "api"},
                                         missing={"Other/Own": "why"}))

    assert [(m.repo, m.own) for m in mounted] == [
        ("Acme/API", True), ("acme/web", False), ("Other/Own", False)], mounted


def test_a_registry_in_capitals_labels_its_lowercase_missing_source_its_own(tmp_path):
    mounted = ProductModule.mounts(_view(tmp_path, own="Acme/API",
                                         mounted={"acme/web": "web"},
                                         missing={"acme/api": "why"}))

    assert [(m.repo, m.own) for m in mounted] == [("acme/api", True), ("acme/web", False)], (
        mounted)


def test_a_lowercase_registry_labels_its_missing_source_in_capitals_its_own(tmp_path):
    """The twin of the test above: the capitals are on the missing source's side, so a fold of
    the registry's side alone still reads `Acme/API` as another repository (#401's review)."""
    mounted = ProductModule.mounts(_view(tmp_path, own="acme/api",
                                         mounted={"acme/web": "web"},
                                         missing={"Acme/API": "why"}))

    assert [(m.repo, m.own) for m in mounted] == [("Acme/API", True), ("acme/web", False)], (
        mounted)


def test_a_registry_in_capitals_labels_its_lowercase_mounted_source_its_own(tmp_path):
    mounted = ProductModule.mounts(_view(tmp_path, own="Acme/API",
                                         mounted={"acme/web": "web", "acme/api": "api"},
                                         missing={"acme/api-docs": "why"}))

    assert [(m.repo, m.own) for m in mounted] == [
        ("acme/api", True), ("acme/web", False), ("acme/api-docs", False)], mounted
