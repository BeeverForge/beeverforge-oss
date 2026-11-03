"""#209 — the cost dashboard's project selector lists only keys of the kinds it reads.

The people store keeps its rows (kind `person`, plus invitations) under `_deployment_`, beside the
audit rows #43 already left out. `dashboard` listed every row's key, so after one `people invite`
and one `agent_run` of `books` the selector read `['_deployment_', 'books']` and the dashboard
opened on `_deployment_`, showing `cost_usd 0, agent_runs 0` beside the project that spent.

The selector is now an allow-list by kind (`agent_run`, `job`), so a future non-project kind
cannot come back into it.
"""

from beeverforge.api.metrics_view import dashboard

RUN = {"pk": "books", "kind": "agent_run", "ticket": "BK-1", "cost_usd": 0.42,
       "model": "m", "harness": "h", "role": "executor", "ts": "2026-11-01T10:00:00"}

DEPLOYMENT = [
    {"pk": "_deployment_", "kind": "person", "email": "a@example.com", "role": "admin"},
    {"pk": "_deployment_", "kind": "invitation", "email": "b@example.com"},
    {"pk": "_deployment_", "kind": "audit", "action": "people.invite"},
]


def test_a_person_row_changes_neither_the_selector_nor_the_default_view():
    alone = dashboard([RUN])
    got = dashboard(DEPLOYMENT + [RUN])
    assert got["projects"] == ["books"]
    assert got["projects"] == alone["projects"]
    assert got["project"] == "books"
    assert got["totals"]["agent_runs"] == 1
    assert got["totals"]["cost_usd"] == alone["totals"]["cost_usd"] == 0.42


def test_the_selector_lists_only_keys_of_the_kinds_it_reads():
    rows = [
        {"pk": "aaa", "kind": "card"},
        {"pk": "_deployment_", "kind": "person"},
        {"project": "jobs-only", "kind": "job", "ticket": "J-1", "state": "done"},
        {"pk": "runs-only", "kind": "agent_run", "ticket": "R-1", "cost_usd": 1.0},
    ]
    got = dashboard(rows)
    assert got["projects"] == ["jobs-only", "runs-only"]
    assert got["project"] == "jobs-only"


def test_a_requested_project_still_scopes_as_before():
    got = dashboard(DEPLOYMENT + [RUN], project="books")
    assert got["project"] == "books"
    assert got["totals"] == dashboard([RUN], project="books")["totals"]
