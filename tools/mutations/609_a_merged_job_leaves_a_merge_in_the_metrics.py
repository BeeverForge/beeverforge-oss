"""A merged job leaves a merge in the metrics (#609). The claims:

  · THE ENDING ROW is written once per job, state and pull request, marked `extra.ending`, with the
    state, the pull request and the platform stamp, and is never raised;
  · BOTH DRIVERS write it: the workflow's `record_outcome` (with the pull request the workflow
    passes in) and the attended driver;
  · THE DOOR records the job's telling of a merge on a card the forge already closed — only that
    telling, only with a pull request, writing nothing to the card — and refuses the box's and the
    settle's `merged` there;
  · A PARKED JOB (`on_hold`, `paused`) writes no ending: it has not ended;
  · THE READERS that took every `job` row for an attempt skip the ending.
"""

TEST = "tests/test_a_merged_job_leaves_a_merge_in_the_metrics.py"
JOB_RECORD = "beeverforge/observability/job_record.py"
CARD = "beeverforge/lifecycle/card.py"
ACTIVITIES = "beeverforge/runtime/temporal/activities.py"
WORKFLOW = "beeverforge/runtime/temporal/workflow.py"
CLI = "beeverforge/cli.py"

MUTATIONS = [
    ("the ending row is not marked", JOB_RECORD,
     'extra={"platform": platform_stamp(), "ending": True})',
     'extra={"platform": platform_stamp()})'),
    ("the ending row carries no pull request", JOB_RECORD,
     'role="_job_", state=state, pr_url=pr_url or "",', 'role="_job_", state=state,'),
    ("the ending row is written again on a replay", JOB_RECORD,
     "        if not isinstance(sink, KeyedSink):\n", "        if True:\n"),
    ("the ending's key ignores its state", JOB_RECORD,
     'hashlib.sha256(f"{state}\\n{pr_url or \'\'}".encode())',
     'hashlib.sha256(f"{pr_url or \'\'}".encode())'),
    ("a failed write of the ending raises", JOB_RECORD,
     '    except Exception as exc:\n'
     '        log.info("the ending of',
     '    except KeyError as exc:\n'
     '        log.info("the ending of'),
    ("the workflow's exit writes no ending", ACTIVITIES,
     "    await asyncio.to_thread(_the_row)     # never raises: telemetry is additive\n", ""),
    ("the workflow's exit does not hand the pull request on", WORKFLOW,
     '                          note=(note or "")[:400], pr_url=pr_url),', 
     '                          note=(note or "")[:400]),'),
    ("the attended driver writes no ending", CLI,
     '    record_job_ending(project=view.name, issue=str(issue), state=state, '
     'pr_url=result.pr_url or "")\n', ""),
    ("the door refuses a merge the forge's close came before", CARD,
     "        if late:\n            # THE FORGE CLOSED", "        if False:\n            # THE FORGE CLOSED"),
    ("the door takes any merge on a closed card, not the job's telling", CARD,
     '                and "stages_follow" in (facts or {}) and bool((facts or {}).get("pr_url")))\n',
     "                )\n"),
    ("the late merge is not marked as late", CARD,
     '        if late:\n            known["late"] = True\n', ""),
    ("the door takes a telling with no pull request on a closed card", CARD,
     'and "stages_follow" in (facts or {}) and bool((facts or {}).get("pr_url")))\n',
     'and "stages_follow" in (facts or {}))\n'),
    ("a parked job writes an ending", JOB_RECORD,
     "    if state in PARKED:\n        return False\n", ""),
    ("the versions seen count the ending as an attempt", "beeverforge/observability/query.py",
     "            if extra.get(\"ending\"):\n", "            if False:\n",
     "tests/test_the_outcomes_are_read_never_inferred.py"),
    ("the dashboard takes the ending for the job's attempt", "beeverforge/api/metrics_view.py",
     '            if r.get("kind") == "job" and not (r.get("extra") or {}).get("ending")}',
     '            if r.get("kind") == "job"}'),
]
