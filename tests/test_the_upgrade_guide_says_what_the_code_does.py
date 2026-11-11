"""The OpenFactory 0.7 upgrade guide states what the code does — GitHub issue #266.

The guide restates facts the code holds elsewhere: the release that stops reading each former name
(`deprecations.REMOVALS`), the image names (`docker-compose.yml`) and the command that goes back
to 0.7 (`install.sh`). Each is read from its source here, so a change to the code that the guide
does not follow fails.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from beeverforge.deprecations import removed_in

ROOT = Path(__file__).resolve().parent.parent
GUIDE = ROOT / "docs" / "upgrading-from-openfactory.md"


def _rows() -> dict[str, str]:
    """The "what keeps working" table: first cell → last cell."""
    rows = {}
    for line in GUIDE.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.startswith("|") and len(cells) == 3 and not set(cells[0]) <= {"-"}:
            rows[cells[0]] = cells[2]
    return rows


@pytest.mark.parametrize("starts, key", [
    ("`OPENFACTORY_*` variables", "openfactory-environment"),
    ("add-on entry points under `openfactory.adapters`", "openfactory-adapters"),
    ("`import openfactory`", "openfactory-import"),
    ("the `openfactory` command", "openfactory-command"),
    ("an evidence pack (`openfactory.certify/1`)", "openfactory-documents"),
    ("the Temporal task queue `openfactory-jobs`", "openfactory-temporal-names"),
])
def test_each_former_name_is_read_until_the_release_the_register_names(starts, key):
    [until] = [last for first, last in _rows().items() if first.startswith(starts)]

    assert until == removed_in(key)


def test_the_guide_names_the_images_the_compose_file_runs():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    ours = set(re.findall(r"image: ghcr\.io/beeverforge/beeverforge-([a-z]+):", compose))
    [named] = re.findall(r"`ghcr\.io/beeverforge/beeverforge-\{([a-z,]+)\}`",
                         GUIDE.read_text(encoding="utf-8"))

    assert set(named.split(",")) == ours


def test_the_way_back_is_the_command_the_installer_prints():
    installer = (ROOT / "install.sh").read_text(encoding="utf-8")
    [back] = re.findall(r"^BACK_TO_0_7='(.+)'$", installer, flags=re.M)

    assert f"\n{back}\n" in GUIDE.read_text(encoding="utf-8")


def test_the_documentation_index_links_the_guide():
    assert "(upgrading-from-openfactory.md)" in (ROOT / "docs" / "README.md").read_text(
        encoding="utf-8")
