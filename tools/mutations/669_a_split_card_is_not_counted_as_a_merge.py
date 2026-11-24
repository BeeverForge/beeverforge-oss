"""A card the sizer splits ends `split`, which no reader counts as a merge (#669), proven by
breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/669_a_split_card_is_not_counted_as_a_merge.py

The pre-flight split closed the parent and the job ended `done`, one of the states past the merge,
so throughput and autonomy counted a card that shipped nothing — and counted each part again when
it merged. The claims, each a row:

  1. the split is its own state, declared outside the merge-to-done slice;
  2. the workflow ends a split `split`, never `done`;
  3. each reader of the states past the merge — the throughput count, the cost per merged ticket,
     autonomy's merges the record never saw — leaves it out, and the endings name it.
"""

TEST = "tests/test_a_split_card_is_not_counted_as_a_merge.py"
STATE = "beeverforge/contracts/state.py"
WORKFLOW = "beeverforge/runtime/temporal/workflow.py"
QUERY = "beeverforge/observability/query.py"
AUTONOMY = "beeverforge/observability/autonomy.py"
WORKFLOW_TEST = ("tests/test_temporal_workflow.py::"
                 "test_preflight_split_creates_children_and_frees_the_floor")

MUTATIONS = [
    ("THE DEFECT ITSELF: the split is declared inside the merge's tail, so it is past the merge",
     STATE,
     '    SPLIT = "split"\n',
     '    SPLIT = "split"\n    DONE = "done"\n'),

    ("the split sits before `done` in the enum, inside the slice", STATE,
     '    ROLLING_BACK = "rolling_back"  # safe pre-defined action; re-deploy last-good tag\n'
     '    DONE = "done"',
     '    ROLLING_BACK = "rolling_back"  # safe pre-defined action; re-deploy last-good tag\n'
     '    SPLIT_FIRST = "split"\n'
     '    DONE = "done"'),

    ("the pre-flight ends a split `done` again", WORKFLOW,
     "return RunResult(ticket_id=params.issue, state=JobState.SPLIT, note=note)",
     "return RunResult(ticket_id=params.issue, state=JobState.DONE, note=note)",
     WORKFLOW_TEST),

    ("the throughput counts a split parent as past the merge", QUERY,
     "        block[\"past_the_merge\"] = sum(1 for j in closed if j.state in PAST_THE_MERGE)",
     "        block[\"past_the_merge\"] = sum(1 for j in closed\n"
     "                                      if j.state in PAST_THE_MERGE | {\"split\"})"),

    ("the cost per merged ticket prices a split parent", QUERY,
     "        merged = sorted({(j.project, j.ticket) for j in closed "
     "if j.state in PAST_THE_MERGE})",
     "        merged = sorted({(j.project, j.ticket) for j in closed\n"
     "                         if j.state in PAST_THE_MERGE | {\"split\"}})"),

    ("autonomy takes a split parent's job row for a merge the record never saw", AUTONOMY,
     "        elif row.get(\"kind\") == \"job\" and "
     "str(row.get(\"state\") or \"\") in PAST_THE_MERGE:",
     "        elif row.get(\"kind\") == \"job\" and "
     "str(row.get(\"state\") or \"\") in (\n"
     "                PAST_THE_MERGE | {\"split\"}):"),

    ("a split ending is read as an unrecognised word", QUERY,
     "        known = {s.value for s in JobState}",
     "        known = {s.value for s in JobState if s is not JobState.SPLIT}"),
]
