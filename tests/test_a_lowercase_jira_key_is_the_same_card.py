"""A Jira key typed in lowercase is the same card as the one the board spells in capitals (#108).

THE BUG. Jira answers every key in capitals, and the board read (`columns()`) is keyed that way.
The edit/close/remove gate (`actions/catalog.py::_stage`) and the product role's queueing
(`ProductModule.promote`) looked the ref up in that read as it was typed, so `dar-1` was missing
from it and read as "nobody moved it": the gate let an edit, a close and a removal of a running
card through, and the queueing sent a running card back to the queue.

WHAT IS DRIVEN HERE is the real `JiraProjectBoard` (and `JiraTracker`), built from a project's
tracker options, against a fake `urllib.request.urlopen` that matches `key = "..."`
case-insensitively, as Jira does.
"""

from __future__ import annotations

import io
import json
import re
import urllib.error
import urllib.parse

import pytest

from tests.test_several_projects_on_one_jira_project_read_only_their_own_slice import (
    SITE,
    _Answer,
    _api_product_module,
)

SM = {"backlog": "Backlog", "todo": "A Fazer", "in_progress": "Em andamento", "done": "Concluído"}


def _search(where: dict[str, tuple[str, str]], req) -> _Answer:
    """A `search/jql` answer: the keys in the label and the key the JQL names, the key matched
    ignoring case, and every key spelled in capitals, as Jira spells it."""
    split = urllib.parse.urlsplit(req.full_url)
    jql = (urllib.parse.parse_qs(split.query)["jql"][0] if req.get_method() == "GET"
           else json.loads(req.data)["jql"])
    label = re.search(r'labels = "([^"]+)"', jql)
    key = re.search(r'key = "([^"]+)"', jql)
    keys = [k for k, (lab, _) in where.items()
            if (label is None or lab == label.group(1))
            and (key is None or k.upper() == key.group(1).upper())]
    return _Answer({"isLast": True, "issues": [
        {"key": k, "fields": {"status": {"name": where[k][1]}}} for k in keys]})


@pytest.mark.parametrize("scope", ['labels = "bf-api"', ""], ids=["scoped", "unscoped"])
def test_a_lowercase_key_is_refused_by_the_gate_as_its_own_spelling(scope, tmp_path,
                                                                    monkeypatch):
    from beeverforge.actions.catalog import _stage_refusal
    from beeverforge.adapters.board import build_board
    from beeverforge.contracts.project import Project, ProviderRef

    where = {"DAR-1": ("bf-api", "Em andamento"), "DAR-2": ("bf-web", "A Fazer")}

    def urlopen(req, timeout=0):
        assert "search/jql" in req.full_url, req.full_url
        return _search(where, req)

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    options = {"site": SITE, "email": "a@b.c", "status_map": json.dumps(SM)}
    if scope:
        options["scope_jql"] = scope
    api = Project(name="api", repo_path=str(tmp_path / "api"),
                  tracker=ProviderRef(kind="jira", repo="DAR", options=options))
    board = build_board(api, token="t")

    for act in ("edit", "close", "remove"):
        lower = _stage_refusal(api, board, "dar-1", act=act)
        upper = _stage_refusal(api, board, "DAR-1", act=act)
        assert lower, act
        assert lower == upper, (act, lower, upper)


def test_the_gate_hands_the_rows_behind_it_the_boards_own_spelling(tmp_path, monkeypatch):
    """Every row behind `_stage` (move, edit, close, remove) acts on `_Stage.ref`, so the door
    records `DAR-1`'s history and the answer echoes `DAR-1`, never a second spelling of one card."""
    from beeverforge.actions.catalog import _stage
    from beeverforge.adapters.board import build_board
    from beeverforge.contracts.project import Project, ProviderRef

    where = {"DAR-1": ("bf-api", "Em andamento")}
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=0: _search(where, req))
    api = Project(name="api", repo_path=str(tmp_path / "api"), tracker=ProviderRef(
        kind="jira", repo="DAR", options={"site": SITE, "email": "a@b.c",
                                          "status_map": json.dumps(SM)}))
    board = build_board(api, token="t")

    assert _stage(api, board, "dar-1").ref == "DAR-1"
    assert _stage(api, board, "DAR-1").ref == ""


