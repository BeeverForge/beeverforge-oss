"""#44: a stopped job ends its agent and publishes nothing after the stop.

The shipped defect was a stop that reached the workflow and not the work: the runner thread went on
through its agent pass and published. Each row below undoes one part of what makes the stop reach
the work:

- every check before a step that reaches the forge or the board, dropped one at a time, each run
  against the case where the stop arrives during the step before it;
- the process-group kill skipped (a no-op, the leader only, the box in the worker's own group, the
  activity that never tells the runner, a command started after the stop left running);
- the worktree's cleanup skipped;
- a timeout read as a stop (#259 keeps those apart), and a silent worker said to be heard;
- (review of #453) a group let go of when its leader returns, the mark dropped from the kill or
  from the box's environment, an emptied group never let go of; the runner that no longer asks
  the engine, or an engine answer misread; the job's `TMPDIR` dropped, made late or left behind.
"""

MACHINE = "beeverforge/orchestrator/machine.py"
STOPPING = "beeverforge/adapters/sandbox/stopping.py"
ACTIVITIES = "beeverforge/runtime/temporal/activities.py"
CONTAINER = "beeverforge/adapters/sandbox/container.py"
CATALOG = "beeverforge/actions/catalog.py"

TEST = "tests/test_a_stopped_job_ends_its_agent_and_publishes_nothing.py"
_STEP = TEST + "::test_a_stop_arriving_during_a_step_skips_the_next"
MID_AGENT = TEST + "::test_a_job_stopped_mid_agent_pass_never_reaches_publish"
WEDGED = "tests/test_a_wedged_job_has_an_exit.py"
WORKTREE = "beeverforge/adapters/sandbox/worktree.py"
LEFT = TEST + "::test_a_stop_kills_what_a_returned_command_left_running"
EMPTIED = TEST + "::test_a_group_is_let_go_of_once_it_is_empty_and_never_signalled_after"
LANDED = TEST + "::test_what_landed_before_the_stop_is_said_and_nothing_after_it_runs"
NO_BYPASS = TEST + "::test_a_stop_before_anything_landed_says_nothing_of_a_landing"
UNHEARD = TEST + "::test_a_stop_the_heartbeat_has_not_heard_yet_publishes_nothing"
ASKED = TEST + "::test_the_runner_asks_the_engine_through_the_heartbeat_loop"
TMP = TEST + "::test_a_jobs_temporary_files_go_with_its_worktree"


def _case(name: str) -> str:
    return f"{_STEP}[{name}]"


