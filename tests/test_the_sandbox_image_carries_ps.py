"""The sandbox image installs procps, so a project whose tests run `ps` or `pgrep` can be proved in it (#567).

The box the repository's own gate runs in is this image, and it had no `ps`: the tests in
`tests/test_the_set_ends_together.py` failed there with `FileNotFoundError: ... 'ps'` and were left to CI.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCKERFILE = ROOT / "docker" / "sandbox.Dockerfile"


def _install_lines() -> list[str]:
    """The `apt-get install` commands, comments dropped and continuations joined."""
    code = "\n".join(line for line in DOCKERFILE.read_text().splitlines()
                     if not line.lstrip().startswith("#"))
    return re.findall(r"apt-get install[^&;\n]*(?:\\\n[^&;\n]*)*", code.replace("\\\n", " \\\n"))


def test_the_sandbox_image_installs_procps():
    installs = " ".join(_install_lines()).replace("\\", " ").split()
    assert "procps" in installs


def test_the_toolchain_record_names_ps():
    assert "/etc/beeverforge-toolchain" in DOCKERFILE.read_text()
    assert "ps=" in DOCKERFILE.read_text()
