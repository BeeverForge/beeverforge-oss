"""#259: a pass that runs past its time limit keeps what it wrote, and Resume continues it.

The shipped defect was a timeout read as a person's stop: the engine says `not_found` for both, so
the agent was killed, the worktree removed with nothing pushed, and the park resumed from the base.
Each row below undoes one part of what tells the two apart and keeps the work:

- the heartbeat loop that no longer asks whether the attempt timed out, or misreads the worker's
  timer, the server's NotFound, or the engine's answer;
- the activity that asks for a stop that keeps nothing;
- the stop's keeping window: a person's stop that leaves it open, a window whose commands are
  killed, a runner whose publishing check refuses the keep's own push;
- the runner that never keeps, or keeps after its worktree is gone;
- the workflow's park: not asked, with no handle, or for a heartbeat timeout too.
"""

MACHINE = "beeverforge/orchestrator/machine.py"
STOPPING = "beeverforge/adapters/sandbox/stopping.py"
ACTIVITIES = "beeverforge/runtime/temporal/activities.py"
WORKFLOW = "beeverforge/runtime/temporal/workflow.py"

TEST = "tests/test_a_timed_out_pass_keeps_its_work.py"
KEPT = TEST + "::test_a_timed_out_pass_is_ended_and_what_it_wrote_reaches_its_branch"
TIMER = KEPT + "[the_workers_timer]"
SERVER = KEPT + "[the_server_noticed_first]"
STOPPED = TEST + "::test_a_stop_the_engine_confirms_keeps_nothing"
WINDOW = TEST + "::test_a_keeping_stop_runs_the_commands_of_its_window_and_kills_the_rest"
PERSON = TEST + "::test_a_persons_stop_ends_the_keeping_and_a_plain_stop_never_opens_it"
CHECK = TEST + "::test_the_runners_publishing_check_lets_the_keeps_push_through"
PARKED = TEST + "::test_a_run_job_past_its_ceiling_parks_resumable_from_its_branch"
OTHER = TEST + "::test_any_other_failure_parks_as_it_did"
ASKED = TEST + "::test_the_workflow_parks_a_failed_run_job_through_it"
SEAM = TEST + "::test_the_failed_run_jobs_park_is_the_timed_out_attempts_or_the_failure_named"
REMOTE = TEST + "::test_a_remote_box_past_its_ceiling_parks_as_any_failure"
TOLD = TEST + "::test_a_timed_out_attempt_is_told_from_a_stop"
LOCK = TEST + "::test_a_lock_a_killed_git_left_does_not_cost_the_keep"
HELD = TEST + "::test_a_lock_a_live_process_holds_is_not_removed_and_the_card_says_so"
RM_FAILS = TEST + "::test_a_lock_that_cannot_be_removed_stops_the_keep_and_the_card_says_so"
UNCLEAN = TEST + "::test_a_kill_that_did_not_finish_clean_leaves_the_lock_and_the_card_says_so"
OUTLIVES = TEST + "::test_a_kill_whose_process_outlives_the_bound_is_not_clean"
RAN_OUT = TEST + "::test_a_kill_whose_sweeps_ran_out_is_not_clean"
ZOMBIE = TEST + "::test_a_zombie_is_not_running_and_a_live_process_is"
KILL_OVER = TEST + "::test_the_keeping_window_opens_only_once_the_kill_is_over"
PERSON_LATE = (TEST + "::test_a_person_who_stops_the_job_while_it_keeps_its_work_gets_nothing"
               "_pushed")

