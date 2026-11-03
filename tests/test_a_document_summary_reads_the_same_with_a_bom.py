"""A document saved with a byte-order mark keeps its summary in the brief (#321).

`_doc_summary` reads the document as `utf-8-sig`, as the front-matter readers of #67 do, so a
leading U+FEFF does not stand in front of `---` (the front-matter `summary`) or `#` (the heading
fallback). Both fixtures are written as bytes, so the mark reaches the reader as it is on disk.
"""
from __future__ import annotations

from pathlib import Path

from beeverforge.orchestrator import context

BOM = b"\xef\xbb\xbf"


def _pair(tmp_path: Path, text: str) -> tuple[Path, Path]:
    plain = tmp_path / "plain" / "doc.md"
    marked = tmp_path / "marked" / "doc.md"
    plain.parent.mkdir()
    marked.parent.mkdir()
    plain.write_bytes(text.encode("utf-8"))
    marked.write_bytes(BOM + text.encode("utf-8"))
    return plain, marked


def test_a_document_summary_reads_the_same_with_a_bom(tmp_path: Path) -> None:
    plain, marked = _pair(tmp_path, "---\nsummary: What a plan costs.\n---\n# Pricing\n")

    assert context._doc_summary(plain) == "What a plan costs."
    assert context._doc_summary(marked) == context._doc_summary(plain)


def test_a_documents_heading_reads_the_same_with_a_bom(tmp_path: Path) -> None:
    plain, marked = _pair(tmp_path, "# Pricing\n\nWhat a plan costs.\n")

    assert context._doc_summary(plain) == "Pricing"
    assert context._doc_summary(marked) == context._doc_summary(plain)
