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
  * only a positive whole number is a work item, and it is compared as a number: a Jira key, a
    `0` or a blank is not sent, `007` and `7` are one item, and an item dropped for not being a
    number is said so in the log;
  * LINKING IS A COURTESY, NEVER A REASON A PULL REQUEST DOES NOT OPEN. A create the vendor
    REFUSES (a 400, 403 or 404) is repeated once without the references, and the log blames the
    link only when that repeat went through. A create whose outcome is not known (no answer, a
    5xx) is NOT repeated blind, because it may have been done: it is looked up, and raises if
    there is nothing to find;
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
    """A Jira key and a blank are not work items of this vendor; the rest are sent once, in the
    order they were handed."""
    f = forge({f"GET {_PRS}": {"value": []}, f"POST {_PRS}": _OPENED})

    f.open_pr(head="feat/x", base="main", title="t", body="b",
              work_items=["PROJ-12", "", " 7 ", "7", "1234"])

    assert _posted(f)[0]["workItemRefs"] == [{"id": "7"}, {"id": "1234"}]


def test_a_work_item_is_compared_as_a_number_and_sent_in_its_canonical_form() -> None:
    """`007` and `7` are one work item: sending both is the same item twice, and the vendor is
    handed the number, not the spelling."""
    f = forge({f"GET {_PRS}": {"value": []}, f"POST {_PRS}": _OPENED})

    f.open_pr(head="feat/x", base="main", title="t", body="b", work_items=["007", "7", "0012"])

    assert _posted(f)[0]["workItemRefs"] == [{"id": "7"}, {"id": "12"}]


@pytest.mark.parametrize("zero", ["0", "00", " 0 "])
def test_zero_is_not_a_work_item(zero, caplog) -> None:
    """Work item ids start at 1. A `0` sent to the vendor is a create it refuses, and the retry that
    follows is a second request for nothing."""
    f = forge({f"GET {_PRS}": {"value": []}, f"POST {_PRS}": _OPENED})

    with caplog.at_level("WARNING"):
        f.open_pr(head="feat/x", base="main", title="t", body="b", work_items=[zero, "9"])

    assert _posted(f)[0]["workItemRefs"] == [{"id": "9"}]


def test_work_items_that_are_all_refused_as_not_numbers_send_no_key() -> None:
    f = forge({f"GET {_PRS}": {"value": []}, f"POST {_PRS}": _OPENED})

    f.open_pr(head="feat/x", base="main", title="t", body="b", work_items=["PROJ-12", ""])

    assert "workItemRefs" not in _posted(f)[0]


def test_an_item_dropped_for_not_being_a_number_is_said(caplog) -> None:
    """The pull request still opens, so without the line it is simply unlinked and nothing says
    why — an owned card whose id is not a plain integer (a qualified id left in `bare`)."""
    f = forge({f"GET {_PRS}": {"value": []}, f"POST {_PRS}": _OPENED})

    with caplog.at_level("WARNING"):
        f.open_pr(head="feat/x", base="main", title="t", body="b",
                  work_items=["owner/repo#12", "0", "1234"])

    assert caplog.text.count("BEEVERFORGE_PR_LINK_SKIPPED") == 2
    assert "owner/repo#12" in caplog.text
    assert _posted(f)[0]["workItemRefs"] == [{"id": "1234"}]


def test_a_blank_and_a_repeat_are_not_drops(caplog) -> None:
    """A blank is nothing handed and a repeat is the same item again: neither is said, or the log
    cries for items that were never lost."""
    f = forge({f"GET {_PRS}": {"value": []}, f"POST {_PRS}": _OPENED})

    with caplog.at_level("WARNING"):
        f.open_pr(head="feat/x", base="main", title="t", body="b",
                  work_items=["", " ", "1234", "1234", "01234"])

    assert "BEEVERFORGE_PR_LINK_SKIPPED" not in caplog.text
    assert _posted(f)[0]["workItemRefs"] == [{"id": "1234"}]


# ── a refusal is not a failure to answer ────────────────────────────────────────────────────────

def _refusing_once(status: int, message: str = "POST … refused"):
    """A create that answers `status` the first time and opens the pull request the second."""
    attempts: list[int] = []

    def create(_params):
        attempts.append(1)
        if len(attempts) == 1:
            raise AzureDevOpsError(message, status=status)
        return _OPENED

    return create


@pytest.mark.parametrize("status", [400, 403, 404])
def test_a_refused_link_does_not_stop_the_pull_request(status, caplog) -> None:
    """The vendor refuses the create while it carries the references (a permission on the work
    item, say): the pull request opens without them, and the log names what did not happen."""
    f = forge({f"GET {_PRS}": {"value": []},
               f"POST {_PRS}": _refusing_once(status, f"POST … → {status} TF401027: no right")})

    with caplog.at_level("WARNING"):
        url = f.open_pr(head="feat/x", base="main", title="t", body="b", work_items=["1234"])

    posts = _posted(f)
    assert len(posts) == 2
    assert posts[0]["workItemRefs"] == [{"id": "1234"}]
    assert "workItemRefs" not in posts[1]
    assert url.endswith("/pullrequest/5")
    assert "BEEVERFORGE_PR_LINK_REFUSED" in caplog.text, "a link that was not made went unsaid"


