"""#44: a stopped job ends its agent and publishes nothing after the stop.

The shipped defect was a stop that reached the workflow and not the work: the runner thread went on
through its agent pass and published. Each row below undoes one part of what makes the stop reach
the work:

- every check before a step that reaches the forge or the board, dropped one at a time, each run
  against the case where the stop arrives during the step before it;
- the process-group kill skipped (a no-op, the leader only, the box in the worker's own group, the
  activity that never tells the runner, a command started after the stop left running);
- the worktree's cleanup skipped;
- a timeout read as a stop (#259 keeps those apart), and a silent worker said to be heard.
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
    ("the stop kills nothing", STOPPING,
     "        os.killpg(pgid, signal.SIGKILL)\n",
     "        pass\n", MID_AGENT),

    ("the stop kills the shell it started and leaves what the harness spawned running", STOPPING,
     "        os.killpg(pgid, signal.SIGKILL)\n",
     "        os.kill(pgid, signal.SIGKILL)\n", MID_AGENT),

    ("a job's box starts its commands in the worker's own group, where no stop reaches them",
     STOPPING,
     '    return {"process_group": 0} if stop is not None else {}',
     "    return {}", MID_AGENT),

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
    ("a stopped job leaves its worktree behind", MACHINE,
     "            return self._charged(result)\n        finally:\n"
     "            self.sandbox.cleanup(workspace=ws)\n",
     "            return self._charged(result)\n        finally:\n"
     "            pass\n", MID_AGENT),

    # ── a stop is not a timeout, and the sentence claims no more than is known ──
    ("a heartbeat timeout is read as a person's stop (#259 keeps them apart)", ACTIVITIES,
     '_THE_WORK_ENDS = ("not_found", "cancel_requested", "worker_shutdown")',
     '_THE_WORK_ENDS = ("not_found", "cancel_requested", "worker_shutdown", "timed_out")', TEST),

    ("a worker silent past its heartbeat window is said to be heard", CATALOG,
     "    if beat is not None and (now - beat).total_seconds() <= _HEARD_WITHIN_SECONDS:",
     "    if beat is not None:", WEDGED),
]
