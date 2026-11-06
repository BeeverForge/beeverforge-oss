"""A harness version bump reaches a deployment that already has a toolbox (#246).

WHAT WAS WRONG: the toolbox stamp recorded the harness NAMES and the variant, and `is_populated`
compared only those, so a worker image rebuilt with a new `HARNESS_CLAUDE` found the volume
"populated" and kept the old copy. Measured on a v0.6.0 deployment: the boxes ran `claude` 2.1.219,
current models refused it, and a rebuild could not fix that. Only a hand install into the volume
did, and after it the stamp was byte-identical, so neither `box prove` nor a reader could tell
which version the boxes ran.

WHAT IS HELD HERE: the stamp records the version of every package the toolbox copied, read from
each package's own `package.json`. A boot whose baked versions differ from the live stamp's copies
again; equal versions do not; a stamp written before versions were recorded is copied once.
A bump that fails midway leaves the old toolbox working, and a box that has the old toolbox open
keeps what it opened. `box prove` prints the versions.
"""

from __future__ import annotations

import json
import shutil

import pytest

from beeverforge.box_prove import Probes, prove
from beeverforge.runtime import toolbox

CLAUDE = "@anthropic-ai/claude-code"


def _install(root, name: str, version: str) -> None:
    """A package as `npm install -g --prefix <root>/pkg` leaves it."""
    pkg = root / toolbox.PACKAGES / name
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "package.json").write_text(json.dumps({"name": name, "version": version}))


def _baked(tmp_path, claude: str):
    """The worker image's toolbox, with `claude` at `claude` and `opencode` unscoped beside it."""
    src = tmp_path / "src"
    src.mkdir(parents=True)
    (src / "claude").symlink_to(f"/opt/beeverforge-toolbox/{toolbox.PACKAGES}/{CLAUDE}/bin/claude")
    (src / "opencode").write_text("#!/bin/sh\nexec true opencode\n")
    _install(src, CLAUDE, claude)
    _install(src, "opencode-linux-x64-baseline", "1.18.13")
    return src


def _live_version(live) -> str:
    return json.loads((live / toolbox.PACKAGES / CLAUDE / "package.json").read_text())["version"]


def test_the_stamp_records_each_package_version(tmp_path):
    stamp = toolbox.populate(source=_baked(tmp_path, "2.1.309"), live=tmp_path / "live")

    assert stamp["packages"] == {CLAUDE: "2.1.309", "opencode-linux-x64-baseline": "1.18.13"}
    assert json.loads((tmp_path / "live" / toolbox.STAMP).read_text()) == stamp


def test_a_bumped_image_copies_over_the_old_toolbox(tmp_path):
    live = tmp_path / "live"
    toolbox.populate(source=_baked(tmp_path / "old", "2.1.219"), live=live)
    assert _live_version(live) == "2.1.219"

    stamp = toolbox.populate(source=_baked(tmp_path / "new", "2.1.309"), live=live)

    assert _live_version(live) == "2.1.309", "the boot kept the old harness after the bump"
    assert stamp["packages"][CLAUDE] == "2.1.309"


def test_the_same_versions_are_not_copied_again(tmp_path):
    src, live = _baked(tmp_path, "2.1.309"), tmp_path / "live"
    toolbox.populate(source=src, live=live)
    marker = live / "opencode"
    marker.write_text("#!/bin/sh\nexec true TOUCHED\n")

    toolbox.populate(source=src, live=live)

    assert "TOUCHED" in marker.read_text(), "it re-copied a toolbox whose versions had not moved"


def test_a_stamp_written_before_versions_were_recorded_is_copied_once(tmp_path):
    src, live = _baked(tmp_path, "2.1.309"), tmp_path / "live"
    toolbox.populate(source=src, live=live)
    stamp = json.loads((live / toolbox.STAMP).read_text())
    del stamp["packages"]
    (live / toolbox.STAMP).write_text(json.dumps(stamp))
    marker = live / "opencode"
    marker.write_text("#!/bin/sh\nexec true OLD\n")

    assert toolbox.is_populated(live, source=src) is False
    toolbox.populate(source=src, live=live)
    assert "OLD" not in marker.read_text(), "a stamp with no versions was taken as current"

    marker.write_text("#!/bin/sh\nexec true TOUCHED\n")
    toolbox.populate(source=src, live=live)
    assert "TOUCHED" in marker.read_text(), "it copied again once the versions were recorded"


