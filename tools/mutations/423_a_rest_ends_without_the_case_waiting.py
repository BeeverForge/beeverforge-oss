"""The engine-connection cases end each target's rest without waiting on real time, and still see
a rest that never ends and a failed attempt that records none (#423).

#423 replaced `_until_no_target_rests()`, which slept until each rest's `until`, with
`_end_the_rest()`, which asserts that the failed attempt left a rest, moves its `until` to now and
asserts that the target is no longer refused. So each row breaks one of those, and runs each case
that calls the helper. Every row must be red.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/423_a_rest_ends_without_the_case_waiting.py
"""

LOGS = "tests/test_the_logs_can_be_json_lines_that_say_the_project.py"
ASKED_AGAIN = LOGS + ("::test_once_its_rest_ends_a_target_is_asked_again_and_a_client_that_lands"
                      "_leaves_no_failed_runtime")
REFUSED = LOGS + "::test_a_connect_refused_once_the_socket_took_it_keeps_no_runtime_alive"

TEST = LOGS

CONNECTION = "beeverforge/runtime/temporal/connection.py"

NEVER_ENDS = "    if rest is None or rest.until <= now:\n"
NO_REST = "                _rest_after(key, failure)\n"

MUTATIONS = [
    ("a rest never ends, so the target is never asked again", CONNECTION,
     NEVER_ENDS, "    if rest is None:\n", ASKED_AGAIN),
    ("a rest never ends, so the refused socket is never reached again", CONNECTION,
     NEVER_ENDS, "    if rest is None:\n", REFUSED),
    ("a failed attempt records no rest, through every door", CONNECTION,
     NO_REST, "                pass\n", ASKED_AGAIN),
    ("a connect refused once the socket took it records no rest", CONNECTION,
     NO_REST, "                pass\n", REFUSED),
]
