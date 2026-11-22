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
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import partial

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
) -> list[dict]:
    """`jobs` without those whose workflow is not running and whose ticket is closed.

    `running` is the `(project, issue)` of every live workflow, or `None` when the engine could not
    be asked. `closed_refs(project, refs, timeout)` answers which of THOSE refs are closed, `None`
    when unreadable. Only the candidates are ever asked about (a job whose workflow runs is listed
    without a question), once per project, through `bounded` (injected so no test waits on a
    clock). The tracker is handed a budget strictly inside `timeout`, so its own call ends before
    the wait on it does."""
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
    return kept
