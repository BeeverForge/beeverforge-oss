"""Start one JobWorkflow and wait for its result.

    python -m beeverforge.runtime.temporal.starter <project> <issue> [--sandbox container]
    [--promote]

The workflow runs on the worker (start it separately); this just kicks it off,
prints the workflow id (find it in the Temporal UI), and blocks for the outcome.
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from dotenv import load_dotenv

from beeverforge.factory import resolve_box_image
from beeverforge.registry import ProjectRegistry
from beeverforge.runtime.temporal import TASK_QUEUE
from beeverforge.runtime.temporal.connection import (
    EngineNotDeclared,
    EngineNotListening,
    connect_at_birth,
)
from beeverforge.runtime.temporal.io import JobParams
from beeverforge.runtime.temporal.workflow import JobWorkflow

log = logging.getLogger("beeverforge.starter")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("issue")
    ap.add_argument("--sandbox", default="container", choices=["worktree", "container", "fargate"])
    ap.add_argument("--promote", action="store_true")
    args = ap.parse_args()

    load_dotenv()
    # Dialled as the worker is born (#73): the bare `connect()` ended an unreachable engine in a
    # traceback; this waits a bounded time for it to listen, then says so in one sentence. An
    # engine nobody declared is refused at once, and its message is the sentence too.
    from beeverforge.observability import logs

    try:
        client = await connect_at_birth()  # dev-server or Temporal Cloud, per env
    except (EngineNotListening, EngineNotDeclared) as exc:
        raise logs.exiting(log, f"starter: {exc}") from None

    wf_id = f"beeverforge-{args.project}-{args.issue}"
    handle = await client.start_workflow(
        JobWorkflow.run,
        JobParams(
            project=args.project, issue=args.issue, sandbox=args.sandbox, promote=args.promote,
            # Resolved at launch like every other entry point, or this one quietly runs the
            # framework image for a project that declares its own (ADR-0037 D4).
            image=resolve_box_image(ProjectRegistry().get(args.project), sandbox=args.sandbox),
            adjust_passes=ProjectRegistry().get(args.project).adjust_passes,  # #448
        ),
        id=wf_id,
        task_queue=TASK_QUEUE,
    )
    print(f"started workflow id={wf_id} (run {handle.result_run_id}) — awaiting…", flush=True)
    result = await handle.result()
    print("RESULT:", result.model_dump_json(indent=2), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
