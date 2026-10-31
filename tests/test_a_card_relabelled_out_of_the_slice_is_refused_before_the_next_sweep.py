"""A card relabelled out of a project's Jira slice is refused before the next full sweep (#122).

THE GAP. The product role's board is swept once and then refreshed with
`list_tickets(updated_since=…)` within the project's scope (`product/board.py::_refresh`). A card
relabelled out of the slice IS updated, but the scoped search no longer returns it, and Jira's
`removed_since` answers `[]`, so the card stays in the snapshot until the full sweep
(`_FULL_AFTER`, six hours). In that window `_close_one` (and `withdraw_card` through it) and
`correct_card` treated it as this project's card; `promote` did not, because it asks `holds`.

WHAT IS HELD HERE. The real `read_board`, with its snapshot, over an in-memory scoped tracker: a
card relabelled between two reads is still in the snapshot (the window is real), and the close
and the correction then ask the board's `holds` and refuse it by name. A slice that could not be
asked is a failure, never "inside"; a card still in the slice is acted on as before.
"""

from __future__ import annotations

import pytest

from beeverforge.adapters.tracker.base import TicketSummary
from beeverforge.contracts.product import ProductConfig
from beeverforge.contracts.project import Project, ProviderRef
from beeverforge.ops import impediment
from beeverforge.product import board as board_module
from beeverforge.product.authoring import NOT_WAITING, ticket_body
from beeverforge.product.module import ProductModule
from beeverforge.product.triage import Ticket
from beeverforge.product.voice import board_move_said, card_said

ADMIN = "U0PO"
TODO = "A Fazer"
API, WEB = "bf-api", "bf-web"
FIRST, LATER = "2026-10-01T10:00:00.000+0000", "2026-10-02T10:00:00.000+0000"


class _Tracker:
    """A Jira project shared by two platform projects: every read is narrowed to `bf-api`.

    It has no removal of its own, so `removed_since` answers `[]`, exactly as the Jira row does.
    It records every write the card's door asks of it."""

    def __init__(self, labels: dict[str, str]) -> None:
        self.labels = labels
        self.updated = {ref: FIRST for ref in labels}
        self.closed: list[str] = []
        self.comments: list[tuple[str, str]] = []
        self.bodies: list[tuple[str, str]] = []
        self.listed: list[str | None] = []

    def relabel(self, ref: str, label: str) -> None:
        """What a person does in Jira: the label changes, and so does the card's `updated`."""
        self.labels[ref] = label
        self.updated[ref] = LATER

    def _summary(self, ref: str) -> TicketSummary:
        return TicketSummary(
            ref=ref, title=f"Card {ref}", labels=[self.labels[ref]],
            body=ticket_body(described=f"o pedido {ref}", reported_by=f"<@{ADMIN}>",
                             source="chat"),
            updated_at=self.updated[ref])

    def list_tickets(self, *, state: str = "open", updated_since: str | None = None,
                     limit: int = 0, **_kw) -> list[TicketSummary]:
        self.listed.append(updated_since)
        return [self._summary(ref) for ref, label in self.labels.items()
                if label == API and (updated_since is None or self.updated[ref] >= updated_since)]

    def get_ticket(self, ref: str):
        ref = str(ref).lstrip("#")
        if ref not in self.labels:
            raise KeyError(ref)
        s = self._summary(ref)
        return Ticket(number=ref, title=s.title, body=s.body, column=TODO,
                      state="closed" if ref in self.closed else "open")

    def close_ticket(self, ref: str, reason: str, *, delivered: bool = True) -> None:
        self.closed.append(str(ref).lstrip("#"))

    def comment(self, ref: str, body: str) -> None:
        self.comments.append((str(ref), body))

    def update_body(self, ref: str, body: str) -> None:
        self.bodies.append((str(ref), body))


class _Board:
    """The scoped Jira board: `holds` answers from the labels, as the slice's own search would."""

    stage_option = "status_map"

    def __init__(self, tracker: _Tracker) -> None:
        self.tracker = tracker
        self.unreadable = False
        self.asked: list[str] = []

    def holds(self, ref: str) -> bool | None:
        self.asked.append(ref)
        if self.unreadable:
            return None
        return self.tracker.labels.get(str(ref).lstrip("#")) == API

    def stage_key(self, column: str) -> str:
        return {TODO: "todo"}.get(column, "")

    def columns(self) -> dict[str, str]:
        return {ref: TODO for ref, label in self.tracker.labels.items() if label == API}


@pytest.fixture(autouse=True)
def _isolate():
    """The snapshot and the impediment memory are process-global."""
    impediment._LAST.clear()
    board_module.forget_board()
    yield
    impediment._LAST.clear()
    board_module.forget_board()


