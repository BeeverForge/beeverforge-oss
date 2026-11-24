"""A message refused at the gate is a person's words, and it reaches no log line (#205).

`perform` writes one WARNING for each of its three refusals (out of scope, an installation row, not
an admin) and one INFO for what ran. The warnings printed every parameter, so a `product_say`
message refused by scope was written to the log in full, at a level an operator ships off the
host. A free-text parameter is now printed as the audit record keeps it, `{chars, sha256}`, and
a secret is still masked.
"""

from __future__ import annotations

import dataclasses
import hashlib

import pytest

from beeverforge import actions
from beeverforge.actions import base, catalog

WORDS = "the client's salary is 91000 and she is leaving in March"

CASES = {
    "out of scope": (
        {}, actions.Actor(id="ba", via="panel", admin=True, scopes=frozenset({base.FLOOR})),
        "DENIED_SCOPE"),
    "by installation": (
        {"installation": True},
        actions.Actor(id="ba", via="panel", admin=True, scopes=frozenset({base.PRODUCT})),
        "DENIED_INSTALLATION"),
    "as not admin": (
        {"needs_admin": True}, actions.Actor(id="eng", via="slack"), "DENIED"),
}


@pytest.mark.parametrize("case", CASES)
async def test_a_refused_message_reaches_no_log_line_at_any_level(case, monkeypatch, caplog):
    changes, by, marker = CASES[case]
    spec = dataclasses.replace(catalog.CATALOG["product_say"], **changes)
    monkeypatch.setattr(catalog, "CATALOG", {"product_say": spec})

    with caplog.at_level("DEBUG"):
        out = await actions.perform("product_say", by=by, project="demo", message=WORDS)

    assert not out.ok
    assert marker in caplog.text
    for word in ("salary", "91000", "leaving", WORDS):
        assert word not in caplog.text
    assert f"'chars': {len(WORDS)}" in caplog.text
    assert hashlib.sha256(WORDS.encode()).hexdigest() in caplog.text


async def test_a_secret_is_still_masked_beside_free_text(monkeypatch, caplog):
    spec = dataclasses.replace(catalog.CATALOG["promote"])
    monkeypatch.setattr(catalog, "CATALOG", {"promote": spec})
    by = actions.Actor(id="ba", via="panel", scopes=frozenset({base.PRODUCT}))

    with caplog.at_level("DEBUG"):
        await actions.perform("promote", by=by, project="demo", issue="1", version="1.0.0",
                              approver="alice", password="hunter2")

    assert "hunter2" not in caplog.text
    assert "***" in caplog.text


async def test_the_info_line_keeps_the_action_the_caller_and_the_kept_parameters(
        monkeypatch, caplog):
    async def ran(**_kw):
        return base.done("done")

    spec = dataclasses.replace(catalog.CATALOG["product_say"], run=ran)
    monkeypatch.setattr(catalog, "CATALOG", {"product_say": spec})
    by = actions.Actor(id="U9", display="Ana", via="slack")

    with caplog.at_level("INFO"):
        await actions.perform("product_say", by=by, project="demo", message=WORDS, thread="t1")

    line = next(r.getMessage() for r in caplog.records if r.getMessage().startswith("action="))
    assert "action=product_say" in line
    assert "Ana (via slack)" in line
    assert "'project': 'demo'" in line and "'thread': 't1'" in line
    assert WORDS not in caplog.text and "salary" not in caplog.text
