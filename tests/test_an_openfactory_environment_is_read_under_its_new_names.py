"""An OpenFactory 0.7 deployment's environment is read under BeeverForge's names until 1.1 (#264).

A deployment running 0.7 has an environment full of `OPENFACTORY_*`, and must upgrade without
editing anything first. What is held here:

  · THE RULE, on `former_names.carry_over`: an `OPENFACTORY_<SUFFIX>` is read as
    `BEEVERFORGE_<SUFFIX>` when the new name is unset; the new name wins when both are set; only
    that exact prefix is read, its suffix verbatim; and the old name leaves the environment.
  · THE WARNING: one line naming the old names and the remedy, never a value — many of these
    variables are credentials.
  · THE BOX: a credential set under its old name is withheld from a worktree workload, through
    the real entry point and the real `_scrubbed_env`, with no deny list naming the old spelling.
  · EVERY ENTRY: the command line (every command, `serve` and `worker` among them), the panel's
    `.env`, the worker's own start, the boxed job, and the two engine scripts carry the old names
    over — DRIVEN where a test can run the entry, and read off the tree where it cannot, with
    every module a process can be started from accounted for.
"""

from __future__ import annotations

import ast
import asyncio
import json
import logging
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from beeverforge import environ, former_names
from beeverforge.adapters.sandbox.worktree import _FORGE_CRED_VARS, _scrubbed_env
from beeverforge.observability import logs
from tests.test_every_process_the_deployment_starts_logs_with_a_time_a_level_and_a_name import (
    _a_fresh_process,
)
from tests.the_tree_read_once import parsed

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "beeverforge"

#: Obviously not a credential: what a test sets wherever a value is needed.
FAKE = "fake-value-for-someone"


def _absent(monkeypatch, *names: str) -> None:
    """Each name unset for this test, and put back as it was afterwards — set first, so the
    monkeypatch records it even when it was not there to begin with."""
    for name in names:
        monkeypatch.setenv(name, "placeholder")
        monkeypatch.delenv(name)


# ── the rule ────────────────────────────────────────────────────────────────────────────────────

def test_an_old_name_alone_is_read_under_the_new_one_and_leaves():
    env = {"OPENFACTORY_GH_APP_ID": "12345", "PATH": "/bin"}

    done = former_names.carry_over(env)

    assert env == {"BEEVERFORGE_GH_APP_ID": "12345", "PATH": "/bin"}
    assert done.carried == ("OPENFACTORY_GH_APP_ID",) and done.ignored == ()


def test_the_new_name_wins_when_both_are_set_and_the_old_one_is_named():
    env = {"OPENFACTORY_SANDBOX": "worktree", "BEEVERFORGE_SANDBOX": "container"}

    done = former_names.carry_over(env)

    assert env == {"BEEVERFORGE_SANDBOX": "container"}
    assert done.ignored == ("OPENFACTORY_SANDBOX",) and done.carried == ()


def test_an_empty_new_name_still_wins():
    """`BEEVERFORGE_APPROVERS=` is how the approvers command withholds the variable from a child
    (`approvals.py`): set and empty is set."""
    env = {"OPENFACTORY_APPROVERS": '{"someone": "fake-hash"}', "BEEVERFORGE_APPROVERS": ""}

    former_names.carry_over(env)

    assert env == {"BEEVERFORGE_APPROVERS": ""}


def test_the_same_value_under_both_names_says_nothing():
    """A deployment that already renamed, or a `.env` read a second time by the same process:
    nothing was ignored, so nothing is said — and the old name still leaves."""
    env = {"OPENFACTORY_SANDBOX": "worktree", "BEEVERFORGE_SANDBOX": "worktree"}

    done = former_names.carry_over(env)

    assert env == {"BEEVERFORGE_SANDBOX": "worktree"}
    assert not done and done.sentence() == ""


def test_only_the_exact_prefix_is_read_and_the_suffix_is_kept_verbatim():
    others = {"OPENFACTORYX_TOKEN": "a", "MY_OPENFACTORY_TOKEN": "b", "openfactory_token": "c",
              "OPENFACTORY_": "d"}
    env = {**others, "OPENFACTORY_GH_APP_INSTALLATION_ID": "7"}

    former_names.carry_over(env)

    assert env == {**others, "BEEVERFORGE_GH_APP_INSTALLATION_ID": "7"}


