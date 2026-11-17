"""#237 — `onboard` is a catalogue row, safe to run twice, and served on the worker — proven by
breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/237_onboard_is_a_catalogue_row.py

SEVEN CUTS, each required to go red:

  1. A pull request a second run finds open is said `already`: read as a change of this run, the
     second onboarding would report that it opened what it only found — the re-run safety, cut.
  2. A preview proposal a second run finds open is said `already`, the same cut on the preview.
  3. A context the second run found proposed is not a change: forced, `changed` lies.
  4. One flight per project: an id drawn fresh per ask, a second ask while one runs would start a
     second onboarding of the same repositories instead of joining it.
  5. The worker serves the activity the workflow runs: dropped from `WORKER_ACTIVITIES`, the
     workflow would schedule an activity no worker takes.
  6. The worker serves the workflow: dropped from `main()`'s list, the row's start would sit on
     the queue with nothing to run it.
  7. The worker's onboarding heartbeats: run without `_turning`, a worker that dies mid-onboarding
     is noticed at the run's ceiling, not within `onboard.ONBOARD_HEARTBEAT`.

The guard under test: `tests/test_onboard_is_a_catalogue_row.py`.
"""

TEST = "tests/test_onboard_is_a_catalogue_row.py"

ONBOARD = "beeverforge/onboarding/onboard.py"
ACTIVITIES = "beeverforge/runtime/temporal/activities.py"
WORKER = "beeverforge/runtime/temporal/worker.py"

MUTATIONS = [
    ("a pull request found open is said as one this run opened", ONBOARD,
     "    if pr and getattr(out, \"existed\", False):\n",
     "    if pr and False:\n",
     TEST + "::test_running_it_twice_changes_nothing_the_second_time_and_says_so"),

    ("a preview proposal found open is said as one this run opened", ONBOARD,
     "    return step(PREVIEW, STEP_ALREADY if proposed.existed else STEP_DONE, where)",
     "    return step(PREVIEW, STEP_DONE, where)",
     TEST + "::test_with_preview_each_repository_proposes_its_preview_once"),

    ("a context found proposed is said as changed", ONBOARD,
     "                   \"changed\": bool(made.created or made.changed)}",
     "                   \"changed\": True}",
     TEST + "::test_running_it_twice_changes_nothing_the_second_time_and_says_so"),

    ("every ask is its own flight", ONBOARD,
     "    return \"onboard-\" + hashlib.sha256(project_name.encode()).hexdigest()",
     "    return \"onboard-\" + __import__(\"uuid\").uuid4().hex",
     TEST + "::test_a_second_ask_while_a_run_is_going_answers_the_same_handle"),

    ("the worker no longer serves the onboarding's activity", WORKER,
     "    # #237 — one project's repositories onboarded when somebody asks through the `onboard` "
     "row\n    onboard_product,\n",
     "",
     TEST + "::test_the_worker_serves_the_onboarding"),

    ("the worker no longer serves the onboarding's workflow", WORKER,
     "                   # an asked onboarding, one flight per project (#237)\n"
     "                   OnboardWorkflow,\n",
     "",
     TEST + "::test_the_worker_serves_the_onboarding"),

    ("the activity onboards without heartbeating", ACTIVITIES,
     "    return await _turning(lambda _abandoned: _do_onboard(inp), f\"onboarding {inp.project}\")",
     "    return await asyncio.to_thread(_do_onboard, inp)",
     TEST + "::test_the_worker_s_run_heartbeats_while_it_goes"),
]
