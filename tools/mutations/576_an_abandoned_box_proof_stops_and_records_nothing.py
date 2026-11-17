"""#576 — a box proof the workflow gave up on stops, lets go of the key and records nothing.

Run:  .venv/bin/python tools/mutate.py \
      tools/mutations/576_an_abandoned_box_proof_stops_and_records_nothing.py

FIVE CUTS, each required to go red:

  1. `prove_the_box` records an abandoned proof: a late proof replaces the standing record.
  2. `_do_prove_box` records a proof that raised after the abandonment.
  3. `_in_box` starts commands after the abandonment: setup and gates run on past the ceiling.
  4. `prove_box` stops handing the event to the body: nothing could ever stop it.
  5. The watcher does not end the run in flight: a gate mid-run keeps the key's lock until its own
     `timeout_minutes`.

The guard under test: `tests/test_box_prove_is_a_catalogue_row.py`.
"""

TEST = "tests/test_box_prove_is_a_catalogue_row.py"

PROVE = "beeverforge/box_prove.py"
ACTIVITIES = "beeverforge/runtime/temporal/activities.py"

MUTATIONS = [
    ("an abandoned proof is recorded", PROVE,
     "    if abandoned is not None and abandoned.is_set():\n"
     "        # THE FAILED WORKFLOW'S PROOF",
     "    if False:\n"
     "        # THE FAILED WORKFLOW'S PROOF",
     TEST + "::test_an_abandoned_proof_is_not_recorded"),

    ("an abandoned proof that raised is recorded as failed", ACTIVITIES,
     "        if abandoned is None or not abandoned.is_set():\n"
     "            _record_a_proof_that_raised(project, inp, exc)\n",
     "        _record_a_proof_that_raised(project, inp, exc)\n",
     TEST + "::test_an_abandoned_worker_proof_that_raises_records_nothing"),

    ("an abandoned proof still starts commands", PROVE,
     "        if abandoned is not None and abandoned.is_set():\n"
     "            return 1, \"the proof was abandoned by the worker",
     "        if False:\n"
     "            return 1, \"the proof was abandoned by the worker",
     TEST + "::test_an_abandoned_proof_runs_no_more_commands_and_lets_go_of_the_key"),

    ("the activity no longer hands the event to the body", ACTIVITIES,
     "    return await _turning(lambda abandoned: _do_prove_box(inp, abandoned),\n",
     "    return await _turning(lambda abandoned: _do_prove_box(inp),\n",
     TEST + "::test_prove_box_hands_the_turn_s_event_to_the_body_and_sets_it_on_cancel"),

    ("the run in flight is not ended when the proof is abandoned", PROVE,
     "        if abandoned is not None and workspace is not None:\n"
     "            threading.Thread(",
     "        if False:\n"
     "            threading.Thread(",
     TEST + "::test_an_abandoned_proof_ends_the_run_in_flight_and_frees_the_key"),
]
