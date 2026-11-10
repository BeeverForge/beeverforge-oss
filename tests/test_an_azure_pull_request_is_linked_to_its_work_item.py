"""The pull request the factory opens on Azure Repos is linked to the card's work item (#515).

The job named its card in the pull request's title and body (`#1234: title`, "Automated by
BeeverForge for #1234.") and the code said that mention "links the change to the card natively".
It links the COMMIT (`Fixed in Commit`); the pull request itself stayed unattached: Azure DevOps
turns a `#1234` into an association only where the pull request carries it as a work item
reference, and `open_pr` posted none. A person added the `Pull Request` link by hand, after the
fact, on every card.

What is held here:

  * the Azure forge sends `workItemRefs` when it is handed work items, and sends no such key when
    it is handed none — the payload of every other caller is unchanged;
  * only a number is a work item: a Jira key, a blank or a repeat is not sent;
  * LINKING IS A COURTESY, NEVER A REASON A PULL REQUEST DOES NOT OPEN. A create the vendor
    refuses because of the references is retried without them, and the log says so by name; a
    create refused for any other reason still raises, after exactly one retry;
  * the capability is DECLARED, like `closing_keyword`: a forge row that does not declare
    `links_work_items` is never handed the argument, so an out-of-tree row whose `open_pr` takes
    no `work_items` keeps working;
  * on the real job path the id is handed over only where the forge OWNS the card, so a local
    board's `#12` is never linked to somebody else's work item (#167).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from beeverforge.adapters.azure_devops import AzureDevOpsError
from beeverforge.contracts import JobState, Manifest
from tests.test_a_card_is_named_in_the_forge_only_where_the_forge_owns_it import (
    _ado_forge,
    _ado_tracker,
    _declaring,
    _local_tracker,
    _make_repo,
    _ticket,
)
from tests.test_the_ado_forge import FX_ADO_REPO, forge

_PRS = "git/repositories/fx-ado/pullrequests"
_OPENED = {"pullRequestId": 5, "repository": FX_ADO_REPO}


def _posted(f) -> list[dict]:
    return [b for m, p, b, _q in f.fake.calls if m == "POST" and p == _PRS]


# ── the Azure forge ─────────────────────────────────────────────────────────────────────────────

def test_the_pull_request_is_created_with_its_work_item() -> None:
    f = forge({f"GET {_PRS}": {"value": []}, f"POST {_PRS}": _OPENED})

    url = f.open_pr(head="feat/x", base="main", title="t", body="b", work_items=["1234"])

    assert _posted(f)[0]["workItemRefs"] == [{"id": "1234"}]
    assert url.endswith("/pullrequest/5")


def test_a_call_with_no_work_items_posts_the_payload_it_always_did() -> None:
    f = forge({f"GET {_PRS}": {"value": []}, f"POST {_PRS}": _OPENED})

    f.open_pr(head="feat/x", base="main", title="t", body="b")

    assert set(_posted(f)[0]) == {"sourceRefName", "targetRefName", "title", "description"}


def test_only_a_number_is_a_work_item() -> None:
    """A Jira key, a blank and a repeat are not work items of this vendor; the rest are sent once,
    in the order they were handed."""
    f = forge({f"GET {_PRS}": {"value": []}, f"POST {_PRS}": _OPENED})

    f.open_pr(head="feat/x", base="main", title="t", body="b",
              work_items=["PROJ-12", "", " 7 ", "7", "1234"])

    assert _posted(f)[0]["workItemRefs"] == [{"id": "7"}, {"id": "1234"}]


def test_work_items_that_are_all_refused_as_not_numbers_send_no_key() -> None:
    f = forge({f"GET {_PRS}": {"value": []}, f"POST {_PRS}": _OPENED})

    f.open_pr(head="feat/x", base="main", title="t", body="b", work_items=["PROJ-12", ""])

    assert "workItemRefs" not in _posted(f)[0]


def test_a_refused_link_does_not_stop_the_pull_request(caplog) -> None:
    """The vendor refuses the create while it carries the references (a permission on the work
    item, say): the pull request opens without them, and the log names what did not happen."""
    attempts: list[int] = []

    def create(_params):
        attempts.append(1)
        if len(attempts) == 1:
            raise AzureDevOpsError("POST … → 403 TF401027: you need the permission to link")
        return _OPENED

    f = forge({f"GET {_PRS}": {"value": []}, f"POST {_PRS}": create})

    with caplog.at_level("WARNING"):
        url = f.open_pr(head="feat/x", base="main", title="t", body="b", work_items=["1234"])

    posts = _posted(f)
    assert len(posts) == 2
    assert posts[0]["workItemRefs"] == [{"id": "1234"}]
    assert "workItemRefs" not in posts[1]
    assert url.endswith("/pullrequest/5")
    assert "BEEVERFORGE_PR_LINK_REFUSED" in caplog.text, "a link that was not made went unsaid"


def test_a_create_refused_for_any_other_reason_still_raises_after_one_retry() -> None:
    """The retry is not a way to swallow a failure: with no pull request to recover, it raises."""
    f = forge({f"GET {_PRS}": {"value": []}},
              raises={f"POST {_PRS}": AzureDevOpsError("POST … → 503 Service Unavailable")})

    with pytest.raises(AzureDevOpsError):
        f.open_pr(head="feat/x", base="main", title="t", body="b", work_items=["1234"])

    assert len(_posted(f)) == 2


def test_a_create_with_no_work_items_is_not_retried() -> None:
    f = forge({f"GET {_PRS}": {"value": []}},
              raises={f"POST {_PRS}": AzureDevOpsError("POST … → 503 Service Unavailable")})

    with pytest.raises(AzureDevOpsError):
        f.open_pr(head="feat/x", base="main", title="t", body="b")

    assert len(_posted(f)) == 1


# ── the declaration ─────────────────────────────────────────────────────────────────────────────

def test_the_azure_forge_declares_the_capability_and_no_other_shipped_row_does(tmp_path) -> None:
    from unittest.mock import MagicMock

    from beeverforge.adapters.forge.github import GitHubForge
    from beeverforge.adapters.forge.local import LocalForge
    from beeverforge.contracts.item_space import links_work_items

    assert links_work_items(_ado_forge("acme")) is True
    assert links_work_items(GitHubForge("acme/api", token="t")) is False
    assert links_work_items(LocalForge("shop", str(tmp_path / "repo"),
                                       db_path=tmp_path / "board.db")) is False
    # a double is not a declaration, and neither is a row that says nothing
    assert links_work_items(MagicMock()) is False
    assert links_work_items(object()) is False


# ── the real job path ───────────────────────────────────────────────────────────────────────────

@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return _make_repo(tmp_path)


def _forge_double(*, declares: bool):
    from tests.test_walking_skeleton import FakeForge

    class _Linking(FakeForge):
        links_work_items = True

        def open_pr(self, *, head, base, title, body, work_items=()):
            self.work_items = list(work_items)
            return super().open_pr(head=head, base=base, title=title, body=body)

    if declares:
        return _Linking()
    # the strict signature of a row from outside the tree: no `work_items`, no declaration
    return FakeForge()


def _run(repo: Path, tmp_path: Path, tracker_row, forge_row, ticket, forge):
    from tests.test_walking_skeleton import FakeTracker, _runner

    tracker = _declaring(FakeTracker(ticket), tracker_row)
    forge.item_space = forge_row.item_space
    forge.closing_keyword = forge_row.closing_keyword
    runner = _runner(repo, tracker, Manifest(validate={"test": "true", "security": "true"}),
                     tmp_path, forge=forge)
    runner.project = type("_Project", (), {"name": "shop"})()
    result = runner.run(ticket.id)
    assert result.state is JobState.PR_OPEN, result
    return forge


def test_a_card_the_forge_owns_is_handed_to_a_forge_that_links(repo, tmp_path) -> None:
    forge = _run(repo, tmp_path, _ado_tracker("Acme"), _ado_forge("acme"),
                 _ticket("1234", "Shop"), _forge_double(declares=True))

    assert forge.work_items == ["1234"]


def test_a_card_the_forge_does_not_own_is_never_handed_over(repo, tmp_path) -> None:
    """A local board's `#12` is a number in another project's board, not the work item 12 of this
    organisation: linking it would attach the pull request to somebody else's item."""
    forge = _run(repo, tmp_path, _local_tracker(tmp_path), _ado_forge("acme"),
                 _ticket("#12", "shop"), _forge_double(declares=True))

    assert forge.work_items == []


def test_a_forge_that_does_not_declare_the_capability_is_not_handed_the_argument(
        repo, tmp_path) -> None:
    """`FakeForge.open_pr` has the strict signature of a row from outside the tree: handed
    `work_items` it would raise `TypeError`. It is not handed it, and the job reaches PR_OPEN."""
    forge = _run(repo, tmp_path, _ado_tracker("Acme"), _ado_forge("acme"),
                 _ticket("1234", "Shop"), _forge_double(declares=False))

    assert forge.opened["title"] == "#1234: add the export"
