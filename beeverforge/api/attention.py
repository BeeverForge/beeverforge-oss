"""The attention list, minus what nobody has left to do (#651).

`/api/attention` used to list every job whose journal ENDS in an attention state. A cancelled or
terminated workflow writes `on_hold` as its last word, so a job whose ticket was closed by a merged
pull request stayed on the list for ever. A job leaves it once its workflow is not running AND its
ticket is closed.

UNKNOWN IS NOT ABSENCE. When the engine cannot say what runs, or the tracker cannot be read in
time, the entry stays listed and carries the reason in `note` — a person reading the list is told
what could not be checked instead of a job silently vanishing.

The tracker is asked ONCE PER PROJECT (its closed tickets, in bulk), never once per job.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import partial

from beeverforge.contracts.project import Project

log = logging.getLogger("beeverforge.panel")

#: The inner budget for one project's tracker read; the engine read has its own, in the route.
TRACKER_TIMEOUT_S = 8.0


def run_bounded(fn: Callable[[], object], timeout: float) -> object:
    """Run `fn` on a worker thread and give up waiting after `timeout` seconds (`TimeoutError`)."""
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        return pool.submit(fn).result(timeout=timeout)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def settle(
    jobs: list[dict],
    *,
    running: set[tuple[str, str]] | None,
    closed_refs: Callable[[str, list[str], float], set[str] | None],
    bounded: Callable[[Callable[[], object], float], object] = run_bounded,
    timeout: float = TRACKER_TIMEOUT_S,
    ending: Callable[[dict, float], object] | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> list[dict]:
    """`jobs` without those whose workflow is not running and whose ticket is closed.

    `running` is the `(project, issue)` of every live workflow, or `None` when the engine could not
    be asked. `closed_refs(project, refs, timeout)` answers which of THOSE refs are closed, `None`
    when unreadable. Only the candidates are ever asked about (a job whose workflow runs is listed
    without a question), once per project, through `bounded` (injected so no test waits on a
    clock). The tracker is handed a budget strictly inside `timeout`, so its own call ends before
    the wait on it does. `ending(job)`, when given, is called for each job dropped because its
    ticket is closed, so how it ended is written down (#652); it never raises into the list.

    THE ENDINGS SHARE ONE DEADLINE, `timeout` from the moment they start (read on `clock`, injected
    so no test waits): each `ending(job, within)` is told how much of it is left, and a job reached
    after it ran out writes nothing and stays listed with a note, for the next pass."""
    if running is None:
        return [{**j, "note": "could not tell whether its workflow still runs"} for j in jobs]
    live = {(str(j.get("project")), str(j.get("issue"))) for j in jobs} & running
    candidates: dict[str, list[str]] = {}
    for job in jobs:
        project, issue = str(job.get("project")), str(job.get("issue"))
        if (project, issue) not in live:
            candidates.setdefault(project, []).append(issue)
    inner = max(timeout / 2, timeout - 1.0)
    closed: dict[str, set[str] | str] = {}
    unread: dict[str, set[str]] = {}
    for project, refs in candidates.items():
        try:
            read = bounded(partial(closed_refs, project, refs, inner), timeout)
            closed[project] = read if isinstance(read, set) else "the tracker could not be read"
            unread[project] = set(getattr(read, "unread", ()))
        except Exception as exc:  # a failed read is listed with its reason
            log.info("attention: tracker read for %s failed: %r", project, exc)
            closed[project] = ("the tracker read timed out" if isinstance(exc, TimeoutError)
                               else f"the tracker could not be read ({type(exc).__name__})")
    kept: list[dict] = []
    deadline = clock() + timeout
    for job in jobs:
        project, issue = str(job.get("project")), str(job.get("issue"))
        verdict = closed.get(project)
        if (project, issue) in live or verdict is None:
            kept.append(job)
        elif isinstance(verdict, str):
            kept.append({**job, "note": verdict})
        elif issue in unread.get(project, ()):
            kept.append({**job, "note": "the tracker did not answer for this ticket "
                                        "(the bound ran out or its read failed)"})
        elif issue not in verdict:
            kept.append(job)
        elif ending is not None:
            within = deadline - clock()
            if within <= 0:
                kept.append({**job, "note": "its ticket is closed; the time for recording how "
                                            "it ended ran out, the next visit will"})
                continue
            try:
                ending(job, within)
            except Exception as exc:  # the list is answered whatever the ending did
                log.info("attention: ending of %s#%s failed: %r", project, issue, exc)
    return kept


def _names(data: dict, pr: str) -> bool:
    """Whether a `merged` line's data names the pull request `pr`.

    The `pr_url` field is compared for EQUALITY. A line from before the field existed is matched on
    the whole URL as a token in its `reason`: followed by the end, a space or punctuation, never by
    more of a number (`/pull/1` is not in `/pull/12`) and never preceded by more of a URL."""
    import re

    if "pr_url" in data:
        return data["pr_url"] == pr
    if not pr:
        return False
    return re.search(rf"(?<![\w/:.-]){re.escape(pr)}(?![\w/-])", str(data.get("reason") or "")) is not None


def _already_ended(project: Project, issue: str, state: str, pr: str = "") -> bool:
    """Whether this ending is in the journal already (a pass that raced, or a stale list).

    `merged` is looked for ANYWHERE in the journal, as an ending naming `pr`: a merged job that was
    resumed and held again has a later last state, and must not get a second `merged` line for the
    same pull request. Any other ending is compared with the journal's LAST state line. An
    unreadable journal is not an ending."""
    import json

    from beeverforge.paths import events_file

    try:
        lines = events_file(project, issue).read_text().splitlines()
    except OSError:
        return False
    for raw in reversed(lines):
        try:
            event = json.loads(raw)
        except ValueError:
            continue
        if event.get("kind") != "state":
            continue
        data = event.get("data") or {}
        if state == "merged":
            if event.get("message") == "merged" and "by" in data and _names(data, pr):
                return True
            continue
        return event.get("message") == state and "by" in data
    return False


#: The budget for one forge read of a pull request's state; a slower forge is unknown.
PR_STATUS_TIMEOUT_S = 5.0

#: How long the check and the append of one ending may wait for another writer of the same job.
ENDING_LOCK_TIMEOUT_S = 2.0


def end_closed(
    job: dict,
    *,
    project: Project,
    pr_status: Callable[[str, str], str],
    bounded: Callable[[Callable[[], object], float], object] = run_bounded,
    timeout: float = PR_STATUS_TIMEOUT_S,
) -> str | None:
    """Write how a held job whose ticket is closed ENDED (#652); the state written, else `None`.

    `project` is the registered project the job belongs to. `pr_status(project, pr_url)` is the
    forge's word: `merged`, `closed` or `open`, and it RAISES when it cannot say. A merged pull
    request journals ONE `merged` ending naming it, and the ending row throughput counts; a pull
    request closed without a merge journals `closed` and no row. A job with NO pull request cannot
    have merged: its closed ticket ends as `closed`, like any ticket closed without a merge.
    UNKNOWN WRITES NOTHING: a failed or timed-out read (bounded by `timeout`) or an open pull
    request is retried by the next pass.

    THE CHECK AND THE APPEND ARE ONE STEP: they run under the file lock beside the job's journal,
    so two threads or two workers ending one job leave one line. A lock not had in time writes
    nothing. The row is written first and keyed, and the journal line second, so a pass that stops
    between them is finished by the next; once the line is written a second pass finds it."""
    from beeverforge.observability.job_record import (
        BY_THE_PLATFORM,
        record_ending,
        record_job_ending,
    )
    from beeverforge.paths import events_file
    from beeverforge.util.filelock import Waited, lock_beside

    name, issue, pr = str(job.get("project")), str(job.get("issue")), str(job.get("pr_url") or "")
    status = "closed"
    if pr:
        try:
            status = str(bounded(partial(pr_status, name, pr), timeout))
        except Exception as exc:  # unknown is not absence: nothing is written
            log.info("attention: pull request of %s#%s unreadable: %r", name, issue, exc)
            return None
    if status not in ("merged", "closed"):
        return None
    try:
        with lock_beside(events_file(project, issue)).held(timeout=ENDING_LOCK_TIMEOUT_S):
            if _already_ended(project, issue, status, pr):
                return None
            if status == "merged":
                record_job_ending(project=name, issue=issue, state="merged", pr_url=pr)
                return record_ending(project, issue, "merged", by=BY_THE_PLATFORM, pr_url=pr,
                                     note=f"its ticket was closed by the merged pull request {pr}")
            note = (f"its ticket was closed and pull request {pr} was not merged" if pr
                    else "its ticket was closed and it has no pull request")
            return record_ending(project, issue, "closed", by=BY_THE_PLATFORM, note=note)
    except Waited as exc:
        log.info("attention: ending of %s#%s waited for another writer: %r", name, issue, exc)
        return None
