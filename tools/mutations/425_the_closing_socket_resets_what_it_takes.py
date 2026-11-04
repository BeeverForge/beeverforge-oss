"""The `closing` fixture's thread refuses each connection it takes with a reset, not a FIN (#425).

`test_a_connect_refused_once_the_socket_took_it_keeps_no_runtime_alive` waited out its 30 s bound
in loaded gate runs. Measured without Docker, it never hung (302 runs under load), so the fixture
now closes each connection it takes with `SO_LINGER` 0, an RST: the one refusal the client sees
whatever it has sent and whenever it reads. Each row puts back a close that is not a reset, and
runs the unit check that reads the client's end on the calling thread. Every row must be red.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/425_the_closing_socket_resets_what_it_takes.py
"""

LOGS = "tests/test_the_logs_can_be_json_lines_that_say_the_project.py"
CHECK = LOGS + "::test_the_closing_socket_resets_what_it_takes"

TEST = CHECK

LINGER = '    taken.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))\n'

MUTATIONS = [
    ("the taken socket is closed without `SO_LINGER`, so the close is a FIN", LOGS,
     LINGER,
     "",
     CHECK),
    ("`SO_LINGER` is set with lingering off, so the close is a FIN", LOGS,
     LINGER,
     LINGER.replace('pack("ii", 1, 0)', 'pack("ii", 0, 0)'),
     CHECK),
    ("`_close_each` closes what it took without `_refuse`", LOGS,
     "            continue\n        _refuse(taken)\n",
     "            continue\n        taken.close()\n",
     CHECK),
]
