"""#652 — a held job whose ticket is closed ends as `merged` (counted) or `closed` (not)."""
import json
import threading
from types import SimpleNamespace

import pytest

from beeverforge.api.attention import end_closed, settle
from beeverforge.observability.registry import deployment_metrics_sink
from beeverforge.paths import events_file

PR = "https://forge.example/acme/pull/9"
ACME = SimpleNamespace(name="acme")
JOB = {"project": "acme", "issue": "7", "state": "on_hold", "pr_url": PR}


@pytest.fixture(autouse=True)
def store(monkeypatch, tmp_path):
    monkeypatch.setenv("BEEVERFORGE_METRICS_SINK", "sqlite")
    monkeypatch.setenv("BEEVERFORGE_METRICS_DB", str(tmp_path / "metrics.db"))
    monkeypatch.setenv("BEEVERFORGE_LOG_DIR", str(tmp_path / "logs"))


def _journal() -> list[dict]:
    path = events_file(ACME, "7")
    return [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []


def _rows() -> list[dict]:
    return [r for r in deployment_metrics_sink().records_of_kind("acme", "job")
            if (r.get("extra") or {}).get("ending")]


def forge(answer):
    def status(project, pr):
        if isinstance(answer, Exception):
            raise answer
        return answer
    return status


def _pass(answer):
    return settle([JOB], running=set(), closed_refs=lambda *_: {"7"},
                  bounded=lambda fn, _t: fn(),
                  ending=lambda job, within: end_closed(job, project=ACME, pr_status=forge(answer),
                                                        timeout=within))


def test_merged_leaves_one_event_naming_the_pr_and_one_row():
    assert _pass("merged") == []
    (event,) = [e for e in _journal() if e["message"] == "merged"]
    assert PR in event["data"]["reason"] and "by" in event["data"]
    (row,) = _rows()
    assert row["state"] == "merged" and row["pr_url"] == PR


def test_a_second_pass_adds_neither_event_nor_row():
    _pass("merged")
    end_closed(JOB, project=ACME, pr_status=forge("merged"))
    _pass("merged")
    assert len([e for e in _journal() if e["message"] == "merged"]) == 1
    assert len(_rows()) == 1


def test_closed_without_a_merge_ends_closed_and_counts_nothing():
    assert _pass("closed") == []
    assert [e["message"] for e in _journal()] == ["closed"]
    assert _rows() == []


@pytest.mark.parametrize("answer", [RuntimeError("forge down"), "open"])
def test_an_unreadable_or_open_pr_writes_nothing(answer):
    assert _pass(answer) == []
    assert _journal() == [] and _rows() == []


def test_a_job_without_a_pr_whose_ticket_is_closed_ends_closed_and_counts_nothing():
    job = {**JOB, "pr_url": None}
    asked = []

    def status(project, pr):
        asked.append(pr)
        return "merged"

    assert end_closed(job, project=ACME, pr_status=status) == "closed"
    assert end_closed(job, project=ACME, pr_status=status) is None
    assert [e["message"] for e in _journal()] == ["closed"] and _rows() == [] and asked == []


def test_a_merge_already_journalled_earlier_is_not_journalled_again():
    _pass("merged")
    from beeverforge.observability.job_record import record_ending
    record_ending(ACME, "7", "on_hold", by="the workflow", note="re-held after a resume")
    end_closed(JOB, project=ACME, pr_status=forge("merged"))
    assert len([e for e in _journal() if e["message"] == "merged"]) == 1
    assert len(_rows()) == 1


def test_a_merge_for_another_pull_request_is_still_journalled():
    _pass("merged")
    other = {**JOB, "pr_url": "https://forge.example/acme/pull/10"}
    assert end_closed(other, project=ACME, pr_status=forge("merged")) == "merged"
    assert len([e for e in _journal() if e["message"] == "merged"]) == 2


def test_two_threads_ending_one_job_leave_one_merged_line(monkeypatch):
    from beeverforge.api import attention

    meet = threading.Barrier(2)
    real = attention._already_ended

    def checked_then_meet(*args):
        seen = real(*args)
        try:
            meet.wait(timeout=0.2)  # both past the check before either appends — if allowed
        except threading.BrokenBarrierError:
            pass
        return seen

    monkeypatch.setattr(attention, "_already_ended", checked_then_meet)
    threads = [threading.Thread(target=end_closed, args=(JOB,),
                                kwargs={"project": ACME, "pr_status": forge("merged")})
               for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len([e for e in _journal() if e["message"] == "merged"]) == 1
    assert len(_rows()) == 1


def test_the_whole_pass_shares_one_deadline_and_cut_off_jobs_stay_listed_with_a_note():
    jobs = [{**JOB, "issue": str(n)} for n in (7, 8, 9)]
    now = [0.0]
    seen = []

    def ending(job, within):
        seen.append((job["issue"], within))
        now[0] += 6.0  # each read spends 6 s of the 10 s the pass has

    out = settle(jobs, running=set(), closed_refs=lambda *_: {"7", "8", "9"},
                 bounded=lambda fn, _t: fn(), timeout=10.0, clock=lambda: now[0], ending=ending)
    assert seen == [("7", 10.0), ("8", 4.0)]
    assert [j["issue"] for j in out] == ["9"] and "time" in out[0]["note"]


def test_a_failing_ending_never_fails_the_list():
    out = settle([JOB], running=set(), closed_refs=lambda *_: {"7"}, bounded=lambda fn, _t: fn(),
                 ending=lambda job, within: 1 / 0)
    assert out == []


def test_a_forge_that_does_not_answer_in_time_writes_nothing():
    def too_slow(fn, timeout):
        raise TimeoutError

    assert end_closed(JOB, project=ACME, pr_status=forge("merged"), bounded=too_slow) is None
    assert _journal() == [] and _rows() == []


def test_the_real_forge_wiring_asks_the_forge_for_the_pr(monkeypatch):
    from beeverforge.api import app

    asked = {}

    class Forge:
        def pr_status(self, *, pr, repo=""):
            asked["pr"] = pr
            return "merged"

    monkeypatch.setattr(app, "_project_or_404", lambda name: ACME)
    monkeypatch.setattr("beeverforge.adapters.forge.registry.build_forge",
                        lambda proj, token=None: Forge())
    monkeypatch.setattr("beeverforge.credentials.forge_token_for", lambda proj: "t")
    assert app._pr_status_of("acme", PR) == "merged"
    assert asked == {"pr": PR}
