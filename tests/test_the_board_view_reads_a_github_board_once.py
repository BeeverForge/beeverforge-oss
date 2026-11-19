"""One board view reads a GitHub project's items once (#591).

The view needs two facts of the board — which columns exist and which card sits in which — and the
GitHub row used to buy them with two reads of the same items. A page the panel opens on demand
must cost one read per page, however many cards the board holds.
"""

from __future__ import annotations

import json

import pytest

from beeverforge.adapters.tracker import github_project as gp

CARDS = 250


def _page(after: str | None) -> dict:
    start = int(after or 0)
    stop = min(start + 100, CARDS)
    nodes = [{"id": f"PVTI_{n}",
              "content": {"number": n, "repository": {"nameWithOwner": "acme/web"}},
              "fieldValueByName": {"name": "TO-DO" if n % 2 else "Done"}}
             for n in range(start + 1, stop + 1)]
    return {"data": {"organization": {"projectV2": {
        "id": "PVT_1",
        "field": {"id": "F1", "options": [{"id": "o1", "name": "TO-DO"},
                                           {"id": "o2", "name": "Done"}]},
        "items": {"pageInfo": {"hasNextPage": stop < CARDS, "endCursor": str(stop)},
                  "nodes": nodes}}}}}


@pytest.fixture
def reads(tmp_path, monkeypatch):
    """A registered project on a GitHub board, every `gh` call recorded and answered locally."""
    from beeverforge.adapters.tracker.base import TicketSummary
    from beeverforge.contracts.project import Project, ProviderRef
    from beeverforge.registry import ProjectRegistry

    monkeypatch.setenv("BEEVERFORGE_REGISTRY", str(tmp_path / "registry.yaml"))
    registry = ProjectRegistry()
    registry.add(Project(name="acme", repo_path=str(tmp_path),
                         tracker=ProviderRef(kind="github", repo="acme/web",
                                             options={"board_owner": "acme",
                                                      "board_number": "1"})))

    seen: list[list[str]] = []

    def fake_gh_json(args, token=None):
        seen.append(list(args))
        if args[:2] == ["project", "view"]:
            return {"id": "PVT_1"}
        if args[:2] == ["project", "field-list"]:
            return {"fields": [{"name": "Status", "id": "F1",
                                "options": [{"id": "o1", "name": "TO-DO"},
                                            {"id": "o2", "name": "Done"}]}]}
        cursor = next((a.split("=", 1)[1] for a in args if a.startswith("cursor=")), None)
        return _page(cursor)

    class _Tracker:
        def list_tickets(self, **kw):
            return [TicketSummary(ref=str(n), title=f"card {n}") for n in range(1, CARDS + 1)]

    monkeypatch.setattr(gp, "_gh_json", fake_gh_json)
    monkeypatch.setattr("beeverforge.adapters.tracker.registry.build_tracker",
                        lambda *a, **k: _Tracker())
    return seen


def test_one_board_view_reads_the_board_once_per_page(reads):
    """The column names and the placement come from the same read: no read of the project beside
    the pages of its items."""
    from beeverforge.api.app import board_view

    got = board_view("acme")

    assert len(got["cards"]) == CARDS and got["columns"] == ["TO-DO", "Done"]
    pages = -(-CARDS // 100)
    assert len(reads) <= pages, (
        f"the view made {len(reads)} GraphQL reads for {pages} pages of cards: "
        + json.dumps([a[:2] for a in reads]))
