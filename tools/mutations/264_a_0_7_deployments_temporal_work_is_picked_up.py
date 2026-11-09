"""#264 (GitHub, BeeverForge/beeverforge-oss): an OpenFactory 0.7 deployment's Temporal work is
picked up.

Each row takes one piece away: the worker on 0.7's task queue, what that worker is built with, the
rule that nothing starts work there, or the retirement of 0.7's schedules — which ones, when, and
what each failure says. Every row must turn
`tests/test_an_openfactory_0_7_deployments_temporal_work_is_picked_up.py` red.
"""

TEST = "tests/test_an_openfactory_0_7_deployments_temporal_work_is_picked_up.py"

INIT = "beeverforge/runtime/temporal/__init__.py"
WORKER = "beeverforge/runtime/temporal/worker.py"
SCHEDULE = "beeverforge/runtime/temporal/schedule.py"
VIEW = "beeverforge/runtime/temporal/view.py"
ACTIVITIES = "beeverforge/runtime/temporal/activities.py"
CATALOG = "beeverforge/actions/catalog.py"
RELEASE = "beeverforge/product/release.py"
FORGET = "beeverforge/product/forget.py"
BREAKING = "beeverforge/product/breaking.py"
APP = "beeverforge/api/app.py"

MUTATIONS = [
    # ── the former queue is polled ──
    ("the former queue is not the one 0.7 polled", INIT,
     'FORMER_TASK_QUEUE = "openfactory-jobs"',
     'FORMER_TASK_QUEUE = "openfactory-job"'),
    ("the worker polls only its own queue", WORKER,
     "    ) for queue in (TASK_QUEUE, FORMER_TASK_QUEUE)]",
     "    ) for queue in (TASK_QUEUE,)]"),
    # RE-PINNED 2026-11-09 (#500): the two workers are run by `run_together` now
    ("the former queue's worker is built and never run", WORKER,
     "    await run_together(workers)",
     "    await workers[0].run()"),
    ("the former queue's worker lacks an activity", WORKER,
     "        activities=WORKER_ACTIVITIES,",
     "        activities=WORKER_ACTIVITIES if queue == TASK_QUEUE else WORKER_ACTIVITIES[:-1],"),
    ("the former queue's worker lacks a workflow", WORKER,
     "                   GateKeyProbeWorkflow],",
     "                   *([GateKeyProbeWorkflow] if queue == TASK_QUEUE else [])],"),
    ("the former queue's worker has no interceptor", WORKER,
     "        interceptors=[AboutItsProject()],",
     "        interceptors=[AboutItsProject()] if queue == TASK_QUEUE else [],"),
    # ── nothing new starts there ──
    ("a job is started on the former queue", VIEW,
     "    await client.start_workflow(JobWorkflow.run, params, id=wf_id, task_queue=TASK_QUEUE)",
     "    await client.start_workflow(JobWorkflow.run, params, id=wf_id,"
     " task_queue=\"openfactory-jobs\")"),
    ("a schedule module aims at the former queue by name", SCHEDULE,
     "from beeverforge.runtime.temporal import TASK_QUEUE\n",
     "from beeverforge.runtime.temporal import FORMER_TASK_QUEUE as TASK_QUEUE\n"),
    # ── 0.7's schedules are retired ──
    ("ensure_all retires none of 0.7's schedules", SCHEDULE,
     "    out += await retire_former_schedules()\n",
     ""),
    ("0.7's schedules are retired before BeeverForge's are ensured", SCHEDULE,
     "    out.append(await ensure_retention())\n    out.append(await ensure_poller())",
     "    out += await retire_former_schedules()\n    out.append(await ensure_retention())\n"
     "    out.append(await ensure_poller())"),
    ("0.7's previews' reaper is left firing", SCHEDULE,
     'FORMER_SCHEDULE_IDS = ("openfactory-poller", "openfactory-preview-reaper")',
     'FORMER_SCHEDULE_IDS = ("openfactory-poller",)'),
    ("0.7's knowledge refreshes are left firing", SCHEDULE,
     '                            "openfactory-card-questions", "openfactory-okf-refresh")',
     '                            "openfactory-card-questions")'),
    ("an id that only starts like 0.7's poller is deleted", SCHEDULE,
     "    return sid in FORMER_SCHEDULE_IDS or any(",
     "    return any(sid.startswith(i) for i in FORMER_SCHEDULE_IDS) or any("),
    ("a prefix is matched without its dash", SCHEDULE,
     '        sid.startswith(f"{prefix}-") for prefix in FORMER_SCHEDULE_PREFIXES)',
     "        sid.startswith(prefix) for prefix in FORMER_SCHEDULE_PREFIXES)"),
    # ── what each failure says ──
    ("a schedule already gone is said as a failure", SCHEDULE,
     "            if exc.status == RPCStatusCode.NOT_FOUND:\n                continue\n",
     ""),
    ("an engine's refusal stops the rest", SCHEDULE,
     "            _could_not_retire(sid, exc)\n            continue\n        except Exception",
     "            _could_not_retire(sid, exc)\n            break\n        except Exception"),
    ("any other failure stops the rest", SCHEDULE,
     "            _could_not_retire(sid, exc)\n            continue\n        retired.append(sid)",
     "            _could_not_retire(sid, exc)\n            break\n        retired.append(sid)"),
    ("a schedule that could not be retired is not said", SCHEDULE,
     "    log.error(\"could not retire OpenFactory 0.7's schedule %s",
     "    log.debug(\"could not retire OpenFactory 0.7's schedule %s"),
    ("a listing that failed ends the boot's reconcile", SCHEDULE,
     "    except Exception as exc:  # noqa: BLE001 — a boot that ensured the new ones must go on",
     "    except ZeroDivisionError as exc:"),
    ("a listing that failed is not said", SCHEDULE,
     "        log.error(\"could not list the engine's schedules to retire OpenFactory 0.7's",
     "        log.debug(\"could not list the engine's schedules to retire OpenFactory 0.7's"),
    ("what was retired is not said", SCHEDULE,
     "    if not retired:\n        return []\n",
     "    return []\n"),
    ("nothing retired is still said as a retirement", SCHEDULE,
     "    if not retired:\n        return []\n",
     "    if False:\n        return []\n"),
    # ── the two workers end together (review of #500) ──
    ("the worker runs its two workers side by side and leaves one running", WORKER,
     "    await run_together(workers)",
     "    await asyncio.gather(*(worker.run() for worker in workers))"),
    ("the others are not stopped when one ends", WORKER,
     "        for task in tasks:\n            task.cancel()\n",
     ""),
    ("the first to end is not what ends the pair", WORKER,
     "return_when=asyncio.FIRST_COMPLETED",
     "return_when=asyncio.ALL_COMPLETED"),
    ("the error of the one that ended is dropped", WORKER,
     "    for task in done:\n        task.result()\n",
     ""),
    # ── a 0.7 workflow keeps its 0.7 id (review of #500) ──
    ("0.7's workflow id prefix is not 0.7's", INIT,
     'FORMER_WORKFLOW_ID_PREFIX = "openfactory-"',
     'FORMER_WORKFLOW_ID_PREFIX = "openfactory_"'),
    ("a 0.7 job id is not parsed", VIEW,
     "    prefix = next((p for p in (_WF_ID_PREFIX, FORMER_WORKFLOW_ID_PREFIX)",
     "    prefix = next((p for p in (_WF_ID_PREFIX,)"),
    ("the engine link filters 0.7's jobs out", APP,
     "    return quote(f'WorkflowId STARTS_WITH \"beeverforge-{project}-\" OR '\n"
     "                 f'WorkflowId STARTS_WITH \"{FORMER_WORKFLOW_ID_PREFIX}{project}-\"')",
     "    return quote(f'WorkflowId STARTS_WITH \"beeverforge-{project}-\"')"),
    ("a job is never looked for under 0.7's id", VIEW,
     "                if exc.status != RPCStatusCode.NOT_FOUND:\n                    raise\n"
     "                missing = exc\n",
     "                raise\n"),
    ("any engine failure is retried under 0.7's id", VIEW,
     "                if exc.status != RPCStatusCode.NOT_FOUND:\n                    raise\n",
     "                if False:\n                    raise\n"),
    ("a job under neither id is said under 0.7's", VIEW,
     "                    raise missing from None\n",
     "                    raise\n"),
    ("the id that answered is not kept", VIEW,
     "            self._handle, self.id = former, self._former_id\n",
     "            self._handle = former\n"),
    ("a gate answer is sealed over BeeverForge's id whatever answered", VIEW,
     "    seal = gate_seal.seal(gate_seal.APPROVE_PROD, handle.id,",
     "    seal = gate_seal.seal(gate_seal.APPROVE_PROD, job_id(project, issue),"),
    ("the merge gate's 'what is it waiting on' asks BeeverForge's id only", CATALOG,
     "    handle = tv.job_handle(client, found.name, issue)\n",
     "    handle = client.get_workflow_handle(tv.job_id(found.name, issue))\n"),
    ("the tech-lead resumes a parked 0.7 job under BeeverForge's id", ACTIVITIES,
     "            handle = tv_job_handle(client, project_name, finding.ticket)\n",
     "            handle = client.get_workflow_handle(f\"beeverforge-{project_name}-{finding.ticket}\")\n"),
    ("the release bridge asks BeeverForge's id only", RELEASE,
     "    handle = job_handle(client, project_name, str(issue).lstrip(\"#\"))\n",
     "    handle = client.get_workflow_handle(f\"beeverforge-{project_name}-{issue}\")\n"),
    ("a 0.7 deploy watch is not read", VIEW,
     "        watch = _EitherId(client, wf_id)\n",
     "        watch = client.get_workflow_handle(wf_id)\n"),
    ("a decision starts a second coordinator beside 0.7's", ACTIVITIES,
     "        if former := await _former_coordinator(client, item.project):",
     "        if former := None:"),
    ("an update starts a second coordinator beside 0.7's", ACTIVITIES,
     "        if former := await _former_coordinator(client, inp.project):",
     "        if former := None:"),
    ("a finished 0.7 coordinator is signalled as if it ran", ACTIVITIES,
     "    return former if described.status == WorkflowExecutionStatus.RUNNING else None",
     "    return former"),
    ("a 0.7 coordinator's messages are filed under its id", VIEW,
     "    prefixes = (f\"{_WF_ID_PREFIX}coordinator-\", f\"{FORMER_WORKFLOW_ID_PREFIX}coordinator-\")",
     "    prefixes = (f\"{_WF_ID_PREFIX}coordinator-\",)"),
    ("forgetting a project leaves 0.7's coordinator running", FORGET,
     "                    f'(WorkflowId = \"{coordinator}\" OR WorkflowId = \"{former}\") '",
     "                    f'(WorkflowId = \"{coordinator}\") '"),
    ("a running 0.7 breakdown is read as not running", BREAKING,
     "    prefixes = (prefix, FORMER_WORKFLOW_ID_PREFIX + prefix.removeprefix(\"beeverforge-\"))",
     "    prefixes = (prefix,)"),
    ("the floor counts BeeverForge's jobs only", ACTIVITIES,
     "    async for _ in client.list_workflows(\n"
     "        'WorkflowType = \"JobWorkflow\" AND ExecutionStatus = \"Running\"'\n"
     "    ):\n        running += 1",
     "    async for _ in client.list_workflows(\n"
     "        'WorkflowType = \"JobWorkflow\" AND ExecutionStatus = \"Running\"'\n"
     "        ' AND WorkflowId STARTS_WITH \"beeverforge-\"'\n"
     "    ):\n        running += 1"),
]
