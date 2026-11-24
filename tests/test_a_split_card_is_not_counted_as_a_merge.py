"""A card the sizer splits is not a merge (#669).

WHAT WAS WRONG. The pre-flight split closed the parent and the job ended `done` — the same word a
merged job ends in, and one of the states past the merge. Throughput (`query.outcomes`'s
`past_the_merge`, the cost per merged ticket) and autonomy (`before_the_record`) counted a card
that shipped nothing as a merge, and counted it again when each of its parts merged.

THE CHOICE: a state of its own, `split`, declared after `failed`, outside the merge-to-done slice
`PAST_THE_MERGE` is read from. A `done` job with a marker in `extra` would have needed every
reader of the rows past the merge to remember to exclude it — the shape of the defect, repeated
once per reader — while a state outside the slice is excluded by the one definition they all read.

WHAT IS PROVEN HERE, on fakes and with no wait on real time: a split ending is `split`,
which no reader counts as landed; a merged part counts once; a normal merged job still counts.
"""

from __future__ import annotations

from beeverforge.contracts.state import PAST_THE_MERGE, JobState
from tests import test_autonomy_is_read_from_the_record as autonomy_tests
from tests.test_the_outcomes_are_read_never_inferred import Deployment, _one_job, at

store = autonomy_tests.store
passes, measure = autonomy_tests.passes, autonomy_tests.measure


def test_a_split_is_a_state_of_its_own_outside_the_states_past_the_merge():
    assert JobState.SPLIT.value == "split"
    assert JobState.SPLIT.value not in PAST_THE_MERGE
    assert JobState.DONE.value in PAST_THE_MERGE


def test_throughput_does_not_count_a_split_parent_and_counts_each_part_once(tmp_path, monkeypatch):
    d = Deployment(tmp_path, monkeypatch)
    _one_job(d, "37", at(3), state="split")
    _one_job(d, "38", at(2), state="merged")
    _one_job(d, "39", at(1), state="merged")
    _one_job(d, "40", at(1, hours=2), state="done")

    got = d.outcomes()

    assert got["past_the_merge"] == 3, "the parent was counted beside its merged parts"
    assert got["ended"]["split"] == 1, "a split is its own ending, not an unrecognised one"
    assert got["ended"].get("unrecognised", 0) == 0


def test_the_cost_per_merged_ticket_leaves_a_split_parent_out(tmp_path, monkeypatch):
    d = Deployment(tmp_path, monkeypatch)
    _one_job(d, "37", at(3), state="split")
    d.run("acme", "37", "sizer", at(3), cost=9.0)
    _one_job(d, "38", at(2), state="merged")
    d.run("acme", "38", "executor", at(2), cost=1.0)

    got = d.outcomes()

    assert got["cost_per_merged_ticket_usd"]["median"] == 1.0


def test_autonomy_does_not_take_a_split_parent_for_a_merge(store):
    passes("37", "sizer", state="split")
    passes("38", "executor", state="merged")

    got = measure()

    assert got["before_the_record"] == ["38"], "the parent is not a card that merged"

