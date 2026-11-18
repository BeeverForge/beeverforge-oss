"""Five more readers of a file a person or an operator writes name a file that is not UTF-8.

Each read below used `read_text(encoding="utf-8")`, so bytes saved as Latin-1 or UTF-16 with a
byte-order mark raised `UnicodeDecodeError` out of the caller, and UTF-16 without a mark (valid
UTF-8, because NUL is a code point) was read as text full of NULs. Each now reads bytes through
`beeverforge/util/utf8.py::decode`, and its outcome carries the sentence naming the file, the byte
offset where it stops being UTF-8, and the remedy.

Each read keeps the shape its function already uses for a file it cannot read: the preview shape
of a pull request treats the manifest as having no `preview:` block and logs why; the knowledge
bundle's manifest reads as `None` and logs why; the thresholds file, the evaluation battery and
the fixture's product manifest are refused with their own exception.
"""

from __future__ import annotations

import logging
import unicodedata
from pathlib import Path

import pytest

REMEDY = "save it as UTF-8"

#: the codec each family's editor saves the WHOLE file in, from its first byte
FAMILIES = {
    "Latin-1": "latin-1",
    "UTF-16 with a byte-order mark": "utf-16",
    "UTF-16-LE without a byte-order mark": "utf-16-le",
    # THE TRAP: UTF-16 of ASCII text alone is valid UTF-8, NUL being a code point, so only the
    # decoder's NUL check stops it; the `é` above has the codec stop it first
    "UTF-16-LE without a byte-order mark, ASCII only": "utf-16-le",
}

_ASCII_ONLY = "UTF-16-LE without a byte-order mark, ASCII only"


def _saved(text: str, family: str) -> bytes:
    """`text` as the family's editor saves it, whole: every fixture begins with an ASCII character
    and holds an `é` (dropped in the family that is ASCII only)."""
    assert text[0].isascii() and "é" in text, text
    if family == _ASCII_ONLY:
        text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return text.encode(FAMILIES[family])


def _offset(text: str, family: str) -> int:
    """Where the decoder must say `_saved(text, family)` stops being UTF-8: Latin-1 at the first
    character that is not ASCII; UTF-16 with a mark at its first byte; UTF-16-LE without one at
    the `é`'s low byte; ASCII only at the first NUL, the first character's high byte."""
    first = next(i for i, c in enumerate(text) if not c.isascii())
    return {"Latin-1": first, "UTF-16 with a byte-order mark": 0,
            _ASCII_ONLY: 1}.get(family, 2 * first)


def _named(said: str, shown: str, at: int) -> None:
    """One sentence naming the file, the offset and the remedy — no exception's words."""
    assert f"`{shown}`" in said, said
    assert said.count(shown) == 1, said
    assert f"offset {at} (" in said, said
    assert REMEDY in said, said
    assert "\n" not in said, said
    assert "Error" not in said, said


def _put(path: Path, raw: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return path


def _logged(caplog, code: str) -> str:
    said = [r.getMessage() for r in caplog.records if code in r.getMessage()]
    assert len(said) == 1, [r.getMessage() for r in caplog.records]
    assert all(r.levelno == logging.WARNING for r in caplog.records if code in r.getMessage())
    return said[0].split(f"{code} ", 1)[1]


# ── the preview shape a pull request carries: the repository's manifest ─────────────────────────

@pytest.mark.parametrize("family", FAMILIES)
def test_the_preview_shape_treats_a_manifest_not_in_utf8_as_no_preview_block(
        tmp_path, caplog, family):
    from types import SimpleNamespace

    from beeverforge import namespace
    from beeverforge.adapters.sandbox.base import Workspace
    from beeverforge.orchestrator.machine import JobRunner

    rel = ".beeverforge/project.yaml"
    text = "name: podbeam\npreview:\n  compose: [deploy/café.yml]\n"
    _put(tmp_path / rel, _saved(text, family))
    holder = SimpleNamespace(_protected=(namespace.MANIFEST,),
                             _SHAPE_NAMES=JobRunner._SHAPE_NAMES)
    ws = Workspace(path=tmp_path, host_path=tmp_path, branch="b", base_branch="main")

    with caplog.at_level(logging.WARNING):
        shape = JobRunner._preview_shape(holder, ws)

    assert shape == []
    _named(_logged(caplog, "BEEVERFORGE_PREVIEW_SHAPE_NOT_UTF8"), rel, _offset(text, family))


# ── the knowledge bundle's manifest ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("family", FAMILIES)
def test_the_knowledge_manifest_not_in_utf8_reads_as_none(tmp_path, caplog, family):
    from beeverforge.knowledge.okf import OKF_MANIFEST_FILE, read_manifest

    text = "version: 1\nname: café\n"
    path = _put(tmp_path / OKF_MANIFEST_FILE, _saved(text, family))

    with caplog.at_level(logging.WARNING):
        manifest = read_manifest(tmp_path)

    assert manifest is None
    _named(_logged(caplog, "BEEVERFORGE_OKF_MANIFEST_NOT_UTF8"), str(path), _offset(text, family))


# ── the operator's thresholds file ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("family", FAMILIES)
def test_thresholds_not_in_utf8_are_refused_by_name(tmp_path, family):
    from beeverforge.certify.verify import THRESHOLDS_SCHEMA, ThresholdsError, load_thresholds

    text = f"schema: {THRESHOLDS_SCHEMA}\n# café\nthresholds: []\n"
    path = _put(tmp_path / "thresholds.yaml", _saved(text, family))

    with pytest.raises(ThresholdsError) as refused:
        load_thresholds(path)

    _named(str(refused.value), str(path), _offset(text, family))


# ── an evaluation battery ───────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("family", FAMILIES)
def test_a_battery_not_in_utf8_is_refused_by_name(tmp_path, family):
    from beeverforge.product.evaluation.battery import BatteryRefused, load_battery

    text = "questions:\n  - id: q1\n    ask: o que é?\n"
    path = _put(tmp_path / "battery.yaml", _saved(text, family))

    with pytest.raises(BatteryRefused) as refused:
        load_battery(path)

    _named(str(refused.value), str(path), _offset(text, family))


# ── a fixture's context repository: the product manifest ────────────────────────────────────────

@pytest.mark.parametrize("family", FAMILIES)
def test_a_fixture_manifest_not_in_utf8_is_refused_by_name(tmp_path, family):
    from beeverforge import namespace
    from beeverforge.product.evaluation.run import FixtureRefused, fixture_name

    text = "product: café\n"
    manifest = _put(tmp_path / "context" / namespace.PRODUCT_MANIFEST, _saved(text, family))

    with pytest.raises(FixtureRefused) as refused:
        fixture_name(tmp_path)

    _named(str(refused.value), str(manifest), _offset(text, family))
