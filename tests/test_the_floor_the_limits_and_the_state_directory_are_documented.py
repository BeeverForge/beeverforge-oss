"""The configuration reference names every variable the worker reads for its floor, its limits and
its state directory, with the code's own defaults (#365).

WHAT WAS WRONG: `docs/reference/configuration.md` listed the floor and two limits as "the throttles"
with no defaults, and left out the product turn ceilings and the state directory, so a tool writing
a worker container's environment could not know the full set or what each falls back to.

WHAT IS HELD HERE, between the table under "The floor, the limits and the state directory" and the
code:
  · every name in the table is read by the code: a string literal in `beeverforge/`, not a comment;
  · every name the code reads that is in scope is in the table. In scope means a floor or limit
    (`BEEVERFORGE_MAX_*`, `BEEVERFORGE_*_MAX`, `BEEVERFORGE_PRODUCT_TURNS_*`), the state directory
    (`BEEVERFORGE_STATE_DIR`), and the pass's wall (`BEEVERFORGE_AGENT_TIMEOUT`, which the old
    "throttles" row named beside the floor);
  · each "unset" cell is what the code falls back to, read from the code with the variable unset;
  · each row says no `OPENFACTORY_*` spelling is read only while the code reads none.
"""

from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path

import pytest

from tests.the_tree_read_once import parsed

ROOT = Path(__file__).resolve().parent.parent
REFERENCE = ROOT / "docs" / "reference" / "configuration.md"
HEADING = "### The floor, the limits and the state directory"

#: What is in scope beyond the patterns: the pass's wall, named beside the floor before #365.
NAMED = {"BEEVERFORGE_AGENT_TIMEOUT"}
IN_SCOPE = re.compile(r"^BEEVERFORGE_(MAX_[A-Z0-9_]+|[A-Z0-9_]+_MAX|PRODUCT_TURNS_[A-Z0-9_]+"
                      r"|STATE_DIR)$")


def _rows() -> dict[str, list[str]]:
    """`{variable: [cells…]}` for the section's table, read from the reference as written."""
    text = REFERENCE.read_text(encoding="utf-8")
    assert HEADING in text, f"{REFERENCE.name} has no '{HEADING}' section"
    section = text.split(HEADING, 1)[1].split("\n#", 1)[0]
    rows: dict[str, list[str]] = {}
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        name = re.fullmatch(r"`(BEEVERFORGE_[A-Z0-9_]+)`", cells[0]) if cells else None
        if name:
            rows[name.group(1)] = cells
    assert rows, "the section has no table rows"
    return rows


def _literals() -> set[str]:
    """Every string literal in `beeverforge/` — what the code can read, never what it comments."""
    found: set[str] = set()
    for path in (ROOT / "beeverforge").rglob("*.py"):
        for node in ast.walk(parsed(path)):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                found.add(node.value)
    return found


def _env_names(literals: set[str]) -> set[str]:
    return {s for s in literals if re.fullmatch(r"BEEVERFORGE_[A-Z0-9_]+", s)}


def test_every_name_in_the_table_is_read_by_the_code():
    names = _env_names(_literals())

    missing = sorted(set(_rows()) - names)

    assert missing == [], f"the table lists names the code never reads: {missing}"


def test_every_floor_limit_and_state_name_the_code_reads_is_in_the_table():
    read = {n for n in _env_names(_literals()) if IN_SCOPE.match(n) or n in NAMED}

    missing = sorted(read - set(_rows()))

    assert missing == [], f"the code reads these and the table does not list them: {missing}"


def _unset(monkeypatch, name: str) -> None:
    monkeypatch.delenv(name, raising=False)


def _default_of(name: str, monkeypatch) -> str:
    """What the code falls back to for `name`, read from the code with `name` unset."""
    _unset(monkeypatch, name)
    if name == "BEEVERFORGE_MAX_CONCURRENT_JOBS":
        from beeverforge.runtime.temporal import max_concurrent_jobs

        return str(max_concurrent_jobs())
    if name == "BEEVERFORGE_MAX_TURNS":
        from beeverforge.adapters.agent.claude_code import ClaudeCodeAdapter

        return str(ClaudeCodeAdapter().max_turns)
    if name == "BEEVERFORGE_AGENT_TIMEOUT":
        import beeverforge.adapters.sandbox.timeouts as timeouts

        value = importlib.reload(timeouts).AGENT_TIMEOUT
        monkeypatch.undo()
        importlib.reload(timeouts)          # leave the module as the rest of the suite found it
        return str(value)
    if name == "BEEVERFORGE_PREVIEW_MAX":
        from beeverforge.preview.demand import max_previews

        return str(max_previews())
    if name in ("BEEVERFORGE_PRODUCT_TURNS_PER_PRODUCT", "BEEVERFORGE_PRODUCT_TURNS_PER_DEPLOYMENT"):
        from beeverforge.product import cap

        return str(cap._declared(name, cap.DEFAULT_PER_PRODUCT if name == cap.PER_PRODUCT_ENV
                                 else cap.DEFAULT_PER_DEPLOYMENT))
    if name == "BEEVERFORGE_STATE_DIR":
        from beeverforge.namespace import _state_dir

        return str(_state_dir())
    raise AssertionError(f"no reader of {name}'s default is known to this test — add one")


@pytest.mark.parametrize("name", sorted(_rows()))
def test_the_unset_cell_is_the_codes_default(name, monkeypatch):
    said = re.match(r"`([^`]*)`", _rows()[name][2])

    assert said, f"{name}'s 'unset' cell names no value in backticks: {_rows()[name][2]!r}"
    assert said.group(1) == _default_of(name, monkeypatch), name


@pytest.mark.parametrize("name", sorted(_rows()))
def test_an_openfactory_spelling_is_said_not_read_only_while_the_code_reads_none(name):
    old = "OPENFACTORY_" + name.removeprefix("BEEVERFORGE_")
    read = old in _literals()
    cell = _rows()[name][4]

    if read:
        assert cell != "not read", f"the code reads {old}, and the table says it does not"
    else:
        assert cell == "not read", f"the code does not read {old}; the table says {cell!r}"
