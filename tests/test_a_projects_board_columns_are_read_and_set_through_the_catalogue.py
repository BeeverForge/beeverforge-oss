"""#585: a project's board column mapping is read and set through the catalogue.

THE MAPPING WAS A LINE OF YAML. `columns: '{"todo": "Approved"}'` (`status_map` on Jira) in a
project's tracker options was how a stage came to be a column, and the doctor's `board_columns` and
`board_stages` findings sent a person to write it by hand, inside the worker image. These rows read
it and set it the way `project_set_preview` sets its field.

DRIVEN OVER THE REAL `GitHubProjectBoard` built by the registry row from the project's own tracker
options — only the one network read, which columns the board has, is replaced — and the real
doctor probes over it, so "the doctor reads the new mapping" is measured, not asserted.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from typer.testing import CliRunner

from beeverforge import actions

ADMIN = actions.Actor(id="rob", via="panel", admin=True)
COLUMNS = ["New", "Ready", "Doing", "Checking", "Shipped"]


@pytest.fixture
def board(tmp_path, monkeypatch):
    """A registry holding `acme` on a GitHub board whose columns are its own words. Yields the
    list the board reports, so a case can change what the board has."""
    from beeverforge.adapters.tracker.github_project import GitHubProjectBoard
    from beeverforge.contracts.project import Project, ProviderRef
    from beeverforge.registry import ProjectRegistry

    path = tmp_path / "registry.yaml"
    monkeypatch.setenv("BEEVERFORGE_REGISTRY", str(path))
    ProjectRegistry().add(Project(
        name="acme", repo_path=str(tmp_path / "acme"),
        tracker=ProviderRef(kind="github", repo="acme/web",
                            options={"board_owner": "acme", "board_number": "7"}),
        forge=ProviderRef(kind="local", repo="acme", options={})))
    reported = list(COLUMNS)
    monkeypatch.setattr(GitHubProjectBoard, "column_names", lambda self: list(reported))
    reported_ref = reported
    return type("Board", (), {"registry": path, "columns": reported_ref})


def _read(**params):
    return asyncio.run(actions.perform("project_board_columns", by=ADMIN, project="acme",
                                       **params))


def _set(**params):
    return asyncio.run(actions.perform("project_set_board_columns", by=ADMIN, project="acme",
                                       **params))


def _held() -> dict:
    from beeverforge.registry import ProjectRegistry

    return ProjectRegistry().get("acme").tracker.options


# ── the read ────────────────────────────────────────────────────────────────────────────────────

def test_the_read_answers_the_board_its_columns_and_a_stage_with_no_column_as_unmapped(board):
    out = _read()

    assert out.ok, out
    data = out.data
    assert data["board"]["kind"] == "github" and data["board"]["address"] == "acme/7"
    assert data["columns"] == COLUMNS
    # nothing declared: no column of this board is a stage's, and the read says so by stage
    assert data["mapping"]["todo"] is None and data["mapping"]["done"] is None
    assert set(data["mapping"]) >= {"backlog", "todo", "in_progress", "in_review", "done"}
    # the platform's own `TO-DO` is what dispatches, and this board has no such column
    assert data["pickup"] == "TO-DO" and data["pickup_on_board"] is False


def test_the_read_answers_the_mapping_a_set_wrote_and_the_column_that_dispatches(board):
    assert _set(columns={"todo": "Ready", "in_progress": "Doing", "done": "Shipped"}).ok

    data = _read().data

    assert data["mapping"]["todo"] == "Ready" and data["mapping"]["done"] == "Shipped"
    assert data["mapping"]["in_review"] is None
    assert data["pickup"] == "Ready"


def test_a_project_with_no_board_reads_as_having_none(tmp_path, monkeypatch):
    from beeverforge.contracts.project import Project, ProviderRef
    from beeverforge.registry import ProjectRegistry

    monkeypatch.setenv("BEEVERFORGE_REGISTRY", str(tmp_path / "registry.yaml"))
    ProjectRegistry().add(Project(
        name="acme", repo_path=str(tmp_path / "acme"),
        tracker=ProviderRef(kind="github", repo="acme/web", options={}),
        forge=ProviderRef(kind="local", repo="acme", options={})))

    out = _read()

    assert out.ok and out.data["board"] is None and "no board" in out.message, out


def test_a_board_that_cannot_be_read_is_unavailable_and_not_a_board_without_columns(board,
                                                                                    monkeypatch):
    from beeverforge.adapters.tracker.github_project import GitHubProjectBoard

    monkeypatch.setattr(GitHubProjectBoard, "column_names", lambda self: None)

    out = _read()

    assert out.code == actions.UNAVAILABLE and "could not be read" in out.message, out


# ── the set ─────────────────────────────────────────────────────────────────────────────────────

def test_a_set_writes_the_tracker_options_and_answers_the_new_mapping(board):
    out = _set(columns={"todo": "ready", "done": "Shipped"})

    assert out.ok, out
    # the board's own spelling is written, whatever case it was asked in
    assert json.loads(_held()["columns"]) == {"todo": "Ready", "done": "Shipped"}
    assert out.data["mapping"]["todo"] == "Ready" and out.data["mapping"]["done"] == "Shipped"
    assert out.data["changed"] is True


def test_a_set_is_idempotent_and_merges_what_is_held(board, monkeypatch):
    assert _set(columns={"todo": "Ready"}).ok
    registry = board.registry.read_bytes()

    again = _set(columns={"todo": "Ready"})
    assert again.ok and again.data["changed"] is False
    assert board.registry.read_bytes() == registry

    # the registry is not asked to write at all, not merely asked to write the same bytes
    from beeverforge.registry import ProjectRegistry

    writes: list[dict] = []
    real = ProjectRegistry.set_tracker_options
    monkeypatch.setattr(ProjectRegistry, "set_tracker_options",
                        lambda self, name, options: (writes.append(options), real(self, name, options)))
    assert _set(columns={"todo": "ready"}).data["changed"] is False
    assert not writes, f"an unchanged mapping was written again: {writes}"
    monkeypatch.setattr(ProjectRegistry, "set_tracker_options", real)

    assert _set(columns={"done": "Shipped"}).ok
    assert json.loads(_held()["columns"]) == {"todo": "Ready", "done": "Shipped"}


def test_the_front_end_words_are_one_request_with_the_shells_mapping(board):
    assert _set(columns="todo=Ready, in progress=Doing").ok

    assert json.loads(_held()["columns"]) == {"todo": "Ready", "in_progress": "Doing"}


def test_pickup_names_the_column_that_dispatches_and_the_queue_moves_with_todo(board):
    assert _set(pickup="Ready").ok
    assert _held()["pickup_status"] == "Ready"
    assert _read().data["pickup"] == "Ready"

    # the queue is the todo column: a todo set while a pickup is held moves it, said, and
    # the poller's precedence (`pickup_status` wins) never leaves the old column dispatching
    out = _set(columns={"todo": "New"})
    assert out.ok and _held()["pickup_status"] == "New", out
    assert _read().data["mapping"]["todo"] == "New"


def test_a_pickup_that_names_two_queues_is_refused(board):
    out = _set(columns={"todo": "Ready"}, pickup="Doing")

    assert out.code == actions.INVALID and "Nothing was changed" in out.message, out
    assert "columns" not in _held() and "pickup_status" not in _held()


# ── the refusals, each naming the board's columns and writing nothing ───────────────────────────

@pytest.mark.parametrize("params,says", [
    ({"columns": {"todo": "Ready!"}}, "Ready!"),
    ({"columns": {"nonsense": "Ready"}}, "nonsense"),
    ({"columns": {"todo": "Ready", "in_progress": "ready"}}, "Ready"),
    ({"pickup": "Elsewhere"}, "Elsewhere"),
    ({"columns": {"todo": ""}}, "todo"),
    ({"columns": "todo"}, "todo"),
])
def test_a_refusal_is_invalid_says_nothing_was_changed_and_names_the_boards_columns(
        params, says, board):
    before = board.registry.read_bytes()

    out = _set(**params)

    assert out.code == actions.INVALID, out
    assert "Nothing was changed" in out.message and says in out.message, out.message
    for column in COLUMNS:
        assert column in out.message, (column, out.message)
    assert board.registry.read_bytes() == before


def test_a_stage_the_core_does_not_define_names_the_stages_it_does(board):
    out = _set(columns={"nonsense": "Ready"})

    assert "todo" in out.message and "in_progress" in out.message, out.message


def test_a_set_on_a_board_that_cannot_be_read_changes_nothing(board, monkeypatch):
    from beeverforge.adapters.tracker.github_project import GitHubProjectBoard

    monkeypatch.setattr(GitHubProjectBoard, "column_names", lambda self: None)
    before = board.registry.read_bytes()

    out = _set(columns={"todo": "Ready"})

    assert out.code == actions.UNAVAILABLE and "Nothing was changed" in out.message, out
    assert board.registry.read_bytes() == before


def test_a_held_columns_option_that_is_not_a_map_is_refused_and_not_written_over(board):
    from beeverforge.registry import ProjectRegistry

    ProjectRegistry().set_tracker_options("acme", {"columns": "not-json"})
    before = board.registry.read_bytes()

    out = _set(columns={"todo": "Ready"})

    assert out.code == actions.INVALID and "Nothing was changed" in out.message, out
    assert board.registry.read_bytes() == before


def test_a_ghost_project_is_refused_with_the_roster(board):
    out = asyncio.run(actions.perform("project_set_board_columns", by=ADMIN, project="acmee",
                                      columns={"todo": "Ready"}))

    assert out.code == actions.NOT_FOUND and "knows: acme." in out.message, out


# ── guarded like the other `project_set_*` rows, audited, listed ────────────────────────────────

@pytest.mark.parametrize("name", ["project_board_columns", "project_set_board_columns"])
def test_both_rows_are_guarded_like_set_preview(name):
    from beeverforge.actions import catalog

    spec, like = catalog.CATALOG[name], catalog.CATALOG["project_set_preview"]

    # the read writes nothing, so it is not an installation row (a guard holds every one of those
    # to a write); it is the administrator's all the same — `needs_admin` — and the floor's
    assert (spec.installation, spec.needs_admin, spec.needs_code, spec.scope) == (
        name == "project_set_board_columns", like.needs_admin, like.needs_code, like.scope)
    assert spec.refuses and actions.INVALID in spec.refuses


@pytest.mark.parametrize("by", [
    actions.Actor(id="bia", via="panel", admin=True, scopes=frozenset({actions.PRODUCT})),
    actions.Actor(id="eve", via="slack", admin=False),
])
def test_a_credential_that_is_not_the_administrators_is_refused_and_writes_nothing(by, board):
    before = board.registry.read_bytes()

    out = asyncio.run(actions.perform("project_set_board_columns", by=by, project="acme",
                                      columns={"todo": "Ready"}))

    assert out.code == actions.DENIED, out
    assert board.registry.read_bytes() == before


def test_the_set_leaves_one_audit_record_allowed_and_one_refused(board, caplog):
    import logging

    with caplog.at_level(logging.INFO):
        _set(columns={"todo": "Ready"})
        mark = len(caplog.records)
        _set(columns={"todo": "Nope"})

    lines = [r.getMessage() for r in caplog.records if "project_set_board_columns" in r.getMessage()]
    assert len(lines) == 2, lines
    assert "rob" in lines[0] and "rob" in lines[1]
    assert len([r for r in caplog.records[:mark]
                if "project_set_board_columns" in r.getMessage()]) == 1


def test_both_rows_are_listed_in_the_catalogue_reference():
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "docs/reference/the-front-end-api.md").read_text()

    assert "| `project_board_columns` | `project` |" in text
    assert "| `project_set_board_columns` | `project`, [`columns`], [`pickup`] |" in text


# ── the doctor and the poller read the new mapping, with no restart ─────────────────────────────

def _findings() -> dict:
    """The two findings the issue names, from the real probes over the registry as it is NOW."""
    from beeverforge import doctor
    from beeverforge.registry import ProjectRegistry

    probes = doctor.probes_for(ProjectRegistry().get("acme"))
    return {"board_columns": doctor._board(probes), **{f.check: f
                                                       for f in doctor._board_stages(probes)}}


def test_the_doctors_findings_clear_after_a_set(board):
    stock = _findings()
    assert not stock["board_columns"].ok, stock["board_columns"]
    assert "no stage this platform maps" in stock["board_stages"].message

    assert _set(columns={"backlog": "New", "todo": "Ready", "in_progress": "Doing",
                         "in_review": "Checking", "done": "Shipped"}).ok

    after = _findings()
    assert after["board_columns"].ok, after["board_columns"]
    assert after["board_stages"].ok and "every column of the board is a stage" in (
        after["board_stages"].message), after["board_stages"]


def test_the_pollers_next_pass_reads_the_new_pickup_with_no_restart(board):
    from beeverforge.adapters.board.factory import build_board
    from beeverforge.registry import ProjectRegistry

    assert _set(columns={"todo": "Ready"}).ok
    first = build_board(ProjectRegistry().get("acme")).pickup_column()

    assert _set(columns={"todo": "Doing"}).ok
    second = build_board(ProjectRegistry().get("acme")).pickup_column()

    assert (first, second) == ("Ready", "Doing")


# ── the command line maps onto the rows ─────────────────────────────────────────────────────────

def test_the_command_sets_and_shows_the_mapping(board):
    from beeverforge.cli import app

    out = CliRunner().invoke(app, ["project", "set-board-columns", "acme", "todo=Ready",
                                   "done=Shipped", "--pickup", "Ready"])

    assert out.exit_code == 0, out.output
    assert "todo" in out.output and "Ready" in out.output and "Shipped" in out.output
    assert json.loads(_held()["columns"]) == {"todo": "Ready", "done": "Shipped"}
    assert _held()["pickup_status"] == "Ready"


def test_the_command_with_no_mapping_shows_the_board(board):
    from beeverforge.cli import app

    out = CliRunner().invoke(app, ["project", "set-board-columns", "acme"])

    assert out.exit_code == 0, out.output
    assert "unmapped" in out.output and "Ready" in out.output


def test_the_command_refuses_as_the_row_does_and_exits_nonzero(board):
    from beeverforge.cli import app

    out = CliRunner().invoke(app, ["project", "set-board-columns", "acme", "todo=Nope"])

    assert out.exit_code != 0
    assert "Nothing was changed" in out.output and "Ready" in out.output
    assert "columns" not in _held()


def test_a_word_that_is_not_stage_equals_column_is_refused_by_the_command(board):
    from beeverforge.cli import app

    out = CliRunner().invoke(app, ["project", "set-board-columns", "acme", "todo"])

    assert out.exit_code != 0 and "stage=column" in out.output


# ── the panel's strip: `paintBoardMap` is executed, not read ────────────────────────────────────

def _paint_board_map(answer: str) -> str:
    """What the page's own `paintBoardMap` draws into `#boardmap` when `act` answers `answer` (a JS
    expression, or `throw` for a call that failed). The function is cut out of the page, whole, and
    run under node over a stub `$`, the page's own `esc`, and an `act` that records its call."""
    import pathlib
    import re
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("node is not on PATH — the page's JavaScript cannot be executed here")
    page = (pathlib.Path(__file__).resolve().parent.parent / "beeverforge" / "api"
            / "panel.html").read_text(encoding="utf-8")
    start = page.index("const paintBoardMap=async()=>{")
    depth, end = 0, start
    for end in range(page.index("{", start), len(page)):
        depth += {"{": 1, "}": -1}.get(page[end], 0)
        if depth == 0:
            break
    strip = page[start:end + 1]
    esc = re.search(r"^const esc=.*$", page, re.M).group(0)
    answer_js = ("(()=>{throw new Error('the board is down')})()" if answer == "throw"
                 else answer)
    script = "\n".join([
        esc, "const name='acme';let asked=null;",
        "const slot={innerHTML:''};const $=s=>s==='#boardmap'?slot:null;",
        f"const act=async(n,p)=>{{asked=[n,p];return {answer_js}}};",
        strip,
        "paintBoardMap().then(()=>console.log(JSON.stringify({html:slot.innerHTML,asked})))"])
    done = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr[-1200:]
    return done.stdout


