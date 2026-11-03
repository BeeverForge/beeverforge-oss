"""#363: the published worker image, run as one long-lived container, runs the worker AND the panel.

`beeverforge worker --with-panel` is that container's command. Its whole contract is held here
with fake children and a fake clock — no process is started and nothing waits:

  - the plan is the worker and the panel, and it needs nothing but the engine's variables;
  - the command ends with the status of whichever process ended, so a restart policy sees it;
  - SIGTERM, what `docker stop` sends through `tini`, reaches both children;
  - the panel can be held to the loopback, for a container that publishes no port;
  - it cannot start an OPEN panel off the loopback: with no panel sign-in configured, a
    `--panel-host` other than the loopback — the default `0.0.0.0` included — is refused by name;
  - with `BEEVERFORGE_LOG_FORMAT=json` the supervisor's own lines are JSON lines, as the worker's
    and the panel's are;
  - `docs/operations.md` shows the command beside the compose stack's, the flags it names exist,
    and the command it documents passes a panel token and starts as written.
"""

from __future__ import annotations

import json
import re
import shlex
import signal
import sys
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from beeverforge.cli import app
from beeverforge.identity.local import CLOSING_ENVS
from beeverforge.observability import logs
from beeverforge.runtime import host
from tests.test_every_process_the_deployment_starts_logs_with_a_time_a_level_and_a_name import (
    _a_fresh_process,
)

ROOT = Path(__file__).resolve().parents[1]

ENGINE_VARS = {"TEMPORAL_ADDRESS": "engine.example:7233",
               "TEMPORAL_NAMESPACE": "acme.a1b2c",
               "TEMPORAL_API_KEY": "key-not-a-secret"}

#: The two variables a person signs in to the panel with, and a value of each's own shape.
PANEL_TOKENS = {"BEEVERFORGE_PANEL_TOKEN": "a-panel-token-not-a-secret",
                "BEEVERFORGE_PANEL_TOKENS": "a-token-not-a-secret:alice:Alice Ferreira"}

#: The real supervisor, kept before `engine_only` captures it, for the case that drives it.
RUN = host.run


class _Child:
    """A child double: `poll` answers `ends_with` once it is set, None until then."""

    def __init__(self, name: str, log: list[str], ends_with: int | None = None) -> None:
        self.name, self.log, self.pid = name, log, 4000 + len(log)
        self.ends_with = ends_with
        self.returncode: int | None = None

    def poll(self):
        if self.ends_with is not None:
            self.returncode = self.ends_with
        return self.returncode

    def terminate(self):
        self.log.append(f"terminate {self.name}")

    def kill(self):
        self.log.append(f"kill {self.name}")

    def wait(self, timeout=None):
        return self.returncode


def _fake_processes(monkeypatch, *, ends: dict[str, int] | None = None) -> list[str]:
    """Patch `Popen` so every child is a double named by its argv's first word; the reaper (the
    argv with `--reap`) is its own double, so what is asserted about it is about IT."""
    log: list[str] = []
    ends = ends or {}

    def popen(argv, *_a, **_kw):
        name = "reaper" if "--reap" in argv else argv[0]
        return _Child(name, log, ends.get(name))

    monkeypatch.setattr(host.subprocess, "Popen", popen)
    monkeypatch.setattr(host.time, "sleep", lambda _s: None)
    return log


@pytest.mark.parametrize(("returncode", "status"), [(7, 7), (-15, 143)])
def test_the_set_ends_with_the_status_of_the_child_that_ended(monkeypatch, returncode, status):
    """It returned 0 whatever ended it, so a container whose worker died exited clean and a
    restart policy of `on-failure` never restarted it. A child killed by signal N is 128+N, as a
    shell reports it."""
    log = _fake_processes(monkeypatch, ends={"worker": returncode})
    said: list[str] = []

    code = host.run([("worker", ["worker"]), ("panel", ["panel"])], say=said.append, grace=0.01)

    assert code == status
    assert "terminate panel" in log, log
    assert any(f"worker exited ({returncode})" in line for line in said), said


