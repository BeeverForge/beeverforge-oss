"""A GitHub repository typed in another case is one repository to the Projects board (#380).

GitHub logins and repository names ignore case, and GitHub's Projects v2 board answers
`nameWithOwner` in GitHub's own spelling. The registry holds whatever a person typed. So a
registry that says `acme/api` reads `Acme/api` back from the board, and the board compared the two
by spelling at three sites:

  · `qualify_ref` qualified the project's own card as `Acme/api#12`, a second identity for the
    ticket the rest of the platform calls `12`;
  · `_item_id` (a move) skipped the card as another repository's, and the move failed with "no
    card for the issue";
  · `_existing_item_id` (a rank's anchor) did the same, and the rank failed with "no card for '7'
    to place it after".

Each site is driven here through `gh`, faked at the adapter's one door (`_run_gh`), answering
real GraphQL-shaped nodes. Each has a twin: a repository that really is different (another owner
or another name) is still another repository.

The casefold is for the comparison only. What is shown keeps the spelling it arrived with: a card
of the project's own repository is bare, and a foreign card is named as GitHub names it.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from beeverforge.adapters.tracker import github_project as gp
from beeverforge.contracts.refs import qualify_ref

REGISTRY_REPO = "acme/api"      # what the person typed into the registry
URL = "https://github.com/acme/api/issues/{n}"


class _Gh:
    """`gh` for one Projects v2 board: project P1, a Status field F1, and the cards it is given as
    `(item id, number, nameWithOwner, status)`. It records every column move and every rank."""

    def __init__(self, cards: list[tuple[str, int, str, str]]) -> None:
        self.cards = cards
        self.moves: list[tuple[str, str]] = []
        self.positions: list[tuple[str, str | None]] = []

    def __call__(self, args: list[str], _token):
        query = next((a[len("query="):] for a in args if a.startswith("query=")), "")
        fields = dict(a.split("=", 1) for a in args if "=" in a and not a.startswith("query="))
        if args[:2] == ["project", "view"]:
            return self._answer({"id": "P1"})
        if args[:2] == ["project", "field-list"]:
            return self._answer({"fields": [{"name": "Status", "id": "F1", "options": [
                {"name": "Backlog", "id": "o1"}, {"name": "In progress", "id": "o2"}]}]})
        if "updateProjectV2ItemFieldValue" in query:
            self.moves.append((fields["item"], fields["option"]))
            return self._answer({})
        if "updateProjectV2ItemPosition" in query:
            self.positions.append((fields["item"], fields.get("after")))
            return self._answer({})
        if "addProjectV2ItemById" in query:
            return self._answer({})
        if "issue(number:$number)" in query:
            return self._answer({"data": {"repository": {"issue": {"id": f"N{fields['number']}"}}}})
        if "organization(login:$owner)" in query:
            nodes = [{"id": item, "content": {"number": number,
                                              "repository": {"nameWithOwner": repo}},
                      "fieldValueByName": {"name": status}}
                     for item, number, repo, status in self.cards]
            return self._answer({"data": {"organization": {"projectV2": {"items": {
                "pageInfo": {"hasNextPage": False}, "nodes": nodes}}}}})
        raise AssertionError(f"the board asked gh for something this fake never had: {args}")

    @staticmethod
    def _answer(payload):
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")


@pytest.fixture
def board(monkeypatch):
    """A board whose registry says `acme/api`, over the cards GitHub answers."""
    for name in ("GH_HOST", "GITHUB_HOST"):
        monkeypatch.delenv(name, raising=False)

    def make(*cards: tuple[str, int, str, str],
             registry: str = REGISTRY_REPO) -> tuple[gp.GitHubProjectBoard, _Gh]:
        gh = _Gh(list(cards))
        monkeypatch.setattr(gp, "_run_gh", gh)
        return gp.GitHubProjectBoard(owner="acme", number="1", token="tok",
                                     default_repo=registry), gh
    return make


# ── qualify_ref: the project's own card is bare ─────────────────────────────────────────────────

def test_a_card_in_the_projects_repository_spelled_otherwise_is_bare(board):
    projects, _ = board(("I12", 12, "Acme/api", "Backlog"))

    assert projects.columns() == {"12": "Backlog"}
    assert projects.items_in_status("Backlog") == ["12"]
    assert qualify_ref("Acme/api", "12", "acme/api") == "12"
    assert qualify_ref("ACME/API", "#12", "acme/api") == "12"


def test_a_card_in_another_repository_is_still_qualified(board):
    projects, _ = board(("I12", 12, "Acme/web", "Backlog"), ("I13", 13, "Other/api", "Backlog"))

    assert projects.columns() == {"Acme/web#12": "Backlog", "Other/api#13": "Backlog"}
    assert projects.items_in_status("Backlog") == ["Acme/web#12", "Other/api#13"]
    assert qualify_ref("acme/web", "12", "acme/api") == "acme/web#12"
    assert qualify_ref("other/api", "12", "acme/api") == "other/api#12"


# ── _item_id: a move finds the card ─────────────────────────────────────────────────────────────

def test_a_move_finds_the_card_github_spells_otherwise(board):
    projects, gh = board(("I12", 12, "Acme/api", "Backlog"))

    assert projects.set_column(issue="12", issue_url=URL.format(n=12), name="In progress")
    assert gh.moves == [("I12", "o2")]


def test_a_move_never_takes_another_repositorys_card(board):
    projects, gh = board(("I12", 12, "Acme/web", "Backlog"), ("J12", 12, "Other/api", "Backlog"))

    assert not projects.set_column(issue="12", issue_url=URL.format(n=12), name="In progress")
    assert gh.moves == []


# ── _existing_item_id: a rank finds its anchor ──────────────────────────────────────────────────

def test_a_rank_finds_the_anchor_github_spells_otherwise(board):
    # the card being placed is matched by `_item_id`; this proves the ANCHOR, so the anchor is the
    # only card spelled otherwise and the placed card's lookup is answered from its own spelling
    projects, gh = board(("I12", 12, "acme/api", "Backlog"), ("I7", 7, "Acme/api", "Backlog"))

    assert projects.place_after(issue="12", issue_url=URL.format(n=12), after="7",
                                column="Backlog")
    assert gh.positions == [("I12", "I7")]


def test_a_rank_never_anchors_on_another_repositorys_card(board):
    projects, gh = board(("I12", 12, "acme/api", "Backlog"), ("I7", 7, "Acme/web", "Backlog"),
                         ("J7", 7, "Other/api", "Backlog"))

    assert not projects.place_after(issue="12", issue_url=URL.format(n=12), after="7",
                                    column="Backlog")
    assert gh.positions == []


# ── the other direction: the registry has the capitals, GitHub does not (#388's review) ─────────
# Each site folds BOTH sides. With the registry always lowercase above, a fold of the board's
# spelling alone passed every test; a registry that says `Acme/API` for the repository GitHub
# spells `acme/api` is the same defect from the other side.

CAPITALISED = "Acme/API"


def test_a_registry_in_capitals_reads_its_own_card_bare(board):
    projects, _ = board(("I12", 12, "acme/api", "Backlog"), registry=CAPITALISED)

    assert projects.columns() == {"12": "Backlog"}
    assert projects.items_in_status("Backlog") == ["12"]
    assert qualify_ref("acme/api", "#12", CAPITALISED) == "12"


def test_a_registry_in_capitals_moves_the_card_github_spells_in_lowercase(board):
    projects, gh = board(("I12", 12, "acme/api", "Backlog"), registry=CAPITALISED)

    assert projects.set_column(issue="12", issue_url="https://github.com/Acme/API/issues/12",
                               name="In progress")
    assert gh.moves == [("I12", "o2")]


def test_a_registry_in_capitals_ranks_after_an_anchor_github_spells_in_lowercase(board):
    projects, gh = board(("I12", 12, "Acme/API", "Backlog"), ("I7", 7, "acme/api", "Backlog"),
                         registry=CAPITALISED)

    assert projects.place_after(issue="12", issue_url="https://github.com/Acme/API/issues/12",
                                after="7", column="Backlog")
    assert gh.positions == [("I12", "I7")]
