"""A `429` in a card key or an email is not GitHub, Jira or Azure DevOps throttling us.

The throttled rule matched a bare `429\\b`, so a park line for card `DAR-429` that Jira answered
404, or a credential refusal naming `ops429@acme.ai`, classified as `transient`: the factory waited
and retried a failure no wait fixes. The 429 is now read only where the tracker park lines put the
HTTP status (Jira `failed: <code>`, Azure DevOps `→ <code>`, gh `HTTP <code>`, a line that starts
with the code), and the tracker's own credential sentences are read before throttling.

The verdict drives workflow commands, so the workflow reads it behind
`workflow.patched("classify-anchored-429")`: `classify(anchored_429=False)` is the reading a job
parked before the fix recorded, and replays.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from beeverforge.adapters.tracker import jira
from beeverforge.techlead.classify import CREDENTIAL, TRANSIENT, UNKNOWN, classify
from tests.the_tree_read_once import parsed

_NOT_THROTTLED = {
    "jira": 'ticket: jira GET issue/DAR-429 failed: 404 {"errorMessages":["Issue does not exist '
            'or you do not have permission to see it."]}',
    "azure-devops": "ticket: GET wit/workitems/429 → 404 Not Found",
    "github-graphql": "ticket: gh issue view failed: GraphQL: Could not resolve to an issue or "
                      "pull request with the number of 429. (repository.issue)",
    "github-http": "ticket: gh issue view failed: HTTP 404: Not Found "
                   "(https://api.github.com/repos/acme/ops429/issues/429)",
    "github-http-repo-code429": "ticket: gh issue view failed: HTTP 404: Not Found "
                                "(https://api.github.com/repos/acme/code429/issues/7)",
    "email-code429": "ticket: jira GET issue/DAR-7 failed: 404 for code429@acme.ai",
    "email-status429": "ticket: jira GET issue/DAR-7 failed: 404 for status429@x.io",
    "email-error429": "ticket: jira GET issue/DAR-7 failed: 404 for error429@x.io",
}


@pytest.mark.parametrize("line", list(_NOT_THROTTLED.values()), ids=list(_NOT_THROTTLED))
def test_a_card_key_with_429_is_not_throttled(line: str) -> None:
    verdict = classify(line)
    assert verdict.cause != TRANSIENT
    assert verdict.cause == UNKNOWN


@pytest.mark.parametrize("has_token", [True, False], ids=["different-accounts", "no-token"])
def test_a_credential_refusal_naming_an_email_with_429_is_a_credential(has_token: bool) -> None:
    msg = jira._not_one_account("ops429@acme.ai", "GET", "issue/DAR-429", has_token=has_token)
    assert classify(f"ticket: {msg[:120]}").cause == CREDENTIAL


_THROTTLED = {
    "jira-rate-limit-body": 'ticket: jira GET issue/DAR-7 failed: 429 {"message":"Rate limit"}',
    "jira-empty-body": "ticket: jira GET issue/DAR-7 failed: 429 ",
    "azure-devops": "ticket: GET wit/workitems/12 → 429 ",
    "azure-devops-reason": "ticket: GET wit/workitems/12 → 429 Too Many Requests",
    "azure-devops-ascii-arrow": "ticket: GET wit/workitems/12 -> 429 ",
    "github-http": "ticket: gh issue view failed: HTTP 429: (https://api.github.com/repos/a/b)",
    "github-app": "429 secondary limit",
    "status-code": "tracker answered status code 429",
    # an agent harness's API refusal as a park note: codex reads a pause only from stderr
    # (`codex._pause_from`) and falls back to the raw stream for its summary
    "agent-api-error": 'API Error: 429 {"type":"error","error":{"type":"rate_limit_error"}}',
}


@pytest.mark.parametrize("line", list(_THROTTLED.values()), ids=list(_THROTTLED))
def test_a_real_429_is_still_throttled(line: str) -> None:
    verdict = classify(line)
    assert verdict.cause == TRANSIENT
    assert verdict.detail == "throttled"


# ═══ the reading a job parked before the fix recorded ═══════════════════════════════════════════

@pytest.mark.parametrize("line", list(_NOT_THROTTLED.values())[:2], ids=list(_NOT_THROTTLED)[:2])
def test_unanchored_a_card_key_with_429_is_still_throttling(line: str) -> None:
    verdict = classify(line, anchored_429=False)
    assert (verdict.cause, verdict.detail) == (TRANSIENT, "throttled")


def test_unanchored_a_credential_refusal_naming_429_is_throttling_as_it_was() -> None:
    msg = jira._not_one_account("ops429@acme.ai", "GET", "issue/DAR-429", has_token=True)
    assert classify(f"ticket: {msg[:120]}", anchored_429=False).cause == TRANSIENT


@pytest.mark.parametrize("has_token", [True, False], ids=["different-accounts", "no-token"])
def test_unanchored_a_credential_refusal_without_429_is_still_a_credential(
        has_token: bool) -> None:
    msg = jira._not_one_account("ops@acme.ai", "GET", "issue/DAR-7", has_token=has_token)
    assert classify(f"ticket: {msg[:120]}", anchored_429=False).cause == CREDENTIAL


@pytest.mark.parametrize("line", list(_THROTTLED.values()), ids=list(_THROTTLED))
def test_unanchored_a_real_429_is_throttled(line: str) -> None:
    verdict = classify(line, anchored_429=False)
    assert (verdict.cause, verdict.detail) == (TRANSIENT, "throttled")


def test_the_workflow_reads_the_anchored_429_behind_its_marker() -> None:
    """ASSERTED ON THE SOURCE: every `classify` the workflow makes passes `anchored_429` from
    `workflow.patched("classify-anchored-429")`, never the default."""
    src = pathlib.Path(__file__).resolve().parent.parent / "beeverforge/runtime/temporal/workflow.py"
    calls = [n for n in ast.walk(parsed(src))
             if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "classify"]
    assert calls, "the workflow makes no `classify` call — this guard measures nothing"
    passed = [next((ast.unparse(k.value) for k in c.keywords if k.arg == "anchored_429"), None)
              for c in calls]
    assert passed == ["workflow.patched('classify-anchored-429')"] * len(calls), passed