def _queueing_site(where: dict[str, tuple[str, str]], moved: list[str], refuse: list[bool]):
    """A Jira site that serves searches, card reads and transitions, records POSTed transitions,
    and answers 429 to the batch read (`ORDER BY Rank ASC`) while `refuse` holds a True."""

    def urlopen(req, timeout=0):
        split = urllib.parse.urlsplit(req.full_url)
        if "search/jql" in split.path:
            jql = (urllib.parse.parse_qs(split.query)["jql"][0] if req.get_method() == "GET"
                   else json.loads(req.data)["jql"])
            if jql.endswith("ORDER BY Rank ASC") and " status = " not in jql and refuse:
                refuse.pop()
                raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", hdrs=None,
                                             fp=io.BytesIO(b'{"errorMessages":["x"]}'))
            return _search(where, req)
        issue = re.search(r"(?i)issue/(DAR-\d+)(/transitions)?$", split.path)
        if issue is None:
            return _Answer({})
        key = issue.group(1).upper()
        if issue.group(2) and req.get_method() == "POST":
            moved.append(key)
            return _Answer({})
        if issue.group(2):
            return _Answer({"transitions": [{"id": "11", "name": "A Fazer",
                                             "to": {"name": "A Fazer"}}]})
        lab, status = where[key]
        return _Answer({"key": key, "fields": {
            "summary": "a running card", "description": None, "labels": [lab],
            "status": {"name": status, "statusCategory": {"key": "indeterminate"}}}})

    return urlopen


@pytest.mark.parametrize("refused_read", [False, True], ids=["read", "read-refused"])
@pytest.mark.parametrize("scope", ['labels = "bf-web"', ""], ids=["scoped", "unscoped"])
def test_a_lowercase_key_is_refused_queueing_as_its_own_spelling(scope, refused_read, tmp_path,
                                                                 monkeypatch):
    """Read or refused, the batch read is not what saves the card: when it is refused (a 429),
    the door reads the board again and must find `dar-2` where the board files `DAR-2`."""
    where = {"DAR-1": ("bf-api", "Backlog"), "DAR-2": ("bf-web", "Em andamento")}
    moved: list[str] = []
    refuse: list[bool] = []
    module = _api_product_module(tmp_path, monkeypatch, _queueing_site(where, moved, refuse),
                                 scope=scope)

    refuse[:] = [True] if refused_read else []
    [upper] = module.promote(["DAR-2"], actor="ana")
    assert refuse == [], "the batch read was not refused"
    refuse[:] = [True] if refused_read else []
    [lower] = module.promote(["dar-2"], actor="ana")
    assert refuse == [], "the batch read was not refused"

    assert not upper.ok, upper
    assert not lower.ok, "a running card typed in lowercase was queued"
    assert lower.refusal == upper.refusal, (lower.refusal, upper.refusal)
    assert lower.detail == upper.detail, (lower.detail, upper.detail)
    assert moved == []


def test_the_door_records_a_lowercase_key_under_the_boards_own_spelling():
    """A card the door is handed as `dar-1` (an unread batch, a caller with no gate of its own)
    keeps ONE history: the door reads the record under the board's spelling, writes it there and
    names the card that way (`contracts/refs.py::canonical_ref`, one spelling)."""
    from beeverforge.lifecycle import record
    from beeverforge.lifecycle.card import transition
    from beeverforge.lifecycle.ports import Seen
    from beeverforge.lifecycle.table import CardEvent, State
    from beeverforge.observability.metrics import InMemoryMetricsSink
    from tests.test_the_card_lifecycle_does_what_its_table_says import Ports, Project

    class Board(Ports):
        def seen(self, card):
            asked.append(card)
            return Seen(state=State.BACKLOG, ref="DAR-1" if card != "DAR-1" else "")

    asked: list[str] = []
    sink = InMemoryMetricsSink()
    ports = Board(Seen(state=State.BACKLOG), sink_=sink)

    moved = transition(Project(), "#dar-1", CardEvent.REMOVED, by="ana", why="filed twice",
                       ports=ports)

    assert moved.ok and moved.recorded, moved.refused
    assert moved.card == "DAR-1"
    assert asked == ["dar-1", "DAR-1"]
    assert len(record.read(sink, "acme", "DAR-1").rows) == 1
    assert not record.read(sink, "acme", "dar-1").rows
    assert {c[1] for c in ports.calls if len(c) > 1} == {"DAR-1"}
