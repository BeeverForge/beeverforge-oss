"""A proposal staged on one product is never read, confirmed or set aside on another (#471).

THE DEFECT. One person talks to the product roles of two products in their own conversation on
each product's page. That conversation's key is the person's own (`Actor.conversation`), the same
on every product page, and this process's copy of staged proposals (`staging._PENDING`) was keyed
by conversation alone. Product B's role staged after product A's, under the same key, and the
person's "yes" on A's page confirmed B's proposal and performed it with A's module: B's
requirement was recorded in A's context repository. A staged queue proposal takes the same path.

The doubles are only the two projects; the staging and the durable store are the shipped ones.
"""

from __future__ import annotations

import logging

import pytest

from beeverforge.contracts.product import ProductConfig
from beeverforge.contracts.project import Project, ProviderRef
from beeverforge.product import staging

#: one person's own conversation key — what both product pages stage under
OWN = "person:u-admin"
PERSON = "u-admin"


def _project(name: str) -> Project:
    return Project(name=name, repo_path="/t", language="en",
                   tracker=ProviderRef(kind="github", repo=f"acme/{name}"),
                   forge=ProviderRef(kind="github", repo=f"acme/{name}"),
                   product=ProductConfig(docs_repo=f"acme/{name}-context", admins=[PERSON]))


A = _project("product-a")
B = _project("product-b")


def _card(title: str) -> dict:
    return {"kind": "card", "title": title}


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    """The real SQLite store, in this test's own directory."""
    monkeypatch.setenv("BEEVERFORGE_METRICS_SINK", "sqlite")
    monkeypatch.setenv("BEEVERFORGE_METRICS_DB", str(tmp_path / "metrics.db"))


def _stage_both() -> tuple[dict, dict]:
    """A's proposal first, then B's, under the one key both pages use."""
    staging.remember(OWN, _card("A: a requester creates a request"), project=A, person=PERSON)
    staging.remember(OWN, _card("B: the catalogue lists every item"), project=B, person=PERSON)
    a = staging.pending_for(OWN, project=A)
    b = staging.pending_for(OWN, project=B)
    return a, b


def test_each_product_reads_its_own_proposal_under_the_shared_key():
    a, b = _stage_both()

    assert a is not None and a["title"].startswith("A:")
    assert b is not None and b["title"].startswith("B:")


def test_a_yes_on_one_product_never_performs_the_other_products_proposal(caplog):
    _a, b = _stage_both()

    with caplog.at_level(logging.WARNING, logger="beeverforge.product.staging"):
        assert staging.consume(OWN, b, project=A, by=PERSON) is None

    assert "BEEVERFORGE_PRODUCT_OTHER_PRODUCT" in caplog.text
    # …and the other product's proposal is still there for its own yes
    assert staging.pending_for(OWN, project=B)["title"].startswith("B:")


def test_each_yes_performs_exactly_its_own_products_proposal():
    a, _b = _stage_both()

    done_a = staging.consume(OWN, a, project=A, by=PERSON)
    done_b = staging.consume(OWN, staging.pending_for(OWN, project=B), project=B, by=PERSON)

    assert done_a is not None and done_a["title"].startswith("A:")
    assert done_b is not None and done_b["title"].startswith("B:")
    assert staging.pending_for(OWN, project=A) is None
    assert staging.pending_for(OWN, project=B) is None


def test_the_scan_for_a_bare_yes_finds_only_this_products_proposals():
    _stage_both()

    key, entry = staging.find_waiting(OWN, project=A, person=PERSON)

    assert key == OWN and entry["title"].startswith("A:")


def test_staging_on_one_product_sets_aside_nothing_of_the_others():
    staging.remember(OWN, _card("B: the catalogue lists every item"), project=B, person=PERSON)

    said = staging.remember(OWN, {"kind": "queue", "numbers": [1]}, project=A, person=PERSON)

    assert "set aside" not in said
    assert staging.pending_for(OWN, project=B)["title"].startswith("B:")


def test_a_staged_entry_carries_the_product_it_was_staged_for():
    _stage_both()

    assert staging.pending_for(OWN, project=A)["product"] == "repo:acme/product-a-context"


def test_a_proposal_staged_with_no_product_or_read_with_no_project_is_read_as_before():
    staging.remember(OWN, _card("no product"))

    assert staging.pending_for(OWN, project=A)["title"] == "no product"

    staging.remember(OWN, _card("B: the catalogue lists every item"), project=B, person=PERSON)

    assert staging.pending_for(OWN)["title"].startswith("B:")


# ── a copy held only in this process ─────────────────────────────────────────────────────────────
# The durable mirror is best-effort (`remember`), so another product's proposal can live in this
# process's copy alone. Then nothing but `_PENDING` holds it, and this product's reads, yes and
# expiry must leave it where it is.

def _stage_b_unmirrored(monkeypatch) -> None:
    from beeverforge.memory import messages

    def refuse(*_a, **_k):
        raise OSError("the store did not answer")

    with monkeypatch.context() as m:
        m.setattr(messages, "ask", refuse)
        staging.remember(OWN, _card("B: the catalogue lists every item"), project=B,
                         person=PERSON)


def test_a_product_with_nothing_staged_reads_nothing_and_drops_nothing(monkeypatch):
    _stage_b_unmirrored(monkeypatch)

    assert staging.pending_for(OWN, project=A) is None
    assert staging.pending_for(OWN, project=B)["title"].startswith("B:")


def test_one_products_read_and_yes_leave_the_others_unmirrored_copy_in_place(monkeypatch):
    staging.remember(OWN, _card("A: a requester creates a request"), project=A, person=PERSON)
    _stage_b_unmirrored(monkeypatch)

    a = staging.pending_for(OWN, project=A)
    assert staging.consume(OWN, a, project=A, by=PERSON)["title"].startswith("A:")

    assert staging.pending_for(OWN, project=B)["title"].startswith("B:")


def test_an_expiry_on_one_product_never_drops_the_others_copy(monkeypatch):
    staging.remember(OWN, _card("A: a requester creates a request"), project=A, person=PERSON)
    _stage_b_unmirrored(monkeypatch)

    with monkeypatch.context() as m:
        m.setattr(staging, "PROPOSAL_TTL_SECONDS", -1)
        assert staging.pending_for(OWN, project=A) is None  # A's aged out

    assert staging.pending_for(OWN, project=B)["title"].startswith("B:")


def test_the_scan_orders_this_products_proposals_by_their_own_staging():
    """Two of A's proposals in one room under other people's keys; B's later one sits on the
    older of the two. A bare yes means A's newest, not the one B's moment would put first."""
    room = "room-1"
    older, newer = staging.key_for(room, "p2"), staging.key_for(room, "p3")
    staging.remember(older, _card("A: the older one"), project=A, person="p2")
    staging.remember(newer, _card("A: the newer one"), project=A, person="p3")
    staging.remember(older, _card("B: the catalogue lists every item"), project=B, person="p2")

    key, entry = staging.find_waiting(room, project=A, person=PERSON)

    assert (key, entry["title"]) == (newer, "A: the newer one")
