"""A file written with Windows line endings keeps its front matter (#67).

Every reader that matches a YAML front-matter block turns `\\r\\n` and a lone `\\r` into `\\n`
before it matches: a capability, a concept, a decision record, a document, a ticket body and a
card's opening read the same with CRLF as with LF. The CRLF fixtures on disk are written as bytes, so the `\\r`
reaches the reader the way `tree.read_text` and `decode()` hand it over.
"""
from __future__ import annotations

from beeverforge.adapters.extract.text import front_matter
from beeverforge.adapters.tracker.parse import _split_front_matter
from beeverforge.knowledge.contracts import Concept
from beeverforge.knowledge.okf import parse_concept, render_concept
from beeverforge.knowledge.system.adrs import read_adr
from beeverforge.product.capabilities import (
    CONFIRMED,
    Capability,
    load_capabilities,
    parse_capability,
    render_capability,
)
from beeverforge.product.documents.record import declared
from beeverforge.product.queue import _opening


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
