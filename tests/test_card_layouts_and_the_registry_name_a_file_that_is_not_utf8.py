"""A product's card template and rubric, the operator's registry and its seed name a file that is
not UTF-8.

Each read below used a bare `read_text()`, so bytes saved as Latin-1 or UTF-16 with a byte-order
mark raised `UnicodeDecodeError` (or decoded by the machine's locale), and UTF-16 without a mark
(valid UTF-8, because NUL is a code point) was read as text full of NULs. Each now reads bytes
through `beeverforge/util/utf8.py`, and its outcome carries the sentence naming the file, the byte
offset where it stops being UTF-8, and the remedy.

Each read keeps the path its function already takes for a file it cannot use: a product's template
is refused and the next candidate (or the shipped layout) is used; a product's rubric is refused
and the shipped one is used; the registry raises its `ValueError`; the seed is not seeded and the
live registry is left as it was. The shipped layouts are ours and are read as explicit UTF-8.
"""

from __future__ import annotations

import ast
import logging
import unicodedata
from pathlib import Path

import pytest

from tests.the_tree_read_once import parsed

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

_TEMPLATE = "## Objetivo do café\n\n{objective}\n\n{description}\n\n{done_when}\n"
_RUBRIC = "id: rubric\n# o café\ncriteria: []\n"
_REGISTRY = ("projects:\n  books:\n    name: books\n    repo_path: /tmp/café\n"
             "    tracker: {kind: github, repo: someone/books}\n")


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
    assert "codec" not in said, said


def _put(path: Path, raw: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return path


def _logged(caplog, code: str) -> str:
    said = [r.getMessage() for r in caplog.records if code in r.getMessage()]
    assert len(said) == 1, [r.getMessage() for r in caplog.records]
    assert all(r.levelno == logging.WARNING for r in caplog.records if code in r.getMessage())
    return said[0].split(f"{code} ", 1)[1]


def _refused_because(said: str, path: Path, tail: str) -> str:
    """The reason a `<CODE> path=<path> — <reason>; <tail>` warning gives."""
    head = f"path={path} — "
    assert said.startswith(head), said
    reason, cut, _ = said[len(head):].rpartition(f"; {tail}")
    assert cut, said
    return reason


# ── a product's card template ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("family", FAMILIES)
def test_a_language_template_not_in_utf8_falls_through_to_the_products_template(
        tmp_path, caplog, family):
    from beeverforge.product.cards import load_template

    own = load_template(language="en").replace("## Objective", "## Goal of the card")
    assert own != load_template(language="en")
    (tmp_path / "cards").mkdir()
    (tmp_path / "cards" / "template.md").write_text(own, encoding="utf-8")
    raw = _saved(_TEMPLATE, family)
    path = _put(tmp_path / "cards" / "template.en.md", raw)

    with caplog.at_level(logging.WARNING):
        layout = load_template(str(tmp_path), "ticket", "en")

    assert layout == own
    said = _logged(caplog, "BEEVERFORGE_CARD_TEMPLATE_REFUSED")
    _named(_refused_because(said, path, "the shipped template is used"), str(path),
           _offset(_TEMPLATE, family))
    assert path.read_bytes() == raw


@pytest.mark.parametrize("family", FAMILIES)
def test_a_template_not_in_utf8_falls_through_to_the_shipped_layout(tmp_path, caplog, family):
    from beeverforge.product.cards import _shipped_for, load_template

    raw = _saved(_TEMPLATE, family)
    path = _put(tmp_path / "cards" / "template.md", raw)

    with caplog.at_level(logging.WARNING):
        layout = load_template(str(tmp_path))

    assert layout == _shipped_for("template.md", None)
    said = _logged(caplog, "BEEVERFORGE_CARD_TEMPLATE_REFUSED")
    _named(_refused_because(said, path, "the shipped template is used"), str(path),
           _offset(_TEMPLATE, family))
    assert path.read_bytes() == raw


# ── a product's card rubric ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("family", FAMILIES)
def test_a_rubric_not_in_utf8_is_refused_with_the_decoders_sentence(tmp_path, caplog, family):
    from beeverforge.product.cards import load_rubric

    raw = _saved(_RUBRIC, family)
    path = _put(tmp_path / "cards" / "rubric.yaml", raw)

    with caplog.at_level(logging.WARNING):
        rubric = load_rubric(str(tmp_path))

    assert rubric.source == "shipped"
    said = _logged(caplog, "BEEVERFORGE_CARD_RUBRIC_REFUSED")
    _named(_refused_because(said, path, "the shipped rubric is used"), str(path),
           _offset(_RUBRIC, family))
    assert path.read_bytes() == raw


# ── the shipped layouts ─────────────────────────────────────────────────────────────────────────

def test_the_shipped_layouts_are_read_as_utf8():
    """The shipped files are ours, so they are a plain read — but in UTF-8 whatever the locale."""
    import beeverforge.product.cards as cards

    tree = parsed(Path(cards.__file__))
    shipped = next(n for n in ast.walk(tree)
                   if isinstance(n, ast.FunctionDef) and n.name == "_shipped")
    reads = [n for n in ast.walk(shipped) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and n.func.attr == "read_text"]
    assert len(reads) == 1, ast.unparse(shipped)
    encoding = [k.value for k in reads[0].keywords if k.arg == "encoding"]
    assert len(encoding) == 1 and isinstance(encoding[0], ast.Constant), ast.unparse(shipped)
    assert encoding[0].value == "utf-8", ast.unparse(shipped)


# ── the operator's registry ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("family", FAMILIES)
def test_a_registry_not_in_utf8_raises_the_decoders_sentence(tmp_path, family):
    from beeverforge.registry import ProjectRegistry

    raw = _saved(_REGISTRY, family)
    path = _put(tmp_path / "registry.yaml", raw)

    with pytest.raises(ValueError) as refused:
        ProjectRegistry(path)._load_raw()

    # `UnicodeDecodeError` IS a `ValueError`, so the type alone proves nothing: the words do
    assert not isinstance(refused.value, UnicodeDecodeError)
    _named(str(refused.value), str(path), _offset(_REGISTRY, family))
    assert path.read_bytes() == raw


# ── the registry's seed ─────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("live_was", ["absent", "empty"])
@pytest.mark.parametrize("family", FAMILIES)
def test_a_seed_not_in_utf8_is_not_seeded_and_the_live_registry_is_untouched(
        tmp_path, caplog, family, live_was):
    from beeverforge.registry import seed_registry

    # THE SAME SEED IN UTF-8 SEEDS, so the `False` below is the decode refusing it, not a seed
    # that would never have seeded
    good = _put(tmp_path / "utf8" / "seed.yaml", _REGISTRY.encode("utf-8"))
    assert seed_registry(seed=good, live=tmp_path / "utf8" / "registry.yaml") is True

    raw = _saved(_REGISTRY, family)
    seed = _put(tmp_path / "saved" / "seed.yaml", raw)
    live = tmp_path / "saved" / "registry.yaml"
    if live_was == "empty":
        live.write_bytes(b"")

    with caplog.at_level(logging.WARNING):
        seeded = seed_registry(seed=seed, live=live)

    assert seeded is False
    said = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(said) == 1, said
    head = f"could not seed the registry from {seed} ("
    assert said[0].startswith(head), said[0]
    reason, cut, _ = said[0][len(head):].rpartition(f") — starting with whatever {live} holds")
    assert cut, said[0]
    _named(reason, str(seed), _offset(_REGISTRY, family))
    assert seed.read_bytes() == raw
    if live_was == "empty":
        assert live.read_bytes() == b""
    else:
        assert not live.exists()
