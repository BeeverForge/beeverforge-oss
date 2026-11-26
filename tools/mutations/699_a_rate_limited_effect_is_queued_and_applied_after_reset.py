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
     "                    self._reload()\n",
     "                    fcntl.flock(fd, fcntl.LOCK_EX)\n"),

    ("no file lock is taken, so the file is not the one truth "
     "(test_two_trackers_on_one_path_lose_no_entry)", DEFERRED,
     "                if fd is not None:\n                    fcntl.flock(fd, fcntl.LOCK_EX)\n"
     "                    self._reload()\n",
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
     "        self._queue = [e for e in self._queue\n"
     "                       if not (self._mine(e) and e[\"key\"] == list(key) "
     "and not e.get(\"claimed\"))]\n",
     ""),

    ("a write for a ticket with entries waiting goes straight to the forge and overtakes them "
     "(test_a_write_for_a_ticket_with_entries_waiting_joins_behind_them)", DEFERRED,
     "            if behind:\n",
     "            if False:\n"),

    ("an entry stays in the file while it is applied, so a restart applies it again "
     "(test_an_entry_is_claimed_in_the_file_while_it_is_applied, "
     "test_an_entry_whose_claim_could_not_be_saved_is_not_applied)",
     DEFERRED,
     "            if not self._save():  # claimed in the file before it is applied: at most once\n",
     "            if False:\n"),

    ("an apply that is still rate-limited is dropped, not re-queued "
     "(test_still_limited_after_the_reset_keeps_the_entry_for_the_next_reset)", DEFERRED,
     "                with self._held():\n                    for e in self._queue:\n",
     "                self._release(entry)\n                with self._held():\n"
     "                    for e in []:\n"),

    ("a limit met again keeps the old reset "
     "(test_a_limit_met_again_moves_the_entry_to_the_new_reset)", DEFERRED,
     '                            e["reset_at"] = exc.reset_at\n',
     ""),

    ("an apply that fails for another reason is kept at the head and blocks the queue "
     "(test_an_entry_that_fails_for_another_reason_is_dropped_and_the_next_applied)", DEFERRED,
     "            except Exception as exc:  # a retry that cannot succeed is dropped, logged\n"
     "                self._release(entry)\n",
     "            except Exception as exc:  # a retry that cannot succeed is dropped, logged\n"
     "                return applied\n"),

    ("whom the state waits on is dropped on replay "
     "(test_a_limit_met_again_keeps_the_order_the_new_reset_and_whom_the_state_waits_on)",
     DEFERRED,
     'needs_person=p.get("needs_person"))',
     "needs_person=None)"),

    # -- second review of #708 --
    ("every tracker applies every repository's entries "
     "(test_trackers_of_two_coordinates_on_one_file_apply_only_their_own)", DEFERRED,
     '        return entry.get("scope", "") == self._scope\n',
     "        return True\n"),

    # RETIRED 2026-11-26: "the factory gives every view one scope" — no view moves the tracker
    # (C-18), so every card's runner has the product's scope; a card is told apart by its ticket
    # (the cuts below), and the scope rule is held by `_mine`'s cut above.

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

    # RETIRED 2026-11-26: "the hourly drain uses the product's tracker for every repository" —
    # the drain no longer builds a view per repository: one product tracker applies every card's
    # entries (test_the_hourly_drain_applies_every_cards_entries).

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
     '            if ticket in waiting or entry["reset_at"] > now:\n'
     "                waiting.add(ticket)\n                continue\n",
     '            if ticket in waiting or entry["reset_at"] > now:\n'
     "                return None\n"),

    ("a ticket's later entry overtakes one still waiting "
     "(test_a_tickets_later_entry_never_overtakes_one_still_waiting)", DEFERRED,
     '            if ticket in waiting or entry["reset_at"] > now:\n',
     '            if entry["reset_at"] > now:\n'),

    ("a dunder is forwarded to the wrapped tracker "
     "(test_a_copy_of_the_tracker_does_not_recurse)", DEFERRED,
     '        if name.startswith("__") or name == "_inner":\n',
     "        if False:\n"),

    # -- the semantic review of #708 at 48ff615 --
    ("a bare ref of the runner's own card is the home repository's ticket "
     "(test_a_card_of_another_repository_is_its_own_ticket_in_the_queue)", DEFERRED,
     "            if card_repo and canonical_ref(card_bare) == bare:\n",
     "            if False:\n"),

    ("build_runner does not tell the queue its card "
     "(test_a_card_of_another_repository_is_judged_by_its_own_record)", FACTORY,
     "            card=issue),",
     '            card=""),'),

    ("the record is read by the bare ref, not the ticket "
     "(test_a_card_of_another_repository_is_judged_by_its_own_record)", FACTORY,
     '        card = canonical_ref(entry.get("ticket") or entry["ref"])\n',
     '        card = canonical_ref(str(entry["ref"]).rsplit("#", 1)[-1])\n'),

    ("a job's end drops another card's marks of the same number "
     "(test_the_end_of_a_card_of_another_repository_drops_only_its_own_marks)", DEFERRED,
     "                    and self._ticket_of(e) == ticket\n",
     ""),

    ("a job's end drops a queued state that is no progress mark "
     "(test_a_job_that_ends_keeps_a_queued_state_that_is_not_a_progress_mark)", MACHINE,
     "                          states=frozenset(s.value for s in PROGRESS_MARKS))",
     "                          states=None)"),

    ("the forge call runs under the queue's lock "
     "(test_the_queue_lock_is_not_held_across_the_forge_call)", DEFERRED,
     "            return call()  # the forge call, with the lock released\n",
     "            with self._held():\n                return call()\n"),

    ("a claimed entry is applied by another tracker too "
     "(test_an_entry_is_claimed_in_the_file_while_it_is_applied)", DEFERRED,
     '            if entry.get("claimed"):\n',
     "            if False:\n"),

    ("a claim its runner left holds its ticket for ever "
     "(test_a_claim_its_runner_left_is_dropped_never_applied_again)", DEFERRED,
     '                if now - float(entry.get("claimed_at") or 0) > CLAIM_EXPIRES:\n',
     "                if False:\n"),

    ("what a failed save could not write is lost at the next reload "
     "(test_an_entry_a_failed_save_could_not_write_is_kept_and_saved_again)", DEFERRED,
     "        if self._dirty:\n",
     "        if False:\n"),

    ("a rate-limited board move answers False, and the label is written instead "
     "(test_a_rate_limited_board_move_on_the_github_row_is_queued)",
     "beeverforge/adapters/tracker/github_project.py",
     "            if limited is not None:\n                raise limited\n",
     ""),
]
