"""#569: a project's box image is set through the catalogue, like its model and language.

`box.image` was a line of YAML inside the worker image. `project_set_box_image` writes it the way
`project_set_preview` writes its field, refuses what `box prove` would refuse before it starts, and
marks the project's recorded proof stale so the next job or `box prove` proves the new image.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging

import pytest
from typer.testing import CliRunner

from beeverforge import actions, box_prove

ADMIN = actions.Actor(id="rob", via="panel", admin=True)


@pytest.fixture
def held(tmp_path, monkeypatch):
    from beeverforge.contracts.project import Project
    from beeverforge.registry import ProjectRegistry

    path = tmp_path / "registry.yaml"
    monkeypatch.setenv("BEEVERFORGE_REGISTRY", str(path))
    monkeypatch.setenv("BEEVERFORGE_PROOFS", str(tmp_path / "proofs"))
    monkeypatch.setenv("BEEVERFORGE_SANDBOX", "container")
    ProjectRegistry().add(Project(name="acme", repo_path="https://github.com/o/r.git"))
    return path


def _set(image, by=ADMIN, project="acme"):
    return asyncio.run(actions.perform("project_set_box_image", by=by, project=project,
                                       image=image))


def _image():
    from beeverforge.registry import ProjectRegistry

    box = ProjectRegistry().get("acme").box
    return box.image if box else None


def _proven():
    box_prove.save(box_prove.Proof(project="acme", image="old:1", ok=True, digest="sha256:a"))


def test_set_writes_the_image_and_answers_the_row_and_its_value(held):
    out = _set("ghcr.io/acme/box:1.2")

    assert out.ok, out
    assert _image() == "ghcr.io/acme/box:1.2"
    assert out.data["project"] == "acme" and out.data["image"] == "ghcr.io/acme/box:1.2"


def test_set_again_is_idempotent_and_changes_nothing(held):
    _set("acme/box:1")
    before = held.read_bytes()
    _proven()

    out = _set("acme/box:1")

    assert out.ok and held.read_bytes() == before
    assert box_prove.load("acme").ok is True and not box_prove.load("acme").stale


def test_an_empty_image_clears_it_back_to_the_default(held):
    _set("acme/box:1")

    out = _set("  ")

    assert out.ok, out
    assert _image() is None
    assert out.data["image"] == ""


@pytest.mark.parametrize("bad", ["has space:1", "-rm:1", "Bad//path", "img:", "a@sha256:xyz"])
def test_an_image_that_does_not_parse_is_refused_and_nothing_is_changed(held, bad):
    _set("acme/box:1")
    before = held.read_bytes()

    out = _set(bad)

    assert out.code == actions.INVALID and "Nothing was changed" in out.message, out
    assert held.read_bytes() == before


def test_an_image_the_sandbox_cannot_honour_is_refused(held, monkeypatch):
    monkeypatch.setenv("BEEVERFORGE_SANDBOX", "worktree")
    before = held.read_bytes()

    out = _set("acme/box:1")

    assert out.code == actions.INVALID and "Nothing was changed" in out.message, out
    assert "cannot honour" in out.message
    assert held.read_bytes() == before


def test_an_unknown_project_is_refused_by_name(held):
    out = _set("acme/box:1", project="nope")

    assert out.code == actions.NOT_FOUND, out


def test_changing_the_image_marks_the_proof_stale_and_a_new_proof_clears_it(held):
    _proven()

    assert _set("acme/box:2").ok

    proof = box_prove.load("acme")
    assert proof.stale and "acme/box:2" in proof.stale
    box_prove.save(box_prove.Proof(project="acme", image="acme/box:2", ok=True))
    assert not box_prove.load("acme").stale


def test_a_stale_proof_holds_pickup_with_a_hold_the_worker_may_clear(held):
    _proven()
    _set("acme/box:2")
    project = __import__("beeverforge.registry", fromlist=["x"]).ProjectRegistry().get("acme")

    reason = box_prove.gate_reason(project, sandbox="container")

    assert isinstance(reason, box_prove.Expired), reason
    assert "acme/box:2" in reason and "box prove acme" in reason


def test_a_foreign_repository_proof_goes_stale_too(held, tmp_path):
    box_prove.save(box_prove.Proof(project="acme--o--api", image="old:1", ok=True))

    _set("acme/box:2")

    assert box_prove.load("acme--o--api").stale


def test_a_project_never_proven_has_nothing_to_mark(held):
    assert _set("acme/box:2").ok
    assert box_prove.load("acme") is None


@pytest.mark.parametrize("by", [
    actions.Actor(id="bia", via="panel", admin=True, scopes=frozenset({actions.PRODUCT})),
    actions.Actor(id="eve", via="slack", admin=False),
])
def test_a_credential_that_is_not_the_administrators_is_refused(by, held):
    before = held.read_bytes()

    assert _set("acme/box:1", by=by).code == actions.DENIED
    assert held.read_bytes() == before


def test_it_is_guarded_like_the_other_project_set_rows():
    from beeverforge.actions import catalog

    spec, like = catalog.CATALOG["project_set_box_image"], catalog.CATALOG["project_set_model"]

    assert (spec.installation, spec.needs_admin, spec.needs_code, spec.scope) == (
        like.installation, like.needs_admin, like.needs_code, like.scope)
    assert spec.required == ("project",) and spec.optional == ("image",) and actions.INVALID in spec.refuses


def test_it_leaves_one_audit_record_allowed_and_one_refused(held, caplog):
    with caplog.at_level(logging.INFO):
        _set("acme/box:1")
        _set("has space")

    lines = [r.getMessage() for r in caplog.records if "project_set_box_image" in r.getMessage()]
    assert len(lines) == 2, lines


def test_the_command_runs_the_row(held):
    from beeverforge import cli

    out = CliRunner().invoke(cli.app, ["project", "set-box-image", "acme", "acme/box:3"])

    assert out.exit_code == 0, out.output
    assert _image() == "acme/box:3" and "acme/box:3" in out.output
    cleared = CliRunner().invoke(cli.app, ["project", "set-box-image", "acme", ""])
    assert cleared.exit_code == 0 and _image() is None


def test_the_command_says_a_refusal_and_exits_non_zero(held):
    from beeverforge import cli

    out = CliRunner().invoke(cli.app, ["project", "set-box-image", "acme", "has space"])

    assert out.exit_code != 0 and "Nothing was changed" in out.output


def test_the_cli_verb_writes_nothing_itself(held, monkeypatch):
    from beeverforge import cli
    from beeverforge.actions import catalog

    seen = []

    async def recorder(by=None, **params):
        seen.append(params)
        return actions.done("recorded", project="acme", image=params["image"])

    monkeypatch.setattr(catalog, "CATALOG", {**catalog.CATALOG, "project_set_box_image":
                        dataclasses.replace(catalog.CATALOG["project_set_box_image"],
                                            run=recorder)})
    before = held.read_bytes()

    out = CliRunner().invoke(cli.app, ["project", "set-box-image", "acme", "x:1"])

    assert out.exit_code == 0 and len(seen) == 1 and held.read_bytes() == before


def test_the_panel_facts_show_the_current_image_and_then_none_after_a_clear(held, monkeypatch):
    from beeverforge import loader
    from beeverforge.api.app import factory

    def no_checkout(project):
        raise ValueError("the manifest is not read here")

    monkeypatch.setattr(loader, "load_manifest", no_checkout)

    _set("acme/box:9")
    assert factory("acme")["box_image"] == "acme/box:9"

    _set("")
    assert factory("acme")["box_image"] == ""
