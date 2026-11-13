"""#237 — `box_prove` is a catalogue row, and its proof on the worker is served, proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/237_box_prove_is_a_catalogue_row.py

FOUR CUTS, each required to go red:

  1. A repository's proof on the worker is its own flight: keyed under the project's name, it
     would join the default repository's proof and never run.
  2. The worker serves the activity the workflow runs: dropped from `WORKER_ACTIVITIES`, the
     workflow would schedule an activity no worker takes.
  3. The worker serves the workflow: dropped from `main()`'s list, the row's start would sit on
     the queue with nothing to run it.
  4. The worker's proof heartbeats: run without `_turning`, a worker that dies mid-proof is
     noticed at the proof's ceiling, not within `box_prove.PROOF_HEARTBEAT`.

The guard under test: `tests/test_box_prove_is_a_catalogue_row.py`.
"""

TEST = "tests/test_box_prove_is_a_catalogue_row.py"

CATALOG = "beeverforge/actions/catalog.py"
ACTIVITIES = "beeverforge/runtime/temporal/activities.py"
WORKER = "beeverforge/runtime/temporal/worker.py"

MUTATIONS = [
    ("a repository's proof on the worker is keyed under the project's name", CATALOG,
     "        view, key = _runner_view(found, f\"{repo}#0\")\n",
     "        view, key = _runner_view(found, f\"{repo}#0\")[0], found.name\n",
     TEST + "::test_a_repository_s_proof_on_the_worker_is_its_own_flight"),

    ("the worker no longer serves the proof's activity", WORKER,
     "    # #237 — one project's box proven when somebody asks through the `box_prove` row\n"
     "    prove_box,\n",
     "",
     TEST + "::test_the_worker_serves_the_box_proof"),

    ("the worker no longer serves the proof's workflow", WORKER,
     "                   # an asked box proof, one flight per key and ref (#237)\n"
     "                   BoxProveWorkflow,\n",
     "",
     TEST + "::test_the_worker_serves_the_box_proof"),

    ("the activity proves without heartbeating", ACTIVITIES,
     "    return await _turning(lambda _abandoned: _do_prove_box(inp),\n"
     "                          f\"proving the box of {inp.project}\")",
     "    return await asyncio.to_thread(_do_prove_box, inp)",
     TEST + "::test_the_worker_s_proof_heartbeats_while_it_runs"),
]
