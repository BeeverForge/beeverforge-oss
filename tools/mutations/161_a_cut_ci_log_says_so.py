"""#161: a failing CI log cut to its limit says it was cut, and the rule reads it as "related".

The reverses are the marker on both forges, the tail kept rather than the head, and the rule's
reading of the marker — without which a log cut before the line naming the changed file has a CI
re-run stand in for the agent.
"""

TEST = "tests/test_a_cut_ci_log_says_it_was_cut.py"
BASE = "beeverforge/adapters/forge/base.py"
GH = "beeverforge/adapters/forge/github.py"
ADO = "beeverforge/adapters/forge/azure_devops.py"
RULE = "beeverforge/runtime/repairable.py"

MUTATIONS = [
    # ── the forges cut through the helper ───────────────────────────────────────────────────────
    ("GitHub cuts its failing log bare again — a cut log reads like a whole one", GH,
     '        return truncated_tail(_redact("\\n".join(chunks)), max_chars)',
     '        return _redact("\\n".join(chunks))[-max_chars:]'),

    ("…and the same on Azure DevOps", ADO,
     '        return truncated_tail(_redact("\\n".join(chunks)), max_chars)',
     '        return _redact("\\n".join(chunks))[-max_chars:]'),

    # ── the helper ──────────────────────────────────────────────────────────────────────────────
    ("the marker is dropped: the tail is kept with nothing saying so", BASE,
     '        return (f"{LOG_CUT_MARKER} {len(text)} characters in total, the last {max_chars} "\n'
     '                f"shown. It is NOT the whole log.]\\n\\n" + kept)',
     "        return kept"),

    ("…and the reverse: a log is never cut", BASE,
     "    if len(text) > max_chars:\n        kept =",
     "    if False:\n        kept ="),

    ("the HEAD is kept instead of the tail — the failure at the log's end is dropped", BASE,
     "        kept = text[len(text) - max_chars:]", "        kept = text[:max_chars]"),

    # ── the rule ────────────────────────────────────────────────────────────────────────────────
    ("the rule ignores the marker: a cut log that names nothing visible reads as unrelated", RULE,
     "    if LOG_CUT_MARKER in log:\n        return True\n", ""),
]