MUTATIONS = [
    # ── the stop check before each publishing step ──
    ("the branch is pushed after a stop that arrived during the review", MACHINE,
     'self._unless_stopped("publish_branch")', "pass", _case("the_review")),

    ("the pull request is opened after a stop that arrived during the push", MACHINE,
     'self._unless_stopped("open_pr")', "pass", _case("publish_branch")),

    ("the review is posted after a stop that arrived while the pull request opened", MACHINE,
     'self._unless_stopped("review_pr")', "pass", _case("open_pr")),

    ("the pull request is merged after a stop that arrived while its review was posted", MACHINE,
     'self._unless_stopped("merge_pr")', "pass", _case("review_pr_auto")),

    ("reviewers are requested after a stop that arrived while the review was posted", MACHINE,
     'self._unless_stopped("request_reviewers")', "pass", _case("review_pr_human")),

    ("the ticket is told the pull request is ready after a stop", MACHINE,
     'self._unless_stopped("say_on_ticket")', "pass", _case("request_reviewers")),

    ("the card is moved and its outcome handed back after a stop", MACHINE,
     'self._unless_stopped(f"set_state {state.value}")', "pass", _case("the_ready_comment")),

    ("the decision's options are commented on the ticket after a stop", MACHINE,
     'self._unless_stopped("record_decision")', "pass", _case("a_decision")),

    ("an unfinished pass's work is pushed for its hold after a stop", MACHINE,
     'self._unless_stopped("publish_branch for a hold")', "pass", _case("the_preserve_for_hold")),

    ("a paused pass's work is pushed after a stop", MACHINE,
     'self._unless_stopped("publish_branch for a pause")', "pass", _case("a_rate_limit_pause")),

    ("a rebased change is pushed again after a stop", MACHINE,
     'self._unless_stopped("publish_branch after a rebase")', "pass",
     _case("the_revalidation_after_a_rebase")),

    # ── the process-group kill ──
    # RE-PINNED (review of #453): the mid-agent `sleep` carries the job's mark, so the mark's kill
    # alone ends it; the group's kill is what reaches the unmarked child in LEFT
    ("the stop kills no group", STOPPING,
     "        os.killpg(pgid, signal.SIGKILL)\n",
     "        pass\n", LEFT),

    ("the stop kills the shell it started and leaves what the harness spawned running", STOPPING,
     "        os.killpg(pgid, signal.SIGKILL)\n",
     "        os.kill(pgid, signal.SIGKILL)\n", LEFT),

    # RE-PINNED (review of #453): the mid-agent `sleep` is reached by its mark wherever its group is
    ("a job's box starts its commands in the worker's own group, where no stop reaches them",
     STOPPING,
     '    return {"process_group": 0} if stop is not None else {}',
     "    return {}", LEFT),

    ("the container box starts a job's `docker exec` in the worker's own group", CONTAINER,
     "                **own_group(stop),\n", "", TEST),

    ("a command started after the stop is adopted and left running", STOPPING,
     "                return\n        _kill_group(proc.pid)\n",
     "                return\n", TEST),

    ("the activity hears the stop and never tells the runner", ACTIVITIES,
     "    stop.request(why)\n", "    pass\n", MID_AGENT),

    ("`run_job` gives its runner no stop to hear", ACTIVITIES,
     "    if stop is not None:\n        runner.hears(stop)\n",
     "    if stop is not None:\n        pass\n", TEST),

    # ── the cleanup ──
    # RE-PINNED 2026-11-09 (#259): a timed-out attempt keeps its work first, in the same places
    ("a stopped job leaves its worktree behind", MACHINE,
     "            self._keep_what_the_attempt_wrote(ticket, ws)\n"
     "            self.sandbox.cleanup(workspace=ws)\n",
     "            self._keep_what_the_attempt_wrote(ticket, ws)\n"
     "            pass\n", MID_AGENT),

    # ── a stop is not a timeout, and the sentence claims no more than is known ──
    ("a heartbeat timeout is read as a person's stop (#259 keeps them apart)", ACTIVITIES,
     '_THE_WORK_ENDS = ("not_found", "cancel_requested", "worker_shutdown")',
     '_THE_WORK_ENDS = ("not_found", "cancel_requested", "worker_shutdown", "timed_out")', TEST),

    ("a worker silent past its heartbeat window is said to be heard", CATALOG,
     "    if beat is not None and (now - beat).total_seconds() <= _HEARD_WITHIN_SECONDS:",
     "    if beat is not None:", WEDGED),

    # ── what a returned command left behind (review of #453) ──
    ("a group is let go of as soon as its leader returns", STOPPING,
     "            if _group_is_empty(proc.pid):\n                self._groups.discard(proc.pid)\n",
     "            self._groups.discard(proc.pid)\n", LEFT),

    # RE-PINNED 2026-11-09 (#259 follow-up): the kill runs under the stop's `_killing` lock
    ("the stop does not kill what carries the job's mark", STOPPING,
     "                _kill_group(pgid)\n            marked = _kill_marked(",
     "                _kill_group(pgid)\n            marked = (lambda _n: True)(", LEFT),

    ("a job's box does not mark its commands", WORKTREE,
     "            env.update(stop.env(), TMPDIR=str(tmp))\n",
     "            env.update(TMPDIR=str(tmp))\n", LEFT),

    ("an emptied group is never let go of", STOPPING,
     "        self._groups = {g for g in self._groups if not _group_is_empty(g)}\n",
     "        pass\n", EMPTIED),

    # ── a stop the heartbeat has not heard yet (review of #453) ──
    # RE-PINNED 2026-11-09 (#259): a timed-out attempt keeps its work first, in the same places
    ("the runner asks only the heartbeat's flag, never the engine", MACHINE,
     "        if stop is not None and not stop.still_keeping() and stop.confirm():\n",
     "        if stop is not None and not stop.still_keeping() and stop.requested:\n", UNHEARD),

    ("the heartbeat loop gives the runner nothing to ask the engine with", ACTIVITIES,
     "        stop.ask = _the_engine_asked(asyncio.get_running_loop())\n",
     "        pass\n", ASKED),

    ("a workflow the engine no longer has is read as running", ACTIVITIES,
     '                return "its workflow is no longer in the engine (a stop)"\n',
     "                return None\n", ASKED),

    ("a running workflow is read as stopped", ACTIVITIES,
     "        if described.status == WorkflowExecutionStatus.RUNNING:\n            return None\n",
     "", ASKED),

    ("an engine that cannot be reached is read as a stop", ACTIVITIES,
     "            return _unasked(info.workflow_id, exc)\n        except Exception",
     '            return "unreachable"\n        except Exception', ASKED),

    # ── the job's temporary files (review of #453) ──
    ("a job's commands get no TMPDIR of their own", WORKTREE,
     "            env.update(stop.env(), TMPDIR=str(tmp))\n",
     "            env.update(stop.env())\n", TMP),

    ("the job's TMPDIR is not made before its first command", WORKTREE,
     "            tmp.mkdir(parents=True, exist_ok=True)\n",
     "", TMP),

    ("`cleanup` leaves the job's TMPDIR behind", WORKTREE,
     "        shutil.rmtree(job_tmpdir(workspace), ignore_errors=True)\n",
     "", TMP),

    # ── what landed on the forge before the stop reached the job (review of #453, option A) ──
    ("a stop after the pull request opened or the merge landed says nothing of it", MACHINE,
     "            if landed is not None:\n                self._say_what_landed(*landed)\n",
     "            pass\n", LANDED),

    ("what landed is said on the ticket and not journalled", MACHINE,
     '        self._emit(ticket, "note", f"stopped after the forge took it: {body}", url=pr, '
     "landed=kind)\n", "", LANDED),

    ("what landed is journalled and not said on the ticket", MACHINE,
     "        try:\n            self.tracker.comment(ticket.id, body)\n"
     "        except Exception as exc:  # noqa: BLE001 — the stop stands",
     "        try:\n            pass\n"
     "        except Exception as exc:  # noqa: BLE001 — the stop stands", LANDED),

    ("the opened pull request is not recorded as landed", MACHINE,
     '            self._landed(ticket, "opened", pr=pr, base=base)\n', "", _case("open_pr")),

    ("a merge is said to be merged when it was only armed", MACHINE,
     '        self._landed(ticket, "merged" if merged else "armed", pr=pr, base=base)\n',
     '        self._landed(ticket, "merged", pr=pr, base=base)\n', LANDED),

    ("the general comment goes through after a stop (the bypass widened)", MACHINE,
     '        self._unless_stopped("say_on_ticket")  # outside the `try`: a stop is not a lost '
     "comment\n", "", NO_BYPASS),

    # ── the "opened" sentence says what else reached the pull request (re-review of #453) ──
    ("a review posted before the stop is said not to have been", MACHINE,
     '                self._landed_also("reviewed")\n', "", _case("review_pr_auto")),

    ("reviewers asked before the stop are said not to have been", MACHINE,
     '                self._landed_also("asked")\n', "", _case("request_reviewers")),
]
