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
    closed_refs: Callable[[str], set[str] | None],
    bounded: Callable[[Callable[[], object], float], object] = run_bounded,
    timeout: float = TRACKER_TIMEOUT_S,
) -> list[dict]:
    """`jobs` without those whose workflow is not running and whose ticket is closed.

    `running` is the `(project, issue)` of every live workflow, or `None` when the engine could not
    be asked. `closed_refs(project)` answers the refs of that project's closed tickets, `None` when
    unreadable; it is called at most once per project, through `bounded` (injected so no test waits
    on a clock)."""
    if running is None:
        return [{**j, "note": "could not tell whether its workflow still runs"} for j in jobs]
    closed: dict[str, set[str] | str] = {}
    kept: list[dict] = []
    for job in jobs:
        key = (str(job.get("project")), str(job.get("issue")))
        if key in running:
            kept.append(job)
            continue
        project = key[0]
        if project not in closed:
            try:
                read = bounded(partial(closed_refs, project), timeout)
                closed[project] = (read if isinstance(read, set)
                                   else "the tracker could not be read")
            except Exception as exc:  # a failed read is listed with its reason
                log.info("attention: tracker read for %s failed: %r", project, exc)
                closed[project] = ("the tracker read timed out" if isinstance(exc, TimeoutError)
                                   else f"the tracker could not be read ({type(exc).__name__})")
        verdict = closed[project]
        if isinstance(verdict, str):
            kept.append({**job, "note": verdict})
        elif key[1] not in verdict:
            kept.append(job)
    return kept
