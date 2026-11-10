"""What this platform still reads under an old name, and the release that stops reading it (#264).

ONE REGISTER, SO A CUT CANNOT FORGET ONE. A compatibility path promised "until 1.1" in a release
note is a promise only while something remembers it at 1.1. Each entry here is that memory:
`tests/test_what_a_release_removes_is_registered.py` fails once the package's own version reaches
an entry's `removed_in`, naming the entry, so the release that is meant to drop it cannot be cut
with it still in.

Adding an entry is one line in `REMOVALS`; the code that serves the old name reads its release
from here (`removed_in(...)`) instead of spelling it again.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Removal:
    #: the key code asks by (`removed_in(key)`)
    key: str
    #: the release that no longer has it: "1.1" means every 1.1 version, its pre-releases included
    removed_in: str
    #: what goes, for the person cutting that release
    what: str


REMOVALS: tuple[Removal, ...] = (
    Removal("openfactory-command", "1.1",
            "OpenFactory 0.7's `openfactory` console script, an alias of `beeverforge` "
            "(`beeverforge/former_command.py`, its `[project.scripts]` row in pyproject.toml)"),
    Removal("openfactory-import", "1.1",
            "OpenFactory 0.7's `openfactory` import name, an alias of the `beeverforge` package "
            "(`openfactory/__init__.py`, its `packages.find` entry in pyproject.toml and its "
            "COPY in the three Dockerfiles)"),
    Removal("openfactory-environment", "1.1",
            "OpenFactory 0.7's `OPENFACTORY_*` environment names, read as `BEEVERFORGE_*` "
            "(`beeverforge/former_names.py`)"),
    Removal("openfactory-adapters", "1.1",
            "OpenFactory 0.7's `openfactory.adapters` entry-point group, scanned after "
            "`beeverforge.adapters` (`FORMER_GROUP` in `beeverforge/plugins.py`)"),
    Removal("openfactory-temporal-names", "1.0",
            "OpenFactory 0.7's Temporal task queue, polled by a second worker, and its "
            "`openfactory-` workflow ids, read beside BeeverForge's "
            "(`FORMER_TASK_QUEUE` and `FORMER_WORKFLOW_ID_PREFIX` in "
            "`beeverforge/runtime/temporal/__init__.py`)"),
)


def removed_in(key: str) -> str:
    """The release that removes `key`'s entry. A key nobody registered is a programming error."""
    for entry in REMOVALS:
        if entry.key == key:
            return entry.removed_in
    raise KeyError(f"no removal registered as {key!r} in beeverforge/deprecations.py")


def _release(version: str) -> tuple[int, ...]:
    """The numeric release of a version, trailing zeros dropped: `0.2.0.dev0` → (0, 2),
    `1.1.0` → (1, 1). Dropped so `1.1.0` and `1.1` are ONE release: as tuples `(1, 1, 0)` is
    greater than `(1, 1)`, which would read the removing release as already past it."""
    found = re.match(r"\d+(?:\.\d+)*", version.strip())
    if not found:
        raise ValueError(f"{version!r} is not a version")
    parts = [int(p) for p in found.group(0).split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def due(version: str) -> list[Removal]:
    """The entries `version` must no longer carry: those whose `removed_in` it has reached. A
    pre-release of the removing release counts — its code is the release's code."""
    return [e for e in REMOVALS if _release(version) >= _release(e.removed_in)]
