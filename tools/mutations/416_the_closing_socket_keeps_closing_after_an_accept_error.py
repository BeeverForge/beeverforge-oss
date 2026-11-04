"""The `closing` fixture's thread keeps taking and closing connections after an accept fails
(#416).

`test_a_connect_refused_once_the_socket_took_it_keeps_no_runtime_alive` timed out at 30 s on CI.
Its `closing` socket's thread left on any `OSError` from `accept`, not only once the case was
over; a socket nobody takes from still completes each handshake, so the library's request waited
out the attempt's whole bound. Each row puts back a loop that ends on an accept error, and runs
the unit check that makes one accept fail. Every row must be red.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/416_the_closing_socket_keeps_closing_after_an_accept_error.py
"""

LOGS = "tests/test_the_logs_can_be_json_lines_that_say_the_project.py"
CHECK = LOGS + "::test_the_closing_socket_keeps_closing_what_it_takes_after_an_accept_error"

TEST = CHECK

MUTATIONS = [
    ("an accept that fails ends the thread, as if the socket were closed", LOGS,
     "            stop.wait(0.01)\n            continue\n",
     "            return\n",
     CHECK),
    ("an accept that fails breaks out of the loop", LOGS,
     "            stop.wait(0.01)\n            continue\n",
     "            break\n",
     CHECK),
]
