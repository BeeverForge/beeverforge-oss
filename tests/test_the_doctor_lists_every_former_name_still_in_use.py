"""The doctor on an upgraded deployment lists every OpenFactory 0.7 name still in use, each with the
new name to use — GitHub issue #266.

Each former name keeps working through its own compatibility path, and each path warns once, in a
log. The doctor's `former_names` line puts them in one list: the environment's `OPENFACTORY_*`
names, `~/.openfactory/` (in use, or stale beside `~/.beeverforge/`), a repository's
`.openfactory/`, the journals in `.openfactory-logs/`, add-ons on `openfactory.adapters`, the
`openfactory` import and the `openfactory` command. A deployment with none has no such line.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from beeverforge import former_in_use, former_names, plugins
from beeverforge.contracts.project import Project
from beeverforge.doctor import Probes, _former_names_probe, diagnose
from beeverforge.former_in_use import still_in_use


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    for name in ("BEEVERFORGE_REGISTRY", "BEEVERFORGE_APPROVERS", "BEEVERFORGE_LOG_DIR"):
        monkeypatch.delenv(name, raising=False)
    return h


def _pairs(found) -> list[tuple[str, str]]:
    return [(f.old, f.new) for f in found]


# ── each source, with the name to use ───────────────────────────────────────────────────────────

def test_each_environment_name_is_listed_with_its_new_name_and_never_its_value():
    found = still_in_use(environment=["OPENFACTORY_FORGE_TOKEN", "OPENFACTORY_LOG_FORMAT"])

    assert _pairs(found) == [("`OPENFACTORY_FORGE_TOKEN`", "`BEEVERFORGE_FORGE_TOKEN`"),
                             ("`OPENFACTORY_LOG_FORMAT`", "`BEEVERFORGE_LOG_FORMAT`")]
    assert all("read until BeeverForge 1.1" in f.sentence() for f in found)


def test_the_0_7_operator_directory_in_use_is_listed(tmp_path):
    (tmp_path / ".openfactory").mkdir()

    assert _pairs(still_in_use(home=tmp_path)) == [("`~/.openfactory/`", "`~/.beeverforge/`")]


def test_a_stale_0_7_operator_directory_is_listed_as_stale(tmp_path):
    (tmp_path / ".openfactory").mkdir()
    (tmp_path / ".beeverforge").mkdir()

    [found] = still_in_use(home=tmp_path)

    assert found.old == "`~/.openfactory/`"
    assert found.new.startswith("remove it")
    assert "nothing under `~/.openfactory/` is" in found.where


@pytest.mark.parametrize("has", [(), (".beeverforge",)])
def test_an_operator_home_without_the_0_7_directory_lists_nothing(tmp_path, has):
    for name in has:
        (tmp_path / name).mkdir()

    assert still_in_use(home=tmp_path) == []


def test_a_repository_on_the_0_7_folder_is_listed_with_migrate(tmp_path):
    (tmp_path / ".openfactory").mkdir()

    [found] = still_in_use(checkout=tmp_path)

    assert (found.old, found.new) == ("`.openfactory/`", "`.beeverforge/`")
    assert "beeverforge migrate" in found.where


def test_a_repository_with_both_folders_is_left_to_the_folder_line(tmp_path):
    (tmp_path / ".openfactory").mkdir()
    (tmp_path / ".beeverforge").mkdir()

    assert still_in_use(checkout=tmp_path) == []


def test_journals_in_the_0_7_directory_are_listed(tmp_path):
    journals = tmp_path / ".openfactory-logs" / "someone-app"

    assert _pairs(still_in_use(journals=journals)) == [
        (f"`{tmp_path / '.openfactory-logs'}`", f"`{tmp_path / '.beeverforge-logs'}`")]


def test_journals_in_the_current_directory_list_nothing(tmp_path):
    assert still_in_use(journals=tmp_path / ".beeverforge-logs" / "someone-app") == []


def test_each_add_on_row_on_the_former_group_is_listed():
    found = still_in_use(add_ons=[{"distribution": "someone-forge", "name": "forge.someone"}])

    assert _pairs(found) == [("`openfactory.adapters` entry point `forge.someone`",
                              "`beeverforge.adapters`")]
    assert "someone-forge" in found[0].where


def test_the_import_and_the_command_are_listed():
    found = still_in_use(imported=True, command="openfactory")

    assert _pairs(found) == [("`import openfactory`", "`import beeverforge`"),
                             ("the `openfactory` command", "`beeverforge`")]


def test_a_deployment_on_the_new_names_lists_nothing(tmp_path):
    (tmp_path / ".beeverforge").mkdir()

    assert still_in_use(environment=[], home=tmp_path, checkout=tmp_path,
                        journals=tmp_path / ".beeverforge-logs" / "x", add_ons=[],
                        imported=False, command="beeverforge") == []


# ── what the process found is what the probe reads ──────────────────────────────────────────────

def test_the_names_a_process_carried_or_ignored_are_found(monkeypatch):
    monkeypatch.setattr(former_names, "_REPORTED", set())
    env = {"OPENFACTORY_A": "1", "OPENFACTORY_B": "2", "BEEVERFORGE_B": "3"}

    former_names.warn(former_names.carry_over(env))

    assert former_names.found() == ("OPENFACTORY_A", "OPENFACTORY_B")


def test_the_probe_reads_this_process_and_this_machine(home, tmp_path, monkeypatch):
    monkeypatch.setattr(former_names, "_REPORTED", {"OPENFACTORY_FORGE_TOKEN"})
    monkeypatch.setattr(plugins, "on_the_former_group",
                        lambda: [{"distribution": "someone-forge", "name": "forge.someone"}])
    monkeypatch.setitem(sys.modules, "openfactory", sys.modules["beeverforge"])
    monkeypatch.setattr(sys, "argv", ["/usr/local/bin/openfactory", "doctor", "someone-app"])
    (home / ".openfactory").mkdir()
    checkout = tmp_path / "work" / "app"
    (checkout / ".openfactory").mkdir(parents=True)
    (tmp_path / "work" / ".openfactory-logs" / "someone-app").mkdir(parents=True)

    found = _former_names_probe(Project(name="someone-app", repo_path=str(checkout)), checkout)

    assert [f.old for f in found] == [
        "`OPENFACTORY_FORGE_TOKEN`", "`~/.openfactory/`", "`.openfactory/`",
        f"`{tmp_path / 'work' / '.openfactory-logs'}`",
        "`openfactory.adapters` entry point `forge.someone`", "`import openfactory`",
        "the `openfactory` command"]


def test_the_probe_on_a_new_deployment_finds_nothing(home, tmp_path, monkeypatch):
    monkeypatch.setattr(former_names, "_REPORTED", set())
    monkeypatch.setattr(plugins, "on_the_former_group", lambda: [])
    monkeypatch.delitem(sys.modules, "openfactory", raising=False)
    monkeypatch.setattr(sys, "argv", ["/usr/local/bin/beeverforge", "doctor", "someone-app"])
    checkout = tmp_path / "work" / "app"
    checkout.mkdir(parents=True)

    assert former_in_use.probe(checkout=checkout, journals=None) == []


# ── the doctor's line ───────────────────────────────────────────────────────────────────────────

def _probes(**over) -> Probes:
    base = dict(
        docker_running=lambda: (True, ""),
        harness_on_path=lambda kind: True,
        manifest=lambda: None,
        forge_reachable=lambda: (True, ""),
        board_columns=lambda: None,
        pickup_column=lambda: "TO-DO",
        floor_enforced=lambda: True,
        harness_kind=lambda: "claude_code",
        product_link=lambda: type("_L", (), {"kind": "off", "active": False})(),
    )
    base.update(over)
    return Probes(**base)


def _line(report):
    return next((f for f in report.findings if f.check == "former_names"), None)


def test_the_doctor_lists_each_former_name_with_its_new_one(tmp_path):
    asked = []

    def former(checkout):
        asked.append(checkout)
        return still_in_use(environment=["OPENFACTORY_FORGE_TOKEN"], checkout=checkout)

    (tmp_path / ".openfactory").mkdir()
    line = _line(diagnose(_probes(checkout=lambda: tmp_path, former_names=former)))

    assert asked == [tmp_path]
    assert line is not None and line.ok
    assert "`OPENFACTORY_FORGE_TOKEN` → `BEEVERFORGE_FORGE_TOKEN`" in line.message
    assert "`.openfactory/` → `.beeverforge/`" in line.message
    assert line.note


def test_a_deployment_with_no_former_name_has_no_such_line():
    assert _line(diagnose(_probes(former_names=lambda checkout: []))) is None


def test_the_line_is_a_pass_so_it_never_makes_a_deployment_not_ready():
    found = still_in_use(environment=["OPENFACTORY_FORGE_TOKEN"])
    without = diagnose(_probes())
    with_line = diagnose(_probes(former_names=lambda checkout: found))

    assert _line(with_line).ok
    assert with_line.ok == without.ok
