"""A project runs only as many cards at once as its lane allows (`BEEVERFORGE_JOBS_PER_PROJECT`,
#473).

THE DEFECT. The floor (`BEEVERFORGE_MAX_CONCURRENT_JOBS`) is shared by every project, and the
poller takes TO-DO cards in board order until the floor is full. With a floor above 1, one
project's cards could take every slot, and cards of one project that build on each other (create a
record, then edit it, then delete it) started at the same time, each from a base where the earlier
ones were not merged yet. With a lane of 1 a project runs one card at a time and its others wait
in TO-DO, while another project's card still starts. No lane keeps the floor alone, as before.

The doubles are the engine's list of running jobs and, for the unit rows, the registry's names;
the cut is the shipped `_within_the_projects_lane`, and the last rows run the shipped `scan_todo`
over a real local board.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from beeverforge.runtime.temporal import activities as act
from beeverforge.runtime.temporal import jobs_per_project

LANE = "BEEVERFORGE_JOBS_PER_PROJECT"
NAMES = ["web", "api", "shop", "shop-admin"]


class _Engine:
    """The engine's visibility list: the ids of the jobs running now."""

    def __init__(self, running: list[str]) -> None:
        self.running = running

    async def list_workflows(self, query: str):
        assert 'WorkflowType = "JobWorkflow"' in query and 'ExecutionStatus = "Running"' in query
        for wid in self.running:
            yield SimpleNamespace(id=wid)


def _engine(monkeypatch, running: list[str]) -> None:
    monkeypatch.setattr(act, "engine_client", lambda: _Engine(running))


def _lane(monkeypatch, value: str | None) -> None:
    if value is None:
        monkeypatch.delenv(LANE, raising=False)
    else:
        monkeypatch.setenv(LANE, value)


@pytest.fixture
def world(monkeypatch):
    def _set(running: list[str], lane: str | None):
        _engine(monkeypatch, running)
        monkeypatch.setattr(act, "ProjectRegistry",
                            lambda: SimpleNamespace(list=lambda: [SimpleNamespace(name=n)
                                                                  for n in NAMES]))
        _lane(monkeypatch, lane)
    return _set


def _cut(project: str, admitted: list[str]) -> list[str]:
    return asyncio.run(act._within_the_projects_lane(project, admitted))


def test_with_a_lane_of_one_a_busy_project_starts_nothing(world):
    world(["beeverforge-web-1"], "1")

    assert _cut("web", ["2", "3"]) == []


def test_with_a_lane_of_one_an_idle_project_starts_only_its_first_card(world):
    world([], "1")

    assert _cut("web", ["1", "2", "3"]) == ["1"]


def test_another_projects_running_card_does_not_take_this_projects_lane(world):
    world(["beeverforge-web-1", "beeverforge-other-74"], "1")

    assert _cut("api", ["1", "2"]) == ["1"]


def test_a_job_belongs_to_the_longest_project_name_that_prefixes_it(world):
    world(["beeverforge-shop-admin-7"], "1")

    assert _cut("shop", ["12"]) == ["12"]
    assert _cut("shop-admin", ["8"]) == []

    world(["beeverforge-shop-12"], "1")

    assert _cut("shop", ["13"]) == []
    assert _cut("shop-admin", ["8"]) == ["8"]


def test_a_ref_with_a_hyphen_is_still_its_projects_job(world):
    """A Jira ref carries a hyphen (`ADM-7`), so the id is split at a registered name, never at its
    last hyphen, which would file the job under a project called `shop-ADM`."""
    world(["beeverforge-shop-ADM-7"], "1")

    assert _cut("shop", ["ADM-8"]) == []


@pytest.mark.parametrize("lane", [None, "", " ", "0", "-1", "many"])
def test_without_a_lane_the_floor_alone_decides(world, lane):
    world(["beeverforge-web-1", "beeverforge-web-2"], lane)

    assert _cut("web", ["3", "4"]) == ["3", "4"]


@pytest.mark.parametrize("value", [None, "", " ", "0", "-1", "-7", "many"])
def test_a_lane_the_reference_calls_none_reads_as_zero(monkeypatch, value):
    """What the configuration reference promises of the value itself: unset, empty, `0`, below `0`
    and not a whole number all read as `0`, never as a negative width a reader could compute with."""
    _lane(monkeypatch, value)

    assert jobs_per_project() == 0


def test_a_wider_lane_lets_that_many_run(world):
    world(["beeverforge-web-1"], "2")

    assert _cut("web", ["2", "3"]) == ["2"]


def test_a_lane_that_is_not_a_number_is_said_in_the_log(monkeypatch, caplog):
    _lane(monkeypatch, "many")

    with caplog.at_level("WARNING", logger="beeverforge.runtime.temporal"):
        assert jobs_per_project() == 0

    assert LANE in caplog.text and "many" in caplog.text


# ── the poller's own read ───────────────────────────────────────────────────────────────────────

QUEUE = "TO-DO"


