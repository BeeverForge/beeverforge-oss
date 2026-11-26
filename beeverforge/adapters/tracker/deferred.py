"""A tracker whose writes survive the forge's rate limit (#699).

A ticket state, label, assignee or comment that fails with `RateLimited` used to be logged and lost:
the board stopped matching the jobs and nothing retried after the reset. `DeferringTracker` wraps
any `TrackerAdapter` and, for those five writes, QUEUES the effect instead, then applies it once
`reset_at` has passed. Every other call — reads, and any failure that is not a rate limit — passes
through untouched.

THE RULES OF THE QUEUE
  - In order: entries are applied oldest first, and a write for a ticket that still has entries
    waiting joins the queue rather than overtaking them.
  - Newest state wins: a later state / assignee set for the same ticket, or a later operation on the
    same label, REPLACES the earlier entry (and takes its place at the back). A comment is keyed by
    its text, so posting the same words twice is one comment.
  - At most once: an entry leaves the queue (and the file) BEFORE it is applied. An apply that fails
    on the rate limit goes back with the new reset; any other failure drops it, logged — a retry
    that cannot succeed must not wait forever (guideline 8).

DURABILITY. With a `path` the queue is a JSON file rewritten atomically on every change, so it
survives a restart of the process. Every runner of a project shares that one file, so each operation
takes an exclusive lock on a sidecar `.lock` file, RELOADS the queue from the file, and only then
reads or changes it: two trackers on one path never overwrite each other's entries, and an entry one
of them applied is gone from the file before the other looks. An entry is applied while the lock is
held, which is what makes "at most once" true across runners. With no path it lives in memory and is
lost with the process. Nothing drains it on a timer: it is drained by `flush()` and at the start of
every write; the job runner calls `flush()` when a job starts and when it ends, so an entry whose
reset had not passed when its job ended is applied by the next job of the project (or the next
write) after it has, and a project with no further job keeps it in the file until there is one.

The clock is a parameter, so nothing here reads the wall.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import os
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from beeverforge.adapters.rate_limit import RateLimited, redact
from beeverforge.contracts import JobState

log = logging.getLogger("beeverforge.tracker")

_COMMENT_CAP = 20_000


class DeferringTracker:
    def __init__(self, inner: Any, *, clock: Callable[[], float] = time.time,
                 path: Path | None = None) -> None:
        self._inner = inner
        self._clock = clock
        self._path = Path(path) if path else None
        self._lock = threading.RLock()
        self._depth = 0
        self._queue: list[dict] = self._load()

    @contextmanager
    def _held(self) -> Iterator[None]:
        """The queue, exclusively, as the file has it NOW: the lock first, then the reload."""
        with self._lock:
            if self._depth or not self._path:
                self._depth += 1
                try:
                    yield
                finally:
                    self._depth -= 1
                return
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                fd = os.open(self._path.with_suffix(".lock"), os.O_CREAT | os.O_RDWR, 0o600)
            except OSError as exc:
                log.error("the queue lock for %s could not be taken (%s) — working on this "
                          "process's copy", self._path, exc)
                fd = None
            try:
                if fd is not None:
                    fcntl.flock(fd, fcntl.LOCK_EX)
                    self._queue = self._load()
                self._depth += 1
                try:
                    yield
                finally:
                    self._depth -= 1
            finally:
                if fd is not None:
                    os.close(fd)  # closing releases the lock

    # -- everything not overridden (reads, close_ticket, ...) is the inner tracker's --
    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    # -- the queued writes --
    def set_state(self, ref: str, state: JobState, reason: str | None = None, *,
                  needs_person: bool | None = None) -> bool | None:
        got = self._write(("state", ref), {"state": state.value, "needs_person": needs_person},
                          lambda: self._inner.set_state(ref, state, reason,
                                                        needs_person=needs_person))
        return False if got is _QUEUED else got

    def comment(self, ref: str, body: str) -> None:
        digest = hashlib.sha256(body.encode()).hexdigest()
        self._write(("comment", ref, digest), {"body": body[:_COMMENT_CAP]},
                    lambda: self._inner.comment(ref, body))

    def set_assignees(self, ref: str, logins: list[str]) -> None:
        self._write(("assignees", ref), {"logins": list(logins)},
                    lambda: self._inner.set_assignees(ref, list(logins)))

    def add_label(self, ref: str, label: str) -> None:
        self._write(("label", ref, label), {"op": "add", "label": label},
                    lambda: self._inner.add_label(ref, label))

    def remove_label(self, ref: str, label: str) -> None:
        self._write(("label", ref, label), {"op": "remove", "label": label},
                    lambda: self._inner.remove_label(ref, label))

    # -- the queue --
    @property
    def pending(self) -> list[dict]:
        with self._held():
            return [dict(e) for e in self._queue]

    def flush(self) -> None:
        """Apply every entry whose reset has passed, oldest first."""
        with self._held():
            now = self._clock()
            while self._queue and self._queue[0]["reset_at"] <= now:
                entry = self._queue.pop(0)
                self._save()
                try:
                    self._apply(entry)
                except RateLimited as exc:
                    entry["reset_at"] = exc.reset_at
                    self._queue.insert(0, entry)
                    self._save()
                    return
                except Exception as exc:  # a retry that cannot succeed is dropped, logged
                    log.error("BEEVERFORGE_QUEUED_EFFECT_DROPPED entry=%s %s %s (%s) — it failed "
                              "for a reason other than the rate limit, so it is not retried",
                              entry["id"], entry["kind"], entry["ref"],
                              redact(str(exc))[:160])
                    continue
                self._recorded(entry)

    def _write(self, key: tuple, payload: dict, call: Callable[[], Any]) -> Any:
        with self._held():
            self.flush()
            if any(e["ref"] == key[1] for e in self._queue):
                self._enqueue(key, payload, self._queue[0]["reset_at"], "waiting behind")
                return _QUEUED
            try:
                return call()
            except RateLimited as exc:
                self._enqueue(key, payload, exc.reset_at, redact(str(exc)))
                return _QUEUED

    def _enqueue(self, key: tuple, payload: dict, reset_at: float, why: str) -> None:
        queued_at = self._clock()
        ident = hashlib.sha256(f"{json.dumps(key)}|{queued_at}|{os.getpid()}".encode()
                               ).hexdigest()[:10]
        self._queue = [e for e in self._queue if e["key"] != list(key)]
        self._queue.append({"id": ident, "key": list(key), "kind": key[0], "ref": key[1],
                            "payload": payload, "queued_at": queued_at, "reset_at": reset_at})
        self._save()
        tag = ("BEEVERFORGE_TICKET_STATE_UNRECORDED" if key[0] == "state"
               else "BEEVERFORGE_EFFECT_QUEUED")
        log.error("%s ticket=%s entry=%s %s (%s) — queued, to be applied after reset_at=%s",
                  tag, key[1], ident, payload, why[:160], reset_at)

    def _apply(self, e: dict) -> None:
        p, ref = e["payload"], e["ref"]
        if e["kind"] == "state":
            self._inner.set_state(ref, JobState(p["state"]), needs_person=p["needs_person"])
        elif e["kind"] == "comment":
            self._inner.comment(ref, p["body"])
        elif e["kind"] == "assignees":
            self._inner.set_assignees(ref, p["logins"])
        elif p["op"] == "add":
            self._inner.add_label(ref, p["label"])
        else:
            self._inner.remove_label(ref, p["label"])

    def _recorded(self, e: dict) -> None:
        tag = ("BEEVERFORGE_TICKET_STATE_RECORDED" if e["kind"] == "state"
               else "BEEVERFORGE_EFFECT_RECORDED")
        log.info("%s ticket=%s entry=%s queued_at=%s at=%s", tag, e["ref"], e["id"],
                 e["queued_at"], self._clock())

    # -- durability --
    def _load(self) -> list[dict]:
        if not self._path or not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text())
            return [e for e in data if isinstance(e, dict)] if isinstance(data, list) else []
        except (OSError, ValueError) as exc:
            log.error("the queued tracker effects at %s could not be read (%s) — starting empty",
                      self._path, exc)
            return []

    def _save(self) -> None:
        if not self._path:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._queue))
            os.replace(tmp, self._path)
        except OSError as exc:
            log.error("the queued tracker effects could not be saved to %s (%s) — they survive "
                      "only until this process stops", self._path, exc)


_QUEUED = object()
