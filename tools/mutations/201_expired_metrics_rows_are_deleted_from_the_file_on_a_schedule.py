"""What the metrics store holds past its period is deleted from the file, on a schedule (#201).

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/201_expired_metrics_rows_are_deleted_from_the_file_on_a_schedule.py

Rows 1-2 break the purge itself: the delete leaves its text in the free pages, and the log is never
checkpointed. Rows 3-4 break the activity: it purges nothing, and a store with no purge passes in
silence. Rows 5-7 break the schedule: another interval, never reconciled at boot, and the
workflow never registered on the worker.
"""

TEST = "tests/test_expired_metrics_rows_are_deleted_from_the_file_on_a_schedule.py"

STORE = "beeverforge/observability/sqlite_metrics.py"
ACT = "beeverforge/runtime/temporal/activities.py"
SCHED = "beeverforge/runtime/temporal/schedule.py"

MUTATIONS = [
    ("the delete leaves the row's text in the free pages", STORE,
     '                conn.execute("PRAGMA secure_delete=ON")\n',
     ""),

    ("the write-ahead log is never checkpointed after a purge", STORE,
     '                if purged:\n                    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")\n',
     ""),

    ("the scheduled activity purges nothing", ACT,
     "    purged = await asyncio.to_thread(purge)\n",
     "    purged = 0\n"),

    ("a store with no purge passes in silence", ACT,
     '        activity.logger.info("BEEVERFORGE_METRICS_PURGE kind=%s — this store deletes nothing "\n'
     '                             "itself (it keeps nothing, or its own TTL deletes expired rows)", kind)\n',
     ""),

    ("the purge runs once a day instead of every six hours", SCHED,
     "METRICS_PURGE_EVERY_HOURS = 6\n",
     "METRICS_PURGE_EVERY_HOURS = 24\n"),

    ("the worker never reconciles the purge's schedule at boot", SCHED,
     "    out.append(await ensure_metrics_purge())\n",
     ""),

    ("the worker never registers the purge's workflow", "beeverforge/runtime/temporal/worker.py",
     "                   PreviewReapWorkflow, PreviewWorkflow, MetricsPurgeWorkflow,\n",
     "                   PreviewReapWorkflow, PreviewWorkflow,\n"),
]
