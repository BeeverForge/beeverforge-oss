"""The sandbox image installs procps, so a project whose tests run `ps` or `pgrep` can be proved in it (#567).

The box the repository's own gate runs in is this image, and it had no `ps`: the tests in
`tests/test_the_set_ends_together.py` failed there with `FileNotFoundError: ... 'ps'` and were left to CI.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCKERFILE = ROOT / "docker" / "sandbox.Dockerfile"


def _run_blocks() -> list[str]:
    """Each `RUN` instruction as one line: continuations joined, comment lines dropped."""
    blocks: list[str] = []
    current: str | None = None
    for raw in DOCKERFILE.read_text().splitlines():
        line = raw.strip()
        if current is None:
            if re.match(r"RUN\s", line):
                current = line[3:].strip()
            else:
                continue
        elif line.startswith("#") or not line:
            continue
        else:
            current += " " + line
        if current.endswith("\\"):
            current = current[:-1].rstrip()
        else:
            blocks.append(current)
            current = None
    if current is not None:
        blocks.append(current)
    return blocks


def _installed_packages() -> set[str]:
    """The words after `apt-get install` in a RUN block, up to the next shell operator."""
    packages: set[str] = set()
    for block in _run_blocks():
        for command in re.split(r"&&|;|\|", block):
            words = command.split()
            if words[:2] == ["apt-get", "install"]:
                packages.update(w for w in words[2:] if not w.startswith("-"))
    return packages


def test_the_sandbox_image_installs_procps():
    assert "procps" in _installed_packages()


def test_the_toolchain_record_names_ps():
    writes = [b for b in _run_blocks() if "> /etc/beeverforge-toolchain" in b]
    assert writes
    assert any('echo "ps=' in b for b in writes)
