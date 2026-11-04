"""A staged product write the module refused, or that raised, is not `done` (#187), proven by
breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/187_a_refused_staged_write_is_not_done.py

On b5f27422 `confirm.answer_staged` answered `("done", sentence)` both when the module refused the
write and when it raised, and `catalog._product_answer` answered `done(...)`: `/api/act/
product_answer` said `ok: true` for a write that did not happen, the CLI's `--propose --yes` exited
0, and the panel's answer route returned its 200 decision payload. The claims, each a row:

  1. the gate names the outcome: a `Refused` sentence is `refused`, a crash — or a `NotDone`
     sentence, an executor's own caught crash — is `failed`;
  2. the executor says a refusal as a `Refused`, carrying the module's word, and the breakdown
     whose engine raised as a `NotDone` (review of #440);
  3. the word crosses the worker in the activity's dict;
  4. the row maps `refused` through `_not_done` (the word's code, `data.refusal`) and `failed`
     through `_failed` (500 with a reference its line names) — and the CLI exits non-zero for both;
  5. the panel's answer route answers neither with its 200 decision payload.
"""

TEST = "tests/test_a_staged_write_the_module_refused_or_raised_is_not_done.py"
REFUSED = TEST + "::test_a_staged_write_the_module_refused_answers_its_refusal_code"
RAISED = TEST + "::test_a_staged_write_whose_module_raised_answers_500_failed_with_a_reference"
CLI = (TEST + "::test_product_ask_propose_yes_exits_non_zero_for_a_refused_and_a_crashed_staged_"
       "write")
PANEL_REFUSED = (TEST + "::test_the_panels_answer_route_answers_a_refused_staged_write_with_its_"
                 "refusal_status")
PANEL_FAILED = TEST + "::test_the_panels_answer_route_answers_a_crashed_staged_write_500"
BREAKDOWN = (TEST + "::test_a_staged_breakdown_whose_engine_raised_answers_500_failed_with_a_"
             "reference")

CONFIRM = "beeverforge/product/confirm.py"
ACTIVITIES = "beeverforge/runtime/temporal/activities.py"
CATALOG = "beeverforge/actions/catalog.py"
APP = "beeverforge/api/app.py"

MUTATIONS = [
    # 1. the gate names the outcome
    ("TODAY'S DEFECT: a refused write is answered `done`", CONFIRM,
     '        outcome = "refused"\n',
     '        outcome = "done"\n',
     REFUSED),
    ("TODAY'S DEFECT: a crashed write is answered `done`", CONFIRM,
     '        sentence, kind, outcome = broke(language=lang), "broke", "failed"\n',
     '        sentence, kind, outcome = broke(language=lang), "broke", "done"\n',
     RAISED),

    ("REVIEW OF #440: a `NotDone` sentence is answered `done`", CONFIRM,
     '        outcome = "failed"\n',
     '        outcome = "done"\n',
     BREAKDOWN),

    # 2. the executor says a refusal as a `Refused`, with its word
    ("the fact's refusal is a plain sentence again", CONFIRM,
     "                              **_checked(module.note_fact, entry))\n"
     "    if not result.ok:\n"
     "        return _refused(result, lang, project=project)\n",
     "                              **_checked(module.note_fact, entry))\n"
     "    if not result.ok:\n"
     "        return _client_detail(result.detail, lang, project=project)\n",
     REFUSED),
    ("a `Refused` carries no word", CONFIRM,
     "    return Refused(head + _client_detail(detail, lang, project=project), refusal=word)\n",
     "    return Refused(head + _client_detail(detail, lang, project=project), refusal=\"\")\n",
     REFUSED),

    ("REVIEW OF #440: the breakdown that did not start is a plain sentence again", CONFIRM,
     "        return NotDone(breakdown_not_begun(number=number, language=lang))\n",
     "        return breakdown_not_begun(number=number, language=lang)\n",
     BREAKDOWN),

    # 3. the word crosses the worker
    ("the answer activity's dict drops the refusal", ACTIVITIES,
     '    return {"outcome": str(code or ""), "message": str(sentence or ""),\n'
     '            "refusal": str(getattr(sentence, "refusal", "") or "")}\n',
     '    return {"outcome": str(code or ""), "message": str(sentence or "")}\n',
     REFUSED),

    # 4. the row maps each outcome
    ("the row's refused arm drops the word, so a 404 answers 500", CATALOG,
     '        return _not_done(text, str(raw.get("refusal") or ""), did="answer the staged '
     'proposal",\n',
     '        return _not_done(text, "", did="answer the staged proposal",\n',
     REFUSED),
    ("the row's refused arm answers `done`", CATALOG,
     '        return _not_done(text, str(raw.get("refusal") or ""), did="answer the staged '
     'proposal",\n'
     "                         project=proj.name)\n",
     "        return done(text, project=proj.name, token=tok, answer=said, outcome=outcome)\n",
     REFUSED),
    ("the row's refused arm answers `done`, seen from the CLI", CATALOG,
     '        return _not_done(text, str(raw.get("refusal") or ""), did="answer the staged '
     'proposal",\n'
     "                         project=proj.name)\n",
     "        return done(text, project=proj.name, token=tok, answer=said, outcome=outcome)\n",
     CLI + "[refused]"),
    ("the row's failed arm carries no reference", CATALOG,
     '        return _failed(text, did="answer the staged proposal", project=proj.name)\n',
     "        return refused(FAILED, text, project=proj.name)\n",
     RAISED),
    ("the row's failed arm answers `done`, seen from the CLI", CATALOG,
     '        return _failed(text, did="answer the staged proposal", project=proj.name)\n',
     "        return done(text, project=proj.name, token=tok, answer=said, outcome=outcome)\n",
     CLI + "[failed]"),

    # 5. the panel's answer route
    ("the panel answers a refused write with its 200 decision payload", APP,
     '        if code == "refused":\n',
     '        if code == "never-refused":\n',
     PANEL_REFUSED),
    ("the panel answers a refused write 500, not its word's status", APP,
     '            status = _STATUS.get(_REFUSAL_CODE.get(getattr(sentence, "refusal", "")), 500)\n',
     "            status = 500\n",
     PANEL_REFUSED),
    ("the panel answers a crashed write with its 200 decision payload", APP,
     '        if code == "failed":\n',
     '        if code == "never-failed":\n',
     PANEL_FAILED),
]
