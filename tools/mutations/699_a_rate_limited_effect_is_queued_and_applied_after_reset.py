"""#699: a tracker write that fails on a rate limit is queued, shared by the project's runners, and
drained when a job starts and ends and on the worker's hourly round — only by a tracker of the
repository it was made for, and never over a newer move of the card (ADR-0055 D5).

One cut per guard: the reload under the lock (two trackers on one path), the lock itself, the
build_runner wiring, the drain at the job's two ends; one cut per rule of the queue in deferred.py:
newest entry wins, a write joins behind waiting entries, an entry leaves the file before it is
applied, a rate-limited apply is re-queued, any other failure is dropped; and, from the second
review of #708, one per new guard: the scope, the card record's newer move, the stopped job, the
job's own marks at its end, a person's assignees, the hourly drain and its views, the worker's
comments, the whole body, the unquoted line, the owner-only file, the unreadable entry, a ticket's
own wait, and the copy. Each is killed by a named test.
"""

TEST = "tests/test_a_rate_limited_effect_is_queued_and_applied_after_reset.py"
DEFERRED = "beeverforge/adapters/tracker/deferred.py"
FACTORY = "beeverforge/factory.py"
MACHINE = "beeverforge/orchestrator/machine.py"
ACTIVITIES = "beeverforge/runtime/temporal/activities.py"

