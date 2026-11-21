"""#527: `project_update` changes where a registered project's repository, tracker or CI is, in one
write, and refuses what `project_add` refuses for the same input.

THE ONLY WAYS TO MOVE A REPOSITORY WERE `project_remove` AND `project_add` — which dropped the
model, the language, the preview policy and the attached board with the entry — or the YAML inside
the worker. The registry is driven for real (a file under `tmp_path`); only the write counter and
the lock's two threads are instrumented, so no case waits on time.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import threading

import pytest
from typer.testing import CliRunner

from beeverforge import actions

ADMIN = actions.Actor(id="rob", via="panel", admin=True)
HELD_URL = "https://github.com/acme/web.git"


def _update(**params):
    return asyncio.run(actions.perform("project_update", by=ADMIN, project="acme", **params))


def _add(name="acme", **params):
    return asyncio.run(actions.perform("project_add", by=ADMIN, project=name, **params))


def _entry(name="acme") -> dict:
    from beeverforge.registry import ProjectRegistry

    return ProjectRegistry().get(name).model_dump(mode="json")


@pytest.fixture
def registry(tmp_path, monkeypatch):
    """A registry holding `acme` on GitHub with everything an update must not touch set."""
    from beeverforge.contracts.project import PreviewPolicy, Project, ProviderRef
    from beeverforge.registry import ProjectRegistry

    path = tmp_path / "registry.yaml"
    monkeypatch.setenv("BEEVERFORGE_REGISTRY", str(path))
    for var in ("GITHUB_TOKEN", "BEEVERFORGE_BOT_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    ProjectRegistry().add(Project(
        name="acme", repo_path=HELD_URL, model="a-model", language="pt-BR", enabled=False,
        preview=PreviewPolicy(required=True),
        tracker=ProviderRef(kind="github", repo="acme/web",
                            options={"board_owner": "acme", "board_number": "7"}),
        ci=ProviderRef(kind="github_actions", repo="acme/web", options={})))
    return path


def _unchanged(before: dict, *, but: set[str]) -> None:
    now = _entry()
    assert {k: v for k, v in now.items() if k not in but} == {
        k: v for k, v in before.items() if k not in but}


# ── in the catalogue ────────────────────────────────────────────────────────────────────────────

def test_the_row_is_in_the_catalogue_and_documented():
    from pathlib import Path

    assert "project_update" in actions.names()
    from beeverforge.actions import catalog

    spec = catalog.CATALOG["project_update"]
    assert spec.installation and spec.required == ("project",)
    assert "model" not in spec.parameters and "language" not in spec.parameters
    text = (Path(__file__).resolve().parents[1] / "docs/reference/the-front-end-api.md").read_text()
    assert "| `project_update` | `project`, [`repo_path`]" in text


# ── what it changes, and only that ──────────────────────────────────────────────────────────────

def test_a_moved_repository_is_written_with_everything_else_unchanged(registry):
    before = _entry()

    out = _update(repo_path="https://github.com/acme/web2.git")

    assert out.ok and out.data["changed"] is True, out
    assert "repo_path" in out.data["fields"] and "tracker" in out.data["fields"]
    now = _entry()
    assert now["repo_path"] == "https://github.com/acme/web2.git"
    assert now["tracker"]["repo"] == "acme/web2"
    # the board attached is the project's, not the address's
    assert now["tracker"]["options"] == {"board_owner": "acme", "board_number": "7"}
    for kept in ("model", "language", "preview", "enabled", "ci"):
        assert now[kept] == before[kept], kept
    assert now["enabled"] is False


def test_a_different_board_changes_the_tracker_alone(registry):
    before = _entry()

    out = _update(board_owner="acme", board_number="9")

    assert out.ok and out.data["fields"] == ["tracker"], out
    assert _entry()["tracker"]["options"]["board_number"] == "9"
    assert _entry()["tracker"]["repo"] == "acme/web"
    _unchanged(before, but={"tracker"})


def test_a_different_provider_changes_the_axes_of_its_kind_and_no_other(registry, tmp_path):
    from beeverforge.contracts.project import Project, ProviderRef
    from beeverforge.registry import ProjectRegistry

    ProjectRegistry().add(Project(
        name="mounted", repo_path=str(tmp_path / "mounted"), model="a-model", language="pt-BR",
        tracker=ProviderRef(kind="github", repo="acme/mounted", options={})))
    before = _entry("mounted")

    out = asyncio.run(actions.perform("project_update", by=ADMIN, project="mounted",
                                      provider="local"))

    assert out.ok and out.data["fields"] == ["tracker", "forge", "ci"], out
    now = _entry("mounted")
    assert now["tracker"]["kind"] == "local"
    assert (now["model"], now["language"], now["repo_path"]) == (
        before["model"], before["language"], before["repo_path"])


def test_a_different_ci_changes_the_ci_alone(registry):
    before = _entry()

    out = _update(ci="none")

    assert out.ok and out.data["fields"] == ["ci"], out
    assert _entry()["ci"]["kind"] == "none"
    _unchanged(before, but={"ci"})


# ── what it refuses, and writes nothing ─────────────────────────────────────────────────────────

def test_a_call_with_nothing_to_change_is_refused(registry):
    before = registry.read_bytes()

    out = _update()

    assert out.code == actions.INVALID, out
    assert registry.read_bytes() == before


@pytest.mark.parametrize("field", ["model", "language", "nonsense"])
def test_a_field_the_action_does_not_take_is_refused_naming_it(registry, field):
    before = registry.read_bytes()

    out = _update(repo_path="https://github.com/acme/web2.git", **{field: "x"})

    assert out.code == actions.INVALID and field in out.message, out
    assert registry.read_bytes() == before


#: What `project_add` refuses, as the parameters that provoke it. The same input is asked of both,
#: so the two cannot drift: `second` is a project already registered in another organisation.
REFUSALS = {
    "a foreign host": {"repo_path": "https://gitlab.com/o/acme.git"},
    "missing coordinates": {"repo_path": "https://dev.azure.com/acme-org/Payments"},
    "a second organisation": {"repo_path": "https://github.com/other-org/web.git"},
}


@pytest.mark.parametrize("case", sorted(REFUSALS))
def test_every_refusal_project_add_makes_is_made_and_the_entry_is_unchanged(registry, case):
    params = REFUSALS[case]
    asked_of_add = _add(name="fresh", **params)
    before = registry.read_bytes()

    out = _update(**params)

    assert not asked_of_add.ok, f"project_add accepted {case}"
    assert not out.ok, f"project_update accepted {case}: {out}"
    assert out.code == asked_of_add.code, (out.code, asked_of_add.code)
    assert registry.read_bytes() == before


@pytest.mark.parametrize("token_env", ["ACME_TOKEN", "bad name", "-x", "GITHUB_TOKEN"])
def test_a_token_env_is_judged_as_project_add_judges_it(registry, token_env):
    """`project_add` has no refusal of its own for this name today, so the two are held to the same
    answer — whatever it is — rather than to a refusal that exists in neither."""
    params = {"repo_path": "https://github.com/acme/other.git", "token_env": token_env}
    asked_of_add = _add(name="fresh", **params)

    out = _update(**params)

    assert (out.ok, out.code) == (asked_of_add.ok, asked_of_add.code), (out, asked_of_add)


def test_a_slug_another_project_has_is_refused_as_project_add_refuses_it(registry):
    import yaml

    from beeverforge.registry import ProjectRegistry

    raw = yaml.safe_load(registry.read_text())
    raw["projects"]["Acme"] = {**copy.deepcopy(raw["projects"]["acme"]),
                               "repo_path": "https://github.com/acme/x"}
    registry.write_text(yaml.safe_dump(raw))
    twin = _add(name="ACME", repo_path="https://github.com/acme/y.git")
    before = registry.read_bytes()

    out = _update(repo_path="https://github.com/acme/web2.git")

    assert not twin.ok and not out.ok, (twin, out)
    assert out.code == twin.code and "short name" in out.message
    assert registry.read_bytes() == before
    assert ProjectRegistry().get("acme").repo_path == HELD_URL


def test_an_unregistered_name_is_refused_with_the_roster_and_nothing_is_written(tmp_path,
                                                                                monkeypatch):
    path = tmp_path / "registry.yaml"
    monkeypatch.setenv("BEEVERFORGE_REGISTRY", str(path))

    out = _update(repo_path="https://github.com/acme/web2.git")

    assert out.code == actions.NOT_FOUND and "It knows: none" in out.message, out
    assert not path.exists() or "acme" not in path.read_text()


def test_the_registry_refuses_an_unheld_name_itself_when_it_is_removed_after_the_ask(registry):
    """The action asks first, so the lock's own refusal is only reached by a name removed in
    between: the registry is asked directly, and holds no entry of that name afterwards."""
    from beeverforge.registry import ProjectRegistry

    before = registry.read_bytes()

    with pytest.raises(KeyError):
        ProjectRegistry().set_axes("ghost", lambda held: {"repo_path": "https://github.com/a/b"})

    assert registry.read_bytes() == before


# ── a call that matches what is held ────────────────────────────────────────────────────────────

def test_a_call_that_matches_what_is_held_answers_unchanged_and_does_not_write(registry,
                                                                                monkeypatch):
    from beeverforge.registry import ProjectRegistry

    writes = []
    real = ProjectRegistry._save_raw
    monkeypatch.setattr(ProjectRegistry, "_save_raw",
                        lambda self, projects: (writes.append(1), real(self, projects))[1])
    before = registry.read_bytes()

    out = _update(repo_path=HELD_URL, board_owner="acme", board_number="7")

    assert out.ok and out.data["changed"] is False and out.data["fields"] == [], out
    assert writes == [] and registry.read_bytes() == before


# ── the answer and the audit record ─────────────────────────────────────────────────────────────

def test_the_answer_names_the_fields_and_the_audit_record_is_one_with_no_credential(registry,
                                                                                    caplog):
    with caplog.at_level(logging.INFO):
        out = _update(board_owner="acme", board_number="9", token_env="ACME_TOKEN")

    assert out.ok and out.data["fields"] == ["tracker"], out
    lines = [r.getMessage() for r in caplog.records if "project_update" in r.getMessage()]
    assert len(lines) == 1, lines
    assert "by=" in lines[0] and "rob" in lines[0] and "ok=True" in lines[0]
    assert "board_owner" in lines[0] and "board_number" in lines[0]
    assert "ghp_" not in lines[0]


# ── two calls at once ───────────────────────────────────────────────────────────────────────────

def test_two_concurrent_updates_of_one_project_lose_neither(registry, monkeypatch):
    """Both calls read the entry under the registry's lock: the first to hold it is made to wait
    for the second to be asking, by events — never by a sleep."""
    from beeverforge.registry import ProjectRegistry

    both_asking = threading.Barrier(2)
    real = ProjectRegistry._locked

    def locked(self):
        both_asking.wait(timeout=10)
        return real(self)

    monkeypatch.setattr(ProjectRegistry, "_locked", locked)
    answers: list = []

    def run(**params):
        answers.append(_update(**params))

    threads = [threading.Thread(target=run, kwargs={"board_number": "9", "board_owner": "acme"}),
               threading.Thread(target=run, kwargs={"ci": "none"})]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    assert [a.ok for a in answers] == [True, True], answers
    now = _entry()
    assert now["tracker"]["options"]["board_number"] == "9" and now["ci"]["kind"] == "none"


# ── the neighbours that point at it ─────────────────────────────────────────────────────────────

def test_project_adds_conflict_points_at_project_update(registry):
    out = _add(repo_path="https://github.com/acme/elsewhere.git")

    assert out.code == actions.CONFLICT and "project_update" in out.message, out


def test_the_command_updates_the_project(registry):
    from beeverforge.cli import app

    out = CliRunner().invoke(app, ["project", "update", "acme", "--repo-path",
                                   "https://github.com/acme/web2.git"])

    assert out.exit_code == 0, out.output
    assert "repo_path" in out.output
    assert _entry()["repo_path"] == "https://github.com/acme/web2.git"


def test_the_command_refuses_as_the_row_does(registry):
    from beeverforge.cli import app

    out = CliRunner().invoke(app, ["project", "update", "acme"])

    assert out.exit_code != 0
    assert _entry()["repo_path"] == HELD_URL


def test_the_command_is_documented():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    assert "beeverforge project update" in (root / "docs/reference/cli.md").read_text()
