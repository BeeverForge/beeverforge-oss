"""A file written with Windows line endings keeps its front matter (#67).

Every reader that matches a YAML front-matter block turns `\\r\\n` and a lone `\\r` into `\\n`
before it matches: a capability, a concept, a decision record, a document, a ticket body and a
card's opening read the same with CRLF as with LF. The CRLF fixtures on disk are written as bytes, so the `\\r`
reaches the reader the way `tree.read_text` and `decode()` hand it over.

A file saved with a byte-order mark keeps its front matter too: the readers that open a file
themselves read it as `utf-8-sig`, as `tree.read_text` and `decode()` already do, so a leading
U+FEFF does not stand in front of `---`.
"""
from __future__ import annotations

from pathlib import Path

from beeverforge.adapters.extract.text import front_matter
from beeverforge.adapters.tracker.parse import _split_front_matter
from beeverforge.knowledge.contracts import Concept
from beeverforge.knowledge.okf import CONCEPTS_DIRNAME, parse_concept, read_concepts, render_concept
from beeverforge.knowledge.system.adrs import read_adr
from beeverforge.product.authoring import distilled_until
from beeverforge.product.capabilities import (
    CONFIRMED,
    OBSERVED,
    Capability,
    confirm_in_repository,
    load_capabilities,
    parse_capability,
    render_capability,
)
from beeverforge.product.documents.record import declared
from beeverforge.product.queue import _opening

BOM = b"\xef\xbb\xbf"


def _crlf(text: str) -> str:
    return text.replace("\n", "\r\n")


def _capability() -> Capability:
    return Capability(slug="checkout", title="Checkout", status=CONFIRMED, requirements=[3, 7],
                      components=["shop/cart"], confirmed_by="ana", confirmed_at="2026-10-01",
                      summary="A shopper pays for what is in the cart.")


def test_a_capability_reads_the_same_with_crlf():
    lf = render_capability(_capability())

    from_lf = parse_capability(lf, path="capabilities/checkout.md")
    from_crlf = parse_capability(_crlf(lf), path="capabilities/checkout.md")

    assert from_lf[0] is not None
    assert from_crlf == from_lf
    assert "no-front-matter" not in [f.code for f in from_crlf[1]]


def test_load_capabilities_reads_a_crlf_file(tmp_path):
    lf = render_capability(_capability())
    lf_root, crlf_root = tmp_path / "lf", tmp_path / "crlf"
    for root, text in ((lf_root, lf), (crlf_root, _crlf(lf))):
        (root / "capabilities").mkdir(parents=True)
        (root / "capabilities" / "checkout.md").write_bytes(text.encode("utf-8"))

    caps, findings = load_capabilities(crlf_root)

    assert findings == []
    assert caps == load_capabilities(lf_root)[0]
    assert [c.slug for c in caps] == ["checkout"]


def test_a_concept_reads_the_same_with_crlf():
    lf = render_concept(Concept(type="policy", title="Billing rules", description="first"))

    from_lf = parse_concept(lf)

    assert from_lf is not None
    assert parse_concept(_crlf(lf)) == from_lf


def test_an_adr_reads_the_same_with_crlf():
    lf = "---\nstatus: accepted\ndate: 2024-05-06\ntitle: Front\n---\n# Heading\n"
    rel = "docs/decisions/0001-front.md"

    from_lf = read_adr(lf, rel)
    from_crlf = read_adr(_crlf(lf), rel)

    assert (from_crlf.number, from_crlf.title, from_crlf.status, from_crlf.date) == (
        "0001", "Front", "accepted", "2024-05-06")
    assert from_crlf == from_lf


def test_markdown_front_matter_reads_the_same_with_crlf(tmp_path):
    lf = ("---\ntitle: Pricing\naudience: client\ndate: 2026-01-02\n---\n"
          "# Pricing\n\nWhat a plan costs.\n")

    fields, _body, problem = front_matter(lf)

    assert (fields["audience"], problem) == ("client", "")
    assert front_matter(_crlf(lf)) == front_matter(lf)

    (tmp_path / "doc.md").write_bytes(_crlf(lf).encode("utf-8"))
    assert declared(tmp_path, "doc.md") == "client"


