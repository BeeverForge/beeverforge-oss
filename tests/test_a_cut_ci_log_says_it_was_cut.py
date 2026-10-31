"""#161 — a failing CI log cut to its limit says it was cut, and is read as "could not see".

WHAT IT COST. `failed_ci_logs` (GitHub and Azure DevOps) returned the last `max_chars` of the
failing log with nothing saying so, so a cut log read exactly like a whole one. Since #756 the
rule `log_names_the_change` reads that log to decide whether a red check is unrelated to the
diff: a changed file named only in the cut-off head was not seen, and a CI re-run stood in for the
agent. The repair agent was also handed the cut log with no marker.

    the helper   `base.truncated_tail` keeps the tail and opens with `base.LOG_CUT_MARKER`
    GitHub       `failed_ci_logs` cuts a long failing log with the marker; a short one has none
    Azure        the same, on the sibling
    the rule     a cut log answers "related", as `changed_paths` answers `None` for a cut diff
    end to end   a log cut before the line naming the changed file launches the agent, handed
                 the cut log with its marker, and nothing is re-run

The mutation plan is `tools/mutations/161_a_cut_ci_log_says_so.py`.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from beeverforge.adapters.forge import base
from beeverforge.adapters.forge.github import GitHubForge
from beeverforge.runtime import repairable
from beeverforge.runtime.temporal import activities as acts
from tests import test_a_failing_check_is_read_for_what_it_is as ado
from tests import test_a_red_check_the_diff_does_not_touch_is_rerun_before_an_agent_is_paid as rr

CHANGED = rr.CHANGED
NAMING = f"FAILED {CHANGED.split('/')[-1]}::test_total - AssertionError: 3 != 4"
FILLER = "".join(f"step {i}: tests/integration/test_queue.py ran\n" for i in range(60))
LAST = "Error: Process completed with exit code 1."
#: A failing log whose ONLY line naming the changed file is its first one.
LONG = f"{NAMING}\n{FILLER}{LAST}"


# ═══ the helper ═════════════════════════════════════════════════════════════════════════════════

def test_a_cut_log_keeps_its_tail_and_says_it_was_cut():
    got = base.truncated_tail(LONG, 200)
    assert base.LOG_CUT_MARKER in got
    assert got.endswith(LONG[-200:])
    assert NAMING not in got
    assert len(got) <= 200 + 200, "the marker is a line, not a second copy of the log"
    assert str(len(LONG)) in got, "the marker does not say how long the whole log was"


def test_a_log_within_its_limit_is_returned_whole_with_no_marker():
    assert base.truncated_tail(LONG, len(LONG)) == LONG
    assert base.truncated_tail("short", 200) == "short"


def test_the_marker_names_no_file():
    """The rule must never read the marker itself as naming a changed file."""
    marker_only = base.truncated_tail("x" * 50, 10).replace("x", "")
    assert not repairable.log_names_the_change(marker_only.replace(base.LOG_CUT_MARKER, ""),
                                               ["a/b.py", "x.ts", "README.md"])


# ═══ GitHub ═════════════════════════════════════════════════════════════════════════════════════

def _github(monkeypatch, log: str) -> GitHubForge:
    """A real `GitHubForge` with one red required run whose failing log is `log`."""
    f = GitHubForge("acme/x")
    row = {"name": "pytest", "bucket": "fail", "state": "FAIL", "workflow": "ci",
           "link": "https://github.com/acme/x/actions/runs/1/job/7"}

    def gh(args, timeout=120):
        out = SimpleNamespace(returncode=0, stdout="", stderr="")
        if args[:2] == ["pr", "checks"]:
            out.stdout = json.dumps([{"name": "pytest", "bucket": "fail"}] if "--required" in args
                                    else [row])
        elif args[:2] == ["run", "view"]:
            out.stdout = log
        return out

    monkeypatch.setattr(f, "_gh", gh)
    return f


def test_github_cuts_a_long_failing_log_with_a_marker(monkeypatch):
    got = _github(monkeypatch, LONG).failed_ci_logs(pr=rr.PR, max_chars=200)
    assert base.LOG_CUT_MARKER in got
    assert got.rstrip().endswith(LAST)
    assert NAMING not in got


def test_github_a_short_failing_log_carries_no_marker(monkeypatch):
    got = _github(monkeypatch, NAMING).failed_ci_logs(pr=rr.PR)
    assert NAMING in got
    assert base.LOG_CUT_MARKER not in got


# ═══ Azure DevOps ═══════════════════════════════════════════════════════════════════════════════

def _azure(lines: list[str]):
    record = {"name": "pytest", "result": "failed", "log": {"id": 9}}
    routes = {"GET build/builds/41/timeline": {"records": [record]},
              "GET build/builds/41/logs/9": {"count": len(lines), "value": lines}}
    return ado._ado([ado._evaluation(ado.BUILD, "rejected", blocking=True, build_id=41,
                                     name="fx-ado-ci")], routes)


def test_ado_cuts_a_long_failing_log_with_a_marker():
    got = _azure(LONG.splitlines()).failed_ci_logs(pr=ado.PR, max_chars=200)
    assert base.LOG_CUT_MARKER in got
    assert got.rstrip().endswith(LAST)
    assert NAMING not in got


def test_ado_a_short_failing_log_carries_no_marker():
    got = _azure([NAMING]).failed_ci_logs(pr=ado.PR)
    assert NAMING in got
    assert base.LOG_CUT_MARKER not in got


# ═══ the rule ═══════════════════════════════════════════════════════════════════════════════════

def test_a_cut_log_is_read_as_naming_the_change():
    cut = base.truncated_tail(LONG, 200)
    assert "invoice.py" not in cut, "premise: the cut dropped the only line naming the file"
    assert repairable.log_names_the_change(cut, [CHANGED]) is True


def test_the_same_tail_without_the_marker_names_nothing():
    """The reverse: it is the marker, not the tail's text, that answers "related"."""
    assert repairable.log_names_the_change(LONG[-200:], [CHANGED]) is False


# ═══ end to end: criterion 3 ════════════════════════════════════════════════════════════════════

@pytest.fixture
def on_the_worker(monkeypatch):
    """#756's worker seams (`rr.on_the_worker`), installed for this module."""
    return rr.on_the_worker.__wrapped__(monkeypatch)


@pytest.mark.parametrize("door", rr.DOORS)
def test_a_log_cut_before_the_line_naming_the_changed_file_launches_the_agent(
        on_the_worker, door):
    cut = base.truncated_tail(LONG, 200)
    assert "invoice.py" not in cut, "premise: the cut dropped the only line naming the file"
    forge = rr._Forge(log=cut)
    agents = on_the_worker(forge, door=door)
    got = acts._run_ci_repair(rr.FIRST, "run-r1")
    assert forge.reruns == 0, f"a re-run stood in for the agent on a cut log: {forge.events}"
    assert forge.comments == []
    assert len(agents) == 1, f"no agent was launched: {agents}"
    if door == "inline":
        assert agents[0] == cut and base.LOG_CUT_MARKER in agents[0]
    assert got.pr_url == rr.PR
