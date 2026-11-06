"""The harness toolbox: framework-owned binaries, mounted into a client's box (ADR-0037 D2).

WHY IT EXISTS. Under D1 the box is built from the CLIENT's image, so the harness cannot live in it
— we do not control that image and would not want to ask a client to rebuild theirs every time we
pin a new agent CLI. The harness is therefore delivered separately: a directory the worker owns,
mounted read-only at a fixed absolute path, with `SandboxAdapter.harness_path` (D2a) naming the
entry so nothing depends on `PATH` inside an image whose `/etc/profile` we did not write.

WHY IT IS NOT ONE IMAGE PER HARNESS. That is stack × harness images, and three harnesses over five
stacks is fifteen artefacts somebody maintains. Injection makes `harness: {executor: codex,
reviewer: claude_code}` pure configuration — rotating between them, or mixing per role, never
touches an image. That property is what the product is sold on.

WHAT IS ACTUALLY IN IT, measured rather than assumed (the first draft of ADR-0037 assumed all three
were self-contained natives; only `claude` is):

    claude   a native ELF, executed directly
    codex    a `#!/usr/bin/env node` shim over a vendored binary
    kimi     an ESM bundle — Node, always

so the toolbox carries a **Node runtime** too, and the entry for the Node-based harnesses is a
wrapper that names both the runtime and the script absolutely. ~50 MB of Node beside three
harnesses is noise, and going through it uniformly removes a per-harness branch that would work
for two and silently not the third.

THE VARIANT IS A PROPERTY OF THE CLIENT'S IMAGE, NOT OF THE WORKER. `ldd` on the `claude` ELF shows
`ld-linux-<arch>.so.1` — glibc. An Alpine or musl-based client image cannot exec it, and the
failure is the dynamic loader's *no such file or directory*, which names the wrong thing and sends
somebody looking for a missing file that is right there. So a toolbox is stamped with the triple it
was built for, and `beeverforge box prove` (D3) is what compares that against the image before a
ticket
ever runs.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import shutil
from pathlib import Path

log = logging.getLogger("beeverforge.toolbox")

#: Where the built toolbox is baked into the worker image.
SOURCE = Path(os.environ.get("BEEVERFORGE_TOOLBOX_SOURCE") or "/opt/beeverforge-toolbox-src")

#: Where the worker keeps the copy it mounts into boxes. A named docker volume in compose —
#: NOT a worker-local path, because a `-v` issued by a containerised worker is resolved by the
#: HOST daemon, where a path inside the worker does not exist. Docker would create an empty
#: directory and the box would get an empty toolbox, in silence.
LIVE = Path(os.environ.get("BEEVERFORGE_TOOLBOX") or "/var/lib/beeverforge-toolbox")

#: Written beside the binaries so a reader — and `box prove` — can tell what this toolbox IS
#: without running anything in it.
STAMP = "toolbox.json"

#: Where the toolbox stage's `npm install -g --prefix <toolbox>/pkg` puts every harness package.
PACKAGES = Path("pkg") / "lib" / "node_modules"


def variant() -> str:
    """The `<os>-<arch>-<libc>` this toolbox was built for.

    Keyed off the machine that BUILT it. `box prove` compares it against the client's image, which
    is the one that has to execute these bytes — the two are the same only by coincidence."""
    machine = {"x86_64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(
        platform.machine(), platform.machine() or "unknown"
    )
    libc = "musl" if (Path("/lib/ld-musl-x86_64.so.1").exists()
                      or Path("/lib/ld-musl-aarch64.so.1").exists()) else "glibc"
    return f"{platform.system().lower()}-{machine}-{libc}"


def read_stamp(root: Path | None = None) -> dict:
    """What a toolbox says about itself, or `{}` when there is none.

    Never raises: this is read on the worker's boot path and by a diagnostic, and a malformed
    stamp must degrade into "no toolbox" rather than take either down."""
    path = (root or LIVE) / STAMP
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        log.warning("the toolbox stamp at %s is unreadable (%s) — treating it as absent", path,
                    exc)
        return {}
    return data if isinstance(data, dict) else {}


def packages(root: Path) -> dict[str, str]:
    """`{package: version}` for every harness package installed in the toolbox at `root`.

    READ FROM THE PACKAGES THEMSELVES (#246), each one's own `package.json`, so it names what was
    installed rather than what a build argument asked for. A scoped package (`@openai/codex`) is
    one level further down. An entry with no readable `package.json` is skipped, never raised:
    this runs on the worker's boot path."""
    found: dict[str, str] = {}
    base = root / PACKAGES
    try:
        entries = sorted(base.iterdir())
    except OSError:
        return found
    for entry in entries:
        dirs = sorted(entry.iterdir()) if entry.name.startswith("@") and entry.is_dir() else [entry]
        for pkg in dirs:
            try:
                meta = json.loads((pkg / "package.json").read_text())
            except (OSError, ValueError):
                continue
            if isinstance(meta, dict) and meta.get("name") and meta.get("version"):
                found[str(meta["name"])] = str(meta["version"])
    return found


def is_populated(root: Path | None = None, *, source: Path | None = None) -> bool:
    """Whether a usable toolbox is already in place, so a restart is not a re-copy.

    Checks the STAMP rather than the directory: a half-finished copy has files in it and is not a
    toolbox. The stamp is written last, so its presence means the copy completed.

    AND IT IS THE SAME TOOLBOX AS THE ONE BAKED IN `source` (#246). The stamp records the version
    of every package it copied; when the worker image is rebuilt with a new harness pin, the baked
    versions differ and the toolbox is copied again on the next boot. Before this, the stamp held
    the harness NAMES alone, so a bump never reached a deployment that already had a toolbox: the
    boxes kept the old CLI, and current models refused it. A stamp written before versions were
    recorded holds none, so it differs from any baked toolbox that has packages, and is copied
    once."""
    stamp = read_stamp(root)
    if not (stamp.get("harnesses") and stamp.get("variant") == variant()):
        return False
    if source is not None and source.is_dir():
        return stamp.get("packages") == packages(source)
    return True


def populate(*, source: Path | None = None, live: Path | None = None,
             force: bool = False) -> dict:
    """Copy the baked toolbox into the volume the boxes mount. Idempotent; returns the stamp.

    CALLED ON THE WORKER'S BOOT PATH, so it must be quiet and safe to run every time: an already
    populated volume of the right variant, holding the same package versions as the baked one, is
    left alone. A harness version bump changes those versions, so it is copied without being asked
    (#246); `force` is an operator's override, for a live copy changed by hand.

    THE STAMP IS WRITTEN LAST, and that is the whole crash-safety story. The new toolbox is copied
    into a staging directory beside the live one, so a copy that dies leaves the live toolbox and
    its stamp untouched: the same harness keeps running, and the next boot tries again. The stamp
    is removed before the staged entries are renamed into place and written after the last one, so
    a worker killed during that swap leaves no stamp, and the next boot copies again. There is no
    state in which a partial or mixed toolbox looks complete.

    A BOX OF A PREVIOUS WORKER CAN STILL BE RUNNING when this runs: a deploy's SIGTERM leaves the
    container box on the host daemon (`adapters/sandbox/container.py`, #165). Its harness keeps the
    files it has open across the swap; a file it opens afterwards comes from the new toolbox.
    The staging copy needs room for a second toolbox on the volume while it is built.
    """
    src = source or SOURCE
    dst = live or LIVE

    if not src.is_dir():
        # Not an error: a development worker, or an image built without the toolbox stage. The
        # boxes will then find nothing at the mount point, which `beeverforge box prove` reports by
        # name.
        log.info("no baked toolbox at %s — boxes will have none (this is a build-time choice)",
                 src)
        return {}

    if not force and is_populated(dst, source=src):
        log.debug("toolbox already present at %s (%s)", dst, variant())
        return read_stamp(dst)
    was = read_stamp(dst).get("packages") or {}

    # A TOP-LEVEL NON-DIRECTORY ENTRY, not "an executable file". The real `claude` entry is a
    # symlink to the IN-BOX mount point, so at copy time it is DANGLING — `is_file()` and
    # `os.access(X_OK)` are both False for it, and the stamp would have listed `codex, kimi` and
    # silently omitted the main harness. `box prove` reports this list to a human.
    harnesses = sorted(e.name for e in src.iterdir()
                       if not e.is_dir() and e.name != STAMP)
    dst.mkdir(parents=True, exist_ok=True)
    # STAGED, THEN SWAPPED (#246's review). A bump now replaces a toolbox that WORKS, so the new
    # one is copied beside it first, on the same volume, and only then renamed into place. A copy
    # that fails (a full disk, a killed worker) leaves the old toolbox and its stamp exactly as they
    # were, so the boxes keep a harness that runs and the next boot tries again; it does not leave
    # them with none.
    for debris in dst.glob(f"{_STAGING}*"):  # what a boot killed mid-copy or mid-swap left
        _remove(debris)
    staging = dst / f"{_STAGING}{os.getpid()}"
    try:
        for entry in src.iterdir():
            if entry.name != STAMP:
                _copy(entry, staging / entry.name)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    # THE SWAP: the stamp goes first, so a crash between two renames leaves no stamp over a mix of
    # old and new entries, and the next boot copies again. Each entry moves with one rename on one
    # filesystem. An entry the new toolbox no longer has moves aside too, so a bump is exact rather
    # than a merge. A box running at the swap keeps every file it already has open (a rename and a
    # removal leave an open file readable); a path it opens afterwards resolves to the new toolbox.
    # A box that STARTS during the swap, between the first rename and the last, finds entries
    # missing: the window is one rename per top-level entry, but it is not empty.
    #
    # A RENAME THAT RAISES puts the old toolbox back (#461's review): the worker's boot swallows
    # the error, so leaving the swap half done would leave the boxes a partial toolbox until the
    # next boot. The new entries already moved in go back to staging, the old ones come back from
    # `.old`, and the old stamp is rewritten over the bytes it describes.
    stamp_was = (dst / STAMP).read_bytes() if (dst / STAMP).is_file() else None
    (dst / STAMP).unlink(missing_ok=True)
    old = staging / _OLD
    old.mkdir()
    fresh = sorted({e.name for e in staging.iterdir()} - {_OLD})
    aside: list[str] = []
    moved: list[str] = []
    try:
        for entry in sorted(dst.iterdir()):
            if entry.name != STAMP and not entry.name.startswith(_STAGING):
                os.rename(entry, old / entry.name)
                aside.append(entry.name)
        for name in fresh:
            os.rename(staging / name, dst / name)
            moved.append(name)
    except BaseException:
        _put_back(dst, staging, old, moved, aside, stamp_was)
        raise

    stamp = {"variant": variant(), "harnesses": harnesses, "packages": packages(src)}
    (dst / STAMP).write_text(json.dumps(stamp, indent=2, sort_keys=True))
    shutil.rmtree(staging, ignore_errors=True)  # the old toolbox, now aside
    log.info("toolbox populated at %s — %s (%s)%s", dst, ", ".join(harnesses) or "nothing",
             stamp["variant"], _changed(was, stamp["packages"]))
    return stamp


#: The staging directory a copy is built in, beside the live toolbox on the same volume, and where
#: the old toolbox is moved aside during the swap. Hidden, so it is never taken for a harness.
_STAGING = ".toolbox-staging-"
_OLD = ".old"


def _put_back(dst: Path, staging: Path, old: Path, moved: list[str], aside: list[str],
              stamp: bytes | None) -> None:
    """Undo a swap that raised: the new entries back to staging, the old ones back in place, and
    the old stamp over them. Best effort: a step that fails here is logged, and what is left has
    no stamp, so the next boot copies again."""
    try:
        for name in reversed(moved):
            os.rename(dst / name, staging / name)
        for name in reversed(aside):
            os.rename(old / name, dst / name)
        if stamp is not None:
            (dst / STAMP).write_bytes(stamp)
        log.warning("the toolbox swap at %s failed — the previous toolbox is back in place", dst)
    except OSError as exc:
        log.warning("the toolbox swap at %s failed and the previous toolbox could not be put back "
                    "(%s) — it has no stamp, so the next boot copies it again", dst, exc)
    shutil.rmtree(staging, ignore_errors=True)


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


def _copy(entry: Path, target: Path) -> None:
    """One baked entry into the staging directory, which starts empty."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if entry.is_dir() and not entry.is_symlink():
        shutil.copytree(entry, target, symlinks=True)
        return
    # `follow_symlinks=False` keeps the entry a LINK. Following it would copy a 260 MB binary to the
    # top level and leave `pkg` unreferenced — twice the disk, and an entry that no longer points at
    # the package it came from. The link targets the IN-BOX mount point, so it is dangling here and
    # resolves where it is mounted.
    shutil.copy2(entry, target, follow_symlinks=False)
    if not target.is_symlink():
        target.chmod(target.stat().st_mode | 0o111)


def _changed(was: dict, now: dict) -> str:
    """What this copy did to the recorded versions, for the boot log: nothing when they are equal,
    every version when none was recorded, and `<package> <old> → <new>` for each one that moved."""
    if was == now:
        return ""
    if not was:
        return " — versions recorded: " + ", ".join(f"{n} {v}" for n, v in sorted(now.items()))
    return " — " + ", ".join(f"{n} {was.get(n) or 'absent'} → {v}"
                             for n, v in sorted(now.items()) if was.get(n) != v)


def versions(stamp: dict) -> str:
    """The package versions a stamp records, as `box prove` prints them, or `""` for none."""
    recorded = stamp.get("packages") or {}
    if not isinstance(recorded, dict):
        return ""
    return ", ".join(f"{name} {version}" for name, version in sorted(recorded.items()))
