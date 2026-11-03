"""A connect refused once the socket took it still keeps no runtime alive, however loaded the
runner (#392).

#392 gave `test_a_connect_refused_once_the_socket_took_it_keeps_no_runtime_alive` a connect bound
of its own (`REFUSED_CONNECT_WITHIN_S`) in place of the 3 s engine deadline it ran under, so a
loaded runner no longer turns the refusal it expects into a `TimeoutError`. A longer bound must
not let the case stop seeing what it guards: a failed connect that keeps its runtime alive. So
each row keeps a failed attempt's runtime, one by skipping the collection that frees it and one
by holding it from outside the attempt's frame, and runs THAT case alone. Every row must be red.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/392_a_refused_connect_is_refused_however_loaded.py
"""

LOGS = "tests/test_the_logs_can_be_json_lines_that_say_the_project.py"
CASE = LOGS + "::test_a_connect_refused_once_the_socket_took_it_keeps_no_runtime_alive"

TEST = LOGS

CONNECTION = "beeverforge/runtime/temporal/connection.py"

MUTATIONS = [
    ("a failed connect keeps its runtime until a collection nobody runs", CONNECTION,
     "            del runtime\n            gc.collect()\n",
     "            del runtime\n",
     CASE),
    ("a failed connect's runtime is kept by the process", CONNECTION,
     "            del runtime\n            gc.collect()\n",
     '            __import__("builtins").__dict__.setdefault("_kept_392", []).append(runtime)\n'
     "            del runtime\n            gc.collect()\n",
     CASE),
]
