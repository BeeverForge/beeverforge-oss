"""A fake engine on which OpenFactory 0.7 left nothing running (#264, review of #500).

Until 1.0 a breakdown's start, its "is it running", and the catalog's door first ask the engine for
0.7's breakdown of the same requirement (`breaking.former_running`), because one 0.7 started keeps
0.7's id and the engine's one-execution-per-id refusal never sees it. A fake engine written before
that question existed has no answer to it. This is the answer of a deployment that was never 0.7, or
whose 0.7 breakdowns have ended: NOT_FOUND, exactly as the engine says it.

Only 0.7's ids are answered here. A fake that never handed out handles still refuses every other id,
by name, so nothing a test asserted about the handles it DID hand out changes; a fake that records
which execution a caller waited on answers 0.7's id here before it records, so its record still
holds only BeeverForge's executions.
"""

from __future__ import annotations

from temporalio.service import RPCError, RPCStatusCode

from beeverforge.runtime.temporal import FORMER_WORKFLOW_ID_PREFIX


def is_0_7s(workflow_id: str) -> bool:
    """Whether `workflow_id` is one OpenFactory 0.7 would have given (`FORMER_WORKFLOW_ID_PREFIX`)."""
    return str(workflow_id).startswith(FORMER_WORKFLOW_ID_PREFIX)


class Absent:
    """A handle on a workflow the engine does not hold: every question is the engine's NOT_FOUND."""

    def __init__(self, workflow_id: str) -> None:
        self.id = workflow_id

    def _not_found(self) -> RPCError:
        return RPCError(f"workflow not found for ID: {self.id}", RPCStatusCode.NOT_FOUND, b"")

    async def describe(self, *_a, **_k):
        raise self._not_found()

    async def query(self, *_a, **_k):
        raise self._not_found()

    async def signal(self, *_a, **_k):
        raise self._not_found()

    async def result(self, *_a, **_k):
        raise self._not_found()


class HoldsNoFormerWorkflow:
    """For a fake engine client that has no `get_workflow_handle` of its own: 0.7's ids are answered
    as absent, and any other id is refused by name — the fake never handed out handles, and still
    does not."""

    def get_workflow_handle(self, workflow_id, **_kw):
        if is_0_7s(workflow_id):
            return Absent(workflow_id)
        raise AssertionError(f"this fake engine holds no handle on {workflow_id!r}")
