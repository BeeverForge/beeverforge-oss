"""A tracker whose writes survive the forge's rate limit (#699).

A ticket state, label, assignee or comment that fails with `RateLimited` used to be logged and lost:
the board stopped matching the jobs and nothing retried after the reset. `DeferringTracker` wraps
any `TrackerAdapter` and, for those five writes, QUEUES the effect instead, then applies it once
`reset_at` has passed. Every other call — reads, and any failure that is not a rate limit — passes
through untouched.

WHAT A QUEUED WRITE ANSWERS. `set_state` answers False, which the port defines as "the card is
where it was" — true until the entry is applied. `comment`, the labels and the assignees answer
None, as a write that landed does: the port gives them no other answer, and the entry is said in
the log (`BEEVERFORGE_EFFECT_QUEUED`, then `..._RECORDED` when it lands).

THE RULES OF THE QUEUE
  - One repository's entries: an entry carries the `scope` it was made for — the repository (or
    the tracker's coordinate) of the tracker that queued it. A product of several repositories
    gives every view of it one queue file, and `#1` names a different issue in each; a tracker
    applies, joins behind and replaces only its own scope's entries (review of #708: a state
    queued for `acme/api#1` was applied to `acme/web#1`).
  - In order per ticket: a ticket's entries are applied oldest first, and a write for a ticket
    that still has entries waiting joins behind them rather than overtaking them. One ticket's
    wait never holds another ticket's entry that is due.
  - Newest state wins: a later state / assignee set for the same ticket, or a later operation on the
    same label, REPLACES the earlier entry (and takes its place at the back). A comment is keyed by
    its text, so posting the same words twice is one comment.
  - Never backwards (ADR-0055 D5): before an entry is applied, `superseded(entry)` is asked; a
    reason it gives drops the entry, logged `BEEVERFORGE_QUEUED_EFFECT_SUPERSEDED`. The factory
    answers it from the card's record (a move recorded after the entry was queued decided where
    the card is now). An assignee set is also dropped when the ticket's assignees are no longer
    the ones this tracker last saw: a person changed them meanwhile.
  - At most once: an entry leaves the queue (and the file) BEFORE it is applied. An apply that fails
    on the rate limit goes back with the new reset; any other failure drops it, logged — a retry
    that cannot succeed must not wait forever (guideline 8).

DURABILITY. With a `path` the queue is a JSON file, readable by its owner only, rewritten
atomically on every change, so it survives a restart of the process. Every runner of a project
shares that one file, so each operation takes an exclusive lock on a sidecar `.lock` file, RELOADS
the queue from the file, and only then reads or changes it: two trackers on one path never
overwrite each other's entries, and an entry one of them applied is gone from the file before the
other looks. An entry is applied while the lock is held, which is what makes "at most once" true
across runners. An entry the file holds that this version cannot read is dropped by name
(`BEEVERFORGE_QUEUED_EFFECT_UNREADABLE`), never a reason to refuse the next write. With no path it
lives in memory and is lost with the process.

WHO DRAINS IT. `flush()` and the start of every write; the job runner when a job starts and when it
ends; and the worker's hourly round (`factory.drain_queued_effects`), so a project with no next job
still applies its queue within the hour after the reset. A REMOTE BOX runs its runner on a machine
that ends with the task: its file goes with it, and what its job queued and did not apply by the
job's end is lost there (its outcome still reaches the card through the door, on the worker).

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
from beeverforge.contracts.refs import canonical_ref

log = logging.getLogger("beeverforge.tracker")

#: The kinds of write the queue holds, and what each entry's payload must carry to be applied.
_PAYLOAD = {"state": ("state",), "comment": ("body",), "assignees": ("logins",),
            "label": ("op", "label")}
_FIELDS = {"id": str, "key": list, "kind": str, "scope": str, "ref": str, "payload": dict,
           "queued_at": (int, float), "reset_at": (int, float)}


def _bare(ref: str) -> str:
    """The ticket a ref names within its scope: `acme/web#7`, `#7` and `7` are one ticket."""
    ref = str(ref or "")
    return canonical_ref(ref.rsplit("#", 1)[-1] if "#" in ref else ref)


def _unreadable(entry: object) -> str:
    """Why `entry` cannot be applied by this version, or "" when it can."""
    if not isinstance(entry, dict):
        return "not an object"
    for name, kind in _FIELDS.items():
        if not isinstance(entry.get(name), kind):
            return f"no {name}"
    if entry["kind"] not in _PAYLOAD:
        return f"kind {entry['kind']!r}"
    missing = [f for f in _PAYLOAD[entry["kind"]] if f not in entry["payload"]]
    if missing:
        return f"no {missing[0]}"
    if entry["kind"] == "state":
        try:
            JobState(entry["payload"]["state"])
        except ValueError:
            return f"state {entry['payload']['state']!r}"
    return ""


def read_queue(path: Path) -> list[dict]:
    """The entries the file at `path` holds that can be applied; each one that cannot is dropped
    by name and logged. Never raises: an unreadable file is an empty queue, said."""
    path = Path(path)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        log.error("BEEVERFORGE_QUEUED_EFFECT_UNREADABLE the queued tracker effects at %s could "
                  "not be read (%s) — starting empty", path, exc)
        return []
    if not isinstance(data, list):
        log.error("BEEVERFORGE_QUEUED_EFFECT_UNREADABLE the queued tracker effects at %s are not "
                  "a list — starting empty", path)
        return []
    kept = []
    for n, entry in enumerate(data):
        why = _unreadable(entry)
        if why:
            name = entry.get("id") if isinstance(entry, dict) else None
            log.error("BEEVERFORGE_QUEUED_EFFECT_UNREADABLE entry=%s (number %d in %s): %s — "
                      "dropped, never applied", name or "-", n, path, why)
            continue
        kept.append(entry)
    return kept


class DeferringTracker:
    def __init__(self, inner: Any, *, clock: Callable[[], float] = time.time,
                 path: Path | None = None, scope: str = "",
                 superseded: Callable[[dict], str] | None = None) -> None:
        self._inner = inner
        self._clock = clock
        self._path = Path(path) if path else None
        self._scope = scope or ""
        self._superseded = superseded
        self._lock = threading.RLock()
        self._depth = 0
        #: the assignees this tracker last set or read, per ticket: what a queued set replaces
        self._assigned: dict[str, list[str]] = {}
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
        # a dunder or the wrapped tracker itself is never forwarded: `copy.copy` builds an empty
        # instance and asks it for `__setstate__`, and forwarding that read `_inner` again, for
        # ever (review of #708: RecursionError)
        if name.startswith("__") or name == "_inner":
            raise AttributeError(name)
        return getattr(self._inner, name)

    # -- the queued writes --
    def set_state(self, ref: str, state: JobState, reason: str | None = None, *,
                  needs_person: bool | None = None) -> bool | None:
        got = self._write(("state", ref), {"state": state.value, "needs_person": needs_person},
                          lambda: self._inner.set_state(ref, state, reason,
                                                        needs_person=needs_person))
        return False if got is _QUEUED else got

    def comment(self, ref: str, body: str) -> None:
        # THE WHOLE BODY (review of #708): a cut comment was posted 20,000 characters long, its
        # end missing and nothing said; the row refuses one over the forge's limit by name
        digest = hashlib.sha256(body.encode()).hexdigest()
        self._write(("comment", ref, digest), {"body": body},
                    lambda: self._inner.comment(ref, body))

    def set_assignees(self, ref: str, logins: list[str]) -> None:
        before = self._assigned.get(_bare(ref))

        def call() -> Any:
            got = self._inner.set_assignees(ref, list(logins))
            self._assigned[_bare(ref)] = list(logins)
            return got

        self._write(("assignees", ref),
                    {"logins": list(logins), "before": None if before is None else list(before)},
                    call)

    def assignees(self, ref: str) -> list[str]:
        got = self._inner.assignees(ref)
        self._assigned[_bare(ref)] = list(got)
        return got

    def add_label(self, ref: str, label: str) -> None:
        self._write(("label", ref, label), {"op": "add", "label": label},
                    lambda: self._inner.add_label(ref, label))

    def remove_label(self, ref: str, label: str) -> None:
        self._write(("label", ref, label), {"op": "remove", "label": label},
                    lambda: self._inner.remove_label(ref, label))

    # -- the queue --
    @property
    def pending(self) -> list[dict]:
        """This tracker's scope's entries, oldest first."""
        with self._held():
            return [dict(e) for e in self._queue if self._mine(e)]

    def supersede(self, ref: str, kinds: tuple[str, ...], why: str) -> int:
        """Drop this scope's entries of `kinds` for the ticket `ref` names, logged; how many."""
        with self._held():
            gone = [e for e in self._queue
                    if self._mine(e) and e["kind"] in kinds and _bare(e["ref"]) == _bare(ref)]
            if gone:
                self._queue = [e for e in self._queue if e not in gone]
                self._save()
            for e in gone:
                self._dropped(e, why)
            return len(gone)

    def flush(self) -> int:
        """Apply every entry of this scope whose reset has passed, each ticket's oldest first;
        how many were applied."""
        applied = 0
        with self._held():
            now = self._clock()
            waiting: set[str] = set()  # tickets with an entry kept: theirs later wait behind it
            i = 0
            while i < len(self._queue):
                entry = self._queue[i]
                if not self._mine(entry):
                    i += 1
                    continue
                ticket = _bare(entry["ref"])
                if ticket in waiting or entry["reset_at"] > now:
                    waiting.add(ticket)
                    i += 1
                    continue
                self._queue.pop(i)
                self._save()  # claimed in the file before it is applied: at most once
                try:
                    why = self._stale(entry)
                    if why:
                        self._dropped(entry, why)
                        continue
                    self._apply(entry)
                except RateLimited as exc:
                    entry["reset_at"] = exc.reset_at
                    self._queue.insert(i, entry)
                    self._save()
                    return applied  # the budget is spent: the rest would meet it too
                except Exception as exc:  # a retry that cannot succeed is dropped, logged
                    log.error("BEEVERFORGE_QUEUED_EFFECT_DROPPED entry=%s %s %s (%s) — it failed "
                              "for a reason other than the rate limit, so it is not retried",
                              entry["id"], entry["kind"], entry["ref"],
                              redact(str(exc))[:160])
                    continue
                applied += 1
                self._recorded(entry)
        return applied

    def _mine(self, entry: dict) -> bool:
        return entry.get("scope", "") == self._scope

    def _stale(self, entry: dict) -> str:
        """Why `entry` must not be applied now, or "" (ADR-0055 D5, never backwards)."""
        if self._superseded is not None:
            why = self._superseded(entry)
            if why:
                return why
        before = entry["payload"].get("before") if entry["kind"] == "assignees" else None
        if before is not None and hasattr(self._inner, "assignees"):
            now = list(self._inner.assignees(entry["ref"]))
            if sorted(now) != sorted(before):
                return f"its assignees were changed meanwhile (now {', '.join(now) or 'nobody'})"
        return ""

    def _write(self, key: tuple, payload: dict, call: Callable[[], Any]) -> Any:
        with self._held():
            self.flush()
            ticket = _bare(key[1])
            behind = [e["reset_at"] for e in self._queue
                      if self._mine(e) and _bare(e["ref"]) == ticket]
            if behind:
                self._enqueue(key, payload, max(behind), "waiting behind")
                return _QUEUED
            try:
                return call()
            except RateLimited as exc:
                self._enqueue(key, payload, exc.reset_at, redact(str(exc)))
                return _QUEUED

    def _enqueue(self, key: tuple, payload: dict, reset_at: float, why: str) -> None:
        queued_at = self._clock()
        ident = hashlib.sha256(f"{self._scope}|{json.dumps(key)}|{queued_at}|{os.getpid()}"
                               .encode()).hexdigest()[:10]
        self._queue = [e for e in self._queue if not (self._mine(e) and e["key"] == list(key))]
        self._queue.append({"id": ident, "key": list(key), "kind": key[0], "scope": self._scope,
                            "ref": key[1], "payload": payload, "queued_at": queued_at,
                            "reset_at": reset_at})
        self._save()
        tag = ("BEEVERFORGE_TICKET_STATE_UNRECORDED" if key[0] == "state"
               else "BEEVERFORGE_EFFECT_QUEUED")
        # A COMMENT IS NAMED, NEVER QUOTED (review of #708): its body is a person's words and
        # may hold a credential; the line names the kind, the entry and the length
        what = (f"a comment of {len(payload['body'])} characters" if key[0] == "comment"
                else {k: v for k, v in payload.items() if k != "before"})
        log.error("%s ticket=%s entry=%s %s (%s) — queued, to be applied after reset_at=%s",
                  tag, key[1], ident, what, why[:160], reset_at)

    def _apply(self, e: dict) -> None:
        p, ref = e["payload"], e["ref"]
        if e["kind"] == "state":
            self._inner.set_state(ref, JobState(p["state"]), needs_person=p.get("needs_person"))
        elif e["kind"] == "comment":
            self._inner.comment(ref, p["body"])
        elif e["kind"] == "assignees":
            self._inner.set_assignees(ref, p["logins"])
            self._assigned[_bare(ref)] = list(p["logins"])
        elif p["op"] == "add":
            self._inner.add_label(ref, p["label"])
        else:
            self._inner.remove_label(ref, p["label"])

    def _recorded(self, e: dict) -> None:
        tag = ("BEEVERFORGE_TICKET_STATE_RECORDED" if e["kind"] == "state"
               else "BEEVERFORGE_EFFECT_RECORDED")
        log.info("%s ticket=%s entry=%s queued_at=%s at=%s", tag, e["ref"], e["id"],
                 e["queued_at"], self._clock())

    def _dropped(self, e: dict, why: str) -> None:
        log.warning("BEEVERFORGE_QUEUED_EFFECT_SUPERSEDED ticket=%s entry=%s %s — not applied: "
                    "%s", e["ref"], e["id"], e["kind"], why[:200])

    # -- durability --
    def _load(self) -> list[dict]:
        return read_queue(self._path) if self._path else []

    def _save(self) -> None:
        if not self._path:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            # THE OWNER'S ONLY (review of #708): the file holds comment bodies, and it was
            # created 0664 under the machine's umask
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as out:
                out.write(json.dumps(self._queue))
            os.chmod(tmp, 0o600)
            os.replace(tmp, self._path)
        except OSError as exc:
            log.error("the queued tracker effects could not be saved to %s (%s) — they survive "
                      "only until this process stops", self._path, exc)


_QUEUED = object()
