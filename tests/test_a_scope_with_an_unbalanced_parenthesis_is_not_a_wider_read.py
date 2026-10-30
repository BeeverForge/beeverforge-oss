"""A `scope_jql` with an unbalanced parenthesis is refused, not read as the whole site (#121).

THE INCIDENT. `within_scope` narrows every Jira read to `project = "<KEY>" AND (<scope>)`. A scope
whose own `)` closes the wrapper — `labels = "bf-api") OR (labels is not empty` — turns that into
`project = "DAR" AND (labels = "bf-api") OR (labels is not empty)`, valid JQL that Jira answers
gladly: every labelled issue on the whole site, every project's, read as this project's queue.

WHAT IS NOW TRUE. `JiraTracker.__init__` refuses a scope whose parentheses go below depth zero
outside a quoted string, with one sentence naming `scope_jql`, the scope, and the `)` that closes
a parenthesis it never opened. `build_tracker` raises it before any request is made. A balanced
scope, and parentheses inside `"..."` or `'...'` strings, construct exactly as before, the value
unchanged. A trailing unclosed `(` is not refused here: Jira answers it 400 and the existing
"unreadable" warning names the scope, which does not widen the read.
"""

from __future__ import annotations

import pytest

KEY = "DAR"
SITE = "https://acme-team.atlassian.net"

UNBALANCED = [
    ('labels = "bf-api") OR (labels is not empty', 17),
    (') OR (project = "OTHER"', 0),
    ("(a = 1)) OR (b = 2", 7),
]


def _project(tmp_path, scope: str):
    from beeverforge.contracts.project import Project, ProviderRef

    options = {"site": SITE, "email": "alice@acme.ai", "scope_jql": scope}
    return Project(name="api", repo_path=str(tmp_path / "api"),
                   tracker=ProviderRef(kind="jira", repo=KEY, options=options))


def _direct(scope: str):
    from beeverforge.adapters.tracker.jira import JiraTracker

    return JiraTracker(site=SITE, project_key=KEY, email="alice@acme.ai", scope_jql=scope)


@pytest.fixture
def no_network(monkeypatch):
    """Any request fails the test: the refusal must come before Jira is asked anything."""
    import urllib.request

    def _never(*_a, **_k):
        pytest.fail("a request was made for a scope that should have been refused")

    monkeypatch.setattr(urllib.request, "urlopen", _never)


def _assert_one_sentence_naming(message: str, scope: str, at: int) -> None:
    assert "\n" not in message, message
    assert ". " not in message.rstrip("."), message
    assert "scope_jql" in message, message
    assert repr(scope) in message, message
    assert f"')' at character {at}" in message, message


@pytest.mark.parametrize(("scope", "at"), UNBALANCED)
def test_a_scope_whose_parenthesis_closes_the_project_clause_is_refused_at_construction(
        scope, at, tmp_path, no_network):
    """Both ways in — the tracker itself, and the registry row the poller and the board use —
    refuse the scope with one sentence, and no request is ever sent."""
    from beeverforge.adapters.tracker.registry import build_tracker

    with pytest.raises(ValueError) as direct:
        _direct(scope)
    _assert_one_sentence_naming(str(direct.value), scope, at)

    with pytest.raises(ValueError) as built:
        build_tracker(_project(tmp_path, scope), token="t")
    _assert_one_sentence_naming(str(built.value), scope, at)


@pytest.mark.parametrize("scope", [
    'labels = "bf-api"',
    'labels = "bf-api" OR labels = "bf-web"',
    '(labels = "a" OR labels = "b") AND status != Done',
    'summary ~ "fix )"',
    "summary ~ 'a ) b'",
    'summary ~ "say \\") here"',
    'labels = "bf-api',
    "",
    "   ",
])
def test_balanced_scopes_and_quoted_parentheses_are_accepted_unchanged(scope, no_network):
    tracker = _direct(scope)
    assert tracker.scope_jql == scope.strip()


def test_the_registry_row_keeps_a_balanced_scope_byte_for_byte(tmp_path, no_network):
    from beeverforge.adapters.tracker.registry import build_tracker

    scope = '(summary ~ "a ) b" OR labels = \'x (\') AND status != Done'
    tracker = build_tracker(_project(tmp_path, scope), token="t")
    assert tracker.scope_jql == scope