MUTATIONS = [
    ("the queue is not reloaded from the file under the lock, so a tracker re-applies what "
     "another applied (test_an_entry_a_live_tracker_applied_is_not_applied_again_by_another)",
     DEFERRED,
     "                    fcntl.flock(fd, fcntl.LOCK_EX)\n"
     "                    self._queue = self._load()\n",
     "                    fcntl.flock(fd, fcntl.LOCK_EX)\n"),

    ("no file lock is taken, so the file is not the one truth "
     "(test_two_trackers_on_one_path_lose_no_entry)", DEFERRED,
     "                if fd is not None:\n                    fcntl.flock(fd, fcntl.LOCK_EX)\n"
     "                    self._queue = self._load()\n",
     "                self._queue = self._queue\n"),

    ("build_runner hands the runner a bare tracker, so nothing is queued "
     "(test_a_runner_from_build_runner_queues_and_drains_when_its_job_ends)", FACTORY,
     "        tracker=deferring_tracker(\n            project,\n",
     "        tracker=(lambda project, inner: inner)(\n            project,\n"),

    ("each tracker gets its own queue file, so a finished job's queue is never drained "
     "(test_a_later_runner_drains_what_a_finished_job_left_when_it_starts)", FACTORY,
     "                            path=project_log_dir(project) / QUEUED_TRACKER_EFFECTS,\n",
     "                            path=project_log_dir(project) / f\"q-{id(tracker)}.json\",\n"),

    ("a job does not drain the queue when it ends "
     "(test_a_runner_from_build_runner_queues_and_drains_when_its_job_ends)", MACHINE,
     "            self._drain_queued_effects(ticket_ref, ended=True)\n",
     "            pass\n"),

    ("a job does not drain the queue when it starts "
     "(test_a_later_runner_drains_what_a_finished_job_left_when_it_starts)", MACHINE,
     "        self._drain_queued_effects()\n        try:\n"
     "            return run(self, *args, **kwargs)",
     "        try:\n            return run(self, *args, **kwargs)"),

    # -- the rules of the queue --
    ("a later write for the same key does not replace the earlier entry, so every state is "
     "applied (test_only_the_newest_state_per_ticket_is_applied)", DEFERRED,
     "        self._queue = [e for e in self._queue if not (self._mine(e) and e[\"key\"] == "
     "list(key))]\n",
     ""),

    ("a write for a ticket with entries waiting goes straight to the forge and overtakes them "
     "(test_a_write_for_a_ticket_with_entries_waiting_joins_behind_them)", DEFERRED,
     "            if behind:\n",
     "            if False:\n"),

    ("an entry stays in the file while it is applied, so a restart applies it again "
     "(test_the_queue_survives_a_restart, test_an_entry_is_out_of_the_file_while_it_is_applied)",
     DEFERRED,
     "                self._queue.pop(i)\n"
     "                self._save()  # claimed in the file before it is applied: at most once\n",
     "                self._queue.pop(i)\n"),

    ("an apply that is still rate-limited is dropped, not re-queued "
     "(test_still_limited_after_the_reset_keeps_the_entry_for_the_next_reset)", DEFERRED,
     '                    entry["reset_at"] = exc.reset_at\n'
     "                    self._queue.insert(i, entry)\n",
     ""),

    ("a limit met again keeps the old reset "
     "(test_a_limit_met_again_moves_the_entry_to_the_new_reset)", DEFERRED,
     '                    entry["reset_at"] = exc.reset_at\n',
     ""),

    ("an apply that fails for another reason is kept at the head and blocks the queue "
     "(test_an_entry_that_fails_for_another_reason_is_dropped_and_the_next_applied)", DEFERRED,
     "                              redact(str(exc))[:160])\n                    continue\n",
     "                              redact(str(exc))[:160])\n"
     "                    self._queue.insert(i, entry)\n                    self._save()\n"
     "                    return applied\n"),

    ("whom the state waits on is dropped on replay "
     "(test_a_limit_met_again_keeps_the_order_the_new_reset_and_whom_the_state_waits_on)",
     DEFERRED,
     'needs_person=p.get("needs_person"))',
     "needs_person=None)"),

    # -- second review of #708 --
    ("every tracker applies every repository's entries "
     "(test_a_queued_entry_is_applied_only_by_a_runner_of_its_own_repository)", DEFERRED,
     '        return entry.get("scope", "") == self._scope\n',
     "        return True\n"),

    ("the factory gives every view one scope "
     "(test_a_queued_entry_is_applied_only_by_a_runner_of_its_own_repository)", FACTORY,
     "                            scope=scope, superseded=_a_newer_move(project, scope))\n",
     '                            scope="", superseded=_a_newer_move(project, scope))\n'),

    ("the queue never asks whether an entry is superseded "
     "(test_a_queued_state_is_not_applied_over_a_move_the_card_record_holds_since)", DEFERRED,
     "        if self._superseded is not None:\n",
     "        if False:\n"),

    ("a move recorded after the entry supersedes nothing "
     "(test_a_queued_state_is_not_applied_over_a_move_the_card_record_holds_since)", FACTORY,
     '        if when > float(entry["queued_at"]):\n',
     "        if False:\n"),

    ("any recorded move supersedes, even one older than the entry "
     "(test_a_move_recorded_before_the_entry_was_queued_supersedes_nothing)", FACTORY,
     '        if when > float(entry["queued_at"]):\n',
     "        if True:\n"),

    ("a move supersedes a comment too "
     "(test_a_queued_state_is_not_applied_over_a_move_the_card_record_holds_since)", FACTORY,
     '        if entry.get("kind") == "comment":\n            return ""\n',
     ""),

    ("a stopped job drains its queue "
     "(test_a_stopped_job_applies_nothing_it_queued)", MACHINE,
     '        try:\n            self._unless_stopped("drain the queued tracker effects")\n'
     "        except JobStopped:\n            return\n",
     ""),

    ("a job's own marks are applied after it ended "
     "(test_a_job_that_ends_drops_its_own_queued_progress_marks)", MACHINE,
     "            if ended and ticket_ref and callable(supersede):\n",
     "            if False:\n"),

    ("an assignee change is applied over a person's "
     "(test_a_queued_assignee_change_is_dropped_when_a_person_changed_them_meanwhile)", DEFERRED,
     "            if sorted(now) != sorted(before):\n",
     "            if False:\n"),

    ("the hourly round does not drain "
     "(test_the_hourly_round_drains_what_a_finished_job_left)", ACTIVITIES,
     "        applied = drain_queued_effects(project, tracker_for=_tracker_for)\n",
     "        applied = 0\n"),

    ("the hourly drain uses the product's tracker for every repository "
     "(test_the_hourly_drain_applies_each_repositorys_entries_with_its_own_tracker)", FACTORY,
     "        if scope != _tracker_scope(project):\n",
     "        if False:\n"),

    ("the diagnosis comment is posted on the bare tracker "
     "(test_the_diagnosis_a_rate_limit_refuses_is_queued_for_after_the_reset)", ACTIVITIES,
     "        _queued(project, tracker).comment(ref, handoff_to_markdown(",
     "        tracker.comment(ref, handoff_to_markdown("),

    ("the gather's chase is posted on the bare tracker "
     "(test_every_comment_the_worker_posts_goes_through_the_queue)", ACTIVITIES,
     "                    _queued(project, tracker).comment(ref, tl_voice.say(",
     "                    tracker.comment(ref, tl_voice.say("),

    ("a queued comment is cut "
     "(test_a_long_queued_comment_is_applied_whole)", DEFERRED,
     '{"body": body},',
     '{"body": body[:20_000]},'),

    ("the queued line quotes the comment "
     "(test_the_queued_line_names_the_comment_and_never_its_words)", DEFERRED,
     'if key[0] == "comment"\n',
     "if False\n"),

    ("the queue file takes the umask "
     "(test_the_queue_file_is_readable_by_its_owner_only)", DEFERRED,
     "            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)\n"
     '            with os.fdopen(fd, "w") as out:\n'
     "                out.write(json.dumps(self._queue))\n"
     "            os.chmod(tmp, 0o600)\n",
     "            tmp.write_text(json.dumps(self._queue))\n"),

    ("an unreadable entry is kept "
     "(test_a_malformed_entry_is_dropped_by_name_and_the_rest_still_works)", DEFERRED,
     "        why = _unreadable(entry)\n",
     '        why = ""\n'),

    ("one ticket's wait holds every later entry "
     "(test_one_tickets_wait_does_not_hold_another_tickets_due_entry)", DEFERRED,
     "                    waiting.add(ticket)\n                    i += 1\n"
     "                    continue\n",
     "                    return applied\n"),

    ("a ticket's later entry overtakes one still waiting "
     "(test_a_tickets_later_entry_never_overtakes_one_still_waiting)", DEFERRED,
     '                if ticket in waiting or entry["reset_at"] > now:\n',
     '                if entry["reset_at"] > now:\n'),

    ("a dunder is forwarded to the wrapped tracker "
     "(test_a_copy_of_the_tracker_does_not_recurse)", DEFERRED,
     '        if name.startswith("__") or name == "_inner":\n',
     "        if False:\n"),
]
