"""The unit tests that stopped waiting out real deadlines still catch what they caught (#362).

#362 shortened, from the test side, the deadlines, walls, drains, lock waits and holds that the
twenty slowest-waiting unit test files sat out: a read that hangs is released when its case is done
with it, a holder process lets go when told, and every bound that is a number was made a few times
the work it bounds. A shorter bound can stop biting — a window shorter than the defect needs to
show, a wall that fires before the line it keeps was written. So each changed test has a row here
that takes away the deadline it guards, or, where the test guards something the deadline only
frames, the thing it guards, and runs THAT test alone. Every row must be red.

Run:  .venv/bin/python tools/mutate.py tools/mutations/362_shorter_bounds_still_bite.py

Two rows are slow on purpose: a cache that waits for its key for ever is only ended by the case's
own 120 s bound, which is the case saying so.
"""

TEST = "tests/test_the_budget_read_leaves_the_panels_loop.py"

BUDGET = "tests/test_the_budget_read_leaves_the_panels_loop.py"
READY = "tests/test_a_running_deployment_says_whether_it_is_alive_and_ready.py"
BOX = "tests/test_the_box_transmits_while_it_runs.py"
SEMAPHORE = "tests/test_the_semaphore_on_work.py"
CHECKOUT = "tests/test_two_processes_never_change_one_checkout_at_once.py"
WATCHED = "tests/test_the_harness_is_watched_while_it_runs.py"
LOGS = "tests/test_the_logs_can_be_json_lines_that_say_the_project.py"
WORKER = "tests/test_the_worker_waits_for_the_engine_to_listen.py"
PUSH = "tests/test_every_push_to_a_context_repository_holds_the_products_semaphore.py"
KIMI = "tests/test_a_kimi_planner_that_writes_holds_the_job_before_its_edit_reaches_a_commit.py"
HARNESS = "tests/test_agent_harness.py"

READING = "beeverforge/floor/reading.py"
HEALTH = "beeverforge/observability/health.py"
SANDBOX = "beeverforge/adapters/sandbox/base.py"
PRODUCT_SEMAPHORE = "beeverforge/product/semaphore.py"
CACHE = "beeverforge/runtime/repo_cache.py"
CONNECTION = "beeverforge/runtime/temporal/connection.py"
PIPELINE = "beeverforge/knowledge/pipeline.py"
MACHINE = "beeverforge/orchestrator/machine.py"

