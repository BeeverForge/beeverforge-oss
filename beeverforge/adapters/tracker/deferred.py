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

WHICH TICKET AN ENTRY IS FOR. A job writes its card's bare id (`#1`) through the product's
tracker, which never moves to the card's repository (C-18, `card_repo._runner_view`). So a bare
`#1` is `acme/api#1` on one runner and `acme/web#1` on another (review of #708 at 48ff615). An
entry is keyed by its TICKET: the ref resolved against the card the runner was built for (`card`)
and the product's own repository (`home`). A bare ref of the runner's own card takes the card's
repository; any other bare ref is the home repository's, and stays bare. The entry is still
applied with the ref as the caller wrote it, which is what the write would have done at once.

THE RULES OF THE QUEUE
  - One tracker coordinate's entries: an entry carries the `scope` it was made for, the
    repository (or coordinate) of the tracker that queued it, and only a tracker of that scope
    applies it.
  - In order per ticket: a ticket's entries are applied oldest first, and a write for a ticket
    that still has entries waiting (or one being applied) joins behind them rather than
    overtaking them. One ticket's wait never holds another ticket's entry that is due.
  - Newest state wins: a later state / assignee set for the same ticket, or a later operation on the
    same label, REPLACES the earlier entry (and takes its place at the back). A comment is keyed by
    its text, so posting the same words twice is one comment.
  - Never backwards (ADR-0055 D5): before an entry is applied, `superseded(entry)` is asked; a
    reason it gives drops the entry, logged `BEEVERFORGE_QUEUED_EFFECT_SUPERSEDED`. The factory
    answers it from the card's record (a move recorded after the entry was queued decided where
    the card is now). An assignee set is also dropped when the ticket's assignees are no longer
    the ones this tracker last saw: a person changed them meanwhile.
  - At most once: an entry is CLAIMED in the file before it is applied, and no other tracker
    applies a claimed entry; it leaves the file when its apply ends. An apply that fails on the
    rate limit goes back with the new reset; any other failure drops it, logged — a retry that
    cannot succeed must not wait forever (guideline 8). A claim older than `CLAIM_EXPIRES` is a
    runner that stopped while applying it: the entry is dropped, logged, never applied again.

