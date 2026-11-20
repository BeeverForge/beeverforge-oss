"""#614: an expired box proof is proven again by the worker — only the expiry, once, with a slot.

Each row cuts one guard of the new path and the test that holds it must go red: a hold that is
not an expiry starts a proof, the same reason starts it every tick, a proof already running is
started over, a proof starts with no free slot, a proof does not take its slot, a scan admits past
the floor, the switch does nothing, the failure sentence loses its remedy, and the channel is not
told.
"""

TEST = "tests/test_an_expired_box_proof_is_proven_again_by_the_worker.py"
ACT = "beeverforge/runtime/temporal/activities.py"
BOX = "beeverforge/box_prove.py"

MUTATIONS = [
    ("a hold that is not an expiry (never proven, failed) starts a proof too", ACT,
     "    if not isinstance(held, bp.Expired) or not bp.reprove_enabled():",
     "    if not bp.reprove_enabled():"),

    ("the same hold reason starts the proof on every tick", ACT,
     "        if not bp.reprove_due(key, held) or bp.proof_running(key):",
     "        if bp.proof_running(key):"),

    ("a proof that is already running is started over", ACT,
     "        if not bp.reprove_due(key, held) or bp.proof_running(key):",
     "        if not bp.reprove_due(key, held):"),

    ("a proof starts with no free slot on the floor", ACT,
     "        if await _floor_free() < 1:",
     "        if False:"),

    ("the start is not remembered, so the next tick starts it again", ACT,
     "        bp.note_reprove_started(key, held)",
     "        pass"),

    ("a start the row refused is remembered as done", ACT,
     "        if not outcome.ok:",
     "        if False:"),

    ("a running proof does not take its slot", ACT,
     'WorkflowType IN ("JobWorkflow", "BoxProveWorkflow") AND',
     'WorkflowType = "JobWorkflow" AND'),

    ("a scan admits cards past the slots a proof has taken", ACT,
     "    return admitted[:free]",
     "    return admitted"),

    ("the setting is ignored: the worker always proves", BOX,
     "    return (os.environ.get(\"BEEVERFORGE_BOX_REPROVE\") or \"\").strip().lower() not in "
     "_REPROVE_OFF",
     "    return True"),

    ("a stale image is no longer an expiry", BOX,
     '        return Expired(f"the image {proof.image} changed',
     '        return (f"the image {proof.image} changed'),

    ("the hold of a failed proof drops the proof's own finding and remedy", BOX,
     "    return f\"the last box proof FAILED — {what}{more} — {line(first.remedy) or run_it}\"",
     "    return f\"the last box proof FAILED — {run_it}\""),

    ("the finding's output tail reaches the hold's sentence", BOX,
     "    return redact(first[0].strip())[:200] if first else \"\"",
     "    return redact(text.strip())[:200] if first else \"\""),

    ("the channel is never told the box was proven again (default repository)", ACT,
     "        announce_reproven(inp.project, registry_name=inp.project)  "
     "# only if the worker proved it",
     "        pass"),

    ("the proven-again marker is never cleared, so it is told on every tick", BOX,
     "    path.unlink(missing_ok=True)\n    return True",
     "    return True"),

    ("a proof's lock is not seen: a running proof looks idle", BOX,
     "    except Waited:\n        return True\n    except OSError as exc:\n"
     "        log.warning(\"could not tell whether",
     "    except Waited:\n        return False\n    except OSError as exc:\n"
     "        log.warning(\"could not tell whether"),
]
