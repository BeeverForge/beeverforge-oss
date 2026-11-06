"""The harness toolbox: populated once, stamped, and mounted read-only (ADR-0037 D2).

The mechanics are what this file pins. Three of them are the ones that would fail in production
and nowhere else, so each has a test that reproduces the production shape rather than the happy
path:

1. **The stamp is written LAST.** A worker killed mid-copy must leave something the next boot
   calls unpopulated, or a half-copied toolbox is mounted for ever and the failure is a harness
   that exists and does not run.
2. **The mount is by VOLUME NAME, read-only.** The compose worker is itself a container talking to
   the host's daemon, so a `-v /some/worker/path` is resolved against the HOST filesystem where
   that path does not exist — Docker silently creates an empty directory and the box gets an empty
   toolbox. A named volume is the daemon's own object and works identically either way.
3. **A missing toolbox is not an error at boot.** A development worker, or an image built without
   the toolbox stage, must still start; `sdlc box prove` is where the absence is reported, by name.
"""

from __future__ import annotations

import json

import pytest

from beeverforge.runtime import toolbox


@pytest.fixture
def baked(tmp_path):
    """What the worker image really bakes — and the SYMLINK matters.

    The real `claude` entry is a symlink into `pkg/`, pointing at the IN-BOX mount point rather
    than at the volume, so it is dangling where it is copied and resolves where it is mounted.
    The first version of this fixture used plain files only, which is why the suite was green
    while the real worker failed with `[Errno 17] File exists` copying that symlink over a
    partial tree."""
    src = tmp_path / "src"
    (src / "runtime" / "bin").mkdir(parents=True)
    (src / "runtime" / "bin" / "node").write_text("#!/bin/sh\necho node\n")
    (src / "pkg").mkdir()
    (src / "pkg" / "claude.exe").write_text("#!/bin/sh\nexec true claude\n")
    (src / "claude").symlink_to("/opt/beeverforge-toolbox/pkg/claude.exe")
    codex = src / "codex"
    codex.write_text("#!/bin/sh\nexec true codex\n")
    codex.chmod(0o755)
    return src


# ── populate ────────────────────────────────────────────────────────────────────────────────────

def test_it_copies_the_binaries_and_the_runtime(baked, tmp_path):
    live = tmp_path / "live"
    toolbox.populate(source=baked, live=live)

    # `claude` is a symlink to the mount point, so it is dangling here — `exists()` follows the
    # link and answers False. That is correct, and it is why the stamp cannot use `is_file()`.
    assert (live / "claude").is_symlink() and (live / "codex").exists()
    assert (live / "runtime" / "bin" / "node").exists(), "the Node runtime must come too — kimi " \
                                                         "and codex are Node entries"


def test_the_entries_stay_executable(baked, tmp_path):
    import os

    live = tmp_path / "live"
    toolbox.populate(source=baked, live=live)

    assert os.access(live / "codex", os.X_OK), "a copied harness that is not executable is a " \
                                               "toolbox that mounts and does nothing"


def test_it_completes_over_a_partial_copy(baked, tmp_path):
    """THE defect, found on the real worker. A crash mid-copy leaves entries behind; the next boot
    must finish the job, not fail on the first one that already exists.

    `shutil.copy2(..., follow_symlinks=False)` raises FileExistsError when the target symlink is
    already there, so the worker looped: partial copy, no stamp, retry, same error, for ever. The
    volume sat at 95 MB of a 701 MB toolbox with `codex`, `kimi` and `pkg` missing entirely."""
    live = tmp_path / "live"
    live.mkdir()
    (live / "claude").symlink_to("/somewhere/stale")     # what the crashed run left
    (live / "runtime").mkdir()

    stamp = toolbox.populate(source=baked, live=live)

    assert stamp.get("harnesses"), "populate could not complete over a partial copy"
    assert (live / "codex").exists() and (live / "pkg" / "claude.exe").exists()
    assert (live / "claude").readlink() == \
        __import__("pathlib").Path("/opt/beeverforge-toolbox/pkg/claude.exe"), "the stale link survived"


def test_the_symlink_entry_is_copied_as_a_link_not_followed(baked, tmp_path):
    """Following it would copy a 260 MB binary to the top level and leave `pkg` unreferenced —
    twice the disk and a toolbox whose entry no longer points at the package it came from."""
    live = tmp_path / "live"
    toolbox.populate(source=baked, live=live)

    assert (live / "claude").is_symlink()


