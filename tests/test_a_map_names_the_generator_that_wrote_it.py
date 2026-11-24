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
    assert is_stale(_with_version(build_bundle(repo), "0.1.3"), repo) is True


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


@pytest.mark.parametrize("version", [beeverforge.__version__, "0.2.0", "0.2.1", "1.0", "10.0.0"])
def test_the_same_or_a_newer_generator_is_not_stale(repo, version):
    assert is_stale(_with_version(build_bundle(repo), version), repo) is False


def test_an_unparseable_version_is_stale(repo):
    assert is_stale(_with_version(build_bundle(repo), "not-a-version"), repo) is True


def test_a_refresh_rebuilds_a_map_from_an_older_generator_over_unchanged_sources(repo, tmp_path):
    dest = tmp_path / "out"
    write_bundle_dir(_with_version(build_bundle(repo), "0.1.3"), dest, force=True)
    assert write_bundle_dir(build_bundle(repo), dest) == dest
    read = read_bundle_dir(dest)
    assert read is not None
    assert read.manifest.generator_version == beeverforge.__version__


def test_a_refresh_over_a_current_map_still_writes_nothing(repo, tmp_path):
    dest = tmp_path / "out"
    write_bundle_dir(build_bundle(repo), dest)
    assert write_bundle_dir(build_bundle(repo), dest) is None