MUTATIONS = [
    # ── the heartbeat loop tells a timed-out attempt from a stop ─────────────────────────────
    ("THE FINDING: a timed-out attempt is read as a stop again, its work discarded", ACTIVITIES,
     "        if await _the_attempt_timed_out(details):\n"
     "            await _keep_the_work(work, stop, detail)\n"
     "        elif _the_work_must_end(details):",
     "        if _the_work_must_end(details):", KEPT),

    ("the worker's own timer (`timed_out`) is not read as a timeout", ACTIVITIES,
     '    if getattr(details, "timed_out", False):\n        return True\n', "", TIMER),

    ("a timeout the server noticed first (a plain NotFound) is read as a stop", ACTIVITIES,
     "    return await _the_workflow_runs_on()\n", "    return False\n", SERVER),

    ("a workflow a person terminated is read as one that runs on, and the stop pushes", ACTIVITIES,
     "    return described.status == WorkflowExecutionStatus.RUNNING\n",
     "    return True\n", TOLD),

    ("the activity asks for a stop that keeps nothing", ACTIVITIES,
     '    stop.request("this attempt ran past its time limit", keep=True)',
     '    stop.request("this attempt ran past its time limit")', KEPT),

    # ── the stop's keeping window ────────────────────────────────────────────────────────────
    ("a person's stop leaves the keeping open, so the push goes on after it", STOPPING,
     "                self.keep = self._keeping = False  # a person's stop closes an open "
     "window too\n",
     "                pass\n", PERSON),

    ("the keep's own commands are killed on adoption, so its commit never runs", STOPPING,
     "            if not self._event.is_set() or self._keeping:\n",
     "            if not self._event.is_set():\n", KEPT),

    ("FOUND ON MAIN'S CI: the window opens while the kill still sweeps, and the keep's own commit "
     "is killed", STOPPING,
     "        with self._killing, self._lock:\n            self._keeping = self.keep",
     "        with self._lock:\n            self._keeping = self.keep", KILL_OVER),

    ("the kill does not hold its lock, so the window does not wait for it", STOPPING,
     "        with self._killing:\n            with self._lock:\n",
     "        if True:\n            with self._lock:\n", KILL_OVER),

    ("the window opens for a stop that keeps nothing", STOPPING,
     "            self._keeping = self.keep\n", "            self._keeping = True\n", PERSON),

    # RE-PINNED 2026-11-09 (review of #503)
    ("the runner's publishing check refuses the keep's own push", MACHINE,
     "        if stop is not None and not stop.still_keeping() and stop.confirm():",
     "        if stop is not None and stop.confirm():", CHECK),

    ("THE REVIEW'S FINDING: the window never asks the engine, so a person's stop during the keep "
     "is not heard and the push goes through", STOPPING,
     "        why = ask() if ask is not None else None\n        if why:\n"
     "            self.request(why)\n        return self._keeping\n",
     "        return self._keeping\n", PERSON_LATE),

    # ── the runner keeps before its worktree goes ────────────────────────────────────────────
    ("FOUND ON MAIN'S CI: a lock a killed git left stops the keep's commit", MACHINE,
     "                said = self._clear_the_lock_a_killed_git_left(ws)\n",
     "                said = None\n", LOCK),

    # ── review of #504: the lock is cleared only when its owner is proven gone ─────────────────
    ("a kill whose last sweep found nothing is clean whether or not what it killed has ended",
     STOPPING, "            return _all_gone(killed)\n", "            return True\n", OUTLIVES),

    ("a kill whose sweeps ran out still finding processes is called clean", STOPPING,
     "                \"processes of the job; what started after the last sweep was not killed\", "
     "_SWEEPS)\n    return False\n",
     "                \"processes of the job; what started after the last sweep was not killed\", "
     "_SWEEPS)\n    return True\n", RAN_OUT),

    ("the stop calls every kill clean", STOPPING,
     "            self.kill_clean = marked and _groups_gone(groups)\n",
     "            self.kill_clean = True\n", UNCLEAN),

    ("a zombie is read as running, so no kill of an unreaped child is ever clean", STOPPING,
     '    return state not in ("Z", "X")\n', "    return True\n", ZOMBIE),

    ("a zombie in a killed group is read as running", STOPPING,
     '        if len(fields) > 2 and fields[2] == str(pgid) and fields[0] not in ("Z", "X"):',
     "        if len(fields) > 2 and fields[2] == str(pgid):", ZOMBIE),

    ("THE REVIEW'S FINDING: the keep clears the lock after a kill that did not finish clean",
     MACHINE, "        if stop is None or not stop.kill_clean:\n",
     "        if stop is None:\n", UNCLEAN),

    ("the keep clears a lock a live process holds open", MACHINE,
     "        if held:\n", "        if False:\n", HELD),

    ("the holder scan never matches the lock", STOPPING,
     "                if os.readlink(fd) == want:\n", "                if False:\n", HELD),

    ("a failed rm is ignored and the keep commits over the lock", MACHINE,
     "        if rc != 0:\n            return _lock_kept_said(here, f\"it could not be removed",
     "        if False:\n            return _lock_kept_said(here, f\"it could not be removed",
     RM_FAILS),

    ("a lock not shown stale is committed over anyway", MACHINE,
     "                if said is not None:\n", "                if False:\n", HELD),

    ("the card is not told why the work was not kept", MACHINE,
     "                    self._say_on_ticket(ticket.id, said)\n                    return\n",
     "                    return\n", RM_FAILS),

    ("the runner never keeps what the timed-out pass wrote", MACHINE,
     "            self._keep_what_the_attempt_wrote(ticket, ws)\n"
     "            self.sandbox.cleanup(workspace=ws)",
     "            self.sandbox.cleanup(workspace=ws)", KEPT),

    ("the runner keeps after its worktree is gone", MACHINE,
     "            self._keep_what_the_attempt_wrote(ticket, ws)\n"
     "            self.sandbox.cleanup(workspace=ws)",
     "            self.sandbox.cleanup(workspace=ws)\n"
     "            self._keep_what_the_attempt_wrote(ticket, ws)", KEPT),

    # ── the workflow parks it resumable from its branch ──────────────────────────────────────
    # RE-PINNED 2026-11-09 (review of #503)
    ("the handler around run_job no longer parks through the seam", WORKFLOW,
     "                result = _the_park_of_a_failed_run_job(exc, params)\n",
     "                result = RunResult(ticket_id=params.issue, state=JobState.ON_HOLD,\n"
     "                                   note=f\"job errored after retries: {exc}\")\n", ASKED),

    ("a failed run_job no longer asks whether it ran past its limit", WORKFLOW,
     "    return _an_attempt_past_its_limit(exc, params) or RunResult(",
     "    return RunResult(", SEAM),

    ("a remote box's timeout is parked as work kept on a branch it never pushed", WORKFLOW,
     "    if params.traits().remote:\n        return None\n", "", REMOTE),

    ("the park carries no handle, so Resume starts from the base again", WORKFLOW,
     "        resume_handle=FROM_THE_FORGE,\n    )\n", "    )\n", PARKED),

    ("a heartbeat timeout (a dead worker, nothing kept) is parked as kept work", WORKFLOW,
     "    if not isinstance(cause, TimedOut) or cause.type != TimeoutType.START_TO_CLOSE:",
     "    if not isinstance(cause, TimedOut):", OTHER),
]