def test_a_SIGTERM_stops_the_worker_and_the_panel_both(monkeypatch):
    """`docker stop` sends SIGTERM to `tini`, which hands it to this process: both children are
    asked to stop, the reaper is killed, and a stop that was ASKED for is a clean exit."""
    log = _fake_processes(monkeypatch)
    calls: list[float] = []

    def sleep(seconds):
        calls.append(seconds)
        if len(calls) == 2:            # the first is the reaper's check; this is the loop's
            signal.raise_signal(signal.SIGTERM)

    monkeypatch.setattr(host.time, "sleep", sleep)

    def before(_signum, _frame):
        raise AssertionError("the supervisor's own handler was not the one installed")

    previous = signal.signal(signal.SIGTERM, before)
    try:
        code = host.run([("worker", ["worker"]), ("panel", ["panel"])], say=lambda _l: None,
                        grace=0.01)
        restored = signal.getsignal(signal.SIGTERM)
    finally:
        signal.signal(signal.SIGTERM, previous)

    assert code == 0
    assert "terminate worker" in log and "terminate panel" in log, log
    assert "kill reaper" in log, log
    assert restored is before, "the handler the supervisor replaced was not put back"


@pytest.fixture
def engine_only(monkeypatch):
    """Only the engine's three variables and a panel token, an install with the client, and NO
    `temporal` binary — the container's case as `docs/operations.md` documents it. No other
    credential closes the panel's door: the cases about an open panel take the token away and
    nothing else is left to close it. `host.run` is captured, never run."""
    for var in ("TEMPORAL_ADDRESS", "TEMPORAL_ENDPOINT", "TEMPORAL_NAMESPACE", "TEMPORAL_API_KEY",
                "TEMPORAL_PORT", "PANEL_PORT", "BEEVERFORGE_PANEL_URL", "BEEVERFORGE_IDENTITY",
                *CLOSING_ENVS):
        monkeypatch.delenv(var, raising=False)
    for var, value in ENGINE_VARS.items():
        monkeypatch.setenv(var, value)
    monkeypatch.setenv("BEEVERFORGE_PANEL_TOKEN", PANEL_TOKENS["BEEVERFORGE_PANEL_TOKEN"])
    monkeypatch.setattr(host, "the_client", lambda: True)
    monkeypatch.setattr(host, "the_engine", lambda: None)
    monkeypatch.setattr(host.shutil, "which", lambda _name: None)
    seen: dict = {"code": 0}

    def run(plan, *, say, env=None, grace=host.GRACE_S):
        seen.update(plan=plan, env=env)
        return seen["code"]

    monkeypatch.setattr(host, "run", run)
    return seen


def _panel_argv(seen: dict) -> list[str]:
    return dict(seen["plan"])["panel"]


def test_worker_with_panel_runs_the_worker_and_the_panel(engine_only):
    result = CliRunner().invoke(app, ["worker", "--with-panel"])

    assert result.exit_code == 0, result.output
    assert [name for name, _ in engine_only["plan"]] == ["worker", "panel"]
    assert dict(engine_only["plan"])["worker"] == [
        sys.executable, "-m", "beeverforge.runtime.temporal.worker"]
    panel = _panel_argv(engine_only)
    assert panel[:4] == [sys.executable, "-m", "beeverforge.cli", "serve"], panel
    assert panel[panel.index("--host") + 1] == "0.0.0.0"
    assert panel[panel.index("--port") + 1] == "8787"
    for var, value in ENGINE_VARS.items():
        assert engine_only["env"][var] == value, var


def test_worker_with_panel_exits_with_the_status_of_the_process_that_ended(engine_only):
    engine_only["code"] = 3

    result = CliRunner().invoke(app, ["worker", "--with-panel"])

    assert result.exit_code == 3, result.output


def test_worker_with_panel_without_an_engine_address_is_refused(engine_only, monkeypatch):
    for var in ENGINE_VARS:
        monkeypatch.delenv(var, raising=False)

    result = CliRunner().invoke(app, ["worker", "--with-panel"])

    assert result.exit_code == 1, result.output
    assert "TEMPORAL_ADDRESS" in result.output
    assert "Traceback" not in result.output
    assert "plan" not in engine_only, "the set was started with nowhere for the worker to dial"


