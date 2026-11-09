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

MUTATIONS = [
    # ── the former queue is polled ──
    ("the former queue is not the one 0.7 polled", INIT,
     'FORMER_TASK_QUEUE = "openfactory-jobs"',
     'FORMER_TASK_QUEUE = "openfactory-job"'),
    ("the worker polls only its own queue", WORKER,
     "    ) for queue in (TASK_QUEUE, FORMER_TASK_QUEUE)]",
     "    ) for queue in (TASK_QUEUE,)]"),
    ("the former queue's worker is built and never run", WORKER,
     "    await asyncio.gather(*(worker.run() for worker in workers))",
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
]