def test_the_process_environment_is_the_default(monkeypatch):
    _absent(monkeypatch, "BEEVERFORGE_REPOS_DIR")
    monkeypatch.setenv("OPENFACTORY_REPOS_DIR", "/srv/someone/repos")

    former_names.carry_over()

    assert os.environ.get("BEEVERFORGE_REPOS_DIR") == "/srv/someone/repos"
    assert "OPENFACTORY_REPOS_DIR" not in os.environ


# ── the warning ─────────────────────────────────────────────────────────────────────────────────

def test_one_warning_names_the_old_names_and_the_remedy_and_no_value(caplog):
    secret = "fake-secret-for-someone"
    env = {"OPENFACTORY_BOT_TOKEN": secret, "OPENFACTORY_SANDBOX": "worktree-for-someone",
           "BEEVERFORGE_SANDBOX": "container"}

    with caplog.at_level(logging.WARNING, logger="beeverforge.environment"):
        former_names.warn(former_names.carry_over(env))

    said = [r for r in caplog.records if r.name == "beeverforge.environment"]
    assert len(said) == 1 and said[0].levelno == logging.WARNING, said
    line = said[0].getMessage()
    assert "OPENFACTORY_BOT_TOKEN" in line and "OPENFACTORY_SANDBOX" in line, line
    assert "rename" in line and former_names.LAST_READ_BEFORE in line, line
    assert secret not in line and "worktree-for-someone" not in line, (
        f"the warning printed a value: {line}")


def test_a_deployment_that_asked_for_json_lines_reads_the_warning_as_one(monkeypatch, capsys):
    """Said before any log is set up — the command line's callback runs before `serve` sets up
    the panel's — the warning would reach stderr as a bare line among the JSON ones."""
    _absent(monkeypatch, logs.LEVEL_VARIABLE, logs.DEPLOYMENT_VARIABLE)
    monkeypatch.setenv(logs.FORMAT_VARIABLE, "json")

    with _a_fresh_process():
        former_names.warn(former_names.carry_over({"OPENFACTORY_SANDBOX": "worktree"}))

    lines = [json.loads(line) for line in capsys.readouterr().err.splitlines() if line.strip()]
    assert [(line["level"], line["logger"]) for line in lines] == [
        ("WARNING", "beeverforge.environment")], lines


def test_nothing_carried_is_nothing_said(caplog):
    with caplog.at_level(logging.DEBUG):
        former_names.warn(former_names.carry_over({"BEEVERFORGE_SANDBOX": "container"}))

    assert not [r for r in caplog.records if r.name == "beeverforge.environment"]


# ── the box ─────────────────────────────────────────────────────────────────────────────────────

def test_a_credential_under_its_old_name_does_not_reach_a_worktree_workload(monkeypatch):
    """Through the real entry (the command line's callback) and the real scrub. The scrub's deny
    list names the new spelling only; the old one is withheld because the entry removed it."""
    from beeverforge import cli

    forge = "BEEVERFORGE_FORGE_TOKEN"
    assert forge in _FORGE_CRED_VARS
    old = former_names.FORMER_PREFIX + forge.removeprefix(environ.ENV_PREFIX)
    assert old not in _FORGE_CRED_VARS, "a deny list names the old spelling: this measures nothing"
    _absent(monkeypatch, forge)
    monkeypatch.setenv(old, FAKE)

    cli._main()
    env = _scrubbed_env()

    assert old not in env and forge not in env, sorted(k for k in env if k.endswith("_TOKEN"))
    assert os.environ.get(forge) == FAKE, "the entry did not read the old name"


# ── every entry, driven ─────────────────────────────────────────────────────────────────────────

