"""An OpenFactory 0.7 deployment's environment, read under BeeverForge's names until 1.1 (#264).

OpenFactory 0.7 was configured with `OPENFACTORY_*` variables; this platform reads
`BEEVERFORGE_*`. A deployment upgraded in place must start without editing anything first, so each
PROCESS ENTRY carries every `OPENFACTORY_<SUFFIX>` over to `BEEVERFORGE_<SUFFIX>` before it reads
its configuration, and the readers spread across the package keep asking for one spelling.

THE NEW NAME WINS. A variable already set under `BEEVERFORGE_<SUFFIX>` — empty included, since an
empty assignment is how a caller withholds one (`BEEVERFORGE_APPROVERS=`) — is never overwritten.

THE OLD NAME LEAVES THE PROCESS. Every `OPENFACTORY_*` is removed from the environment once it is
read, whichever name won. The worktree box scrubs credentials BY NAME, and its deny lists name the
spellings this platform reads: an `OPENFACTORY_FORGE_TOKEN` left beside its `BEEVERFORGE_` copy
would reach the agent under the name no list carries. Removed here, it reaches nothing this process
starts, and no deny list has to learn the old names.

AT AN ENTRY, NEVER AT IMPORT. Changing the environment when a module is imported is the side effect
`cli._load_environment` was written against; a process calls `carry_over` where it loads `.env`,
after the load, so a 0.7 `.env` is carried too.

ONE LINE SAYS IT, NAMES ONLY. Many of these variables hold credentials, so the warning names the
variables and never prints a value. A name set under both spellings with the SAME value says
nothing: that is a deployment that already renamed, or this process carrying a `.env` read again.

ONCE PER PROCESS, HOWEVER MANY LOADS (review of #499). A process loads `.env` more than once —
`serve` through the command line's callback and then the panel's own load, the worker in `born`
and again in `main` — and each load puts an `OPENFACTORY_*` from the file back, so `carry_over`
runs, and finds it, each time. It stays idempotent; `warn` remembers which names this process has
already said and says only the new ones.

The old names are read until the release `deprecations.py` registers for them, and removed then.
"""

from __future__ import annotations

import logging
import os
from collections.abc import MutableMapping
from dataclasses import dataclass

from beeverforge.deprecations import removed_in
from beeverforge.environ import ENV_PREFIX

log = logging.getLogger("beeverforge.environment")

#: The prefix an OpenFactory 0.7 deployment's variables carry.
FORMER_PREFIX = "OPENFACTORY_"

#: The prefix they are read under.
PREFIX = ENV_PREFIX

#: The release that stops reading the former names — the register's, not restated here.
LAST_READ_BEFORE = removed_in("openfactory-environment")

#: The former names this process has already warned about, carried or ignored. Bounded by the
#: environment, never by traffic: one entry per distinct `OPENFACTORY_*` name a load has found.
_REPORTED: set[str] = set()

#: Of those, the ones not read because their new name was set to another value. Bounded likewise.
_IGNORED: set[str] = set()


@dataclass(frozen=True)
class CarriedOver:
    """What one `carry_over` did, by NAME (a value never enters it)."""

    #: former names read under the new name, which was unset
    carried: tuple[str, ...] = ()
    #: former names not read, because the new name was set to another value
    ignored: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.carried or self.ignored)

    def sentence(self) -> str:
        """The one warning line, or "" when there is nothing to say."""
        parts = []
        if self.carried:
            parts.append(f"read {', '.join(self.carried)} as their {PREFIX}* names")
        if self.ignored:
            parts.append(f"ignored {', '.join(self.ignored)} because their {PREFIX}* names are "
                         f"set")
        if not parts:
            return ""
        return (f"the environment still uses OpenFactory's names: {'; '.join(parts)} — rename "
                f"them to {PREFIX}*, because {FORMER_PREFIX}* names are read only until "
                f"BeeverForge {LAST_READ_BEFORE}")


def carry_over(environ: MutableMapping[str, str] | None = None) -> CarriedOver:
    """Read every `OPENFACTORY_<SUFFIX>` in `environ` (this process's by default) as
    `BEEVERFORGE_<SUFFIX>`, the new name winning, and remove the former names from it."""
    env = os.environ if environ is None else environ
    carried, ignored = [], []
    former = sorted(k for k in list(env) if k.startswith(FORMER_PREFIX) and k != FORMER_PREFIX)
    for old in former:
        value = env.pop(old)
        new = PREFIX + old[len(FORMER_PREFIX):]
        if new not in env:
            env[new] = value
            carried.append(old)
        elif env[new] != value:
            ignored.append(old)
    return CarriedOver(carried=tuple(carried), ignored=tuple(ignored))


def found() -> tuple[str, ...]:
    """The former names this process has found and said, carried or ignored — for the doctor's
    list of former names still in use. Every entry calls `warn` after `carry_over`, and
    `carry_over` has removed them from the environment by then, so this is where they are left."""
    return tuple(sorted(_REPORTED))


def ignored() -> tuple[str, ...]:
    """Of `found()`, the names not read because their new name holds another value: these are
    removed, not renamed — renaming one would overwrite the value that is read."""
    return tuple(sorted(_IGNORED))


def warn(done: CarriedOver, logger: logging.Logger | None = None) -> None:
    """Log what `carry_over` did as ONE warning, naming only what this process has not said yet.

    A deployment that asked for JSON lines has its log set up first, so the line is one JSON
    object like the rest of its log and not a bare line among them."""
    new = CarriedOver(carried=tuple(n for n in done.carried if n not in _REPORTED),
                      ignored=tuple(n for n in done.ignored if n not in _REPORTED))
    if not new:
        return
    _REPORTED.update(new.carried + new.ignored)
    _IGNORED.update(new.ignored)
    from beeverforge.observability import logs

    if logs.structured():
        logs.configure()
    (logger or log).warning(new.sentence())
