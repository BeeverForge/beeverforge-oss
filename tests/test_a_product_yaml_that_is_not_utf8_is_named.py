"""A `product.yaml`, or a compose file a preview reads, saved in an encoding that is not UTF-8 is
refused by name, never raised.

Both readers of `.beeverforge/product.yaml` promise `(docs, error)` for any file. Bytes that are
not UTF-8 raised a `UnicodeDecodeError` out of both: the product module read with
`read_text(encoding="utf-8")` and caught only `OSError`, and the preview opened the file as text
and caught nothing. A person who opens the file in an editor sees nothing wrong, so the sentence
names the file, the byte offset where it stops being UTF-8, and the remedy.

UTF-16 WITHOUT A BYTE-ORDER MARK IS A TRAP: `p\\x00r\\x00...` is valid UTF-8, because NUL is a
code point, so it decodes and then fails as YAML in words that name neither the encoding nor the
remedy. A NUL is therefore refused at its offset as not UTF-8 text.

The compose files a preview reads go through the same reader, so they are refused the same way.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from beeverforge.contracts.manifest import PreviewConfig
from beeverforge.contracts.product import ProductPreview
from beeverforge.preview.plan import Layout, Refused, Tree
from beeverforge.preview.product import ProductShape, _declares_preview, reached, read_docs
from beeverforge.preview.read import texts_of
from beeverforge.product.loader import DOCS_MANIFEST, _read_docs_manifest

REMEDY = "save it as UTF-8"

#: both readers of the file: the product module's, and the preview's from its own checkout
READERS = {
    "the product module": lambda root: _read_docs_manifest(root),
    "the preview": lambda root: read_docs(str(root)),
}

#: one file per encoding family, and the offset of the first byte that is not UTF-8 text
FAMILIES = {
    "Latin-1": ("product: café\n".encode("latin-1"), 12),
    # the little-endian mark written explicitly, whatever the machine's byte order
    "UTF-16 with a byte-order mark": (b"\xff\xfe" + "product: books\n".encode("utf-16-le"), 0),
    "UTF-16-LE without a byte-order mark": ("product: books\n".encode("utf-16-le"), 1),
    "UTF-16-BE with a byte-order mark": (b"\xfe\xff" + "product: books\n".encode("utf-16-be"), 0),
    "invalid bytes": (b"product: \x80\xff\n", 9),
}


def _held(raw: bytes, offset: int) -> None:
    """The table's offset is the written bytes' own: everything before it is UTF-8 text with no
    NUL, and the byte at it is a NUL or does not start a UTF-8 character."""
    assert b"\x00" not in raw[:offset]
    raw[:offset].decode("utf-8")
    if raw[offset] != 0:
        with pytest.raises(UnicodeDecodeError):
            raw[offset:offset + 4].decode("utf-8")


def _named(said: str, shown: str, offset: int) -> None:
    """One sentence naming the file, the offset and the remedy — no exception's words."""
    assert shown in said, said
    assert f"offset {offset}" in said, said
    assert REMEDY in said, said
    assert "\n" not in said, said
    assert "Error" not in said, said


def _write(root: Path, rel: str, raw: bytes) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


@pytest.mark.parametrize("reader", READERS)
@pytest.mark.parametrize("family", FAMILIES)
def test_a_manifest_not_in_utf8_is_named_never_raised(tmp_path, reader, family):
    raw, offset = FAMILIES[family]
    _held(raw, offset)
    _write(tmp_path, DOCS_MANIFEST, raw)

    docs, said = READERS[reader](tmp_path)

    assert docs is None
    _named(said, DOCS_MANIFEST, offset)


@pytest.mark.parametrize("reader", READERS)
def test_a_manifest_under_openfactory_not_in_utf8_is_named(tmp_path, reader):
    raw, offset = FAMILIES["Latin-1"]
    _write(tmp_path, ".openfactory/product.yaml", raw)

    docs, said = READERS[reader](tmp_path)

    assert docs is None
    _named(said, ".openfactory/product.yaml", offset)


@pytest.mark.parametrize("reader", READERS)
def test_a_utf8_manifest_still_loads(tmp_path, reader):
    _write(tmp_path, DOCS_MANIFEST, "product: café\n".encode())

    docs, said = READERS[reader](tmp_path)

    assert docs is not None, said
    assert docs.product == "café"


# ── the compose files a preview reads through the same reader ───────────────────────────────────


def _layout(tmp_path: Path) -> tuple[Layout, Path]:
    wd = Path(os.path.realpath(tmp_path)) / "beeverforge-pv-someone-1"
    root = wd / "base" / "app"
    root.mkdir(parents=True)
    return Layout(workdir=str(wd), trees={"app": Tree(repo="someone/shop", dir="app")}), root


CONFIG = PreviewConfig(compose=["compose.yaml"], expose={"api": 8000})


def test_a_compose_file_not_in_utf8_is_refused_by_name(tmp_path):
    layout, root = _layout(tmp_path)
    raw, offset = FAMILIES["Latin-1"]
    _write(root, "compose.yaml", raw)

    found = texts_of(layout, CONFIG, tree="app")

    assert isinstance(found, Refused), found
    (said,) = found.reasons
    _named(said, "compose.yaml", offset)


def test_an_extended_file_not_in_utf8_is_refused_by_name(tmp_path):
    layout, root = _layout(tmp_path)
    _write(root, "compose.yaml",
           b"services:\n  api:\n    extends:\n      file: ops/common.yml\n      service: base\n")
    raw, offset = FAMILIES["invalid bytes"]
    _write(root, "ops/common.yml", raw)

    found = texts_of(layout, CONFIG, tree="app")

    assert isinstance(found, Refused), found
    (said,) = found.reasons
    _named(said, "ops/common.yml", offset)


def test_reached_refuses_a_compose_file_not_in_utf8(tmp_path):
    shape = ProductShape(context="someone/context", context_dir="context", shape_dir="context",
                         members={"context": "someone/context"},
                         preview=ProductPreview(compose="compose.yaml", expose={"api": 8000}))
    raw, offset = FAMILIES["UTF-16-LE without a byte-order mark"]
    _write(tmp_path, "compose.yaml", raw)

    found = reached(shape, str(tmp_path))

    assert isinstance(found, Refused), found
    (said,) = found.reasons
    _named(said, "compose.yaml", offset)


def test_a_source_manifest_not_in_utf8_declares_no_preview(tmp_path):
    _write(tmp_path, ".beeverforge/project.yaml",
           "# café\npreview:\n  compose: [c.yml]\n".encode("latin-1"))

    assert _declares_preview(str(tmp_path), ".beeverforge/project.yaml") is False


def test_an_onboarding_compose_file_not_in_utf8_reaches_nothing_to_ask(tmp_path):
    from beeverforge.onboarding.infer import Proposal
    from beeverforge.onboarding.preview_infer import PreviewProposal
    from beeverforge.onboarding.preview_product import _dirs_asked

    _write(tmp_path, "compose.yaml",
           b"services:\n  web:\n    build: ../backend\n")
    raw, _ = FAMILIES["Latin-1"]
    _write(tmp_path, "ops.yaml", raw)
    found = PreviewProposal(repo="someone/web", name="web", case="compose",
                            compose=Proposal(field="preview.compose",
                                             value=["compose.yaml", "ops.yaml"]))

    asked = _dirs_asked("someone/web", found, Path(os.path.realpath(tmp_path)),
                        {"web": "someone/web"})

    # the file that is not UTF-8 is skipped, and the one that is still asks about `../backend`
    assert len(asked) == 1, asked
    assert "`../backend`" in asked[0], asked
