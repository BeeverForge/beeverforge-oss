"""The box proof builds its box with the same knobs as the job's box (#191).

WHAT WAS WRONG: `box_prove.box_probes` built the proof's box from its own copy of the knob list
`factory.build_runner` builds the job's box from, and the copy had fallen a knob behind: the image's
pull credential (#742) never reached the proof. A proof of an image in a private registry pulled
with no login while the job's box pulled with one. #191's own case (a minted credential for
`setup:`) is not this: no local box, the job's included, is handed one; that is said on #191.

WHAT IS HELD HERE: the real `box_probes`, over a stub box, hands `build_sandbox` exactly
`factory.box_knobs(project)` (the registry's knobs, `box.env`, the pull credential, the toolbox
volume and the operator guidelines), and so does the real `build_runner` for the job's box, so the
next knob added for the job reaches the proof with it. Both are read at the box's own constructor,
by running each path, never by reading its source. A private pull the registry refuses ends the
proof's box start with the image and the credential's reference, never its secret.
"""

from __future__ import annotations

from types import SimpleNamespace

from beeverforge import box_prove, factory
from beeverforge.adapters.sandbox import registry as sandboxes
from beeverforge.adapters.sandbox.pull import PullCredential


def _project():
    from beeverforge.contracts.project import BoxConfig, Project

    return Project(name="someone", repo_path="/tmp/someone",
                   box=BoxConfig(network="acme-net", cache_volume="acme-cache", cpus="2",
                                 memory="4g", env=["ACME_SCANNER_TOKEN"],
                                 pull_credential="env:ACME_REGISTRY", pull_username="someone"))


def _built_by_the_proof(tmp_path, monkeypatch) -> dict:
    built: dict = {}

    class _Box:
        def prepare(self, **_kw):
            return SimpleNamespace(path=str(tmp_path))

        def cleanup(self, **_kw):
            pass

    def build(kind, **kwargs):
        built.update(kwargs)
        return _Box()

    monkeypatch.setattr(box_prove, "PROOF_DIR", tmp_path / "proofs")
    monkeypatch.setattr(sandboxes, "installed_box_traits",
                        lambda _kind: SimpleNamespace(honours_image=True))
    monkeypatch.setattr(sandboxes, "build_sandbox", build)
    manifest = SimpleNamespace(base_branch="main", setup=[], validation={})
    with box_prove.box_probes(_project(), "img", repo_path=tmp_path, manifest=manifest,
                              key="someone", sandbox="container"):
        pass
    return built


def test_the_proof_box_is_built_with_the_jobs_knobs(tmp_path, monkeypatch):
    monkeypatch.setenv("BEEVERFORGE_TOOLBOX_VOLUME", "beeverforge-toolbox")

    built = _built_by_the_proof(tmp_path, monkeypatch)
    knobs = {k: v for k, v in built.items() if k not in ("image", "project")}

    assert knobs == factory.box_knobs(_project())


def test_the_proof_box_pulls_with_the_jobs_pull_credential(tmp_path, monkeypatch):
    built = _built_by_the_proof(tmp_path, monkeypatch)

    assert built.get("pull_credential") == PullCredential(reference="env:ACME_REGISTRY",
                                                          username="someone")


def _built_by_the_job(monkeypatch) -> dict:
    """The keywords `build_runner` builds the job's container box with, read at the box's own
    constructor: the job's real path, run, never its source read."""
    built: dict = {}
    traits, real = sandboxes.BOXES["container"]

    def spy(**kw):
        built.update(kw)
        return real(**kw)

    monkeypatch.setitem(sandboxes.BOXES, "container", (traits, spy))
    try:
        factory.build_runner(_project(), "#1", sandbox="container", image="img", review=False)
    except Exception:  # noqa: BLE001 — wiring after the box may want credentials; the box is built
        pass
    assert built, "build_runner built no container box"
    return built


def test_the_job_box_is_built_with_the_same_knobs(monkeypatch):
    monkeypatch.setenv("BEEVERFORGE_TOOLBOX_VOLUME", "beeverforge-toolbox")

    built = _built_by_the_job(monkeypatch)
    knobs = {k: v for k, v in built.items() if k not in ("image", "project", "root")}

    assert knobs == factory.box_knobs(_project())


def test_a_proof_whose_private_pull_fails_says_so_by_reference_never_by_secret(
        tmp_path, monkeypatch):
    """The proof's real container box, with the pull credential the job's box gets, pulls before
    anything else is made (`ContainerSandbox._pull_if_absent`). A pull the registry refuses ends
    the proof's box start with the image and the credential's REFERENCE, never the secret the
    reference resolves to. The daemon is asked nothing: the image check says absent, and the pull
    says refused."""
    import beeverforge.adapters.sandbox.container as container
    import beeverforge.adapters.sandbox.pull as pulling

    monkeypatch.setenv("ACME_REGISTRY", "s3cr3t-registry-value")
    monkeypatch.setattr(container, "_host", lambda argv, **_k: (1, "no such image"))
    monkeypatch.setattr(pulling, "pull", lambda image, credential: (False, "unauthorized"))
    monkeypatch.setattr(box_prove, "PROOF_DIR", tmp_path / "proofs")
    manifest = SimpleNamespace(base_branch="main", setup=[], validation={})

    with box_prove.box_probes(_project(), "registry.example/acme/app:1", repo_path=tmp_path,
                              manifest=manifest, key="someone", sandbox="container") as probes:
        said = probes.box_start_error()

    assert "registry.example/acme/app:1" in said and "env:ACME_REGISTRY" in said, said
    assert "unauthorized" in said, said
    assert "s3cr3t-registry-value" not in said, "the pull credential's secret reached the proof"
