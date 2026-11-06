"""What the metrics store holds past its period is deleted from the file, on a schedule (#201).

WHAT WAS WRONG: `SqliteMetricsSink.purge_expired` existed, was tested, and was reached by nothing.
Every read already hid an expired row, so answers were right, but on a `sqlite` deployment every
row stayed in the file for ever: conversation messages kept for a period under ADR-0024,
invitations, staged suggestions. And `purge_expired` itself was a plain `DELETE`, which leaves a
row's text in SQLite's free pages and, in WAL mode, in the `-wal` file.

WHAT IS HELD HERE:
  · after a purge, a row past its period is in neither the database file's bytes nor the log's,
    and a row inside its period still is;
  · the activity the schedule runs purges the deployment's own store, and says what it did;
  · a store with no `purge_expired` (one that keeps nothing, or deletes by its own TTL) is said,
    not skipped in silence;
  · the schedule runs that workflow, deployment-wide, every six hours, and the worker reconciles it
    at boot (`ensure_all`).
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from beeverforge.observability.metrics import MetricRecord
from beeverforge.observability.sqlite_metrics import SqliteMetricsSink

GONE = "a-message-past-its-period"
KEPT = "a-message-inside-its-period"


def _message(text: str, expires_at: int) -> MetricRecord:
    return MetricRecord(project="demo", ticket="#7", ts=f"2026-11-06T10:00:00+00:00#{text}",
                        kind="message", role="person", expires_at=expires_at,
                        extra={"text": text})


def _bytes(path: Path) -> bytes:
    """The database file and its write-ahead log, as a reader of the disk would find them."""
    return b"".join(p.read_bytes() for p in (path, path.with_name(path.name + "-wal"))
                    if p.exists())


def _store_with_both(path: Path) -> SqliteMetricsSink:
    sink = SqliteMetricsSink(path)
    now = int(time.time())
    assert sink.record(_message(GONE, now - 60))
    assert sink.record(_message(KEPT, now + 3600))
    assert GONE.encode() in _bytes(path), "the expired row was never on disk to begin with"
    return sink


def _a_build_that_keeps_deleted_bytes(monkeypatch) -> None:
    """Every connection the store opens starts with `secure_delete` off, as a SQLite built without
    `SQLITE_SECURE_DELETE` does (SQLite's own default, and the bundled library of some Pythons).
    Ubuntu's build turns it on, which hid this on the machine the fix was written on: a plain
    `DELETE` already zeroed the row there and left it readable elsewhere."""
    import sqlite3

    real = sqlite3.connect

    def connect(*args, **kwargs):
        conn = real(*args, **kwargs)
        conn.execute("PRAGMA secure_delete=OFF")
        return conn

    monkeypatch.setattr(sqlite3, "connect", connect)


def test_a_purged_row_is_in_neither_the_file_nor_its_log(tmp_path, monkeypatch):
    _a_build_that_keeps_deleted_bytes(monkeypatch)
    path = tmp_path / "m.db"
    sink = _store_with_both(path)

    assert sink.purge_expired() == 1

    on_disk = _bytes(path)
    assert GONE.encode() not in on_disk, "the purged row's text is still in the file's bytes"
    assert KEPT.encode() in on_disk, "a row inside its period went too"


def test_a_purged_row_is_not_left_in_the_log_while_another_process_holds_the_store(
        tmp_path, monkeypatch):
    """The panel and the worker both hold the store open, so the `-wal` file is not removed when
    the purge's own connection closes, and the row's earlier versions stay in it until a
    checkpoint copies the log back and truncates it. Here a second connection, idle, holds the
    store open across the write and the purge."""
    import sqlite3

    _a_build_that_keeps_deleted_bytes(monkeypatch)
    path = tmp_path / "m.db"
    SqliteMetricsSink(path).record(_message("first", int(time.time()) + 3600))   # the file exists
    held = sqlite3.connect(path)
    held.execute("PRAGMA journal_mode=WAL")
    try:
        sink = _store_with_both(path)

        assert sink.purge_expired() == 1

        assert GONE.encode() not in _bytes(path), "the purged row is still in the log's bytes"
    finally:
        held.close()


def test_the_scheduled_activity_purges_the_deployments_own_store(tmp_path, monkeypatch, caplog):
    from beeverforge.runtime.temporal.activities import purge_expired_records

    _a_build_that_keeps_deleted_bytes(monkeypatch)
    path = tmp_path / "m.db"
    _store_with_both(path)
    monkeypatch.setenv("BEEVERFORGE_METRICS_SINK", "sqlite")
    monkeypatch.setenv("BEEVERFORGE_METRICS_DB", str(path))

    with caplog.at_level(logging.INFO):
        said = asyncio.run(purge_expired_records())

    assert said == "purged 1 expired row(s) from the sqlite store"
    assert GONE.encode() not in _bytes(path)
    assert any("BEEVERFORGE_METRICS_PURGED kind=sqlite rows=1" in r.getMessage()
               for r in caplog.records)


def test_a_store_that_keeps_nothing_is_said_not_skipped(monkeypatch, caplog):
    from beeverforge.runtime.temporal.activities import purge_expired_records

    monkeypatch.setenv("BEEVERFORGE_METRICS_SINK", "null")

    with caplog.at_level(logging.INFO):
        said = asyncio.run(purge_expired_records())

    assert said == "nothing to purge: the null store does not keep expired rows itself"
    assert any("BEEVERFORGE_METRICS_PURGE kind=null" in r.getMessage() for r in caplog.records)


def test_the_schedule_runs_the_purge_every_six_hours():
    from beeverforge.runtime.temporal import schedule

    built = schedule._metrics_purge_schedule(schedule.METRICS_PURGE_EVERY_HOURS)

    assert built.action.workflow == "MetricsPurgeWorkflow"
    assert built.action.id == schedule.METRICS_PURGE_SCHEDULE_ID
    assert [i.every.total_seconds() for i in built.spec.intervals] == [6 * 3600]


def _registered_workflows() -> set[str]:
    """The names in the `workflows=` list the worker hands `Worker(...)`, read from its source."""
    import ast

    from tests.the_tree_read_once import parsed

    tree = parsed(Path(__file__).resolve().parents[1] / "beeverforge/runtime/temporal/worker.py")
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "Worker":
            for kw in node.keywords:
                if kw.arg == "workflows" and isinstance(kw.value, ast.List):
                    return {e.id for e in kw.value.elts if isinstance(e, ast.Name)}
    raise AssertionError("worker.py builds no Worker(workflows=[...])")


def test_the_worker_registers_the_purge_and_reconciles_its_schedule_at_boot():
    import inspect

    from beeverforge.runtime.temporal import schedule
    from beeverforge.runtime.temporal.activities import purge_expired_records
    from beeverforge.runtime.temporal.worker import WORKER_ACTIVITIES

    assert "MetricsPurgeWorkflow" in _registered_workflows()
    assert purge_expired_records in WORKER_ACTIVITIES
    assert "ensure_metrics_purge()" in inspect.getsource(schedule.ensure_all)