MUTATIONS = [
    # ── the budget read: a hang released by the case, a deadline of 0.3 s, a 0.25 s window ──
    ("the budget read's wait is unbounded", READING,
     "_budget_read.shared(lambda flight: _read_budget(flight, stamp)), budget_deadline())",
     "_budget_read.shared(lambda flight: _read_budget(flight, stamp)), None)",
     BUDGET + "::test_a_read_that_HANGS_degrades_to_unread_inside_the_declared_deadline"),
    ("the budget deadline is not the deployment's to set", READING,
     '        wanted = float(os.environ.get("BEEVERFORGE_BUDGET_DEADLINE", "") or 5.0)',
     "        wanted = 5.0",
     BUDGET + "::test_the_deadline_is_the_DEPLOYMENTS_to_set"),
    ("a budget read that ran out of time is thrown away with its wait", READING,
     "            _budget_read.shared(lambda flight: _read_budget(flight, stamp)), "
     "budget_deadline())",
     "            _read_budget(_Flight(loop=asyncio.get_running_loop()), stamp), "
     "budget_deadline())",
     BUDGET + "::test_a_read_that_ran_out_of_time_STILL_FILLS_the_window_when_it_lands"),
    ("a budget read that lost its slot fills the window anyway", READING,
     '    if got.get("state") != "unread" and _budget_read.holds(flight):',
     '    if got.get("state") != "unread":',
     BUDGET + "::test_a_read_DETACHED_while_it_was_in_flight_does_not_fill_the_window"),

    # ── readiness: a hung check's deadline of 0.2 s, the probe's own wait of 0.3 s ──────────
    ("a check that hangs holds readiness's answer", HEALTH,
     "        _when, said, cause = await asyncio.wait_for(_SLOTS[name].kept_or_asked(name), bound)",
     "        _when, said, cause = await _SLOTS[name].kept_or_asked(name)",
     READY + "::test_a_check_that_hangs_is_named_within_the_deadline"),
    ("a check that hangs holds every /readyz behind it", HEALTH,
     "        _when, said, cause = await asyncio.wait_for(_SLOTS[name].kept_or_asked(name), bound)",
     "        _when, said, cause = await _SLOTS[name].kept_or_asked(name)",
     READY + "::test_a_hung_check_starves_no_request_and_blames_no_other_check"),
    ("each poll that gives up asks the hung dependency again", HEALTH,
     "        return await self.read.shared(lambda flight: self._ask(name, flight))",
     "        return await self._ask(name, None)",
     READY + "::test_polls_that_give_up_on_a_hung_check_share_its_one_question"),
    ("a hung check is logged on every poll that gives up", HEALTH,
     "    elif not ok and before is not False:", "    elif not ok:",
     READY + "::test_a_check_that_hangs_is_said_once_however_many_polls_give_up"),
    ("the probe waits for its answer for ever", HEALTH,
     "timeout=probe_timeout() if timeout is None else timeout)",
     "timeout=None)",
     READY + "::test_the_probe_gives_up_on_a_listener_that_never_answers"),

    # ── the box's wall: 0.5 s and 0.2 s walls, 0.2 s and 0.5 s drains ───────────────────────
    ("the worktree box drops what a walled command had written", SANDBOX,
     "    return timeout_result(command, timeout, captured) if walled else",
     "    return timeout_result(command, timeout) if walled else",
     BOX + "::test_the_worktree_wall_keeps_the_partial_output"),
    ("the container box drops what a walled command had written", SANDBOX,
     "    return timeout_result(command, timeout, captured) if walled else",
     "    return timeout_result(command, timeout) if walled else",
     BOX + "::test_the_container_wall_keeps_the_partial_output_too"),
    ("a walled command's orphan writes into the next command", SANDBOX,
     "            if run != self._run:\n                return False\n",
     "",
     BOX + "::test_a_walled_command_s_late_output_cannot_land_in_the_next_command"),
    ("a walled run waits for the orphan that holds its pipe", SANDBOX,
     "        thread.join(timeout=_DRAIN_SECONDS)",
     "        thread.join()",
     BOX + "::test_a_walled_run_returns_within_its_own_bound"),
    ("a walled run is an exception again, not an exit", SANDBOX,
     "            proc.wait(timeout=timeout)\n        except subprocess.TimeoutExpired:",
     "            proc.wait(timeout=timeout)\n        except ArithmeticError:",
     HARNESS + "::test_a_timeout_becomes_a_non_zero_exit_not_an_exception"),

    # ── the harness is read while it runs: a fake harness the case moves on ─────────────────
    ("the box's output is read only once the process has ended", SANDBOX,
     '        for line in iter(proc.stdout.readline, ""):',
     "        for line in proc.stdout.read().splitlines(keepends=True):",
     WATCHED + "::test_a_real_box_running_a_real_harness_is_read_while_it_runs"),

    # ── the product's semaphore: a holder that lets go when told, a 0.25 s rendezvous ───────
    *[("every write of the product proceeds without the semaphore", PRODUCT_SEMAPHORE,
       '    lock = FileLock(_dir(key) / "semaphore.lock")',
       '    lock = __import__("types").SimpleNamespace(acquire=lambda **_: None, '
       'release=lambda: None)',
       SEMAPHORE + "::" + case)
      for case in ("test_a_semaphore_held_by_another_process_times_out_in_words",
                   "test_a_write_that_cannot_have_the_semaphore_tells_the_person_and_writes_nothing",
                   "test_two_proposals_at_once_never_mint_one_number",
                   "test_two_registry_projects_of_one_product_share_one_semaphore",
                   "test_a_requirement_asked_twice_at_once_is_written_once_and_the_second_is_told",
                   "test_two_decisions_saved_at_once_both_land")],

    # ── one checkout at a time: a 0.6 s window for the second process, a 0.2 s lock wait ────
    *[("the key's lock is held per process", CACHE,
       '    return FileLock(Path(root) / _LOCKS_DIRNAME / f"{key}.lock")',
       '    return FileLock(Path(root) / _LOCKS_DIRNAME / f"{key}.{os.getpid()}.lock")',
       CHECKOUT + f"::test_TODAYS_RUN_a_second_process_waits_for_the_key_the_first_is_changing"
                  f"[{cache}]")
      for cache in ("RepoCache", "SparseRepoCache")],
    ("the plain cache waits for its key for ever (ended by the case's 120 s bound)", CACHE,
     "            with _key_lock(self.root, project).held(timeout=_LOCK_WAIT_SECONDS):\n"
     "                try:\n                    return self._sync(",
     "            with _key_lock(self.root, project).held(timeout=10 ** 9):\n"
     "                try:\n                    return self._sync(",
     CHECKOUT + "::test_a_sync_that_cannot_have_the_key_in_time_degrades[RepoCache]"),

    # ── the engine's door: a 0.15 s attempt, a 0.01 s wait on a port nobody listens on ──────
    ("the held client and the flight are read and written without their lock", CONNECTION,
     "_HOLDING = threading.Lock()",
     "_HOLDING = __import__('contextlib').nullcontext()",
     LOGS + "::test_callers_who_arrive_at_the_same_instant_on_many_threads_make_one_attempt"),

    # ── the worker's wait for its engine: every number a third or less of what it was ───────
    ("the worker dials at once, before anything listens", CONNECTION,
     "    while not await _listening(host, port):", "    while False:",
     WORKER + "::test_a_listener_that_starts_LATE_is_waited_for_and_dialled_once"),
    ("the wait for an engine that never listens has no bound", CONNECTION,
     "        if time.monotonic() >= deadline:", "        if False:",
     WORKER + "::test_an_engine_that_NEVER_listens_is_a_bounded_wait_and_a_sentence"),
    ("the birth connect is given a read's deadline, not the start-up wait", CONNECTION,
     "    within = max(deadline - time.monotonic(), read_deadline())\n",
     "    within = read_deadline()\n",
     WORKER + "::test_an_engine_that_takes_the_socket_and_never_answers_is_given_the_start_up_wait"),
    ("the probe blocks the loop, so the wait cannot be cancelled", CONNECTION,
     "        await asyncio.sleep(every)\n    # ITS OWN WAIT IS THE CONNECT'S BOUND",
     "        time.sleep(every * 8)\n    # ITS OWN WAIT IS THE CONNECT'S BOUND",
     WORKER + "::test_the_wait_ends_when_it_is_cancelled"),
    ("the start-up wait is not the deployment's to set", CONNECTION,
     '        wanted = float(os.environ.get(_STARTS_IN_VAR, "") or _STARTS_IN_S)',
     "        wanted = _STARTS_IN_S",
     WORKER + "::test_a_worker_with_no_engine_to_reach_ends_in_a_SENTENCE_not_a_traceback"),

    # ── a publish holds the semaphore: a 1.2 s window, a 0.2 s semaphore wait ───────────────
    *[("a publish of derived knowledge takes no semaphore", PIPELINE,
       "        with semaphore.held(project, timeout=timeout):\n            return _publish_dir(",
       "        with open(os.devnull):\n            return _publish_dir(",
       PUSH + "::" + case)
      for case in ("test_TODAYS_RUN_three_members_publishing_at_once_all_land",
                   "test_a_publish_never_lands_between_a_persons_clone_and_their_push")],
    ("a publish that could not have the semaphore in time reads as a failed push", PIPELINE,
     "        return BUSY\n", "        return FAILED\n",
     PUSH + "::test_a_publish_that_cannot_have_the_semaphore_in_time_is_busy"),

    # ── a walled kimi planner: a 0.5 s wall, the orphan at 1 s, 2 s to outlast it ───────────
    ("a walled planner's job goes on to the executor", MACHINE,
     "                if before is not None and plan_result.walled:\n",
     "                if False:\n",
     KIMI + "::test_a_kimi_planner_that_outlives_its_timeout_and_writes_later_reaches_no_commit"),
]