def test_the_panel_can_be_told_to_bind_the_loopback_only(engine_only):
    result = CliRunner().invoke(app, ["worker", "--with-panel", "--panel-host", "127.0.0.1"])

    assert result.exit_code == 0, result.output
    panel = _panel_argv(engine_only)
    assert panel[panel.index("--host") + 1] == "127.0.0.1"
    assert "0.0.0.0" not in panel


def _no_panel_token(monkeypatch) -> None:
    for var in PANEL_TOKENS:
        monkeypatch.delenv(var, raising=False)


@pytest.mark.parametrize("flags", [[], ["--panel-host", "0.0.0.0"], ["--panel-host", "::"],
                                   ["--panel-host", "192.0.2.10"]],
                         ids=["the default", "0.0.0.0", "every IPv6 interface", "one address"])
def test_an_open_panel_off_the_loopback_is_refused_by_name(engine_only, monkeypatch, flags):
    """THE DOCUMENTED COMMAND SERVED AN OPEN PANEL ON EVERY INTERFACE (review of #406): the panel
    listened on `0.0.0.0` and no token was passed, and in this mode the open panel is the process
    that holds the worker's credentials. With no panel sign-in configured the set does not start."""
    _no_panel_token(monkeypatch)

    result = CliRunner().invoke(app, ["worker", "--with-panel", *flags])

    assert result.exit_code == 1, result.output
    host_said = flags[1] if flags else "0.0.0.0"
    assert host_said in result.output, result.output
    for remedy in ("BEEVERFORGE_PANEL_TOKEN", "BEEVERFORGE_PANEL_TOKENS",
                   "--panel-host 127.0.0.1"):
        assert remedy in result.output, (remedy, result.output)
    assert "Traceback" not in result.output
    assert "plan" not in engine_only, "the set was started with an open panel off the loopback"


@pytest.mark.parametrize("var", sorted(PANEL_TOKENS))
def test_with_a_panel_token_it_starts_on_every_interface(engine_only, monkeypatch, var):
    _no_panel_token(monkeypatch)
    monkeypatch.setenv(var, PANEL_TOKENS[var])

    result = CliRunner().invoke(app, ["worker", "--with-panel"])

    assert result.exit_code == 0, result.output
    panel = _panel_argv(engine_only)
    assert panel[panel.index("--host") + 1] == "0.0.0.0"


@pytest.mark.parametrize("loopback", ["127.0.0.1", "::1", "localhost"])
def test_on_the_loopback_it_starts_with_no_panel_token(engine_only, monkeypatch, loopback):
    """THE SIDECAR'S CASE: a container that publishes no port, whose panel nothing outside its
    network namespace reaches."""
    _no_panel_token(monkeypatch)

    result = CliRunner().invoke(app, ["worker", "--with-panel", "--panel-host", loopback])

    assert result.exit_code == 0, result.output
    panel = _panel_argv(engine_only)
    assert panel[panel.index("--host") + 1] == loopback


def test_with_json_lines_the_supervisors_own_lines_are_json(engine_only, monkeypatch, capsys):
    """A DEPLOYMENT PROCESS (review of #406): `worker --with-panel` is the container's command, so
    its own lines — where the panel will be, the set started, which child ended it, the stop — sit
    in the container's log beside the worker's and the panel's JSON lines. With JSON on they are
    JSON lines too, and the one that says a child ended the set is an ERROR."""
    from beeverforge import cli

    monkeypatch.setattr(host, "run", RUN)
    _fake_processes(monkeypatch, ends={sys.executable: -15})
    monkeypatch.setenv(logs.FORMAT_VARIABLE, "json")
    with _a_fresh_process(), pytest.raises(typer.Exit) as ended:
        cli._worker_with_panel(panel_host="0.0.0.0", panel_port=None)

    assert ended.value.exit_code == 143
    written = capsys.readouterr()
    assert not written.out.strip(), f"a plain line on stdout: {written.out!r}"
    lines = [json.loads(line) for line in written.err.splitlines() if line.strip()]
    said = {(line["level"], line["message"].split(" (", 1)[0]) for line in lines
            if line["logger"] == cli.log.name}
    assert {("INFO", "the panel will be at http://localhost:8787"),
            ("INFO", "✓ worker, panel — Ctrl-C stops them together."),
            ("ERROR", "✗ worker exited"),
            ("INFO", "stopping…")} <= said, said


