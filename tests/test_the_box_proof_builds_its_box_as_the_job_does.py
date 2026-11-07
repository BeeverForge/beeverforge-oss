"""The box proof builds its box with the same knobs as the job's box (#191).

WHAT WAS WRONG: `box_prove.box_probes` built the proof's box from its own copy of the knob list
`factory.build_runner` builds the job's box from, and the copy had fallen a knob behind: the image's
pull credential (#742) never reached the proof. A proof of an image in a private registry pulled
with no login while the job's box pulled with one. #191's own case (a minted credential for
`setup:`) is not this: no local box, the job's included, is handed one; that is said on #191.

WHAT IS HELD HERE: the real `box_probes`, over a stub box, hands `build_sandbox` exactly
`factory.box_knobs(project)` (the registry's knobs, `box.env`, the pull credential, the toolbox
volume and the operator guidelines), and `build_runner` asks the same function, so the next knob
added for the job reaches the proof with it.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

from beeverforge import box_prove, factory
from beeverforge.adapters.sandbox import registry as sandboxes
from beeverforge.adapters.sandbox.pull import PullCredential


def _project():
    return SimpleNamespace(
        name="someone",
        box=SimpleNamespace(network="acme-net", cache_volume="acme-cache", cpus="2", memory="4g",
                            env=("ACME_SCANNER_TOKEN",), pull_credential="env:ACME_REGISTRY",
                            pull_username="someone"))


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


def test_the_job_box_is_built_from_the_same_function():
    assert "box_knobs(project)" in inspect.getsource(factory.build_runner)
