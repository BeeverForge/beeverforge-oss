"""The day a line was said is compared against the moment handed to the code, never against a
second read of the test's own clock (#393).

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/393_the_day_the_role_is_told_is_read_once.py

`test_the_role_knows_what_day_it_is.py` compared the day stamped on the conversation's lines with
its own `datetime.now(UTC)`, read after the code had read its clock: a run that straddled UTC
midnight failed though the code was right. The new case stubs both clocks, the code's at 23:59:59.9
UTC and the test's own just after midnight. Row 1 puts the comparison back on the test's own clock,
and the case must go red.
"""

TEST = "tests/test_the_role_knows_what_day_it_is.py"

MUTATIONS = [
    ("the comparison reads its own `datetime.now(UTC)` again, a day later than the code read",
     TEST,
     '    told = moment.strftime("%Y-%m-%d")\n',
     '    told = datetime.now(UTC).strftime("%Y-%m-%d")\n'),
]
