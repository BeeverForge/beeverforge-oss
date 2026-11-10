"""An OpenFactory 0.7 machine's operator files are read where 0.7 left them (#266).

WHAT A 0.7 MACHINE HAS. `~/.openfactory/` holds the registry, the approver store, the resume
handles, the gate key, the board database and the one-machine deployment's `env`; the journals of
a project registered by its checkout sit beside it, in `.openfactory-logs/<name>`. BeeverForge
looked only under `~/.beeverforge/` and `.beeverforge-logs/`, so an upgrade in place started with
no project registered, none of the `env` file's settings, and journals the panel could not tail.

THE RULE IS THE REPOSITORY FOLDER'S (#265): the current name when it is there, the former one when
it is the only one — read and written there — and the current name on a machine with neither.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from beeverforge import approvals, namespace, paths
from beeverforge.contracts.project import Project
from beeverforge.registry import ProjectRegistry


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    for name in ("BEEVERFORGE_REGISTRY", "BEEVERFORGE_APPROVERS", "BEEVERFORGE_LOG_DIR"):
        monkeypatch.delenv(name, raising=False)
    return h


def test_a_machine_with_only_the_0_7_directory_is_read_there(home):
    (home / ".openfactory").mkdir()

    assert namespace.operator_dir() == home / ".openfactory"
    assert namespace.operator_path("registry.yaml") == home / ".openfactory" / "registry.yaml"
    assert ProjectRegistry().path == home / ".openfactory" / "registry.yaml"
    assert approvals._store_path() == home / ".openfactory" / "approvers.json"
    assert not namespace.stale_former_operator_dir()


def test_the_current_directory_wins_and_the_0_7_one_is_then_stale(home):
    (home / ".openfactory").mkdir()
    (home / ".beeverforge").mkdir()

    assert namespace.operator_dir() == home / ".beeverforge"
    assert ProjectRegistry().path == home / ".beeverforge" / "registry.yaml"
    assert namespace.stale_former_operator_dir()


def test_a_machine_with_neither_gets_the_current_name(home):
    assert namespace.operator_dir() == home / ".beeverforge"
    assert not namespace.stale_former_operator_dir()


def test_a_file_named_like_the_directory_is_not_the_directory(home):
    (home / ".openfactory").write_text("not a directory")

    assert namespace.operator_dir() == home / ".beeverforge"


def test_the_0_7_env_file_is_loaded_by_every_command(home, monkeypatch, tmp_path):
    from beeverforge import cli

    (home / ".openfactory").mkdir()
    (home / ".openfactory" / "env").write_text("BEEVERFORGE_SOMEONE_SETTING=from-the-0-7-file\n")
    monkeypatch.delenv("BEEVERFORGE_SOMEONE_SETTING", raising=False)
    monkeypatch.chdir(tmp_path)  # no `.env` here to answer first

    try:
        cli._load_environment()
        assert os.environ.get("BEEVERFORGE_SOMEONE_SETTING") == "from-the-0-7-file"
    finally:
        os.environ.pop("BEEVERFORGE_SOMEONE_SETTING", None)


def test_certify_finds_the_0_7_env_file_and_names_it_without_its_path(home, tmp_path):
    from beeverforge.certify import pack

    (home / ".openfactory").mkdir()
    (home / ".openfactory" / "env").write_text("X=1\n")
    (home / ".openfactory" / "env").chmod(0o600)

    found = pack._env_file(tmp_path)

    assert found.name == "~/.openfactory/env"
    assert found.exists and found.mode == 0o600


def test_the_0_7_env_files_name_is_kept_by_the_redactor():
    from beeverforge.certify.redact import PLATFORM_WORDS

    assert "~/.openfactory/env" in PLATFORM_WORDS


def _project(checkout: Path) -> Project:
    return Project(name="someone-app", repo_path=str(checkout))


def test_a_0_7_checkouts_journals_are_read_where_0_7_wrote_them(home, tmp_path):
    checkout = tmp_path / "work" / "app"
    checkout.mkdir(parents=True)
    former = tmp_path / "work" / ".openfactory-logs" / "someone-app"
    former.mkdir(parents=True)

    assert paths.project_log_dir(_project(checkout)) == former


def test_once_the_current_journal_directory_exists_it_wins(home, tmp_path):
    checkout = tmp_path / "work" / "app"
    checkout.mkdir(parents=True)
    (tmp_path / "work" / ".openfactory-logs" / "someone-app").mkdir(parents=True)
    current = tmp_path / "work" / ".beeverforge-logs" / "someone-app"
    current.mkdir(parents=True)

    assert paths.project_log_dir(_project(checkout)) == current


def test_a_checkout_with_no_journals_yet_gets_the_current_name(home, tmp_path):
    checkout = tmp_path / "work" / "app"
    checkout.mkdir(parents=True)

    assert paths.project_log_dir(_project(checkout)) == (
        tmp_path / "work" / ".beeverforge-logs" / "someone-app")


# THE OTHER TWO READERS OF THE HOST FILE: `init --runtime local` writes it, `up` keeps its state
# beside it, and doctor's remedy for a refused `up` names it. Each was left on `~/.beeverforge/`
# once; on a 0.7 machine `init` then made the new directory, which hides the 0.7 one for good.

def _local_init():
    return ("init", "--runtime", "local", "--forge", "local", "--tracker", "local",
            "--harness", "claude_code", "--channel", "panel", "--panel-local")


def test_init_writes_the_host_file_into_the_0_7_directory(home, tmp_path, monkeypatch):
    import sys
    sys.path.insert(0, "tests")
    from one_machine import cli

    (home / ".openfactory").mkdir()
    monkeypatch.chdir(tmp_path)

    code, out = cli(*_local_init())

    assert code == 0, out
    assert (home / ".openfactory" / "env").exists(), out
    assert not (home / ".beeverforge").exists(), "init made the directory that hides 0.7's"


def test_up_keeps_its_state_in_the_0_7_directory(home, monkeypatch):
    from typer.testing import CliRunner

    from beeverforge import cli
    from beeverforge.listeners import CannotHonour
    from beeverforge.runtime import host

    (home / ".openfactory").mkdir()
    seen = {}

    def deployment(*, state, **_):
        seen["state"] = state
        raise CannotHonour("stop here")

    monkeypatch.setattr(host, "durable_half", lambda asked: (None, ""))
    monkeypatch.setattr(host, "deployment", deployment)

    CliRunner().invoke(cli.app, ["up", "--no-engine"])

    assert seen.get("state") == home / ".openfactory"
    assert not (home / ".beeverforge").exists()


def test_doctors_remedy_for_a_refused_up_names_the_0_7_file(home):
    from beeverforge import doctor

    (home / ".openfactory").mkdir()
    # Only `processes` is read by this check, so only it is given.
    probes = SimpleNamespace(processes=lambda: {"refused": (False, "a port is taken")})

    found = doctor._processes(probes)

    assert "~/.openfactory/env" in found.remedy
    assert "~/.beeverforge/env" not in found.remedy
