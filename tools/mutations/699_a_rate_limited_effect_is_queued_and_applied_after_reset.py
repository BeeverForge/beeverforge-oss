"""#699: a tracker write that fails on a rate limit is queued, shared by the project's runners, and
drained when a job starts and ends.

One cut per guard: the reload under the lock (two trackers on one path), the lock itself, the
build_runner wiring, and the drain at the job's two ends. Each is killed by a named test.
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
     "        self._drain_queued_effects()\n        try:\n            return self._run_ticket(",
     "        try:\n            return self._run_ticket("),
]
