"""A forge or tracker call that fails on a rate limit raises `RateLimited`, carrying when the limit
resets (#698) — not a generic failure a caller can only treat as "it did not work".

The reset is read from the response's headers (`X-RateLimit-Reset`, `Retry-After`) or its body
(`resetAt`); the clock is injected, so no test waits or reads the wall. `gh` is a fake runner:
a real one would spend the production App's rate limit.
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime

import pytest

from beeverforge.adapters.forge.github import GitHubForge
from beeverforge.adapters.rate_limit import DEFAULT_WAIT, RateLimited, rate_limited
from beeverforge.adapters.tracker.github import GitHubIssuesTracker

NOW = 1_700_000_000.0


def _p(stderr: str = "", stdout: str = "", code: int = 1) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["gh"], code, stdout=stdout, stderr=stderr)


_EXCEEDED = "gh: API rate limit exceeded for installation ID 42. (HTTP 403)"


def test_a_reset_header_gives_the_reset_epoch():
    got = rate_limited(_p(_EXCEEDED, "HTTP/2.0 403\nX-Ratelimit-Reset: 1700000500\n"),
                       clock=lambda: NOW)
    assert isinstance(got, RateLimited)
    assert got.reset_at == 1_700_000_500.0


def test_a_retry_after_header_is_seconds_from_the_injected_clock():
    got = rate_limited(_p(_EXCEEDED, "Retry-After: 60\n"), clock=lambda: NOW)
    assert got is not None and got.reset_at == NOW + 60


def test_a_graphql_body_names_its_reset():
    body = ('{"errors":[{"type":"RATE_LIMITED","message":"API rate limit already exceeded"}],'
            '"data":{"rateLimit":{"resetAt":"2023-11-14T22:21:40Z"}}}')
    got = rate_limited(_p("", body), clock=lambda: NOW)
    expected = datetime(2023, 11, 14, 22, 21, 40, tzinfo=UTC).timestamp()
    assert got is not None and got.reset_at == expected


def test_a_limit_that_names_no_reset_waits_the_default_from_now():
    got = rate_limited(_p(_EXCEEDED), clock=lambda: NOW)
    assert got is not None and got.reset_at == NOW + DEFAULT_WAIT


def test_a_reset_in_the_past_is_not_trusted():
    got = rate_limited(_p(_EXCEEDED, "X-Ratelimit-Reset: 5\n"), clock=lambda: NOW)
    assert got is not None and got.reset_at == NOW + DEFAULT_WAIT


def test_any_other_failure_is_not_a_rate_limit():
    assert rate_limited(_p("gh: Could not resolve to an issue (HTTP 404)"), clock=lambda: NOW) is None
    assert rate_limited(_p("", "", code=0), clock=lambda: NOW) is None


def test_the_text_passes_through_the_redactor():
    got = rate_limited(
        _p("API rate limit exceeded https://x-access-token:SECRET@github.com/o/r.git"),
        clock=lambda: NOW)
    assert got is not None and "SECRET" not in str(got)


class _Runner:
    def __init__(self, answer: subprocess.CompletedProcess[str]) -> None:
        self.answer = answer

    def __call__(self, argv, **kw):
        return self.answer


@pytest.fixture
def no_sleep(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)


def _tracker() -> GitHubIssuesTracker:
    t = GitHubIssuesTracker("o/r")
    t.clock = lambda: NOW
    return t


def test_the_trackers_write_raises_rate_limited(monkeypatch, no_sleep):
    monkeypatch.setattr(subprocess, "run", _Runner(_p(_EXCEEDED + "\nRetry-After: 30")))
    with pytest.raises(RateLimited) as err:
        _tracker().comment("#7", "hello")
    assert err.value.reset_at == NOW + 30


def test_the_trackers_read_raises_rate_limited(monkeypatch, no_sleep):
    monkeypatch.setattr(subprocess, "run", _Runner(_p(_EXCEEDED)))
    with pytest.raises(RateLimited):
        _tracker().get_ticket("#7")


def test_the_trackers_other_failure_stays_generic(monkeypatch, no_sleep):
    monkeypatch.setattr(subprocess, "run", _Runner(_p("boom")))
    with pytest.raises(RuntimeError) as err:
        _tracker().comment("#7", "hello")
    assert not isinstance(err.value, RateLimited)


def test_the_forges_failure_raises_rate_limited(monkeypatch):
    forge = GitHubForge("o/r")
    forge.clock = lambda: NOW
    monkeypatch.setattr(subprocess, "run", _Runner(_p(_EXCEEDED + "\nRetry-After: 10")))
    with pytest.raises(RateLimited) as err:
        forge.close_pr(pr="1")
    assert err.value.reset_at == NOW + 10


def test_the_forges_other_failure_stays_generic(monkeypatch):
    forge = GitHubForge("o/r")
    monkeypatch.setattr(subprocess, "run", _Runner(_p("boom")))
    with pytest.raises(RuntimeError) as err:
        forge.close_pr(pr="1")
    assert not isinstance(err.value, RateLimited)


def test_free_text_on_stdout_that_says_rate_limit_is_not_a_refusal():
    assert rate_limited(_p("boom", "PR title: fix the rate limit docs"), clock=lambda: NOW) is None


def test_a_graphql_body_on_stdout_is_a_refusal():
    body = '{"errors":[{"type":"RATE_LIMITED"}]}'
    assert isinstance(rate_limited(_p("", body), clock=lambda: NOW), RateLimited)


def test_a_board_read_that_hits_the_limit_is_not_wrapped_as_unreadable(monkeypatch):
    from beeverforge.adapters.tracker import github_project as gp

    monkeypatch.setattr(gp, "_run_gh", lambda args, token=None: _p(_EXCEEDED))
    board = gp.GitHubProjectBoard.__new__(gp.GitHubProjectBoard)
    board.owner, board.number = "o", 1
    monkeypatch.setattr(gp.GitHubProjectBoard, "token", None)
    with pytest.raises(RateLimited):
        board._board_items_via_graphql("organization")


def test_a_close_that_hits_the_limit_after_its_reason_keeps_its_type_and_reset(monkeypatch):
    tracker = _tracker()
    limited = RateLimited("spent", reset_at=NOW + 99)

    def _write(args, *a, **kw):
        if args[:2] == ["issue", "close"]:
            raise limited
        return _p(code=0)

    monkeypatch.setattr(tracker, "_write", _write)
    monkeypatch.setattr(tracker, "_post_reason", lambda *a, **kw: True)
    monkeypatch.setattr(tracker, "_locate", lambda ref: ("o/r", "7"))
    with pytest.raises(RateLimited) as err:
        tracker.close_ticket("#7", "done")
    assert err.value.reset_at == NOW + 99


def _forge_paths():
    """Every forge read that used to fold a rate limit into None / False / a generic error."""
    return {
        "list_branches": lambda f: f.list_branches("o/r", prefix="req/"),
        "delete_branch": lambda f: f.delete_branch("req/1"),
        "pr_for_head": lambda f: f.pr_for_head("req/1"),
        "merge_gates": lambda f: f.merge_gates(base="main"),
        "credential_permissions": lambda f: f.credential_permissions(),
        "review_comments": lambda f: f.review_comments(pr="https://github.com/o/r/pull/3"),
        "published_releases": lambda f: f.published_releases("https://github.com/o/r"),
        "workflow_states": lambda f: f.disabled_ci_paths(),
        "latest_tag": lambda f: f.latest_tag(),
        "ensure_repo": lambda f: f.create_repository(name="o/new"),
    }


@pytest.mark.parametrize("path", sorted(_forge_paths()))
def test_every_forge_read_and_the_repo_creation_raise_rate_limited(monkeypatch, path):
    forge = GitHubForge("o/r")
    forge.clock = lambda: NOW
    monkeypatch.setattr(subprocess, "run", _Runner(_p(_EXCEEDED + "\nRetry-After: 20")))
    with pytest.raises(RateLimited) as err:
        _forge_paths()[path](forge)
    assert err.value.reset_at == NOW + 20


def test_a_repo_creation_refused_for_its_limit_after_the_app_refusal_is_rate_limited(monkeypatch):
    forge = GitHubForge("o/r")
    forge.clock = lambda: NOW
    refusals = iter([_p("", "", 1), _p("Resource not accessible by integration"),
                     _p("", "Organization", 0), _p(_EXCEEDED)])
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: next(refusals))
    with pytest.raises(RateLimited):
        forge.create_repository(name="o/new")


def test_an_owner_probe_that_hits_the_limit_is_not_read_as_a_personal_account(monkeypatch):
    forge = GitHubForge("o/r")
    forge.clock = lambda: NOW
    answers = iter([_p("", "", 1), _p("Resource not accessible by integration"), _p(_EXCEEDED)])
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: next(answers))
    with pytest.raises(RateLimited):
        forge.create_repository(name="o/new")
