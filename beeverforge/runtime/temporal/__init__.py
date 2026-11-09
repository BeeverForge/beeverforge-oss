"""The Temporal durable-execution runtime (ADR-0001 D-16).

Our generic SDLC logic runs as a Temporal *workflow*; every side-effecting
adapter call is a Temporal *activity* (auto retry/timeout, resumable on crash);
the human prod-approval is a *signal*; long waits are *timers*. This is the
engine layer of the three-layer model (docs/architecture.md; the cloud realisation is drawn
in the runtime document that ships with the beeverforge-aws add-on package) — it adds
durability around the existing JobRunner/PromotionRunner without changing them.
"""

TASK_QUEUE = "beeverforge-jobs"

#: OpenFactory 0.7's task queue, POLLED BY THE WORKER UNTIL 1.0 and never a destination (#264).
#: A 0.7 deployment upgraded in place against the same Temporal server has workflows 0.7 started,
#: and activities they scheduled, waiting on this queue; a worker polling only `TASK_QUEUE` would
#: strand every one of them — a job in flight, a merge gate a person answers hours later, a deploy
#: watch. The worker runs a second `Worker` on it with the same workflows and activities; nothing
#: starts a workflow or aims a schedule at it, so it drains and stays empty. Removed in 1.0.
FORMER_TASK_QUEUE = "openfactory-jobs"


def max_concurrent_jobs() -> int:
    """The floor size — how many jobs may be IN FLIGHT at once. v1 is **1**: a single agent
    token, so tickets run strictly one at a time. The poller and the manual scan start at most
    (this − currently-running) new tickets per pass, so a batch dropped in TO-DO is picked up in
    order, one at a time, instead of all launching at once. Tunable via
    BEEVERFORGE_MAX_CONCURRENT_JOBS
    (0 pauses pickup entirely; the schedule pause is the other lever)."""
    import os

    try:
        return max(0, int(os.environ.get("BEEVERFORGE_MAX_CONCURRENT_JOBS", "1")))
    except ValueError:
        return 1
