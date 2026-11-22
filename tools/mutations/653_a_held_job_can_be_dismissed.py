"""#653 — `dismiss` closes a held job whose workflow has ended, and only that.

Run:  .venv/bin/python tools/mutate.py tools/mutations/653_a_held_job_can_be_dismissed.py

Each cut breaks one claim of `tests/test_a_held_job_can_be_dismissed.py`:

  1. the held-state check is dropped, so a merged or done job is overwritten by `dismissed`;
  2. the lock around the check and the append is dropped;
  3. an engine error is taken for "not running";
  4. a running workflow is not refused;
  5. an already-dismissed job is written again;
  6. the NOT_FOUND status is not read from the status code but from the error's text;
  7. a missing namespace is taken for a missing workflow;
  8. a job nobody ran is not refused as NOT_FOUND;
  9. the issue is not validated;
 10. the panel's dismiss row no longer escapes its values.
"""

TEST = "tests/test_a_held_job_can_be_dismissed.py"
CATALOG = "beeverforge/actions/catalog.py"
PANEL = "beeverforge/api/panel.html"

MUTATIONS = [
    ("the held-state check is dropped", CATALOG,
     "            if last not in ATTENTION_STATES:\n",
     "            if False:\n",
     TEST + "::test_a_job_that_is_not_held_is_refused_and_unchanged"),

    ("the lock around check and append is dropped", CATALOG,
     "        with lock_beside(journal).held(timeout=2.0):\n",
     "        with __import__(\"contextlib\").nullcontext():\n",
     TEST + "::test_the_journal_is_checked_and_written_only_while_the_lock_is_held"),

    ("an engine error is taken for not running", CATALOG,
     "        return refused(UNAVAILABLE, f\"could not ask the engine",
     "        runs = False\n        (refused)(UNAVAILABLE, f\"could not ask the engine",
     TEST + "::test_an_engine_error_refuses_and_writes_nothing"),

    ("a running workflow is not refused", CATALOG,
     "    if runs:\n        return refused(\n            CONFLICT,",
     "    if False:\n        return refused(\n            CONFLICT,",
     TEST + "::test_a_workflow_that_still_runs_is_refused_naming_skip"),

    ("an already-dismissed job is written again", CATALOG,
     "            if _already_ended(found, issue, \"dismissed\"):",
     "            if False:",
     TEST + "::test_a_dismissed_job_is_a_successful_no_op"),

    ("no such workflow is read from the text, not the status code", CATALOG,
     "        if exc.status == RPCStatusCode.NOT_FOUND and not any(",
     "        if \"not found\" in str(exc).lower() and not any(",
     TEST + "::test_only_the_status_code_says_no_such_workflow_never_the_text"),

    ("a missing namespace is taken for a missing workflow", CATALOG,
     "                d.Is(NamespaceNotFoundFailure.DESCRIPTOR) for d in exc.grpc_status.details):",
     "                False for d in exc.grpc_status.details):",
     TEST + "::test_a_missing_namespace_is_not_a_missing_workflow"),

    ("a job nobody ran is not refused as not found", CATALOG,
     "    if not journal.exists():\n        return refused(NOT_FOUND,",
     "    if False:\n        return refused(NOT_FOUND,",
     TEST + "::test_an_issue_nothing_ran_for_is_not_found"),

    ("the issue is not validated", CATALOG,
     "    if not re.fullmatch(r\"\\d+\", issue or \"\", re.ASCII):\n"
     "        return refused(INVALID, f\"{issue!r} is not an issue number — digits only.\")\n"
     "    found, bad = _project(project)\n    if bad:\n        return bad\n    client, bad",
     "    found, bad = _project(project)\n    if bad:\n        return bad\n    client, bad",
     TEST + "::test_the_issue_must_be_digits"),

    ("the dismiss row no longer escapes its project", PANEL,
     "data-act=\"dismissJob\" data-p=\"${esc(p)}\"",
     "data-act=\"dismissJob\" data-p=\"${p}\"",
     TEST + "::test_every_value_the_dismiss_row_interpolates_goes_through_esc"),
]