@pytest.fixture
def world(monkeypatch):
    tracker = _Tracker({"DAR-1": API, "DAR-9": API})
    board = _Board(tracker)
    monkeypatch.setattr(board_module, "_tracker", lambda project, credential: tracker)
    monkeypatch.setattr(board_module, "_columns", lambda project, token: board.columns())
    # the card's door builds its own board for the move; it is this one, never a real site
    monkeypatch.setattr("beeverforge.adapters.board.build_board",
                        lambda project, **kw: board)
    project = Project(name="api", repo_path="/work/api",
                      tracker=ProviderRef(kind="jira", repo="DAR",
                                          options={"scope_jql": 'labels = "bf-api"'}),
                      product=ProductConfig(docs_repo="acme/docs", admins=[ADMIN]))
    module = ProductModule(project, tracker=tracker, board=board)
    return project, tracker, board, module


def _relabelled_between_two_reads(project, tracker) -> None:
    """Read, relabel `DAR-1` out of the slice, read again — the refresh, not a sweep."""
    first, error = board_module.read_board(project)
    assert not error and "DAR-1" in [t.number for t in first]
    tracker.relabel("DAR-1", WEB)
    second, error = board_module.read_board(project)
    assert not error
    assert tracker.listed[-1] == FIRST, "the second read was a sweep, not the refresh"
    assert "DAR-1" in [t.number for t in second]


def _close(module, ref):
    return module._close_one(ref, actor=ADMIN, in_favour_of=None, reason="x")


def _correct(module, ref):
    return module.correct_card(ref, actor=ADMIN, text="o pedido corrigido")


ACTS = [pytest.param(_close, id="close"), pytest.param(_correct, id="correct")]


def test_the_snapshot_still_holds_a_relabelled_card(world):
    """The window is real: two reads, a relabel between them, and the card is still there."""
    project, tracker, _, _ = world

    _relabelled_between_two_reads(project, tracker)


def test_a_close_of_a_card_relabelled_out_of_the_slice_is_refused_before_the_next_sweep(world):
    project, tracker, board, module = world
    _relabelled_between_two_reads(project, tracker)

    res = _close(module, "DAR-1")

    assert not res.ok
    assert res.refusal == NOT_WAITING
    assert res.detail == board_move_said("outside_the_slice", ref="DAR-1", project="api")
    assert "DAR-1" in board.asked
    assert tracker.closed == [] and tracker.comments == []


def test_a_withdrawal_of_a_card_relabelled_out_of_the_slice_is_refused_too(world):
    """`withdraw_card` closes through `_close_one`, so the card's own control is refused too."""
    project, tracker, _, module = world
    _relabelled_between_two_reads(project, tracker)

    res = module.withdraw_card("DAR-1", actor=ADMIN, reason="x")

    assert not res.ok and res.refusal == NOT_WAITING
    assert tracker.closed == []


def test_a_correction_of_a_card_relabelled_out_of_the_slice_is_refused_before_the_next_sweep(
        world):
    project, tracker, board, module = world
    _relabelled_between_two_reads(project, tracker)

    res = _correct(module, "DAR-1")

    assert not res.ok
    assert res.refusal == NOT_WAITING
    assert res.detail == board_move_said("outside_the_slice", ref="DAR-1", project="api")
    assert "DAR-1" in board.asked
    assert tracker.bodies == [] and tracker.comments == []


@pytest.mark.parametrize("act", ACTS)
def test_a_slice_that_cannot_be_asked_is_a_failure_not_inside(world, act):
    project, tracker, board, module = world
    _relabelled_between_two_reads(project, tracker)
    board.unreadable = True

    res = act(module, "DAR-1")

    assert not res.ok
    assert res.refusal != NOT_WAITING
    assert res.detail == card_said("board_unreadable")
    assert tracker.closed == [] and tracker.bodies == [] and tracker.comments == []


@pytest.mark.parametrize("act", ACTS)
def test_a_card_still_in_the_slice_is_acted_on(world, act):
    """The guard is not a blanket refusal: `DAR-9` stayed `bf-api`."""
    project, tracker, board, module = world
    _relabelled_between_two_reads(project, tracker)

    res = act(module, "DAR-9")

    assert res.ok, res.detail
    assert "DAR-9" in board.asked
    assert tracker.closed == ["DAR-9"] or tracker.bodies[0][0].lstrip("#") == "DAR-9"


@pytest.mark.parametrize("act", ACTS)
def test_a_board_that_has_no_slice_acts_as_before(world, monkeypatch, act):
    """A board with no `holds` (the local board, GitHub) has no slice to leave: the act goes on."""
    project, tracker, board, module = world
    _relabelled_between_two_reads(project, tracker)
    monkeypatch.delattr(_Board, "holds")

    res = act(module, "DAR-9")

    assert res.ok, res.detail
