"""A document `build_context` cannot decode is named in the log, not raised (#325)."""

from __future__ import annotations

from pathlib import Path

import pytest

from beeverforge.contracts import Manifest, Ticket
from beeverforge.orchestrator import context
from beeverforge.orchestrator.context import build_context


def _ticket() -> Ticket:
    return Ticket(id="#1", title="t", objective="o", repo="someone/x")


def test_a_utf16_document_does_not_stop_build_context(tmp_path: Path, caplog):
    (tmp_path / "docs" / "arch").mkdir(parents=True)
    (tmp_path / "docs" / "arch" / "notes.md").write_bytes(
        "---\nsummary: X\n---\n# H\n".encode("utf-16"))
    manifest = Manifest(docs={"architecture": "docs/arch/**"})

    with caplog.at_level("WARNING"):
        ctx = build_context(manifest, tmp_path, _ticket())

    assert "notes.md — notes" in ctx.doc_index
    named = [r.getMessage() for r in caplog.records if "notes.md" in r.getMessage()]
    assert len(named) == 1
    assert "is not UTF-8" in named[0]
    assert "save it as UTF-8" in named[0]


@pytest.mark.parametrize("data", [
    pytest.param("---\nsummary: X\n---\n# H\n".encode("utf-16"), id="utf-16"),
    pytest.param(b"# Caf\xe9\n", id="latin-1"),
])
def test_a_document_that_is_not_utf8_is_named_not_raised(tmp_path: Path, caplog, data: bytes):
    p = tmp_path / "notes.md"
    p.write_bytes(data)

    with caplog.at_level("WARNING"):
        assert context._doc_summary(p) == p.stem

    named = [r.getMessage() for r in caplog.records if p.name in r.getMessage()]
    assert len(named) == 1
    assert "is not UTF-8" in named[0]
    assert "save it as UTF-8" in named[0]
