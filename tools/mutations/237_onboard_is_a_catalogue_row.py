"""#237 — `onboard` is a catalogue row, safe to run twice, and served on the worker — proven by
breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/237_onboard_is_a_catalogue_row.py

THIRTEEN CUTS, each required to go red:

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
  8. A manifest proposed and not merged is said proposed: read as this run's work, a second run
     would say it did what it only found open.
  9. A preview proposal is opened only in the name of a person who asked: an opener handed to an
     ask that names nobody, the worker would open one on its own account.
 10. A box the worker cannot prove in is refused before anything starts: without the `if why:`
     return, a remote, unbounded or unknown box would be answered `running` and fail on the
     worker where nobody reads it.
 11. A context review a second run finds open is returned, never force-pushed over — the re-run
     safety of the context step, cut where the port's answer is read.
 12. The context's own `changed` is read: a run whose only change is the context would say that
     nothing changed.
 13. The verb answers a usage refusal with exit 2: read as a failure, a malformed --source would
     exit 1 like a repository that did not finish.

The guards under test: `tests/test_onboard_is_a_catalogue_row.py`, and for the context's re-run
safety `tests/test_onboard_builds_the_context_too.py`.
"""

TEST = "tests/test_onboard_is_a_catalogue_row.py"
CONTEXT_TEST = "tests/test_onboard_builds_the_context_too.py"

ONBOARD = "beeverforge/onboarding/onboard.py"
ACTIVITIES = "beeverforge/runtime/temporal/activities.py"
WORKER = "beeverforge/runtime/temporal/worker.py"
CATALOGUE = "beeverforge/actions/catalog.py"
CLI = "beeverforge/cli.py"

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

    ("a manifest found proposed is said as one this run read", ONBOARD,
     "    elif pr and getattr(out, \"existed\", False):\n        steps.append(step(MANIFEST, "
     "STEP_SKIPPED,",
     "    elif False:\n        steps.append(step(MANIFEST, STEP_SKIPPED,",
     TEST + "::test_a_manifest_proposed_and_not_merged_is_said_proposed_on_the_second_run"),

    ("an ask that names nobody is handed an opener", CATALOGUE,
     "    if not (getattr(by, \"id\", \"\") or \"\").strip() or by.id == \"worker\":\n"
     "        return None\n",
     "",
     TEST + "::test_the_worker_proposes_a_preview_only_as_the_person_who_asked"),

    ("a box the worker cannot prove in is answered running", CATALOGUE,
     "    if why:\n        return refused(INVALID, f\"{why} Nothing was started.\", "
     "project=found.name,\n                       sandbox=box_kind)\n"
     "    client, bad_engine = await _connected()\n    if bad_engine:\n        return bad_engine\n"
     "    from beeverforge.runtime.temporal import TASK_QUEUE\n"
     "    from beeverforge.runtime.temporal.io import OnboardInput\n",
     "    client, bad_engine = await _connected()\n    if bad_engine:\n        return bad_engine\n"
     "    from beeverforge.runtime.temporal import TASK_QUEUE\n"
     "    from beeverforge.runtime.temporal.io import OnboardInput\n",
     TEST + "::test_away_from_the_shell_a_box_the_worker_cannot_prove_in_is_refused"),

    ("an open context review is pushed over on a second run", ONBOARD,
     "        if pushed_already.strip():\n",
     "        if False:\n",
     CONTEXT_TEST + "::test_an_open_context_review_is_found_not_force_pushed_over"),

    ("the context's own change is not read", ONBOARD,
     "                   \"changed\": bool(made.created or made.changed)}",
     "                   \"changed\": bool(made.created)}",
     TEST + "::test_a_run_whose_only_change_is_the_context_says_it_changed"),

    ("a usage refusal exits as a failure", CLI,
     "        typer.echo(f\"✗ {outcome.message}\")\n"
     "        raise typer.Exit(2 if outcome.code in (INVALID, NOT_FOUND) else 1)\n"
     "    outcomes = outcome.data.get(\"repos\")",
     "        typer.echo(f\"✗ {outcome.message}\")\n"
     "        raise typer.Exit(1)\n"
     "    outcomes = outcome.data.get(\"repos\")",
     TEST + "::test_the_verb_refuses_a_malformed_source_and_exits_2"),
]