def test_it_stamps_what_it_is(baked, tmp_path):
    live = tmp_path / "live"
    stamp = toolbox.populate(source=baked, live=live)

    assert stamp["harnesses"] == ["claude", "codex"], (
        "the stamp must list the symlinked entry too — it is the main harness"
    )
    assert stamp["variant"] == toolbox.variant()
    assert json.loads((live / toolbox.STAMP).read_text()) == stamp


def test_a_second_boot_does_not_copy_again(baked, tmp_path):
    """This runs on every worker start. Re-copying ~800 MB each time would add a minute to every
    restart, and a restart happens on every deploy."""
    live = tmp_path / "live"
    toolbox.populate(source=baked, live=live)
    marker = live / "codex"          # a plain file; `claude` is a symlink in the real toolbox
    marker.write_text("#!/bin/sh\nexec true TOUCHED\n")

    toolbox.populate(source=baked, live=live)

    assert "TOUCHED" in marker.read_text(), "it re-copied over an already-populated toolbox"


def test_force_copies_again(baked, tmp_path):
    """The harness version bump path."""
    live = tmp_path / "live"
    toolbox.populate(source=baked, live=live)
    (live / "codex").write_text("stale")

    toolbox.populate(source=baked, live=live, force=True)

    assert "stale" not in (live / "codex").read_text()


# ── the crash-safety story ──────────────────────────────────────────────────────────────────────

def test_a_directory_with_binaries_but_no_stamp_is_not_populated(baked, tmp_path):
    """The state a worker killed mid-copy leaves behind. It has files in it and is NOT a toolbox;
    reading the directory would call it done and mount something incomplete for ever."""
    live = tmp_path / "live"
    live.mkdir()
    (live / "codex").write_text("half a binary")

    assert toolbox.is_populated(live) is False

    toolbox.populate(source=baked, live=live)
    assert toolbox.is_populated(live) is True


