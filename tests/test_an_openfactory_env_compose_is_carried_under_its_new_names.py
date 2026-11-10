"""An OpenFactory 0.7 `.env.compose` keeps its values through the installer's upgrade, under
BeeverForge's names (#266).

THE UPGRADE IS A RE-RUN OVER 0.7'S FILE: `install.sh --force` runs `beeverforge init --force`, and
`init` carries every value the file holds (`deployment.carry_over`). A 0.7 file names its rows
`OPENFACTORY_*`, so they were carried under those names, into the "kept" section, while the
`BEEVERFORGE_*` rows compose interpolates stayed empty: the forge token, the panel token, the
concurrency limit, all read as unset by `docker-compose.yml`. Each is now carried as its new name,
and a `BEEVERFORGE_*` value the file already holds wins, as in a process's environment.
"""

from __future__ import annotations

import re

import pytest
from typer.testing import CliRunner

from beeverforge.cli import app
from beeverforge.onboarding.deployment import Answers, carry_over, render

_FLAGS = ["--runtime", "compose", "--forge", "github", "--tracker", "github", "--harness",
          "claude_code", "--github-auth", "token", "--claude-auth", "subscription", "--channel",
          "panel"]

_BOT = "ghp_SOMEONEMARKERbot0000000000000000000000"
_PANEL = "SOMEONEMARKERpanel"


@pytest.fixture(autouse=True)
def _no_login_on_this_machine(monkeypatch, tmp_path):
    monkeypatch.setattr("beeverforge.credentials.discover_forge_token", lambda kind: None)
    monkeypatch.setenv("BEEVERFORGE_WORK_DIR", str(tmp_path / "work"))


def _rows(text: str) -> dict[str, str]:
    return dict(re.findall(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", text, re.MULTILINE))


def _rendered() -> str:
    return render(Answers(runtime="compose", forge="github", tracker="github",
                          harness="claude_code", github_auth="token", claude_auth="subscription",
                          channel="panel", panel_exposed=True)).text


def test_a_0_7_row_is_carried_as_its_new_name():
    previous = f"OPENFACTORY_BOT_TOKEN={_BOT}\nOPENFACTORY_MAX_CONCURRENT_JOBS=2\n"

    text, kept = carry_over(previous, _rendered())

    rows = _rows(text)
    assert rows["BEEVERFORGE_BOT_TOKEN"] == _BOT
    assert rows["BEEVERFORGE_MAX_CONCURRENT_JOBS"] == "2"
    assert not [n for n in rows if n.startswith("OPENFACTORY_")], (
        "a 0.7 row was carried under its old name, which compose never interpolates")
    assert {"BEEVERFORGE_BOT_TOKEN", "BEEVERFORGE_MAX_CONCURRENT_JOBS"} <= set(kept)


def test_the_new_name_the_file_already_holds_wins_over_the_0_7_one():
    previous = "OPENFACTORY_BOT_TOKEN=the-old-one\nBEEVERFORGE_BOT_TOKEN=the-new-one\n"

    text, _ = carry_over(previous, _rendered())

    assert _rows(text)["BEEVERFORGE_BOT_TOKEN"] == "the-new-one"


def test_an_empty_new_name_does_not_hide_the_0_7_value():
    previous = f"BEEVERFORGE_BOT_TOKEN=\nOPENFACTORY_BOT_TOKEN={_BOT}\n"

    text, _ = carry_over(previous, _rendered())

    assert _rows(text)["BEEVERFORGE_BOT_TOKEN"] == _BOT


def test_the_0_7_pin_and_the_rows_the_caller_owns_are_not_carried():
    previous = "OPENFACTORY_VERSION=v0.7.0\nOPENFACTORY_WORK_DIR=/var/lib/openfactory-work\n"

    text, _ = carry_over(previous, _rendered(), ours=frozenset({"BEEVERFORGE_WORK_DIR"}))

    rows = _rows(text)
    assert "BEEVERFORGE_VERSION" not in rows and "OPENFACTORY_VERSION" not in rows
    assert rows.get("BEEVERFORGE_WORK_DIR") != "/var/lib/openfactory-work"


def test_the_installers_upgrade_of_a_0_7_file_keeps_its_credentials(tmp_path):
    dest = tmp_path / ".env.compose"
    dest.write_text(f"OPENFACTORY_BOT_TOKEN={_BOT}\nOPENFACTORY_PANEL_TOKEN={_PANEL}\n"
                    "OPENFACTORY_VERSION=v0.7.0\nPANEL_PORT=8899\n")
    dest.chmod(0o600)

    result = CliRunner().invoke(app, ["init", *_FLAGS, "--panel-exposed", "--out", str(dest),
                                      "--force"])

    assert result.exit_code == 0, result.output
    rows = _rows(dest.read_text())
    assert rows["BEEVERFORGE_BOT_TOKEN"] == _BOT, "the 0.7 forge credential was not carried"
    assert rows["BEEVERFORGE_PANEL_TOKEN"] == _PANEL, (
        "the 0.7 panel token was regenerated, locking out everyone who holds it")
    assert rows["PANEL_PORT"] == "8899"
    assert "fill BEEVERFORGE_BOT_TOKEN" not in result.output, (
        "the to-do list asks for a credential the 0.7 file already holds")
    for value in (_BOT, _PANEL):
        assert value not in result.output, "a carried secret was echoed to the terminal"