def test_a_command_reads_the_old_names_from_the_deployments_env_file(monkeypatch, tmp_path):
    """`beeverforge project list`, end to end: the registry is named ONLY by the old name, and only
    in `~/.beeverforge/env`, which the command line loads before it carries — so it is read."""
    registry = tmp_path / "registry.yaml"
    registry.write_text(f"projects:\n  someone-app:\n    name: someone-app\n"
                        f"    repo_path: {tmp_path}\n")
    _absent(monkeypatch, "BEEVERFORGE_REGISTRY", "OPENFACTORY_REGISTRY")
    host_env = Path(os.environ["HOME"]) / ".beeverforge" / "env"
    host_env.parent.mkdir(parents=True, exist_ok=True)
    host_env.write_text(f"OPENFACTORY_REGISTRY={registry}\n")

    from beeverforge.cli import app

    result = CliRunner().invoke(app, ["project", "list"])

    assert result.exit_code == 0, result.output
    assert "someone-app" in result.output, result.output
    assert "OPENFACTORY_REGISTRY" not in os.environ


def test_the_panel_carries_what_its_own_env_load_finds(monkeypatch):
    """`serve` loads `.env` again for the panel; what is there under an old name is carried."""
    import uvicorn

    from beeverforge import cli

    _absent(monkeypatch, "BEEVERFORGE_PLATFORM_NAME")
    monkeypatch.setenv("OPENFACTORY_PLATFORM_NAME", "Someone's Factory")
    monkeypatch.setattr(uvicorn, "run", lambda *_a, **_k: None)
    monkeypatch.setattr("beeverforge.namespace.announce_build", lambda *_a, **_k: None)

    with _a_fresh_process():
        cli.serve(host="127.0.0.1", port=8787)

    assert os.environ.get("BEEVERFORGE_PLATFORM_NAME") == "Someone's Factory"
    assert "OPENFACTORY_PLATFORM_NAME" not in os.environ


def test_the_worker_carries_before_its_log_is_set_up_and_says_so_in_it(monkeypatch, capsys):
    """`OPENFACTORY_LOG_FORMAT=json` is how a 0.7 worker asked for JSON lines. Carried before the
    log is set up, the worker writes JSON; said after it, the warning is one of those lines."""
    from beeverforge.runtime.temporal import worker

    _absent(monkeypatch, logs.FORMAT_VARIABLE, logs.LEVEL_VARIABLE, logs.DEPLOYMENT_VARIABLE)
    monkeypatch.setenv("OPENFACTORY_LOG_FORMAT", "json")

    async def _up() -> None:
        pass

    monkeypatch.setattr(worker, "main", _up)
    with _a_fresh_process():
        asyncio.run(worker.born())

    lines = [json.loads(line) for line in capsys.readouterr().err.splitlines() if line.strip()]
    warned = [line for line in lines if line["logger"] == "beeverforge.environment"]
    assert len(warned) == 1 and warned[0]["level"] == "WARNING", lines
    assert "OPENFACTORY_LOG_FORMAT" in warned[0]["message"], warned


# ── every entry, read off the tree ──────────────────────────────────────────────────────────────

#: Where each process this package can be started as carries the old names: `(module, function)`.
#: The command line's environment is loaded by the callback that runs before every command, so
#: `serve`, `worker`, `worker --with-panel` and `up` are all behind it; the panel's own `.env` load
#: (`api/app.py`) is `serve`'s second one.
ENTRIES = {
    ("cli.py", "_load_environment"),
    ("api/app.py", "_load_environment"),
    ("runtime/temporal/worker.py", "born"),
    ("runtime/temporal/worker.py", "main"),
    ("runtime/boxed_job.py", "main"),
    ("runtime/temporal/schedule.py", "main"),
    ("runtime/temporal/starter.py", "main"),
}

#: The modules a process can be started from that read no deployment configuration of their
#: own, and why — a module that gains a `__main__` must land in one of these two tables.
NOT_ENTRIES = {
    "observability/health.py": "a container's healthcheck: reads its port from its arguments, "
                               "and runs every few seconds",
    "api/openapi.py": "writes the panel's API description from a checkout",
    "api/events.py": "writes the event schema from a checkout",
    "adapters/extract/pdf.py": "a child of the worker, started with the worker's carried "
                               "environment",
    "runtime/host.py": "the reaper a supervisor leaves behind, a child of a carried process",
    "product/evaluation/__main__.py": "a contributor's battery, run from a checkout",
}


