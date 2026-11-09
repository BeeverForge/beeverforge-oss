"""The core reads the platform's folder under BOTH of its names — GitHub issue #265.

OpenFactory 0.7 called the folder in a client's repository `.openfactory/`; BeeverForge calls it
`.beeverforge/`. The rename must not rewrite anybody's repository on its own, so:

    READ BOTH. A repository with only `.openfactory/` is read there — the manifest, the product's
    declaration, the profiles, a preview's shape. With both, `.beeverforge/` wins and `doctor`
    names the other as stale.

    WRITE WHERE IT WAS FOUND. A writer into an EXISTING repository writes under the folder it
    found; only a repository with neither gets `.beeverforge/`.

    GUARD BOTH. Every guard that names a path under the folder — the context-write policy, the
    preview's shape files, the floor's protected globs, the certify control, the import's
    never-landed list — holds for both names, and each test below fails when either is removed.

`.sdlc/`, the name before both, stays REFUSED: `tests/test_the_namespace_is_the_products_name.py`.

Every door is driven through the real function on a real directory; test data names `someone`.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import tarfile
from pathlib import Path

import pytest

from beeverforge import namespace
from beeverforge.actions.base import Actor

CURRENT, FORMER = namespace.DIR, ".openfactory"
BOTH = (CURRENT, FORMER)
THEIRS = "version: 1\nbase_branch: develop\nvalidate:\n  test: pytest -q\n"
BY = Actor(id="someone", via="test")
#: An import's id, the shape `importing.import_id` mints.
IMPORT = "2026-11-07-0123456789"


def _repo(root: Path, *folders: str, manifest: str = THEIRS) -> Path:
    """A repository the inference can read, carrying `project.yaml` under each folder named."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text("[project]\nname = 'acme'\nversion = '0'\n")
    (root / "requirements.txt").write_text("pytest\n")
    (root / ".git").mkdir(exist_ok=True)
    (root / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    for folder in folders:
        (root / folder).mkdir(exist_ok=True)
        (root / folder / "project.yaml").write_text(manifest)
    return root


def _snapshot(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


@pytest.fixture
def isolated_registry(tmp_path, monkeypatch):
    monkeypatch.setenv("BEEVERFORGE_REGISTRY", str(tmp_path / "registry.yaml"))


# ── 1. the one answer: which folder a repository uses ──────────────────────────────────────────

def test_the_former_name_is_openfactorys():
    assert namespace.FORMER_DIR == FORMER
    assert namespace.DIRS == BOTH


@pytest.mark.parametrize("has,uses", [
    ((), CURRENT),                    # a new repository gets the current name
    ((CURRENT,), CURRENT),
    ((FORMER,), FORMER),              # an existing one keeps the name it has
    ((CURRENT, FORMER), CURRENT),     # with both, the current one wins
])
def test_a_repository_is_read_under_the_folder_it_has(tmp_path, has, uses):
    for folder in has:
        (tmp_path / folder).mkdir()

    assert namespace.dir_in(tmp_path) == uses
    assert namespace.in_repo(tmp_path, namespace.MANIFEST) == f"{uses}/project.yaml"
    assert namespace.stale_former_dir(tmp_path) is (len(has) == 2)


def test_an_explicit_path_is_never_moved(tmp_path):
    (tmp_path / FORMER).mkdir()

    assert namespace.in_repo(tmp_path, "conf/factory.yaml") == "conf/factory.yaml"
    assert namespace.resolve(tmp_path, "conf/factory.yaml") == tmp_path / "conf/factory.yaml"


# ── 2. the readers ─────────────────────────────────────────────────────────────────────────────

def test_the_manifest_loader_reads_a_repository_that_keeps_openfactory(tmp_path):
    from beeverforge.contracts.project import Project
    from beeverforge.loader import load_manifest

    repo = _repo(tmp_path / "acme", FORMER)

    manifest = load_manifest(Project(name="acme", repo_path=str(repo)), repo_root=repo)

    assert manifest.base_branch == "develop"


def test_with_both_folders_the_current_one_is_read(tmp_path):
    repo = _repo(tmp_path / "acme", FORMER, manifest="version: 1\nbase_branch: stale\n")
    (repo / CURRENT).mkdir()
    (repo / CURRENT / "project.yaml").write_text("version: 1\nbase_branch: current\n")

    assert namespace.resolve(repo, namespace.MANIFEST).read_text().endswith("current\n")


def test_with_both_folders_and_the_file_only_in_the_former_one_it_is_refused_by_name(tmp_path):
    """#469's review: `.beeverforge/` exists (half made, mid-migration) and the manifest is still
    in `.openfactory/`. `.beeverforge/` is the one read, so the file is missing from what is read
    while it sits next door: refused by name, both folders and the remedy in the sentence, never
    a plain "no manifest" telling a person to create a file they already have."""
    import pytest

    repo = _repo(tmp_path / "acme", FORMER, manifest="version: 1\nbase_branch: main\n")
    (repo / CURRENT).mkdir()

    with pytest.raises(namespace.TwoFolders, match=r"has both `\.beeverforge/` and "
                                                    r"`\.openfactory/`.*at `\.openfactory/"
                                                    r"project\.yaml`.*Move it"):
        namespace.resolve(repo, namespace.MANIFEST, project="acme")


def test_the_two_folders_refusal_reaches_whoever_loads_the_manifest(tmp_path):
    from beeverforge.contracts.project import Project
    from beeverforge.loader import load_manifest

    repo = _repo(tmp_path / "acme", FORMER, manifest="version: 1\nbase_branch: main\n")
    (repo / CURRENT).mkdir()

    try:
        load_manifest(Project(name="acme", repo_path=str(repo)), repo_root=repo)
    except FileNotFoundError as exc:
        said = str(exc)
    else:
        raise AssertionError("a manifest only in the stale folder was read")
    assert ".openfactory/project.yaml" in said and "only `.beeverforge/` is read" in said, said


def test_a_missing_manifest_is_named_under_the_folder_the_repository_keeps(tmp_path):
    """`.openfactory/` without its `project.yaml`: the sentence names the file to create THERE —
    not one under `.beeverforge/`, which would then shadow the folder the client keeps."""
    from beeverforge.contracts.project import Project
    from beeverforge.loader import load_manifest

    repo = _repo(tmp_path / "acme")
    (repo / FORMER).mkdir()

    with pytest.raises(FileNotFoundError) as missing:
        load_manifest(Project(name="acme", repo_path=str(repo)), repo_root=repo)

    assert f"{FORMER}/project.yaml" in str(missing.value), missing.value


def test_the_product_declaration_is_read_under_openfactory(tmp_path):
    from beeverforge.preview.product import read_docs
    from beeverforge.product.loader import _read_docs_manifest

    (tmp_path / FORMER).mkdir()
    (tmp_path / FORMER / "product.yaml").write_text("product: acme\nsources: [someone/api]\n")

    docs, reason = _read_docs_manifest(tmp_path)
    assert docs is not None and docs.product == "acme", reason
    shaped, error = read_docs(str(tmp_path))
    assert shaped is not None and shaped.sources == ["someone/api"], error


def test_a_clients_profile_is_read_under_openfactory(tmp_path):
    from beeverforge.policy.profiles import available_profiles, load_profile

    (tmp_path / FORMER / "profiles").mkdir(parents=True)
    (tmp_path / FORMER / "profiles" / "someones.yaml").write_text("summary: theirs\n")

    assert "someones" in available_profiles(tmp_path)
    assert load_profile("someones", project_dir=tmp_path).name == "someones"


def test_an_imports_record_is_found_under_openfactory(tmp_path):
    from beeverforge.product.importing import newest, record_of

    record = tmp_path / FORMER / "imports" / IMPORT / "record.json"
    record.parent.mkdir(parents=True)
    record.write_text('{"landed_at": "2026-11-07", "by": "someone"}\n')

    assert record_of(tmp_path, IMPORT) == {"landed_at": "2026-11-07", "by": "someone"}
    assert newest(tmp_path)["by"] == "someone"


def test_a_preview_reads_the_manifest_under_openfactory(tmp_path):
    from beeverforge.onboarding.preview_infer import infer_preview

    repo = _repo(tmp_path / "acme", FORMER,
                 manifest="version: 1\npreview:\n  compose: [c.yml]\n  expose: {a: 1}\n")

    found = infer_preview(repo, name="acme")

    assert found.case == "declared", found.case
    assert found.compose.evidence[0].path == f"{FORMER}/project.yaml"


# ── 3. the writers: where the folder was found, and only a new repository gets the new name ────

def test_env_apply_writes_the_manifest_into_the_openfactory_it_found(tmp_path, isolated_registry):
    from beeverforge.actions.catalog import _env_apply_impl

    repo = _repo(tmp_path / "acme")
    (repo / FORMER).mkdir()

    out = asyncio.run(_env_apply_impl(project=str(repo), by=BY, yes=True, accept=["all"],
                                      answers={"base_branch": "develop"}))

    assert out.ok, out.message
    assert "base_branch: develop" in (repo / FORMER / "project.yaml").read_text()
    assert not (repo / CURRENT).exists(), "a second folder was created beside the client's"


def test_env_apply_into_a_new_repository_writes_the_current_name(tmp_path, isolated_registry):
    from beeverforge.actions.catalog import _env_apply_impl

    repo = _repo(tmp_path / "acme")

    out = asyncio.run(_env_apply_impl(project=str(repo), by=BY, yes=True, accept=["all"],
                                      answers={"base_branch": "develop"}))

    assert out.ok, out.message
    assert (repo / namespace.MANIFEST).is_file() and not (repo / FORMER).exists()


def test_env_apply_force_replaces_the_openfactory_manifest_and_nothing_else(
        tmp_path, isolated_registry):
    from beeverforge.actions.catalog import _env_apply_impl

    repo = _repo(tmp_path / "acme", FORMER)

    out = asyncio.run(_env_apply_impl(project=str(repo), by=BY, yes=True, force=True,
                                      accept=["all"], answers={"base_branch": "release"}))

    assert out.ok, out.message
    assert "base_branch: release" in (repo / FORMER / "project.yaml").read_text()
    assert (repo / FORMER / "project.yaml.bak").read_text() == THEIRS
    assert not (repo / CURRENT).exists()


def test_project_init_scaffolds_into_the_openfactory_it_found(tmp_path):
    from beeverforge.actions.catalog import _the_manifest_step
    from beeverforge.contracts.project import Project

    repo = _repo(tmp_path / "acme")
    (repo / FORMER).mkdir()

    step, _ = _the_manifest_step(Project(name="acme", repo_path=str(repo)), local=False)

    assert (repo / FORMER / "project.yaml").is_file(), step
    assert not (repo / CURRENT).exists(), step


def test_the_import_writes_its_record_under_the_folder_it_found(tmp_path):
    """The path the import's writer composes, and the one its reader looks for: the same folder
    the context repository already uses."""
    from beeverforge.policy.context_writes import import_record

    (tmp_path / FORMER).mkdir()

    assert import_record(IMPORT, namespace.dir_in(tmp_path)) == f"{FORMER}/imports/{IMPORT}/"
    assert import_record(IMPORT) == f"{CURRENT}/imports/{IMPORT}/"
    assert import_record(IMPORT, "elsewhere") == "", "only the folder's two names admit a record"


# ── the preview's draft: files, the `compose:` value and the body, all under the folder found ──

FIXTURES = Path(__file__).parent / "fixtures" / "preview" / "propose"


@pytest.mark.parametrize("scenario,name,repo,accept", [
    ("s3", "acme-api", "acme/api", True),
    ("s5", "acme-shop", "acme/shop", True),     # drafts a Dockerfile under `<folder>/preview/`
])
def test_a_drafted_preview_lands_under_the_openfactory_the_repository_keeps(
        tmp_path, monkeypatch, scenario, name, repo, accept):
    """The golden of each scenario, with every `.beeverforge/` it says moved to `.openfactory/`:
    the files' paths, what they point at, the manifest's `compose:` value and the pull request."""
    from beeverforge.contracts.project import Project
    from beeverforge.onboarding import preview_propose
    from beeverforge.util.bounded import BoundedDict

    monkeypatch.delenv("BEEVERFORGE_PREVIEW_DOMAIN", raising=False)
    monkeypatch.setattr(preview_propose, "_ASKED", BoundedDict(16))
    root = Path(os.path.realpath(tmp_path)) / "app"
    shutil.copytree(FIXTURES / scenario / "tree", root)
    (root / CURRENT).rename(root / FORMER)

    out = preview_propose.propose_preview(Project(name=name, repo_path=str(root)), repo=repo,
                                          accept=accept)

    assert out.ok, out.detail
    golden = FIXTURES / scenario / "expected"
    moved = {str(p.relative_to(golden)).replace(f"{CURRENT}/", f"{FORMER}/", 1):
             p.read_text().replace(f"{CURRENT}/", f"{FORMER}/")
             for p in sorted(golden.rglob("*")) if p.is_file() and p.name != "pull-request.md"}
    assert sorted(out.wrote) == sorted(moved)
    for rel, text in moved.items():
        assert (root / rel).read_text() == text, rel
    assert out.body == (golden / "pull-request.md").read_text().replace(f"{CURRENT}/",
                                                                         f"{FORMER}/")
    assert not (root / CURRENT).exists(), "the draft created the other folder"


def test_moving_a_draft_leaves_the_operators_own_directory_alone():
    from beeverforge.onboarding.preview_propose import in_folder

    said = "write `.beeverforge/preview.compose.yml`; your `~/.beeverforge/env` is untouched"

    assert in_folder(said, FORMER) == (
        "write `.openfactory/preview.compose.yml`; your `~/.beeverforge/env` is untouched")
    assert in_folder(said, CURRENT) == said


# ── 4. the guards hold for both names ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("folder", BOTH)
@pytest.mark.parametrize("rest", ["", "/product.yaml", "/preview.compose.yml", "/imports/x"])
def test_no_writer_lands_anything_under_either_name(folder, rest):
    from beeverforge.policy.context_writes import outside

    path = folder + rest

    assert outside([path], [folder, "requirements"]) == [path]


@pytest.mark.parametrize("folder", BOTH)
def test_an_import_lands_its_own_record_under_either_name_and_nothing_else_there(folder):
    from beeverforge.policy.context_writes import outside_an_import

    own = f"{folder}/imports/{IMPORT}/record.json"
    other = f"{folder}/imports/2026-11-07-9999999999/record.json"
    climbs = f"{folder}/imports/{IMPORT}/../../product.yaml"

    assert outside_an_import([own], ["requirements"], import_id=IMPORT) == []
    for refused in (other, climbs, f"{folder}/product.yaml"):
        assert outside_an_import([refused], ["requirements"], import_id=IMPORT) == [refused]


@pytest.mark.parametrize("folder", BOTH)
@pytest.mark.parametrize("rest", ["/preview.compose.yml", "/product.yaml",
                                  "/preview/api.Dockerfile", "/project.yaml"])
def test_an_edit_to_the_shape_under_either_name_is_an_edit_to_the_shape(folder, rest):
    from beeverforge.preview.assemble import shape_edits

    assert shape_edits([folder + rest, "src/app.py"], None) == [folder + rest]


@pytest.mark.parametrize("folder", BOTH)
def test_the_pull_request_shows_the_shape_kept_under_either_name(tmp_path, folder):
    from tests.test_a_preview_is_declared_by_the_project_and_decided_by_the_operator import (
        _shape,
    )

    shape = _shape(tmp_path, [f"{folder}/preview.compose.yml"], {
        f"{folder}/project.yaml": "preview:\n  compose: [deploy/dev.yml]\n",
        "deploy/dev.yml": "services: {web: {build: .}}\n",
        f"{folder}/preview.compose.yml": "services: {web: {build: ..}}\n",
        f"{folder}/preview/web.Dockerfile": "FROM python:3.12-slim\n",
    })

    assert [line.split()[0] for line in shape] == [
        "deploy/dev.yml", f"{folder}/preview/web.Dockerfile", f"{folder}/preview.compose.yml"]


@pytest.mark.parametrize("folder", BOTH)
def test_the_floor_protects_the_manifest_under_either_name(folder):
    from beeverforge.contracts import Manifest
    from beeverforge.policy import presets, protected

    presets.clear_floor_caches()
    path = f"{folder}/project.yaml"

    assert path in protected.violations([path, "src/app.py"], Manifest())
    assert f"{folder}/**" in protected.floor_protected_paths()


@pytest.mark.parametrize("folder", BOTH)
def test_a_drafted_dockerfile_under_either_name_is_not_read_as_the_repositorys(tmp_path, folder):
    from beeverforge.onboarding.preview_infer import infer_preview

    repo = _repo(tmp_path / "acme")
    (repo / folder / "preview").mkdir(parents=True)
    (repo / folder / "preview" / "api.Dockerfile").write_text("FROM python:3.12-slim\n")

    assert infer_preview(repo, name="acme").case == "nothing"


@pytest.mark.parametrize("folder", BOTH)
def test_the_import_never_lands_a_file_from_either_folder(tmp_path, folder):
    """The never-landed list: a folder, or an archive, that brings the platform's own directory
    under either name has it left out, and said — never a document, never a requirement."""
    from beeverforge.product import importing

    source = tmp_path / "brought"
    (source / folder).mkdir(parents=True)
    (source / folder / "product.yaml").write_text("product: someone-else\n")
    (source / "design.md").write_text("# a document\n")
    archive = tmp_path / "brought.tar"
    with tarfile.open(archive, "w") as tar:
        tar.add(source / folder / "product.yaml", arcname=f"{folder}/product.yaml")
        tar.add(source / "design.md", arcname="design.md")

    for brought in (importing.read(source), importing.read(archive)):
        assert not any(folder in p for p in brought.documents), brought.documents
        assert any(p.startswith(folder) and why == "hidden" for p, why in brought.left_out), (
            brought.left_out)


@pytest.mark.parametrize("folder", BOTH)
def test_a_document_event_never_names_a_file_under_either_folder(tmp_path, folder):
    from beeverforge.product.documents.ingest import admitted, documents_in

    (tmp_path / folder).mkdir()
    (tmp_path / folder / "product.yaml").write_text("product: acme\n")
    (tmp_path / "design.md").write_text("# a document\n")

    assert documents_in(tmp_path) == ["design.md"]
    assert admitted(tmp_path, f"{folder}/product.yaml")[0] == ""


@pytest.mark.parametrize("folder", BOTH)
def test_the_product_module_keeps_what_an_import_recorded_out_of_the_document_pass(folder):
    from beeverforge.product import module

    landed = [f"{folder}/imports/{IMPORT}/record.json", "imported/design/flow.md"]

    assert module.documents_of_an_import(landed) == ["imported/design/flow.md"]


# ── 5. doctor names the stale folder ───────────────────────────────────────────────────────────

def test_doctor_names_the_stale_openfactory_when_both_are_there(tmp_path):
    from beeverforge.doctor import diagnose
    from tests.test_doctor import _probes

    (tmp_path / CURRENT).mkdir()
    (tmp_path / FORMER).mkdir()

    report = diagnose(_probes(checkout=lambda: tmp_path))

    found = [f for f in report.findings if f.check == "folder"]
    assert len(found) == 1, [f.check for f in report.findings]
    line = found[0]
    assert f"`{FORMER}/` is stale" in line.message, line.message
    assert f"remove `{FORMER}/`" in line.note, line.note


@pytest.mark.parametrize("has", [(), (CURRENT,), (FORMER,)])
def test_doctor_says_nothing_about_the_folder_when_there_is_one_or_none(tmp_path, has):
    from beeverforge.doctor import diagnose
    from tests.test_doctor import _probes

    for folder in has:
        (tmp_path / folder).mkdir()

    report = diagnose(_probes(checkout=lambda: tmp_path))

    assert "folder" not in [f.check for f in report.findings]