def test_a_ticket_front_matter_reads_the_same_with_crlf():
    lf = "---\ndepends_on: [3]\n---\n## Goal\n\nShip the checkout.\n"

    fields, markdown = _split_front_matter(lf)

    assert fields == {"depends_on": [3]}
    assert _split_front_matter(_crlf(lf)) == (fields, markdown)


def test_a_lone_carriage_return_reads_as_a_line_end():
    lf = render_capability(_capability())

    assert parse_capability(lf.replace("\n", "\r"), path="capabilities/checkout.md") == (
        parse_capability(lf, path="capabilities/checkout.md"))


def test_a_cards_opening_reads_the_same_with_crlf():
    lf = "---\ndepends_on: [3]\n---\nBuilding on the per-version storage.\n\n## Goal\n\nShip it.\n"

    from_lf = _opening(lf)

    assert from_lf == "Building on the per-version storage."
    assert _opening(_crlf(lf)) == from_lf


def test_a_concept_file_reads_the_same_with_a_bom(tmp_path):
    text = render_concept(Concept(type="policy", title="Billing rules", description="first"))
    plain, marked = tmp_path / "plain", tmp_path / "marked"
    for bundle, data in ((plain, text.encode("utf-8")), (marked, BOM + text.encode("utf-8"))):
        (bundle / CONCEPTS_DIRNAME).mkdir(parents=True)
        (bundle / CONCEPTS_DIRNAME / "billing-rules.md").write_bytes(data)

    from_plain = read_concepts(plain)

    assert [c.title for c in from_plain] == ["Billing rules"]
    assert read_concepts(marked) == from_plain


def _confirm_a_file_on_disk(monkeypatch, data: bytes) -> tuple[object, str]:
    """`confirm_in_repository` over a clone that holds `data` as the capability file: the git
    calls are stood in for, so the read of the cloned file is what is measured, with no git."""
    written: list[str] = []

    def fake_git(args, cwd=None):
        if args[0] == "clone":
            target = Path(args[-1]) / "capabilities" / "checkout.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        elif args[0] == "commit":
            written.append((Path(cwd) / "capabilities" / "checkout.md").read_text(encoding="utf-8"))
        return 0, ""

    monkeypatch.setattr("beeverforge.product.authoring._git", fake_git)
    result = confirm_in_repository(docs_repo="docs", clone_url="file:///nowhere", slug="checkout",
                                   flow=None, confirmed_by="ana", today="2026-10-30")
    return result, "".join(written)


def test_confirming_a_capability_file_reads_the_same_with_a_bom(monkeypatch):
    text = render_capability(_capability().model_copy(
        update={"status": OBSERVED, "confirmed_by": "", "confirmed_at": ""}))

    plain, plain_written = _confirm_a_file_on_disk(monkeypatch, text.encode("utf-8"))
    marked, marked_written = _confirm_a_file_on_disk(monkeypatch, BOM + text.encode("utf-8"))

    assert (plain.ok, plain.ref) == (True, "capabilities/checkout.md")
    assert "status: confirmed" in plain_written
    assert (marked.ok, marked.ref, marked.detail) == (plain.ok, plain.ref, plain.detail)
    assert marked_written == plain_written


def test_a_distillate_reads_the_same_with_a_bom(tmp_path):
    text = "---\nafter: ''\nsince: '1'\nuntil: '1700000000.5'\n---\n# Kept\n"
    plain, marked = tmp_path / "plain", tmp_path / "marked"
    for folder, data in ((plain, text.encode("utf-8")), (marked, BOM + text.encode("utf-8"))):
        folder.mkdir()
        (folder / "one.md").write_bytes(data)

    assert distilled_until(plain) == "1700000000.5"
    assert distilled_until(marked) == distilled_until(plain)
