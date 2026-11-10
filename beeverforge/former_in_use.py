"""The OpenFactory 0.7 names a deployment still uses, each beside the name to use instead (#266).

An upgrade in place keeps working under 0.7's names: its `OPENFACTORY_*` variables, its
`~/.openfactory/` directory, a repository's `.openfactory/` folder, the journals beside a checkout,
add-ons declared under `openfactory.adapters`, the `openfactory` import and command. Each is read
by its own compatibility path, and each path warns once, where it is read, in a log nobody may be
watching. The doctor is where an operator asks what is left to do, so this gathers them into one
list there.

NAMES ONLY, NEVER A VALUE. A variable is named, never what it holds: many of them are credentials.

EACH SOURCE IS PASSED IN. The doctor's probe reads the machine (`probe`); `still_in_use` only
assembles what it is handed, so a test states the machine in its arguments.

A STALE `~/.openfactory/` IS LISTED TOO. With both operator directories present the current one
is read and the former one is not, and no other line of the doctor says so. A repository's stale
`.openfactory/` is not listed here: the doctor's `folder` line already names it.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from beeverforge import namespace
from beeverforge.deprecations import removed_in
from beeverforge.former_names import FORMER_PREFIX, PREFIX
from beeverforge.paths import FORMER_LOGS_BESIDE, LOGS_BESIDE


@dataclass(frozen=True)
class StillInUse:
    """One former name this deployment still uses, said the way the doctor prints it."""

    #: the former name, as the operator finds it
    old: str
    #: the name to use instead, or what to do when there is nothing to rename
    new: str
    #: where it was found
    where: str
    #: the release that stops reading it, `""` where none is registered
    until: str = ""

    def sentence(self) -> str:
        until = f", read until BeeverForge {self.until}" if self.until else ""
        return f"{self.old} → {self.new} ({self.where}{until})"


def still_in_use(*, environment: Iterable[str] = (), home: Path | None = None,
                 checkout: Path | None = None, journals: Path | None = None,
                 add_ons: Iterable[dict[str, str]] = (), imported: bool = False,
                 command: str = "") -> list[StillInUse]:
    """Every former name in what it is handed, in a fixed order.

    `environment`: the `OPENFACTORY_*` names this process found; `home`: the operator's home;
    `checkout`: the project's repository; `journals`: the project's journal directory;
    `add_ons`: `plugins.on_the_former_group()`'s rows; `imported`: whether this process imported
    `openfactory`; `command`: the name this process was started under."""
    found: list[StillInUse] = []
    environ = removed_in("openfactory-environment")
    for name in sorted(set(environment)):
        found.append(StillInUse(f"`{name}`", f"`{PREFIX}{name[len(FORMER_PREFIX):]}`",
                                "the environment", environ))
    if home is not None:
        former, current = f"`~/{namespace.FORMER_DIR}/`", f"`~/{namespace.DIR}/`"
        if namespace.dir_in(home) == namespace.FORMER_DIR:
            found.append(StillInUse(former, current, "the operator's directory"))
        elif namespace.stale_former_dir(home):
            found.append(StillInUse(
                former, f"remove it once nothing in it is newer than its twin under {current}",
                f"the operator's directory: {current} is read and nothing under {former} is"))
    if checkout is not None and namespace.dir_in(checkout) == namespace.FORMER_DIR:
        found.append(StillInUse(f"`{namespace.FORMER_DIR}/`", f"`{namespace.DIR}/`",
                                "the repository; `beeverforge migrate` proposes the rename"))
    if journals is not None and journals.parent.name == FORMER_LOGS_BESIDE:
        found.append(StillInUse(f"`{journals.parent}`",
                                f"`{journals.parent.with_name(LOGS_BESIDE)}`",
                                "the journals beside the checkout"))
    from beeverforge.plugins import FORMER_GROUP, GROUP

    adapters = removed_in("openfactory-adapters")
    for row in add_ons:
        dist = row.get("distribution") or "an add-on"
        found.append(StillInUse(f"`{FORMER_GROUP}` entry point `{row.get('name', '')}`",
                                f"`{GROUP}`", f"declared by {dist}", adapters))
    if imported:
        found.append(StillInUse(
            "`import openfactory`", "`import beeverforge`",
            "something this process loaded; the warning printed at that import names its line",
            removed_in("openfactory-import")))
    if command == "openfactory":
        found.append(StillInUse("the `openfactory` command", "`beeverforge`",
                                "how this command was run", removed_in("openfactory-command")))
    return found


def probe(*, checkout: Path | None, journals: Path | None) -> list[StillInUse]:
    """`still_in_use` for this process and this machine: the environment names this process
    carried, the operator's home, the add-ons installed, the import and the command."""
    from beeverforge import former_names, plugins

    return still_in_use(environment=former_names.found(), home=Path.home(), checkout=checkout,
                        journals=journals, add_ons=plugins.on_the_former_group(),
                        imported="openfactory" in sys.modules,
                        command=Path(sys.argv[0]).name if sys.argv else "")