def test_a_copy_that_fails_leaves_the_old_toolbox_and_its_stamp(baked, tmp_path, monkeypatch):
    """The copy is built in a staging directory beside the live toolbox (#246's review), so a copy
    that dies has written nothing into it: the old bytes and the old stamp still agree, the boxes
    keep a harness that runs, and nothing half-copied is left on the volume."""
    live = tmp_path / "live"
    toolbox.populate(source=baked, live=live)
    before = (live / toolbox.STAMP).read_text()
    (live / "codex").write_text("#!/bin/sh\nexec true OLD\n")

    import shutil as _shutil

    def _die(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(_shutil, "copy2", _die)
    with pytest.raises(OSError):
        toolbox.populate(source=baked, live=live, force=True)

    assert (live / toolbox.STAMP).read_text() == before, "the stamp changed over the old bytes"
    assert "OLD" in (live / "codex").read_text(), "the old toolbox was touched by a failed copy"
    assert not list(live.glob(".toolbox-staging-*")), "a failed copy left its staging behind"


def _renames_failing_at(monkeypatch, *calls: int) -> None:
    """`os.rename` in the toolbox raises on the given calls (counted from 1) and works otherwise."""
    real, seen = toolbox.os.rename, []

    def _rename(a, b):
        seen.append(a)
        if len(seen) in calls:
            raise OSError(f"rename {len(seen)} failed")
        return real(a, b)

    monkeypatch.setattr(toolbox.os, "rename", _rename)


#: The fixture's live toolbox has four top-level entries (`claude`, `codex`, `pkg`, `runtime`), so
#: a swap renames four aside (calls 1-4) and then four into place, in that order (calls 5-8). Call 8
#: fails with three new entries in place, among them the `pkg` DIRECTORY: putting the old `pkg`
#: back over it fails unless the new one is moved out first (a rename replaces a file or a link,
#: never a directory that has entries).
AFTER_NEW_ENTRIES_ARE_IN = 8


def test_a_swap_that_fails_puts_the_old_toolbox_back(baked, tmp_path, monkeypatch):
    """The worker's boot swallows a populate error, so a swap left half done would leave the boxes
    a partial toolbox until the next boot (#461's review). A rename that raises after a new entry
    is already in place moves those entries back out, puts the old entries and the old stamp back,
    and leaves no staging behind."""
    live = tmp_path / "live"
    toolbox.populate(source=baked, live=live)
    before = (live / toolbox.STAMP).read_text()
    (live / "codex").write_text("#!/bin/sh\nexec true OLD\n")
    (live / "pkg" / "OLD").write_text("old")
    entries = sorted(e.name for e in live.iterdir())

    _renames_failing_at(monkeypatch, AFTER_NEW_ENTRIES_ARE_IN)
    with pytest.raises(OSError):
        toolbox.populate(source=baked, live=live, force=True)
    monkeypatch.undo()

    assert (live / toolbox.STAMP).read_text() == before, "the old stamp was not put back"
    assert "OLD" in (live / "codex").read_text(), "the old toolbox was not put back"
    assert (live / "pkg" / "OLD").exists(), "a new entry already moved in stayed in place"
    assert sorted(e.name for e in live.iterdir()) == entries
    assert not list(live.glob(".toolbox-staging-*")), "a failed swap left its staging behind"


def test_an_undo_that_fails_keeps_the_old_toolbox_on_the_volume(baked, tmp_path, monkeypatch):
    """When the undo's own rename raises, staging still holds the old entries it had not put back
    (in `.old`). Removing it there would leave the volume with neither toolbox, so it stays, and
    with no stamp the next boot clears it and copies again."""
    live = tmp_path / "live"
    toolbox.populate(source=baked, live=live)
    (live / "codex").write_text("#!/bin/sh\nexec true OLD\n")

    # call 8 fails the swap; the undo then moves the three new entries back out (9-11) and fails on
    # the first old entry it puts back (12)
    _renames_failing_at(monkeypatch, AFTER_NEW_ENTRIES_ARE_IN, 12)
    with pytest.raises(OSError):
        toolbox.populate(source=baked, live=live, force=True)
    monkeypatch.undo()

    held = [*live.glob("codex"), *live.glob(".toolbox-staging-*/.old/codex")]
    assert held and "OLD" in held[0].read_text(), "the undo's failure removed the old toolbox"
    assert not (live / toolbox.STAMP).exists()

    toolbox.populate(source=baked, live=live)
    assert toolbox.is_populated(live, source=baked) is True
    assert not list(live.glob(".toolbox-staging-*"))


def test_a_swap_killed_midway_leaves_no_stamp(baked, tmp_path, monkeypatch):
    """A worker KILLED during the swap runs nothing after the rename it died on, so nothing is put
    back: what it leaves is a mix of old and new entries. The stamp went before the first rename,
    so nothing says that mix is complete, and the next boot clears the debris and copies again.
    The kill is the swap raising with the undo switched off."""
    live = tmp_path / "live"
    toolbox.populate(source=baked, live=live)

    _renames_failing_at(monkeypatch, AFTER_NEW_ENTRIES_ARE_IN)
    monkeypatch.setattr(toolbox, "_put_back", lambda *a, **k: None)
    with pytest.raises(OSError):
        toolbox.populate(source=baked, live=live, force=True)
    monkeypatch.undo()

    assert not (live / toolbox.STAMP).exists(), "a stamp survived a swap that was killed"
    assert toolbox.is_populated(live) is False

    toolbox.populate(source=baked, live=live)
    assert toolbox.is_populated(live, source=baked) is True
    assert not list(live.glob(".toolbox-staging-*")), "the next boot left the dead swap's debris"


def test_a_toolbox_built_for_another_variant_is_not_populated(baked, tmp_path, monkeypatch):
    """A worker rebuilt for a different architecture must not inherit the old volume's contents —
    the binaries in it cannot execute, and the failure would be a dynamic-loader error naming the
    wrong thing."""
    live = tmp_path / "live"
    toolbox.populate(source=baked, live=live)

    monkeypatch.setattr(toolbox, "variant", lambda: "linux-riscv64-glibc")
    assert toolbox.is_populated(live) is False


# ── absence is a condition, not a crash ─────────────────────────────────────────────────────────

def test_no_baked_toolbox_is_not_an_error(tmp_path):
    """A development worker, or an image built without the toolbox stage. It must still boot; the
    absence is reported by `box prove`, not by refusing to start."""
    assert toolbox.populate(source=tmp_path / "nope", live=tmp_path / "live") == {}


def test_an_unreadable_stamp_degrades_to_absent(tmp_path):
    live = tmp_path / "live"
    live.mkdir()
    (live / toolbox.STAMP).write_text("{not json")

    assert toolbox.read_stamp(live) == {}
    assert toolbox.is_populated(live) is False


# ── the variant ─────────────────────────────────────────────────────────────────────────────────

def test_the_variant_names_os_arch_and_libc():
    parts = toolbox.variant().split("-")

    assert len(parts) == 3, toolbox.variant()
    assert parts[2] in ("glibc", "musl"), toolbox.variant()


# ── the mount ───────────────────────────────────────────────────────────────────────────────────

def _argv(monkeypatch, **box_kwargs):
    import beeverforge.adapters.sandbox.container as mod
    from beeverforge.adapters.sandbox.container import ContainerSandbox

    calls: list[list[str]] = []
    monkeypatch.setattr(mod, "_host",
                        lambda args, timeout=None: (calls.append(list(args)), (0, ""))[1])
    ContainerSandbox(image="img", **box_kwargs).prepare(
        repo_path=__import__("pathlib").Path("."), base_branch="main", branch="sdlc/1"
    )
    return next(a for a in calls if "run" in a)


def test_the_toolbox_is_mounted_read_only(monkeypatch):
    """Read-only bounds the accident, not the adversary: a process at uid 0 in the box can copy a
    binary out and run a patched copy, and ADR-0037 says so plainly. What `:ro` buys is that the
    toolbox one job leaves behind is the toolbox the next job gets."""
    from beeverforge.adapters.sandbox.container import TOOLBOX_MOUNT

    argv = _argv(monkeypatch, toolbox="beeverforge_toolbox")

    assert f"beeverforge_toolbox:{TOOLBOX_MOUNT}:ro" in argv, argv


def test_a_box_with_no_toolbox_mounts_nothing(monkeypatch):
    """The worktree-era default and every existing test. A bare `-v :/opt/beeverforge-toolbox:ro` would
    be a docker error, and mounting an empty host path would be worse — a toolbox that exists and
    is empty."""
    from beeverforge.adapters.sandbox.container import TOOLBOX_MOUNT

    argv = _argv(monkeypatch)

    assert not any(TOOLBOX_MOUNT in part for part in argv), argv


def test_the_mount_point_matches_what_the_adapters_are_told(monkeypatch):
    """The two halves are connected by nothing but agreement: `harness_path` tells the adapter
    where to look, and `prepare` decides where to mount. This is the only thing that checks they
    are the same place."""
    from beeverforge.adapters.sandbox.container import ContainerSandbox

    argv = _argv(monkeypatch, toolbox="beeverforge_toolbox")
    mount = next(p for p in argv if p.startswith("beeverforge_toolbox:")).split(":")[1]
    told = ContainerSandbox(image="img").harness_path("claude")

    assert told.startswith(mount + "/"), (told, mount)


# ── reachability: the deployment's volume must reach the box ────────────────────────────────────

def test_the_factory_hands_the_deployment_volume_to_the_box(monkeypatch):
    """`BEEVERFORGE_TOOLBOX_VOLUME` is a DEPLOYMENT fact — one volume for every project on this worker —
    so it comes from the environment, not from `box:`. A client naming the framework's volume
    would be a client naming what gets mounted into their own container.

    Asserted at the end of the chain, because the last three times this shape appeared the value
    was accepted somewhere in the middle and dropped before it arrived."""
    import beeverforge.adapters.sandbox.registry as reg
    from beeverforge.contracts.project import Project

    monkeypatch.setenv("BEEVERFORGE_TOOLBOX_VOLUME", "beeverforge_toolbox")
    built: list[object] = []
    traits, real = reg.BOXES["container"]
    reg.BOXES["container"] = (traits, lambda **kw: built.append(real(**kw)) or built[-1])
    try:
        from beeverforge import factory

        try:
            factory.build_runner(Project(name="acme", repo_path="/tmp/acme"), "#1",
                                 sandbox="container", image="img", review=False)
        except Exception:
            pass
    finally:
        reg.BOXES["container"] = (traits, real)

    assert built and built[0].toolbox == "beeverforge_toolbox", built


def test_no_volume_configured_mounts_nothing(monkeypatch):
    """Every deployment that exists today, and every local `sdlc run`."""
    import beeverforge.adapters.sandbox.registry as reg
    from beeverforge.contracts.project import Project

    monkeypatch.delenv("BEEVERFORGE_TOOLBOX_VOLUME", raising=False)
    built: list[object] = []
    traits, real = reg.BOXES["container"]
    reg.BOXES["container"] = (traits, lambda **kw: built.append(real(**kw)) or built[-1])
    try:
        from beeverforge import factory

        try:
            factory.build_runner(Project(name="acme", repo_path="/tmp/acme"), "#1",
                                 sandbox="container", image="img", review=False)
        except Exception:
            pass
    finally:
        reg.BOXES["container"] = (traits, real)

    assert built and built[0].toolbox is None


def test_the_worker_populates_the_toolbox_on_boot():
    """The population is on the worker's boot path or it is a function nobody calls — which is the
    defect this repository is named for. Asserted structurally: `main()` must reach it."""
    import pathlib

    src = (pathlib.Path(__file__).resolve().parent.parent
           / "beeverforge/runtime/temporal/worker.py").read_text()
    assert "populate_toolbox" in src or "toolbox import populate" in src, (
        "the worker never populates the toolbox, so the volume the boxes mount stays empty"
    )
