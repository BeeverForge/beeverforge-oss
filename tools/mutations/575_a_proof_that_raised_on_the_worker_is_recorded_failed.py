"""#575 — a box proof that raises on the worker is recorded as failed, proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/575_a_proof_that_raised_on_the_worker_is_recorded_failed.py

FOUR CUTS, each required to go red:

  1. The raise is recorded: without the call, the previous green proof keeps standing for a box
     nobody could measure, and `doctor` reports it.
  2. A repository's raise lands under that repository's key: keyed under the project's name, it
     would overwrite the default repository's proof and leave the asked one green.
  3. A branch's proof (`ref`) records nothing: recorded anyway, a failed measurement of a branch
     would replace the proof of the project's own box.
  4. The raise still reaches the workflow: swallowed, the workflow would end COMPLETED on a proof
     that never ran.

The guard under test: `tests/test_box_prove_is_a_catalogue_row.py`.
"""

TEST = "tests/test_box_prove_is_a_catalogue_row.py"

ACTIVITIES = "beeverforge/runtime/temporal/activities.py"

MUTATIONS = [
    ("a proof that raised is not recorded", ACTIVITIES,
     "        _record_a_proof_that_raised(project, inp, exc)\n        raise\n",
     "        raise\n",
     TEST + "::test_a_worker_proof_that_raises_replaces_the_previous_green_proof"),

    ("a repository's failed proof is recorded under the project's name", ACTIVITIES,
     "            _, key = _runner_view(project, f\"{inp.repo}#0\")\n",
     "            _runner_view(project, f\"{inp.repo}#0\")\n",
     TEST + "::test_a_repository_proof_that_raises_replaces_the_green_proof_under_that_repository_s_key"),

    ("a branch's failed proof is recorded too", ACTIVITIES,
     "    if inp.ref:\n        return\n    try:\n",
     "    try:\n",
     TEST + "::test_a_ref_proof_that_raises_leaves_the_recorded_proof_alone"),

    ("the raise is swallowed after recording", ACTIVITIES,
     "        _record_a_proof_that_raised(project, inp, exc)\n        raise\n",
     "        _record_a_proof_that_raised(project, inp, exc)\n        return str(exc)\n",
     TEST + "::test_a_worker_proof_that_raises_replaces_the_previous_green_proof"),
]
