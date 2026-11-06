"""A product role whose model call fails says so, logs why, and files one impediment (#437).

Run:  .venv/bin/python tools/mutate.py tools/mutations/437_a_product_role_that_cannot_answer_says_so.py

Row 1 is the defect as it shipped: a failed answer says the requirements cannot be seen. Rows 2-6
break the report: no log line, nothing filed, an alert always promised, the board not asked again
(a ticket a person closed is taken as open), and the next answered turn closing nothing. Rows 7-8
break the draft: a harness failure read as nothing to draft, and every refused draft read as a
failure. Row 9 hands the platform's sentences back to the model. Rows 10-11 are the role no longer
saying which failure it was. Rows 12-14 are #463's review: no lock around the check and the create,
the waiting occurrence not trusting the one that filed, and the cause logged and filed unscrubbed.
"""

TEST = "tests/test_a_product_role_that_cannot_answer_says_so.py"

ENGINE = "beeverforge/product/engine.py"
ROLE = "beeverforge/product/role.py"
IMP = "beeverforge/ops/impediment.py"

MUTATIONS = [
    ("TODAY'S DEFECT: a failed answer says the requirements cannot be seen", ENGINE,
     '        return _could_not(project, getattr(answer, "error", ""), step="answer", language=lang)\n',
     "        return unavailable(language=lang)\n"),

    ("the cause is not logged", ENGINE,
     '    log.warning("BEEVERFORGE_PRODUCT_CANNOT_ANSWER project=%s step=%s — the product role\'s model "\n'
     '                "call failed: %s", getattr(project, "name", "?"), step, detail)\n',
     ""),

    ("no impediment is filed", ENGINE,
     '    ref = impediment.report(project, cause, f"{step}: {detail}", recheck=True)\n',
     '    ref = ""\n'),

    ("an alert is promised whether or not one was filed", ENGINE,
     "    alerted = bool(ref)\n",
     "    alerted = True\n"),

    ("the board is not asked again, so a ticket a person closed is taken as open", ENGINE,
     '    ref = impediment.report(project, cause, f"{step}: {detail}", recheck=True)\n',
     '    ref = impediment.report(project, cause, f"{step}: {detail}") or "known"\n'),

    ("the next answered turn closes nothing", ENGINE,
     "    _answered_again(project)\n    try:\n        _case.note_turn(",
     "    try:\n        _case.note_turn("),

    ("a draft whose harness failed reads as nothing to draft", ENGINE,
     '    if not answer.ok and getattr(answer, "harness_failed", False):\n',
     "    if False:\n"),

    ("every refused draft is reported as a failure", ENGINE,
     '    if not answer.ok and getattr(answer, "harness_failed", False):\n',
     "    if not answer.ok:\n"),

    ("the platform's sentences are read back to the model", ENGINE,
     "    return [t for t in turns\n"
     '            if not (getattr(t, "role", "") == "agent" and voice.own_voice_kind(t.text))]\n',
     "    return list(turns)\n"),

    ("the answer does not say its harness failed", ROLE,
     "                                 error=_failure_reason(res), harness_failed=True)\n",
     "                                 error=_failure_reason(res))\n"),

    ("the draft does not say its harness failed", ROLE,
     '        res = self._ask(sandbox, workspace, prompt, "product_draft")\n'
     "        if not res.ok:\n"
     '            return ProductAnswer(ok=False, raw=res.raw_output or "", error=_failure_reason(res),\n'
     "                                 harness_failed=True)\n",
     '        res = self._ask(sandbox, workspace, prompt, "product_draft")\n'
     "        if not res.ok:\n"
     '            return ProductAnswer(ok=False, raw=res.raw_output or "", error=_failure_reason(res))\n'),

    ("the board's check and create run with no lock", IMP,
     "    with _lock_for(key):\n",
     "    if True:\n"),

    ("an occurrence that waited files again instead of trusting the one that filed", IMP,
     "        if seen is not False and _LAST.get(key) is False:\n",
     "        if False:\n"),

    ("the cause is logged and filed unscrubbed", ENGINE,
     '    detail = scrub_credentials((error or "").strip())[:400] or "no cause declared"\n',
     '    detail = (error or "").strip()[:400] or "no cause declared"\n'),
]