def test_a_refused_link_is_said_with_everything_the_vendor_said(caplog) -> None:
    """The part of a TF4xxxx sentence that names the work item and the missing permission comes
    late in the line; cutting the message at 160 characters threw away what the operator needed."""
    long_sentence = "POST … → 403 Forbidden: " + "x" * 300 + " TF401027 work item 1234 needs LINK"
    f = forge({f"GET {_PRS}": {"value": []}, f"POST {_PRS}": _refusing_once(403, long_sentence)})

    with caplog.at_level("WARNING"):
        f.open_pr(head="feat/x", base="main", title="t", body="b", work_items=["1234"])

    assert "TF401027 work item 1234 needs LINK" in caplog.text


@pytest.mark.parametrize("status", [None, 500, 502, 503, 504])
def test_a_create_whose_outcome_is_not_known_is_not_repeated(status) -> None:
    """No answer at all, or a 5xx: the vendor may have created the pull request before the line
    dropped. A second create is then a second request for the same branch pair, and what keeps it
    from being a duplicate is the vendor refusing it. It is not sent: nothing is found to recover,
    so it raises, once."""
    f = forge({f"GET {_PRS}": {"value": []}},
              raises={f"POST {_PRS}": AzureDevOpsError("POST … failed", status=status)})

    with pytest.raises(AzureDevOpsError):
        f.open_pr(head="feat/x", base="main", title="t", body="b", work_items=["1234"])

    assert len(_posted(f)) == 1


@pytest.mark.parametrize("status", [401, 409])
def test_a_refusal_the_references_cannot_have_caused_is_not_repeated(status) -> None:
    """A bad credential and a lost race fail the same way with or without the references."""
    f = forge({f"GET {_PRS}": {"value": []}},
              raises={f"POST {_PRS}": AzureDevOpsError("POST … refused", status=status)})

    with pytest.raises(AzureDevOpsError):
        f.open_pr(head="feat/x", base="main", title="t", body="b", work_items=["1234"])

    assert len(_posted(f)) == 1


def test_a_create_that_dropped_after_the_vendor_made_it_finds_the_pull_request(caplog) -> None:
    """THE CASE THE RETRY MADE WORSE: the first create was done server-side and the answer was lost
    (a 503). The lookup that follows finds the pull request and returns it — with no second create
    to depend on the vendor refusing it."""
    lookups: list[int] = []

    def active(_params):
        lookups.append(1)
        # empty at the idempotency check, the pull request itself at the recovery lookup
        return {"value": [] if len(lookups) == 1 else [_OPENED]}

    f = forge({f"GET {_PRS}": active},
              raises={f"POST {_PRS}": AzureDevOpsError("POST … → 503", status=503)})

    with caplog.at_level("WARNING"):
        url = f.open_pr(head="feat/x", base="main", title="t", body="b", work_items=["1234"])

    assert url.endswith("/pullrequest/5")
    assert len(_posted(f)) == 1, "a create whose outcome was unknown was sent again"
    assert "BEEVERFORGE_PR_LINK_REFUSED" not in caplog.text, "the link was blamed for a 503"


def test_a_link_is_not_blamed_when_the_repeat_without_it_is_refused_too(caplog) -> None:
    """Refused with the references and refused without them: the references were not the cause,
    and a line that says they were sends the operator to the wrong permission."""
    f = forge({f"GET {_PRS}": {"value": []}},
              raises={f"POST {_PRS}": AzureDevOpsError("POST … → 403", status=403)})

    with caplog.at_level("WARNING"), pytest.raises(AzureDevOpsError):
        f.open_pr(head="feat/x", base="main", title="t", body="b", work_items=["1234"])

    assert len(_posted(f)) == 2
    assert "BEEVERFORGE_PR_LINK_REFUSED" not in caplog.text


def test_a_create_with_no_work_items_is_not_retried() -> None:
    f = forge({f"GET {_PRS}": {"value": []}},
              raises={f"POST {_PRS}": AzureDevOpsError("POST … → 403", status=403)})

    with pytest.raises(AzureDevOpsError):
        f.open_pr(head="feat/x", base="main", title="t", body="b")

    assert len(_posted(f)) == 1


# ── the client says whether the server answered ─────────────────────────────────────────────────

def test_the_client_carries_the_status_the_server_answered_with(monkeypatch) -> None:
    """What `open_pr` decides on: a 4xx is a refusal, no answer is not."""
    import io
    import urllib.error
    import urllib.request

    from beeverforge.adapters.azure_devops import AzureDevOpsClient

    def refuse(req, timeout=None):  # noqa: ARG001 — the real signature
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {},
                                     io.BytesIO(b'{"message": "TF401027: you need LINK"}'))

    def drop(req, timeout=None):  # noqa: ARG001
        raise urllib.error.URLError("connection reset")

    client = AzureDevOpsClient(organization="acme-ai", project="factory", token="x" * 52)

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    with pytest.raises(AzureDevOpsError) as refused:
        client.call("POST", "git/repositories/r/pullrequests", body={})
    assert refused.value.status == 403
    assert "TF401027" in str(refused.value)

    monkeypatch.setattr(urllib.request, "urlopen", drop)
    with pytest.raises(AzureDevOpsError) as dropped:
        client.call("POST", "git/repositories/r/pullrequests", body={})
    assert dropped.value.status is None


def test_an_error_built_with_a_sentence_alone_has_no_status() -> None:
    """Every `AzureDevOpsError("…")` in the tree keeps working, and says it has no status."""
    assert AzureDevOpsError("a sentence").status is None
    assert str(AzureDevOpsError("a sentence")) == "a sentence"


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
