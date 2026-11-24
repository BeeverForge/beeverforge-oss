"""#680 — a knowledge map records which generator wrote it, and an older one is rebuilt.

`bundle_version` is the schema version and stays "1", so a map from an older generator looked
current to a newer deployment, which never rebuilt it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import beeverforge
from beeverforge.knowledge.bundle import build_bundle, read_bundle_dir, write_bundle_dir
from beeverforge.knowledge.staleness import is_stale, is_trustworthy


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text('"""A package."""\n\ndef f():\n    return 1\n')
    return tmp_path


def _release(version: str) -> tuple[int, int, int]:
    major, minor, patch = (int(piece) for piece in version.split(".")[:3])
    return major, minor, patch


def _dotted(release: tuple[int, int, int]) -> str:
    return ".".join(str(piece) for piece in release)


def _older(release: tuple[int, int, int]) -> str | None:
    """A release below this one, or None when it is 0.0.0 and nothing is."""
    major, minor, patch = release
    if patch:
        return _dotted((major, minor, patch - 1))
    if minor:
        return _dotted((major, minor - 1, 0))
    if major:
        return _dotted((major - 1, 0, 0))
    return None


def _with_version(bundle, version: str):
    manifest = bundle.manifest.model_copy(update={"generator_version": version})
    return bundle.model_copy(update={"manifest": manifest})


def test_a_new_bundle_records_the_generator_version(repo):
    assert build_bundle(repo).manifest.generator_version == beeverforge.__version__


def test_the_version_survives_a_write_and_a_read(repo, tmp_path):
    dest = tmp_path / "out"
    write_bundle_dir(build_bundle(repo), dest)
    read = read_bundle_dir(dest)
    assert read is not None
    assert read.manifest.generator_version == beeverforge.__version__


def test_a_fresh_bundle_is_not_stale(repo):
    bundle = build_bundle(repo)
    assert is_stale(bundle, repo) is False
    assert is_trustworthy(bundle, repo) is True


def test_a_bundle_from_an_older_generator_is_stale(repo):
    older = _older(_release(beeverforge.__version__))
    assert older is not None
    assert is_stale(_with_version(build_bundle(repo), older), repo) is True


def test_a_bundle_with_no_recorded_version_is_stale_and_still_read(repo, tmp_path):
    dest = tmp_path / "out"
    write_bundle_dir(build_bundle(repo), dest)
    manifest = dest / "manifest.yaml"
    manifest.write_text("".join(
        line for line in manifest.read_text().splitlines(keepends=True)
        if not line.startswith("generator_version")))
    read = read_bundle_dir(dest)
    assert read is not None
    assert read.manifest.generator_version == ""
    assert is_stale(read, repo) is True


@pytest.fixture(params=["as-built", "0.3.0.dev0", "1.0.0"])
def running(request, monkeypatch) -> str:
    """The running generator's version: the real one, then two a bump could land on."""
    if request.param != "as-built":
        monkeypatch.setattr(beeverforge, "__version__", request.param)
    return beeverforge.__version__


def test_the_same_or_a_newer_generator_is_not_stale(repo, running):
    major, minor, patch = _release(running)
    for version in (running, _dotted((major, minor, patch + 1)),
                    _dotted((major, minor + 1, 0)), _dotted((major + 1, 0, 0))):
        assert is_stale(_with_version(build_bundle(repo), version), repo) is False, version


def test_an_older_generator_is_stale_whatever_the_running_one(repo, running):
    older = _older(_release(running))
    if older is None:
        pytest.skip("no release is older than 0.0.0")
    assert is_stale(_with_version(build_bundle(repo), older), repo) is True


def test_an_unparseable_version_is_stale(repo):
    assert is_stale(_with_version(build_bundle(repo), "not-a-version"), repo) is True


def test_a_refresh_rebuilds_a_map_from_an_older_generator_over_unchanged_sources(repo, tmp_path):
    dest = tmp_path / "out"
    older = _older(_release(beeverforge.__version__))
    assert older is not None
    write_bundle_dir(_with_version(build_bundle(repo), older), dest, force=True)
    assert write_bundle_dir(build_bundle(repo), dest) == dest
    read = read_bundle_dir(dest)
    assert read is not None
    assert read.manifest.generator_version == beeverforge.__version__


def test_a_refresh_over_a_current_map_still_writes_nothing(repo, tmp_path):
    dest = tmp_path / "out"
    write_bundle_dir(build_bundle(repo), dest)
    assert write_bundle_dir(build_bundle(repo), dest) is None