def _a_project_with_three_cards_in_todo(monkeypatch, tmp_path) -> None:
    """`shop` and `shop-admin` registered on the local row, `shop`'s #1–#3 in TO-DO."""
    from beeverforge.adapters.board import build_board
    from beeverforge.adapters.board_setup.local import LocalBoardSetup
    from beeverforge.adapters.tracker.registry import build_tracker
    from beeverforge.contracts.project import Project, ProviderRef
    from beeverforge.registry import ProjectRegistry

    monkeypatch.setenv("BEEVERFORGE_BOARD_DB", str(tmp_path / "board.db"))
    monkeypatch.setenv("BEEVERFORGE_REGISTRY", str(tmp_path / "registry.yaml"))
    # A WORKTREE BOX HAS NOTHING TO PROVE (ADR-0037 D5), so no proof gates this pickup
    monkeypatch.setenv("BEEVERFORGE_SANDBOX", "worktree")
    registry = ProjectRegistry()
    for name in ("shop", "shop-admin"):
        registry.add(Project(name=name, repo_path=str(tmp_path), language="en",
                             tracker=ProviderRef(kind="local", repo=name, options={})))
    project = registry.get("shop")
    LocalBoardSetup().create(project=project, owner="", title="shop", token=None)
    tracker = build_tracker(project)
    cards = [tracker.create_ticket(title=t, body="x") for t in ("create", "edit", "delete")]
    assert cards == ["#1", "#2", "#3"]
    board = build_board(project)
    for n in ("1", "2", "3"):
        assert board.set_column(issue=n, issue_url="", name=QUEUE) is True


def _scan() -> list[str]:
    from beeverforge.runtime.temporal.io import ScanInput

    return asyncio.run(act.scan_todo(ScanInput(project="shop", board_owner="", board_number="",
                                               pickup_status=QUEUE)))


def test_the_poller_reads_the_queue_through_the_lane(monkeypatch, tmp_path):
    _a_project_with_three_cards_in_todo(monkeypatch, tmp_path)
    _lane(monkeypatch, "1")

    # a job of `shop-admin`, whose id `shop`'s prefix also starts, is not `shop`'s
    _engine(monkeypatch, ["beeverforge-shop-admin-9"])
    assert _scan() == ["1"]

    _engine(monkeypatch, ["beeverforge-shop-1"])
    assert _scan() == []


def test_without_a_lane_the_poller_reads_the_whole_queue(monkeypatch, tmp_path):
    _a_project_with_three_cards_in_todo(monkeypatch, tmp_path)
    _lane(monkeypatch, None)
    _engine(monkeypatch, ["beeverforge-shop-1"])

    assert _scan() == ["1", "2", "3"]


# ── the panel's "Scan TO-DO now" button holds the same lane (#480) ──────────────────────────────
#
# The button (`actions/catalog.py::_scan`, `POST /api/projects/{project}/scan`) counted the floor
# alone, so pressing it on an idle floor started a project's whole TO-DO at once — the dependent
# cards the lane exists to keep apart. The doubles are the ones `test_the_action_layer.py` gives
# `_scan`; the cut is the shipped action.

from beeverforge import actions  # noqa: E402
from tests.test_the_action_layer import (  # noqa: E402
    _AsyncReturns,
    _FakeBoard,
    _FakeTemporalClient,
    _scan_project,
)


@pytest.fixture
def button(monkeypatch):
    from beeverforge.registry import ProjectRegistry

    project = _scan_project()  # registered as `demo`
    monkeypatch.setattr(ProjectRegistry, "get", lambda self, name: project)
    monkeypatch.setattr(ProjectRegistry, "list",
                        lambda self: [SimpleNamespace(name=n) for n in ("demo", "demo-admin")])
    monkeypatch.setattr("beeverforge.credentials.tracker_token", lambda: "tok")
    monkeypatch.setattr("beeverforge.factory.resolve_box_image",
                        lambda *_a, **_kw: "beeverforge-python")
    monkeypatch.setattr("beeverforge.runtime.temporal.max_concurrent_jobs", lambda: 3)

    def _set(todo: list[str], running: list[str], lane: str | None) -> _FakeTemporalClient:
        client = _FakeTemporalClient(running=running)
        monkeypatch.setattr("beeverforge.adapters.board.build_board",
                            lambda *_a, **_kw: _FakeBoard(todo))
        monkeypatch.setattr("beeverforge.runtime.temporal.view.connect",
                            lambda: _AsyncReturns(client))
        _lane(monkeypatch, lane)
        return client
    return _set


async def test_the_button_starts_only_the_first_card_on_an_idle_floor(button):
    client = button(["1", "2", "3"], [], "1")

    out = await actions.perform("scan", by=actions.SYSTEM, project="demo")

    assert out.data["started"] == ["1"] and out.data["skipped"] == ["2", "3"]
    assert [wf_id for wf_id, _ in client.launched] == ["beeverforge-demo-1"]


async def test_the_button_starts_nothing_while_the_projects_card_runs_and_says_why(button):
    client = button(["2", "3"], ["beeverforge-demo-1"], "1")

    out = await actions.perform("scan", by=actions.SYSTEM, project="demo")

    assert out.data["started"] == [] and client.launched == []
    assert "lane of 1" in out.message


async def test_a_job_of_a_longer_name_does_not_take_the_buttons_lane(button):
    button(["1", "2"], ["beeverforge-demo-admin-9"], "1")

    out = await actions.perform("scan", by=actions.SYSTEM, project="demo")

    assert out.data["started"] == ["1"]


async def test_a_ref_with_a_hyphen_is_still_the_buttons_projects_job(button):
    button(["1", "2"], ["beeverforge-demo-CONT-7"], "1")

    out = await actions.perform("scan", by=actions.SYSTEM, project="demo")

    assert out.data["started"] == []


async def test_a_wider_lane_lets_the_button_start_that_many(button):
    button(["2", "3", "4"], ["beeverforge-demo-1"], "3")

    out = await actions.perform("scan", by=actions.SYSTEM, project="demo")

    assert out.data["started"] == ["2", "3"]  # the lane has room for 2, and so has the floor


async def test_without_a_lane_the_button_fills_the_floor(button):
    button(["1", "2", "3"], [], None)

    out = await actions.perform("scan", by=actions.SYSTEM, project="demo")

    assert out.data["started"] == ["1", "2", "3"]