def test_worker_without_the_flag_still_runs_the_worker_alone(engine_only, monkeypatch):
    import beeverforge.runtime.temporal.worker as worker

    ran: list[str] = []

    async def born():
        ran.append("worker")

    monkeypatch.setattr(worker, "born", born)

    result = CliRunner().invoke(app, ["worker"])

    assert result.exit_code == 0, result.output
    assert ran == ["worker"]
    assert "plan" not in engine_only, "plain `worker` started the panel too"


@pytest.mark.parametrize("flags", [["--panel-host", "127.0.0.1"], ["--panel-port", "8090"]])
def test_a_panel_flag_without_with_panel_is_refused_not_dropped(engine_only, monkeypatch, flags):
    import beeverforge.runtime.temporal.worker as worker

    ran: list[str] = []

    async def born():
        ran.append("worker")

    monkeypatch.setattr(worker, "born", born)

    result = CliRunner().invoke(app, ["worker", *flags])

    assert result.exit_code == 2, result.output
    assert "--with-panel" in result.output and "no panel is started" in result.output
    assert ran == [], "the worker started alone, and the panel flag was dropped"
    assert "plan" not in engine_only


def _container_section() -> str:
    text = (ROOT / "docs" / "operations.md").read_text()
    sections = re.split(r"(?m)^(?=#{2,3} )", text)
    found = [s for s in sections if "worker --with-panel" in s]
    assert found, "docs/operations.md does not show `worker --with-panel`"
    return found[0]


def _documented_commands(section: str) -> list[list[str]]:
    """Every `docker run` the section shows for `worker --with-panel`, as the shell splits it."""
    blocks = re.findall(r"```bash\n(.*?)```", section, flags=re.S)
    return [shlex.split(block.replace("\\\n", " ")) for block in blocks
            if "worker --with-panel" in block and "docker run" in block]


def test_operations_shows_the_container_command_beside_the_compose_stacks(engine_only,
                                                                            monkeypatch):
    section = _container_section()

    assert "docker compose --env-file .env.compose up" in section
    assert "TEMPORAL_ADDRESS" in section
    assert "--panel-host 127.0.0.1" in section

    # THE DOCUMENTED COMMANDS RUN AS WRITTEN: each is handed to the CLI from `worker` on, so the
    # page cannot name a flag the command does not have — and with only the panel token the
    # command itself passes (`-e NAME` hands on this shell's value), so a page that drops the
    # token documents a command that is refused.
    commands = _documented_commands(section)
    assert len(commands) >= 2, section
    for words in commands:
        passed = {words[i + 1] for i, word in enumerate(words) if word == "-e"}
        assert passed & set(PANEL_TOKENS), (
            "the documented command passes no panel token, so the panel it serves is open: "
            + shlex.join(words))
        _no_panel_token(monkeypatch)
        for var in passed & set(PANEL_TOKENS):
            monkeypatch.setenv(var, PANEL_TOKENS[var])
        result = CliRunner().invoke(app, words[words.index("worker"):])
        assert result.exit_code == 0, (shlex.join(words), result.output)


def test_operations_publishes_the_panel_on_the_loopback(engine_only):
    """`-p 8787:8787` publishes on every interface of the host; the compose stack binds the panel
    to `127.0.0.1` unless the deployment says otherwise, and the page shows the same."""
    for words in _documented_commands(_container_section()):
        published = [words[i + 1] for i, word in enumerate(words) if word == "-p"]
        assert all(port.startswith("127.0.0.1:") for port in published), shlex.join(words)
