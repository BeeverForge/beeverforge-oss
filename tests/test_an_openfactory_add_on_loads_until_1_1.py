"""An OpenFactory 0.7 add-on still loads after an upgrade in place, until BeeverForge 1.1 (#266).

WHAT A 0.7 DEPLOYMENT HAS INSTALLED. Add-on packages whose `entry_points.txt` declares their rows
under `openfactory.adapters`, 0.7's group. BeeverForge scans `beeverforge.adapters`; until this,
nothing scanned the old group, so every such row vanished on the upgrade and a project naming its
kind was refused as unknown.

THE PACKAGES HERE ARE REAL: a directory on `sys.path` holding a module and a `*.dist-info` with an
`entry_points.txt`, which is exactly what `importlib.metadata` scans. Nothing of ours is patched,
because the claim is about the packaging a 0.7 add-on already shipped.

WHAT EACH TEST HOLDS:
  · a row declared only under the old group is built, listed and named in the doctor's list;
  · a name declared under both groups is the new group's row, and is not on the old-group list;
  · one warning per process names the distribution, the group to move to and the release;
  · the old group is in the removal register, so the release that drops it cannot forget it.
"""

from __future__ import annotations

import logging
import textwrap
import uuid
from pathlib import Path

import pytest

from beeverforge import deprecations, plugins


def _install(root: Path, monkeypatch, *, dist: str, groups: dict[str, dict[str, str]],
             source: str) -> str:
    """Install `dist` under `root`: one module named after it, and a dist-info declaring
    `groups` ({group: {name: "module:attr"}}). Returns the module's name."""
    module = f"{dist.replace('-', '_')}_{uuid.uuid4().hex[:8]}"
    (root / f"{module}.py").write_text(textwrap.dedent(source))
    info = root / f"{dist.replace('-', '_')}-1.0.dist-info"
    info.mkdir()
    (info / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {dist}\nVersion: 1.0\n")
    lines = []
    for group, rows in groups.items():
        lines.append(f"[{group}]")
        lines += [f"{name} = {target.replace('MODULE', module)}" for name, target in rows.items()]
    (info / "entry_points.txt").write_text("\n".join(lines) + "\n")
    monkeypatch.syspath_prepend(str(root))
    return module


@pytest.fixture
def fresh(monkeypatch):
    """A loader that has read nothing and warned about nothing yet, for this test only."""
    monkeypatch.setattr(plugins, "_REPORTED_FORMER", set())
    plugins.reset_cache()
    yield
    plugins.reset_cache()


_SOURCE = '''
def build_tracker(*args, **kwargs):
    return "the 0.7 add-on's tracker"

def build_new(*args, **kwargs):
    return "the moved row"

def build_old(*args, **kwargs):
    return "the row it moved from"
'''


def test_a_row_declared_only_under_the_0_7_group_is_built_and_listed(tmp_path, monkeypatch,
                                                                     fresh):
    module = _install(tmp_path, monkeypatch, dist="someone-addons",
                      groups={"openfactory.adapters": {"tracker.someone": "MODULE:build_tracker"}},
                      source=_SOURCE)

    built = plugins.builder("tracker", "someone", builtin={})

    assert built is not None, "a 0.7 add-on's row was not loaded from `openfactory.adapters`"
    assert built() == "the 0.7 add-on's tracker"
    assert built.__module__ == module
    assert "someone" in plugins.known("tracker", {})
    assert {"distribution": "someone-addons", "axis": "tracker", "kind": "someone",
            "version": "1.0"} in plugins.installed()
    assert plugins.on_the_former_group() == [{"distribution": "someone-addons",
                                              "name": "tracker.someone"}]


def test_a_name_both_groups_declare_is_the_new_groups_row(tmp_path, monkeypatch, fresh):
    _install(tmp_path, monkeypatch, dist="someone-moving",
             groups={"beeverforge.adapters": {"tracker.someone": "MODULE:build_new"},
                     "openfactory.adapters": {"tracker.someone": "MODULE:build_old"}},
             source=_SOURCE)

    built = plugins.builder("tracker", "someone", builtin={})

    assert built is not None and built() == "the moved row"
    assert [r for r in plugins.installed() if r["kind"] == "someone"] == [
        {"distribution": "someone-moving", "axis": "tracker", "kind": "someone",
         "version": "1.0"}], "the row both groups declare was listed twice"
    assert plugins.on_the_former_group() == []


def test_a_built_in_still_wins_over_a_0_7_row(tmp_path, monkeypatch, fresh):
    _install(tmp_path, monkeypatch, dist="someone-shadow",
             groups={"openfactory.adapters": {"tracker.github": "MODULE:build_old"}},
             source=_SOURCE)

    assert plugins.builder("tracker", "github", builtin={"github": object()}) is None
    assert plugins.shadowed("tracker", {"github": object()}) == ["github"]


def test_the_distribution_on_the_old_group_is_named_once_per_process(tmp_path, monkeypatch,
                                                                     fresh, caplog):
    _install(tmp_path, monkeypatch, dist="someone-addons",
             groups={"openfactory.adapters": {"tracker.someone": "MODULE:build_tracker"}},
             source=_SOURCE)
    caplog.set_level(logging.WARNING, logger="beeverforge.plugins")

    plugins.builder("tracker", "someone", builtin={})
    plugins.reset_cache()
    plugins.builder("tracker", "someone", builtin={})

    said = [r.getMessage() for r in caplog.records if "openfactory.adapters" in r.getMessage()]
    assert len(said) == 1, said
    assert "someone-addons" in said[0]
    assert "`beeverforge.adapters`" in said[0]
    assert f"BeeverForge {deprecations.removed_in('openfactory-adapters')}" in said[0]


def test_nothing_is_said_when_no_add_on_is_on_the_old_group(tmp_path, monkeypatch, fresh, caplog):
    _install(tmp_path, monkeypatch, dist="someone-current",
             groups={"beeverforge.adapters": {"tracker.someone": "MODULE:build_new"}},
             source=_SOURCE)
    caplog.set_level(logging.WARNING, logger="beeverforge.plugins")

    assert plugins.builder("tracker", "someone", builtin={}) is not None
    assert not [r for r in caplog.records if "openfactory.adapters" in r.getMessage()]


def test_the_old_group_is_in_the_removal_register():
    assert plugins.FORMER_GROUP == "openfactory.adapters"
    assert plugins.FORMER_GROUP_READ_UNTIL == "1.1"
    assert deprecations.removed_in("openfactory-adapters") == "1.1"

