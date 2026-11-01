"""#295: a `429` in a card key or an email is not throttling; a real HTTP 429 still is.

The 429 is read only where the park lines put the HTTP status, and the tracker's credential
sentences are read before throttling. Each anchor is dropped on its own, so every one is proven by
a line that needs it. The reverses carry the replay safety: a job parked under the bare `429` must
keep replaying it, so the gate must be honoured and both workflow calls must pass it.
"""

TEST = "tests/test_a_429_in_a_card_key_or_email_is_not_throttling.py"
CLASSIFY = "beeverforge/techlead/classify.py"
WORKFLOW = "beeverforge/runtime/temporal/workflow.py"

_ANCHORED = ('    (TRANSIENT, _throttled(r"(?:(?:^|failed:|→|->|\\bhttp)[\\s:=]*|"\n'
             '                           r"(?:\\bstatus(?: code)?|\\bcode|\\berror)[\\s:=]+)429\\b"), '
             '"throttled"),')


def _without(alternative: str) -> str:
    """The anchored rule with one status position cut out of it."""
    return _ANCHORED.replace(alternative, "", 1)


MUTATIONS = [
    # ── the original defect ─────────────────────────────────────────────────────────────────────
    ("the bare `429` comes back, so `DAR-429`'s 404 is throttling again", CLASSIFY,
     _ANCHORED, '    (TRANSIENT, _throttled(r"429\\b"), "throttled"),'),

    ("the credential sentences are no longer read first, so `ops429@acme.ai` is not a credential",
     CLASSIFY,
     '    (CREDENTIAL, re.compile(r"different accounts|no api token reached|no email reached", '
     're.I),\n     "credential"),\n',
     ""),

    # ── each status position is needed by a real 429 ───────────────────────────────────────────
    ("a line that starts with 429 (github_app) is no longer a status", CLASSIFY,
     _ANCHORED, _without("^|")),
    ("Jira's `failed: 429` is no longer a status", CLASSIFY,
     _ANCHORED, _without("failed:|")),
    ("Azure DevOps' `→ 429` is no longer a status", CLASSIFY,
     _ANCHORED, _without("→|")),
    ("the ASCII `-> 429` is no longer a status", CLASSIFY,
     _ANCHORED, _without("->|")),
    ("gh's `HTTP 429` is no longer a status", CLASSIFY,
     _ANCHORED, _without("|\\bhttp")),
    ("an agent harness's `API Error: 429` is no longer a status", CLASSIFY,
     _ANCHORED, _without("|\\berror")),
    ("`status`/`code`/`error` need no separator, so `code429@acme.ai` is a status", CLASSIFY,
     _ANCHORED, _ANCHORED.replace("[\\s:=]+)429", "[\\s:=]*)429", 1)),

    # ── replay safety ───────────────────────────────────────────────────────────────────────────
    ("the gate is ignored, so a replayed park computes the anchored verdict (TMPRL1100)",
     CLASSIFY,
     '    text = note or ""\n',
     '    anchored_429 = True\n    text = note or ""\n'),

    ("the self-heal verdict stops passing patched(), so an in-flight park replays the new rule",
     WORKFLOW,
     '                                       engine=workflow.patched("classify-engine-interrupted"),'
     '\n                                       anchored_429=workflow.patched('
     '"classify-anchored-429"),\n',
     '                                       engine=workflow.patched("classify-engine-interrupted"),'
     '\n'),

    ("the remedy's verdict stops passing patched(), so its sentence and `resume` change on replay",
     WORKFLOW,
     '                        parked.note or "", state=parked.state.value,\n'
     '                        anchored_429=workflow.patched("classify-anchored-429"),\n',
     '                        parked.note or "", state=parked.state.value,\n'),
]