def _function(tree: ast.Module, name: str) -> ast.AST:
    found = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
             and n.name == name]
    assert len(found) == 1, f"no top-level function {name}"
    return found[0]


def _calls(node: ast.AST, attr: str, owner: str | None = None) -> list[int]:
    """The lines `owner.attr(...)` (or a bare `attr(...)` when `owner` is None) is called on."""
    lines = []
    for n in ast.walk(node):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if owner is None and isinstance(f, ast.Name) and f.id == attr:
            lines.append(n.lineno)
        elif (isinstance(f, ast.Attribute) and f.attr == attr and isinstance(f.value, ast.Name)
              and f.value.id == owner):
            lines.append(n.lineno)
    return lines


def _starts_a_process(tree: ast.Module) -> bool:
    for n in tree.body:
        if isinstance(n, ast.If):
            for c in ast.walk(n.test):
                if isinstance(c, ast.Constant) and c.value == "__main__":
                    return True
    return False


def test_every_module_a_process_starts_from_is_accounted_for():
    starts = {p.relative_to(PACKAGE).as_posix() for p in sorted(PACKAGE.rglob("*.py"))
              if _starts_a_process(parsed(p))}
    assert starts, "the scan found no `__main__` module — it has stopped scanning"

    accounted = {m for m, _ in ENTRIES} | set(NOT_ENTRIES)

    assert starts - accounted == set(), (
        f"{sorted(starts - accounted)} can be started as a process: carry the old names there "
        f"(`former_names.carry_over`) or say in NOT_ENTRIES why it reads no configuration")
    assert set(NOT_ENTRIES) - starts == set(), f"{sorted(set(NOT_ENTRIES) - starts)} start no process"


@pytest.mark.parametrize("module,function", sorted(ENTRIES))
def test_each_entry_carries_the_old_names_and_says_so(module, function):
    body = _function(parsed(PACKAGE / module), function)

    carried = _calls(body, "carry_over", "former_names")
    said = _calls(body, "warn", "former_names")

    assert carried, f"{module}:{function} does not carry the old names over"
    assert said, f"{module}:{function} carries the old names over and says nothing"
    loaded = _calls(body, "load_dotenv")
    assert not loaded or max(carried) > max(loaded), (
        f"{module}:{function} carries before it loads `.env`, so a 0.7 `.env` is not carried")


def test_every_function_that_loads_an_env_file_carries_after_it():
    """Derived, not listed: a new place that loads `.env` is a new place an old name arrives."""
    missing = []
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = parsed(path)
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            loaded = _calls(fn, "load_dotenv")
            carried = _calls(fn, "carry_over", "former_names")
            if loaded and not (carried and max(carried) > max(loaded)):
                missing.append(f"{path.relative_to(ROOT)}:{fn.name}")
    assert missing == [], f"these load `.env` and do not carry its old names after: {missing}"


def test_the_worker_carries_before_its_log_is_set_up():
    body = _function(parsed(PACKAGE / "runtime/temporal/worker.py"), "born")

    carried = _calls(body, "carry_over", "former_names")
    configured = _calls(body, "configure", "logs")

    assert carried and configured and min(carried) < min(configured), (
        "the worker sets up its log before it reads `OPENFACTORY_LOG_FORMAT`")


def test_the_boxed_job_carries_before_it_reads_the_environment():
    body = _function(parsed(PACKAGE / "runtime/boxed_job.py"), "main")

    carried = _calls(body, "carry_over", "former_names")
    reads = [n.lineno for n in ast.walk(body) if isinstance(n, ast.Attribute)
             and n.attr == "environ"]

    assert carried and reads and min(carried) < min(reads)


# ── no add-on may take the old prefix ───────────────────────────────────────────────────────────

def test_an_add_on_may_not_name_its_variable_under_the_old_prefix():
    """Its variable would be read under the platform's name and gone before the add-on looked."""
    why = environ.reserved(former_names.FORMER_PREFIX + "SOMEONE_MODEL")

    assert why and former_names.FORMER_PREFIX in why, why
    assert environ.reserved("SOMEONE_ADDON_MODEL") is None  # the twin: a free name stays free