THE LOCK IS HELD FOR THE FILE, NEVER FOR THE FORGE (review of #708 at 48ff615). Every runner of a
project shares one file, so each read or change of it takes an exclusive lock on a sidecar
`.lock` file and RELOADS the queue first: two trackers never overwrite each other's entries. The
lock covers claiming an entry, asking whether a ticket has entries waiting, and recording what an
apply came to; the forge call itself — a direct write or an entry's apply, up to a minute of `gh`
with its retries — runs with the lock released, so two lanes write at the same time.

DURABILITY. With a `path` the queue is a JSON file, readable by its owner only, rewritten
atomically on every change, so it survives a restart of the process. A change a save could not
write is kept in this process's memory and written again at its next operation on the queue; it is
lost only if the process stops first. An entry whose CLAIM could not be saved is not applied,
since the file would still offer it to another runner. An entry the file holds that this version
cannot read is dropped by name (`BEEVERFORGE_QUEUED_EFFECT_UNREADABLE`). With no path the queue
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
from beeverforge.contracts.refs import canonical_ref, split_repo_ref

log = logging.getLogger("beeverforge.tracker")

#: How long a claimed entry belongs to the runner applying it. One apply is one forge call of at
#: most a minute with its retries; past this the runner is gone, and the entry is dropped rather
#: than applied a second time.
CLAIM_EXPIRES = 600.0

#: The kinds of write the queue holds, and what each entry's payload must carry to be applied.
_PAYLOAD = {"state": ("state",), "comment": ("body",), "assignees": ("logins",),
            "label": ("op", "label")}
_FIELDS = {"id": str, "key": list, "kind": str, "scope": str, "ref": str, "payload": dict,
           "queued_at": (int, float), "reset_at": (int, float)}


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


def _ids(entries: list[dict]) -> set[str]:
    return {e["id"] for e in entries}


class DeferringTracker:
    def __init__(self, inner: Any, *, clock: Callable[[], float] = time.time,
                 path: Path | None = None, scope: str = "",
                 superseded: Callable[[dict], str] | None = None,
                 card: str = "", home: str = "") -> None:
        self._inner = inner
        self._clock = clock
        self._path = Path(path) if path else None
        self._scope = scope or ""
        self._superseded = superseded
        self._card = card or ""
        self._home = home or ""
        self._lock = threading.RLock()
        self._depth = 0
        #: the assignees this tracker last set or read, per ticket: what a queued set replaces
        self._assigned: dict[str, list[str]] = {}
        #: a change a failed save could not write is merged into the file at the next operation:
        #: `_base` is what the file held when this copy last matched it
        self._dirty = False
        self._queue: list[dict] = self._load()
        self._base = _ids(self._queue)

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
                    self._reload()
                self._depth += 1
                try:
                    yield
                finally:
                    self._depth -= 1
            finally:
                if fd is not None:
                    os.close(fd)  # closing releases the lock

    def _reload(self) -> None:
        loaded = self._load()
        if self._dirty:
            # WHAT A FAILED SAVE COULD NOT WRITE IS KEPT (review of #708 at 48ff615): the file
            # wins for every entry this copy did not change, and this copy's additions and
            # removals since the file last matched it are applied over it, then saved again
            removed = self._base - _ids(self._queue)
            added = [e for e in self._queue if e["id"] not in self._base]
            self._queue = ([e for e in loaded if e["id"] not in removed]
                           + [e for e in added if e["id"] not in _ids(loaded)])
            self._base = _ids(loaded)
            self._save()
        else:
            self._queue = loaded
            self._base = _ids(loaded)

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
        got = self._write("state", ref, (), {"state": state.value, "needs_person": needs_person},
                          lambda: self._inner.set_state(ref, state, reason,
                                                        needs_person=needs_person))
        return False if got is _QUEUED else got

    def comment(self, ref: str, body: str) -> None:
        # THE WHOLE BODY (review of #708): a cut comment was posted 20,000 characters long, its
        # end missing and nothing said; the row refuses one over the forge's limit by name
        digest = hashlib.sha256(body.encode()).hexdigest()
        self._write("comment", ref, (digest,), {"body": body},
                    lambda: self._inner.comment(ref, body))

    def set_assignees(self, ref: str, logins: list[str]) -> None:
        ticket = self.ticket(ref)
        before = self._assigned.get(ticket)

        def call() -> Any:
            got = self._inner.set_assignees(ref, list(logins))
            self._assigned[ticket] = list(logins)
            return got

        self._write("assignees", ref, (),
                    {"logins": list(logins), "before": None if before is None else list(before)},
                    call)

    def assignees(self, ref: str) -> list[str]:
        got = self._inner.assignees(ref)
        self._assigned[self.ticket(ref)] = list(got)
        return got

    def add_label(self, ref: str, label: str) -> None:
        self._write("label", ref, (label,), {"op": "add", "label": label},
                    lambda: self._inner.add_label(ref, label))

    def remove_label(self, ref: str, label: str) -> None:
        self._write("label", ref, (label,), {"op": "remove", "label": label},
                    lambda: self._inner.remove_label(ref, label))

    # -- the queue --
    def ticket(self, ref: str) -> str:
        """The ticket `ref` names here: `owner/name#n` for a card of another repository than
        `home`, the bare id for one of `home` (see the module, "which ticket")."""
        repo, bare = split_repo_ref(str(ref or ""), "")
        bare = canonical_ref(bare)
        if not repo and self._card:
            card_repo, card_bare = split_repo_ref(self._card, "")
            if card_repo and canonical_ref(card_bare) == bare:
                repo = card_repo
        if not repo or repo.casefold() == self._home.casefold():
            return bare
        return f"{repo.casefold()}#{bare}"

    def _ticket_of(self, entry: dict) -> str:
        return str(entry.get("ticket") or self.ticket(entry["ref"]))

    @property
    def pending(self) -> list[dict]:
        """This tracker's scope's entries, oldest first."""
        with self._held():
            return [dict(e) for e in self._queue if self._mine(e)]

    def supersede(self, ref: str, kinds: tuple[str, ...], why: str, *,
                  states: frozenset[str] | None = None) -> int:
        """Drop this scope's unclaimed entries of `kinds` for the ticket `ref` names — of a state
        entry only one whose state is in `states`, when given — logged; how many."""
        ticket = self.ticket(ref)
        with self._held():
            gone = [e for e in self._queue
                    if self._mine(e) and not e.get("claimed") and e["kind"] in kinds
                    and self._ticket_of(e) == ticket
                    and (states is None or e["kind"] != "state"
                         or e["payload"]["state"] in states)]
            if gone:
                self._queue = [e for e in self._queue if e not in gone]
                self._save()
            for e in gone:
                self._dropped(e, why)
            return len(gone)

    def flush(self) -> int:
        """Apply every entry of this scope whose reset has passed, each ticket's oldest first;
        how many were applied. The lock is held to claim each entry and to record what its apply
        came to, never across the apply."""
        applied = 0
        now = self._clock()
        while True:
            with self._held():
                entry = self._claim(now)
            if entry is None:
                return applied
            try:
                why = self._stale(entry)
                if why:
                    self._release(entry)
                    self._dropped(entry, why)
                    continue
                self._apply(entry)
            except RateLimited as exc:
                with self._held():
                    for e in self._queue:
                        if e["id"] == entry["id"]:
                            e.pop("claimed", None)
                            e.pop("claimed_at", None)
                            e["reset_at"] = exc.reset_at
                            self._save()
                            break
                return applied  # the budget is spent: the rest would meet it too
            except Exception as exc:  # a retry that cannot succeed is dropped, logged
                self._release(entry)
                log.error("BEEVERFORGE_QUEUED_EFFECT_DROPPED entry=%s %s %s (%s) — it failed "
                          "for a reason other than the rate limit, so it is not retried",
                          entry["id"], entry["kind"], entry["ref"],
                          redact(str(exc))[:160])
                continue
            self._release(entry)
            applied += 1
            self._recorded(entry)

    def _claim(self, now: float) -> dict | None:
        """The next entry of this scope that is due, claimed in the file; None when there is
        none, or when the claim could not be saved (applying it then could apply it twice)."""
        waiting: set[str] = set()  # tickets with an entry kept: theirs later wait behind it
        for entry in list(self._queue):
            if not self._mine(entry):
                continue
            ticket = self._ticket_of(entry)
            if entry.get("claimed"):
                if now - float(entry.get("claimed_at") or 0) > CLAIM_EXPIRES:
                    self._queue.remove(entry)
                    self._save()
                    log.error("BEEVERFORGE_QUEUED_EFFECT_DROPPED entry=%s %s %s — the runner "
                              "applying it stopped before it said what the apply came to, so "
                              "it is not applied again", entry["id"], entry["kind"], entry["ref"])
                    continue
                waiting.add(ticket)
                continue
            if ticket in waiting or entry["reset_at"] > now:
                waiting.add(ticket)
                continue
            entry["claimed"] = f"{os.getpid()}-{id(self)}"
            entry["claimed_at"] = now
            if not self._save():  # claimed in the file before it is applied: at most once
                entry.pop("claimed", None)
                entry.pop("claimed_at", None)  # as the file still holds it
                log.error("BEEVERFORGE_QUEUED_EFFECT_NOT_CLAIMED entry=%s %s %s — not applied "
                          "now: its claim could not be saved", entry["id"], entry["kind"],
                          entry["ref"])
                return None
            return dict(entry)
        return None

    def _release(self, entry: dict) -> None:
        """The claimed `entry` leaves the queue: its apply ended, whatever it came to."""
        with self._held():
            kept = [e for e in self._queue if e["id"] != entry["id"]]
            if len(kept) != len(self._queue):
                self._queue = kept
                self._save()

    def _mine(self, entry: dict) -> bool:
        return entry.get("scope", "") == self._scope

    def _stale(self, entry: dict) -> str:
        """Why `entry` must not be applied now, or "" (ADR-0055 D5, never backwards)."""
        if self._superseded is not None:
            why = self._superseded({**entry, "ticket": self._ticket_of(entry)})
            if why:
                return why
        before = entry["payload"].get("before") if entry["kind"] == "assignees" else None
        if before is not None and hasattr(self._inner, "assignees"):
            now = list(self._inner.assignees(entry["ref"]))
            if sorted(now) != sorted(before):
                return f"its assignees were changed meanwhile (now {', '.join(now) or 'nobody'})"
        return ""

    def _write(self, kind: str, ref: str, extra: tuple, payload: dict,
               call: Callable[[], Any]) -> Any:
        self.flush()
        ticket = self.ticket(ref)
        key = (kind, ticket, *extra)
        with self._held():
            behind = [e["reset_at"] for e in self._queue
                      if self._mine(e) and self._ticket_of(e) == ticket]
            if behind:
                self._enqueue(key, ref, payload, max(behind), "waiting behind")
                return _QUEUED
        try:
            return call()  # the forge call, with the lock released
        except RateLimited as exc:
            with self._held():
                self._enqueue(key, ref, payload, exc.reset_at, redact(str(exc)))
            return _QUEUED

    def _enqueue(self, key: tuple, ref: str, payload: dict, reset_at: float, why: str) -> None:
        queued_at = self._clock()
        ident = hashlib.sha256(f"{self._scope}|{json.dumps(key)}|{queued_at}|{os.getpid()}"
                               .encode()).hexdigest()[:10]
        self._queue = [e for e in self._queue
                       if not (self._mine(e) and e["key"] == list(key) and not e.get("claimed"))]
        self._queue.append({"id": ident, "key": list(key), "kind": key[0], "scope": self._scope,
                            "ticket": key[1], "ref": ref, "payload": payload,
                            "queued_at": queued_at, "reset_at": reset_at})
        self._save()
        tag = ("BEEVERFORGE_TICKET_STATE_UNRECORDED" if key[0] == "state"
               else "BEEVERFORGE_EFFECT_QUEUED")
        # A COMMENT IS NAMED, NEVER QUOTED (review of #708): its body is a person's words and
        # may hold a credential; the line names the kind, the entry and the length
        what = (f"a comment of {len(payload['body'])} characters" if key[0] == "comment"
                else {k: v for k, v in payload.items() if k != "before"})
        log.error("%s ticket=%s entry=%s %s (%s) — queued, to be applied after reset_at=%s",
                  tag, ref, ident, what, why[:160], reset_at)

    def _apply(self, e: dict) -> None:
        p, ref = e["payload"], e["ref"]
        if e["kind"] == "state":
            self._inner.set_state(ref, JobState(p["state"]), needs_person=p.get("needs_person"))
        elif e["kind"] == "comment":
            self._inner.comment(ref, p["body"])
        elif e["kind"] == "assignees":
            self._inner.set_assignees(ref, p["logins"])
            self._assigned[self._ticket_of(e)] = list(p["logins"])
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

    def _save(self) -> bool:
        """Write the queue; False when it could not be, and the change is then kept in memory
        and written again at the next operation on the queue."""
        if not self._path:
            return True
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
            self._dirty = True
            log.error("the queued tracker effects could not be saved to %s (%s) — the change is "
                      "kept in this process's memory and written again at its next operation on "
                      "the queue; it is lost if the process stops first", self._path, exc)
            return False
        self._dirty = False
        self._base = _ids(self._queue)
        return True


_QUEUED = object()