def test_the_panel_strip_draws_every_stage_and_says_unmapped_for_one_with_no_column():
    out = json.loads(_paint_board_map(
        "{ok:true,data:{board:{kind:'github'},mapping:{todo:'Ready',done:null},"
        "pickup:'Ready',pickup_on_board:true}}"))
    assert out["asked"] == ["project_board_columns", {"project": "acme"}]
    html = out["html"]
    assert "<b>Ready</b>" in html and "todo" in html
    assert "unmapped" in html and html.index("done") < html.index("unmapped")
    assert "not a column of this board" not in html


def test_the_panel_strip_flags_a_pickup_the_board_does_not_have_and_escapes_what_it_draws():
    html = json.loads(_paint_board_map(
        "{ok:true,data:{board:{kind:'github'},mapping:{todo:'<i>x</i>'},"
        "pickup:'TO-DO',pickup_on_board:false}}"))["html"]
    assert "not a column of this board" in html
    assert "<i>" not in html and "&lt;i&gt;" in html


def test_the_panel_strip_says_a_board_could_not_be_read_and_never_draws_an_empty_map():
    refused = json.loads(_paint_board_map(
        "{ok:false,message:'its columns are not known'}"))["html"]
    assert "its columns are not known" in refused and "unmapped" not in refused
    thrown = json.loads(_paint_board_map("throw"))["html"]
    assert "the board is down" in thrown
    nothing = json.loads(_paint_board_map("{ok:true,data:{board:null}}"))["html"]
    assert "no board configured" in nothing
