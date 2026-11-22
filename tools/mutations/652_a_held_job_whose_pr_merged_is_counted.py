"""#652 — a held job whose ticket is closed ends as `merged` (counted) or `closed` (not).

Run:  .venv/bin/python tools/mutate.py \
      tools/mutations/652_a_held_job_whose_pr_merged_is_counted.py

Each cut breaks one claim of `tests/test_a_held_job_whose_pr_merged_is_counted.py`:

  1. the lock around the check and the append is dropped, so two threads write two lines;
  2. the merged guard looks only at the last state, so a re-held merged job is ended again;
  3. the merged guard ignores which pull request the event names;
  4. a failed forge read is taken for merged;
  5. an open pull request is taken for closed;
  6. a closed-without-a-merge ticket writes the merged row too;
  7. the shared deadline is never checked, so a slow pass records every job;
  8. each ending is given the whole budget instead of what is left of it;
  9. a job with no pull request is left listed instead of ending as closed.
"""

TEST = "tests/test_a_held_job_whose_pr_merged_is_counted.py"
ATTENTION = "beeverforge/api/attention.py"

MUTATIONS = [
    ("the lock around check and append is dropped", ATTENTION,
     "        with lock_beside(events_file(project, issue)).held(timeout=ENDING_LOCK_TIMEOUT_S):\n",
     "        with __import__(\"contextlib\").nullcontext():\n",
     TEST + "::test_two_threads_ending_one_job_leave_one_merged_line"),

    ("the merged guard reads only the last state", ATTENTION,
     "            continue\n        return event.get(\"message\") == state",
     "            return False\n        return event.get(\"message\") == state",
     TEST + "::test_a_merge_already_journalled_earlier_is_not_journalled_again"),

    ("the merged guard ignores which pull request", ATTENTION,
     "and pr in str(data.get(\"reason\") or \"\")):",
     "):",
     TEST + "::test_a_merge_for_another_pull_request_is_still_journalled"),

    ("a failed forge read is taken for merged", ATTENTION,
     "            log.info(\"attention: pull request of %s#%s unreadable: %r\", name, issue, exc)\n"
     "            return None\n",
     "            status = \"merged\"\n",
     TEST + "::test_an_unreadable_or_open_pr_writes_nothing"),

    ("an open pull request is taken for closed", ATTENTION,
     "    if status not in (\"merged\", \"closed\"):\n        return None\n",
     "    status = \"merged\" if status == \"merged\" else \"closed\"\n",
     TEST + "::test_an_unreadable_or_open_pr_writes_nothing"),

    ("a closed ticket also writes the merged row", ATTENTION,
     "            note = (f\"its ticket was closed and pull request",
     "            record_job_ending(project=name, issue=issue, state=\"merged\", pr_url=pr)\n"
     "            note = (f\"its ticket was closed and pull request",
     TEST + "::test_closed_without_a_merge_ends_closed_and_counts_nothing"),

    ("the shared deadline is never checked", ATTENTION,
     "            if within <= 0:\n",
     "            if False:\n",
     TEST + "::test_the_whole_pass_shares_one_deadline_and_cut_off_jobs_stay_listed_with_a_note"),

    ("each ending gets the whole budget", ATTENTION,
     "                ending(job, within)\n",
     "                ending(job, timeout)\n",
     TEST + "::test_the_whole_pass_shares_one_deadline_and_cut_off_jobs_stay_listed_with_a_note"),

    ("a job with no pull request stays listed", ATTENTION,
     "    status = \"closed\"\n    if pr:\n",
     "    status = \"open\"\n    if pr:\n",
     TEST + "::test_a_job_without_a_pr_whose_ticket_is_closed_ends_closed_and_counts_nothing"),
]