def test_packages_reads_scoped_and_unscoped_and_skips_what_it_cannot_read(tmp_path):
    root = tmp_path / "tb"
    _install(root, CLAUDE, "2.1.309")
    _install(root, "opencode-linux-x64-baseline", "1.18.13")
    (root / toolbox.PACKAGES / "broken").mkdir()
    (root / toolbox.PACKAGES / "broken" / "package.json").write_text("{not json")
    (root / toolbox.PACKAGES / ".bin").mkdir()

    assert toolbox.packages(root) == {CLAUDE: "2.1.309", "opencode-linux-x64-baseline": "1.18.13"}
    assert toolbox.packages(tmp_path / "none") == {}


def _proof(stamp: dict):
    return prove("acme", "img", Probes(
        resolve_digest=lambda image: "sha256:" + "a" * 64,
        image_platform=lambda image: ("linux", "arm64", "glibc"),
        toolbox_stamp=lambda: stamp,
        contract=lambda image: {},
        run_in_box=lambda cmd: (0, ""),
        harness_reachable=lambda: (True, ""),
        setup_commands=lambda: [],
        validate_commands=lambda: {"test": "pytest -q"},
        harness_name=lambda: "claude",
    ))


def test_box_prove_prints_the_versions_the_boxes_run():
    proof = _proof({"variant": "linux-arm64-glibc", "harnesses": ["claude"],
                    "packages": {CLAUDE: "2.1.309"}})

    line = next(f.message for f in proof.findings if f.check == "toolbox")
    assert line == f"linux-arm64-glibc — claude ({CLAUDE} 2.1.309)", line


def test_box_prove_says_when_no_version_was_recorded():
    proof = _proof({"variant": "linux-arm64-glibc", "harnesses": ["claude"]})

    line = next(f.message for f in proof.findings if f.check == "toolbox")
    assert line == "linux-arm64-glibc — claude (versions not recorded)", line


def test_a_bump_that_fails_midway_leaves_the_old_harness_working(tmp_path, monkeypatch):
    live = tmp_path / "live"
    toolbox.populate(source=_baked(tmp_path / "old", "2.1.219"), live=live)
    new = _baked(tmp_path / "new", "2.1.309")

    def _die(*a, **k):
        raise OSError("No space left on device")

    monkeypatch.setattr(shutil, "copytree", _die)
    with pytest.raises(OSError):
        toolbox.populate(source=new, live=live)

    assert _live_version(live) == "2.1.219", "a failed bump left the boxes with no harness"
    assert toolbox.read_stamp(live)["packages"][CLAUDE] == "2.1.219", (
        "the stamp claims a version the volume does not hold")
    assert toolbox.is_populated(live, source=new) is False, "the next boot would not try again"
    assert not list(live.glob(".toolbox-staging-*"))


def test_a_box_with_the_old_toolbox_open_keeps_what_it_opened(tmp_path):
    live = tmp_path / "live"
    toolbox.populate(source=_baked(tmp_path / "old", "2.1.219"), live=live)

    with open(live / toolbox.PACKAGES / CLAUDE / "package.json") as held:  # a running harness
        toolbox.populate(source=_baked(tmp_path / "new", "2.1.309"), live=live)
        assert json.loads(held.read())["version"] == "2.1.219"

    assert _live_version(live) == "2.1.309"


def test_a_file_the_new_toolbox_dropped_is_gone_and_no_staging_is_left(tmp_path):
    live = tmp_path / "live"
    old = _baked(tmp_path / "old", "2.1.219")
    (old / "kimi").write_text("#!/bin/sh\nexec true kimi\n")
    toolbox.populate(source=old, live=live)

    stamp = toolbox.populate(source=_baked(tmp_path / "new", "2.1.309"), live=live)

    assert not (live / "kimi").exists(), "a harness the new toolbox dropped lingered"
    assert stamp["harnesses"] == ["claude", "opencode"]
    assert sorted(e.name for e in live.iterdir()) == ["claude", "opencode", "pkg", toolbox.STAMP]
