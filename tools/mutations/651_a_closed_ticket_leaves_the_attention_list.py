"""#651 — a held job leaves /api/attention only when its workflow is gone AND its ticket is closed.

Run:  .venv/bin/python tools/mutate.py \
      tools/mutations/651_a_closed_ticket_leaves_the_attention_list.py

Each cut breaks one claim of `tests/test_a_closed_ticket_leaves_the_attention_list.py`:

  1. the running-workflow check is dropped, so a live job whose ticket is closed leaves the list;
  2. the tracker is asked once per job instead of once per project;
  3. a failed tracker read is taken for "closed", so the entry vanishes instead of being listed;
  4. an engine that could not be asked (`running=None`) is read as "nothing runs";
  5. the `isinstance(read, set)` guard goes, so an unreadable answer is trusted as a closed set.
"""

TEST = "tests/test_a_closed_ticket_leaves_the_attention_list.py"
ATTENTION = "beeverforge/api/attention.py"
APP = "beeverforge/api/app.py"

MUTATIONS = [
    ("the running-workflow check is dropped", ATTENTION,
     "    live = {(str(j.get(\"project\")), str(j.get(\"issue\")))"
     " for j in jobs} & running\n",
     "    live: set[tuple[str, str]] = set()\n",
     TEST + "::test_running_workflow_is_listed_even_if_closed"),

    ("the tracker is asked once per job, not once per project", ATTENTION,
     "    for project, refs in candidates.items():\n",
     "    for project, refs in [(p, [r]) for p, rs in candidates.items() for r in rs]:\n",
     TEST + "::test_tracker_is_asked_once_per_project"),

    ("a failed tracker read is taken for closed", ATTENTION,
     "            closed[project] = (\"the tracker read timed out\" "
     "if isinstance(exc, TimeoutError)\n"
     "                               else f\"the tracker could not be read "
     "({type(exc).__name__})\")\n",
     "            closed[project] = set(candidates[project])\n",
     TEST + "::test_failed_or_unreadable_read_keeps_entry_with_reason"),

    ("an engine that cannot be asked is read as nothing running", APP,
     "        logging.getLogger(\"beeverforge.panel\").info("
     "\"attention: engine unreadable: %r\", exc)\n"
     "        return None\n",
     "        return set()\n",
     TEST + "::test_running_workflows_is_none_when_the_engine_cannot_be_asked"),

    ("the status == running filter is dropped", APP,
     "            for r in rows if r.get(\"status\") == \"running\"}\n",
     "            for r in rows}\n",
     TEST + "::test_running_workflows_keeps_only_the_running_status"),

    ("running=None becomes an empty set", ATTENTION,
     "    if running is None:\n"
     "        return [{**j, \"note\": \"could not tell whether its workflow still runs\"} "
     "for j in jobs]\n",
     "    running = running or set()\n",
     TEST + "::test_unknown_engine_keeps_entries_with_reason"),

    ("the isinstance(read, set) guard is removed", ATTENTION,
     "            closed[project] = read if isinstance(read, set) "
     "else \"the tracker could not be read\"\n",
     "            closed[project] = read\n",
     TEST + "::test_failed_or_unreadable_read_keeps_entry_with_reason"),

    ("a full page of running workflows is read as complete", APP,
     "    if len(rows) >= _RUNNING_PAGE:\n",
     "    if False:\n",
     TEST + "::test_a_full_page_of_running_workflows_is_unknown_not_absent"),

    ("the tracker is asked about every ref, not only the candidates", ATTENTION,
     "            candidates.setdefault(project, []).append(issue)\n",
     "            pass\n"
     "        candidates.setdefault(project, []).append(issue)\n",
     TEST + "::test_tracker_is_asked_only_for_the_candidates"),
]
