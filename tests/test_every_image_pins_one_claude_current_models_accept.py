"""Every image pins one `claude`, and it is a version current Claude models accept (#436).

WHAT WAS WRONG: the three places that install the CLI (`base-python.Dockerfile`'s box copy,
`worker.Dockerfile`'s toolbox `ARG HARNESS_CLAUDE` and the worker's own copy) all pinned 2.1.219.
Current models refuse that version: every harness call answered `API Error: 400 Claude Code 2.1.219
does not support this model; version 2.1.280 or newer is required`, and the installer, `doctor`
and `box prove` all stayed green. The pin is what a new image installs, so a hand upgrade in a
running container never reached a fresh install.

WHAT IS HELD HERE, read from the Dockerfiles' instructions (never their comments):
  · every install of `@anthropic-ai/claude-code` names an exact version, and there are three;
  · the three are the same version, so the worker's passes and the boxes run one CLI;
  · it is the version the parser fixtures were measured on (`tests/claude_cli_output.py`), so the
    shapes the tests read are the shapes the shipped CLI prints;
  · it is at least the oldest version the API named as accepted.
"""

from __future__ import annotations

import re

from tests import claude_cli_output as cli
from tests.dockerfiles import DOCKER, instructions

#: The oldest version the API accepted when 2.1.219 was refused (#436, measured 2026-11-04).
OLDEST_ACCEPTED = (2, 1, 280)

#: Every place an image installs the CLI: the base image's box copy, the toolbox stage's build
#: argument and the worker's own copy.
SITES = ("base-python.Dockerfile", "worker.Dockerfile")
#: The package spec an install names (`…/claude-code@<version>`, or bare), never a path that runs
#: through the package's folder (`node_modules/@anthropic-ai/claude-code/bin/…`).
_INSTALL = re.compile(r"(?<![\w/])@anthropic-ai/claude-code(?:@(\S+)|(?![\w/-]))")


def _pins() -> list[tuple[str, str | None]]:
    found = []
    for name in SITES:
        text = instructions((DOCKER / name).read_text(encoding="utf-8"))
        found += [(name, m.group(1)) for m in _INSTALL.finditer(text)]
    return found


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def test_every_install_names_an_exact_version():
    pins = _pins()
    assert len(pins) == 3, f"expected the box, toolbox and worker installs, found {pins}"
    loose = [(name, v) for name, v in pins
             if v is None or not re.fullmatch(r"\d+\.\d+\.\d+", v)]
    assert loose == [], f"an install that is not pinned to an exact version: {loose}"


def test_the_box_the_toolbox_and_the_worker_run_one_version():
    assert {v for _, v in _pins()} == {cli.PINNED}, (
        f"the images pin {_pins()}, the parser fixtures were measured on {cli.PINNED}")


def test_the_fixtures_were_measured_on_the_pinned_version():
    assert cli.FIXTURES.name == cli.PINNED
    assert (cli.FIXTURES / "json.stdout.jsonl").is_file()
    assert (cli.FIXTURES / "stream-json-verbose.stdout.jsonl").is_file()


def test_the_pin_is_a_version_current_models_accept():
    assert _version(cli.PINNED) >= OLDEST_ACCEPTED, (
        f"{cli.PINNED} is older than {'.'.join(map(str, OLDEST_ACCEPTED))}, the oldest version "
        "the API accepts")
