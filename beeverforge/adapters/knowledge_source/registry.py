"""Which knowledge source the product role reads beside its own — from configuration, never from an
import (ADR-0052 D15).

ONE LINE OF CONFIGURATION, AND OFF UNLESS IT IS SAID. `BEEVERFORGE_KNOWLEDGE_SOURCE` names the
row; unset, it is `none`, and the core is what it was before this axis existed: no request is
made, no file is written, no line is added to the manifest. `beeverforge-knowledge` asks
BeeverForge Knowledge, an optional separate service, as the role its administrator registered
(`service.py`). An add-on's row joins through the `knowledge_source.<kind>` entry point
(`plugins.py`); a built-in wins a collision.

AN UNKNOWN ROW RAISES, NAMING WHAT IS KNOWN — the house rule: falling back to another row would
put somebody's answers in front of the role that nobody chose. A KNOWN ROW THAT CANNOT BE BUILT
HERE (its address or its token missing) raises `NotAsked` with the variable to set, and the turn
goes on without it, saying so (`for_the_turn`).

READ EACH TIME, NEVER CACHED. Building the row costs a read of the environment and the
credential store and nothing else — no connection is opened until it is asked — so a token the
store rotates is the one the next turn sends.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable

from beeverforge import plugins
from beeverforge.adapters.knowledge_source.base import KnowledgeSource, NotAsked

log = logging.getLogger("beeverforge.knowledge_source")

#: The entry-point axis: `knowledge_source.<kind>` — a builder `build(project=None)` returning a
#: `KnowledgeSource`.
AXIS = "knowledge_source"

#: The deployment's choice of row, and what it is when nobody chose: off.
KIND_ENV = "BEEVERFORGE_KNOWLEDGE_SOURCE"
OFF = "none"
DEFAULT_KIND = OFF
#: The row that asks BeeverForge Knowledge (`service.py`).
SERVICE = "beeverforge-knowledge"


def _none(**_kw):
    raise NotAsked(f"no knowledge source is switched on ({KIND_ENV}={OFF})")


def _service(**_kw):
    from beeverforge.adapters.knowledge_source.service import KnowledgeService

    return KnowledgeService.configured()


_service.display_name = "BeeverForge Knowledge"  # type: ignore[attr-defined]

#: kind → builder, `build(project=None) -> KnowledgeSource`. Every row the platform ships; an
#: add-on's join through the entry point, and a built-in wins a collision (`plugins.builder`).
SOURCES: dict[str, Callable[..., object]] = {
    OFF: _none,
    SERVICE: _service,
}


def kind() -> str:
    return (os.environ.get(KIND_ENV) or "").strip().lower() or DEFAULT_KIND


def switched_on() -> bool:
    """Whether a deployment named a row: the one question the prompt and the pack ask before they
    say or write anything of this axis, so that off is the core as it was."""
    return kind() != OFF


def display_name(chosen: str | None = None) -> str:
    """What the row is called in a sentence a person reads: its own name when it declares one,
    else "the knowledge source `<kind>`"."""
    chosen = chosen or kind()
    builder = SOURCES.get(chosen) or plugins.builder(AXIS, chosen, builtin=SOURCES)
    said = getattr(builder, "display_name", "")
    return said if isinstance(said, str) and said.strip() else f"the knowledge source `{chosen}`"


def build_knowledge_source(name: str | None = None, *, project=None) -> KnowledgeSource:
    """The row `name` (the configured one when None) — `ValueError` for a row nobody knows,
    `NotAsked` for one that cannot be built here, with why."""
    chosen = (name or kind()).strip().lower()
    builder = SOURCES.get(chosen) or plugins.builder(AXIS, chosen, builtin=SOURCES)
    if builder is None:
        raise ValueError(f"unknown knowledge source {chosen!r} — known: "
                         f"{', '.join(plugins.known(AXIS, SOURCES))}")
    row = builder(project=project)
    if not callable(getattr(row, "ask", None)):
        raise ValueError(f"the knowledge source {chosen!r} built something with no "
                         f"`ask(question)` — it could not be asked anything")
    return row  # type: ignore[return-value]


def for_the_turn(project=None) -> tuple[KnowledgeSource | None, str]:
    """`(None, "")` when no row is switched on — nothing to say; `(row, "")` when one is; `(None,
    why)` when the one named cannot be built here. Never raises: the turn goes on without it."""
    if not switched_on():
        return None, ""
    try:
        return build_knowledge_source(project=project), ""
    except (NotAsked, ValueError) as exc:
        log.warning("BEEVERFORGE_KNOWLEDGE_SOURCE_UNAVAILABLE %s", exc)
        return None, str(exc)
    except Exception:  # noqa: BLE001 — an add-on's row that raised is a reason too
        # ITS WORDS GO TO THE LOG: the reason is written into the manifest the role reads, and a
        # stranger's exception is not a sentence anybody wrote for a person
        log.warning("BEEVERFORGE_KNOWLEDGE_SOURCE_UNAVAILABLE the %s row could not be built",
                    kind(), exc_info=True)
        return None, f"the {kind()} row could not be built (the reason is in the platform's log)"
