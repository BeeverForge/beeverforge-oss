"""#699: a tracker write that fails on a rate limit is queued, shared by the project's runners, and
drained when a job starts and ends.

One cut per guard: the reload under the lock (two trackers on one path), the lock itself, the
build_runner wiring, and the drain at the job's two ends; then one cut per rule of the queue in
deferred.py: newest entry wins, a write joins behind waiting entries, an entry leaves the file
before it is applied, a rate-limited apply is re-queued, and any other failure is dropped. Each is
killed by a named test.
"""

TEST = "tests/test_a_rate_limited_effect_is_queued_and_applied_after_reset.py"
DEFERRED = "beeverforge/adapters/tracker/deferred.py"
FACTORY = "beeverforge/factory.py"
MACHINE = "beeverforge/orchestrator/machine.py"

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
     "        tracker=DeferringTracker(\n            build_tracker(",
     "        tracker=(lambda inner, path: inner)(\n            build_tracker("),

    ("build_runner gives each runner its own queue file, so a finished job's queue is never "
     "drained (test_a_later_runner_drains_what_a_finished_job_left_when_it_starts)", FACTORY,
     'project_log_dir(project) / "queued-tracker-effects.json"',
     'project_log_dir(project) / f"queued-tracker-effects-{issue.strip(chr(35))}.json"'),

    ("a job does not drain the queue when it ends "
     "(test_a_runner_from_build_runner_queues_and_drains_when_its_job_ends)", MACHINE,
     "        finally:\n            self._drain_queued_effects()\n",
     "        finally:\n            pass\n"),

    ("a job does not drain the queue when it starts "
     "(test_a_later_runner_drains_what_a_finished_job_left_when_it_starts)", MACHINE,
     "        self._drain_queued_effects()\n        try:\n"
     "            return run(self, *args, **kwargs)",
     "        try:\n            return run(self, *args, **kwargs)"),

    # -- the rules of the queue --
    ("a later write for the same key does not replace the earlier entry, so every state is "
     "applied (test_only_the_newest_state_per_ticket_is_applied)", DEFERRED,
     '        self._queue = [e for e in self._queue if e["key"] != list(key)]\n',
     ""),

    ("a write for a ticket with entries waiting goes straight to the forge and overtakes them "
     "(test_a_write_for_a_ticket_with_entries_waiting_joins_behind_them)", DEFERRED,
     '            if any(e["ref"] == key[1] for e in self._queue):\n',
     "            if False:\n"),

    ("an entry stays in the file while it is applied, so a restart applies it again "
     "(test_the_queue_survives_a_restart)", DEFERRED,
     "                entry = self._queue.pop(0)\n                self._save()\n",
     "                entry = self._queue.pop(0)\n"),

    ("an apply that is still rate-limited is dropped, not re-queued "
     "(test_still_limited_after_the_reset_keeps_the_entry_for_the_next_reset)", DEFERRED,
     '                    entry["reset_at"] = exc.reset_at\n'
     "                    self._queue.insert(0, entry)\n",
     ""),

    ("an apply that fails for another reason is kept at the head and blocks the queue "
     "(test_an_entry_that_fails_for_another_reason_is_dropped_and_the_next_applied)", DEFERRED,
     "                    continue\n",
     "                    self._queue.insert(0, entry)\n                    self._save()\n"
     "                    return\n"),
]
