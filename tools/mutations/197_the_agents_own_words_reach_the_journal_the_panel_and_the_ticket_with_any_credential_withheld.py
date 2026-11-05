"""Proven by breaking it: the agent's own words reach the journal, the panel and the ticket with any
credential withheld (#197).

Claims:
  - every journal note that quotes the planner's, the executor's or a repair's words withholds a
    credential in them, on the whole text, BEFORE its `[:N]` cut;
  - every `agent_action` the harness reports reaches the journal withheld;
  - every hold, decision and assumption note `_hold` and `_record_decision` post on the ticket
    withholds it;
  - a review event's finding detail withholds it, in the description before its cut and in the file;
  - the activity payload (`agent_account`) stays raw.

One row removes each new `_without_credentials` call; four rows move a scrub after its cut, which a
token straddling the cut survives as `ghp_` and ten characters.

The guard is `tests/test_the_agents_own_words_reach_the_journal_the_panel_and_the_ticket_with_any_
credential_withheld.py`.
"""

TEST = ("tests/test_the_agents_own_words_reach_the_journal_the_panel_and_the_ticket_with_any_"
        "credential_withheld.py")
MACHINE = "beeverforge/orchestrator/machine.py"

MUTATIONS = [
    # ── the journal notes ──────────────────────────────────────────────────────────────────────
    ("the paused planner's note quotes its words as written", MACHINE,
     'f"{_without_credentials(plan_result.summary)[:200]}",',
     'f"{plan_result.summary[:200]}",'),
    ("the plan-ready note quotes the plan as written", MACHINE,
     'f"plan ready: {_without_credentials(ctx.plan)[:200]}"',
     'f"plan ready: {ctx.plan[:200]}"'),
    ("THE DEFECT ITSELF: the agent-finished note quotes the executor as written", MACHINE,
     'f"agent finished: {_without_credentials(agent_result.summary)[:200]}"',
     'f"agent finished: {agent_result.summary[:200]}"'),
    ("the agent-finished note is withheld after its cut, as #885 warned", MACHINE,
     'f"agent finished: {_without_credentials(agent_result.summary)[:200]}"',
     'f"agent finished: {_without_credentials(agent_result.summary[:200])}"'),
    ("the recovery note quotes what the executor said when it stopped, as written", MACHINE,
     'f"({_without_credentials(agent_result.summary)[:120]})"',
     'f"({agent_result.summary[:120]})"'),
    ("the recovery note is withheld after its cut", MACHINE,
     'f"({_without_credentials(agent_result.summary)[:120]})"',
     'f"({_without_credentials(agent_result.summary[:120])})"'),
    ("the recovery-finished note quotes the recovery as written", MACHINE,
     'f"{_without_credentials(agent_result.summary)[:150]}",',
     'f"{agent_result.summary[:150]}",'),
    ("the gate repair's note quotes it as written", MACHINE,
     'f"repair {attempts}: {_without_credentials(rep.summary)[:150]}"',
     'f"repair {attempts}: {rep.summary[:150]}"'),
    ("the suppression repair's note quotes it as written", MACHINE,
     '                           f"suppression-repair {supp_attempts}: "\n'
     '                           f"{_without_credentials(rep.summary)[:150]}",\n',
     '                           f"suppression-repair {supp_attempts}: "\n'
     '                           f"{rep.summary[:150]}",\n'),
    ("the review repair's note quotes it as written", MACHINE,
     '                        ticket, "note", f"review-repair {rev_attempts}: "\n'
     '                                        f"{_without_credentials(rep.summary)[:150]}",\n',
     '                        ticket, "note", f"review-repair {rev_attempts}: "\n'
     '                                        f"{rep.summary[:150]}",\n'),
    ("the CI repair's note quotes it as written", MACHINE,
     'f"ci-repair: {_without_credentials(rep.summary)[:150]}"',
     'f"ci-repair: {rep.summary[:150]}"'),
    ("the adjust pass's gate repair note quotes it as written", MACHINE,
     'f"adjust repair {attempts}: {_without_credentials(fix.summary)[:150]}"',
     'f"adjust repair {attempts}: {fix.summary[:150]}"'),

    # ── every agent_action ─────────────────────────────────────────────────────────────────────
    ("the planner's actions reach the journal as written", MACHINE,
     '"agent_action", _without_credentials(action), role="planner")',
     '"agent_action", action, role="planner")'),
    ("the executor's actions reach the journal as written", MACHINE,
     '            for action in agent_result.actions:\n'
     '                self._emit(ticket, "agent_action", _without_credentials(action), '
     'role="executor")\n',
     '            for action in agent_result.actions:\n'
     '                self._emit(ticket, "agent_action", action, role="executor")\n'),
    ("the recovery's actions reach the journal as written", MACHINE,
     '                for action in agent_result.actions:\n'
     '                    self._emit(ticket, "agent_action", _without_credentials(action),\n',
     '                for action in agent_result.actions:\n'
     '                    self._emit(ticket, "agent_action", action,\n'),
    ("the gate repair's actions reach the journal as written", MACHINE,
     '                                   _gates_brief(validations))\n'
     '                for action in rep.actions:\n'
     '                    self._emit(ticket, "agent_action", _without_credentials(action),\n',
     '                                   _gates_brief(validations))\n'
     '                for action in rep.actions:\n'
     '                    self._emit(ticket, "agent_action", action,\n'),
    ("the suppression repair's actions reach the journal as written", MACHINE,
     '                                   _suppression_repair_brief(result.suppression_details))\n'
     '                for action in rep.actions:\n'
     '                    self._emit(ticket, "agent_action", _without_credentials(action),\n',
     '                                   _suppression_repair_brief(result.suppression_details))\n'
     '                for action in rep.actions:\n'
     '                    self._emit(ticket, "agent_action", action,\n'),
    ("the review repair's actions reach the journal as written", MACHINE,
     '                        self._emit(ticket, "agent_action", _without_credentials(action),\n',
     '                        self._emit(ticket, "agent_action", action,\n'),
    ("the CI repair's actions reach the journal as written", MACHINE,
     '            for action in rep.actions:\n'
     '                self._emit(ticket, "agent_action", _without_credentials(action), '
     'role="executor")\n',
     '            for action in rep.actions:\n'
     '                self._emit(ticket, "agent_action", action, role="executor")\n'),
    ("the adjust pass's gate repair actions reach the journal as written", MACHINE,
     '            for action in fix.actions:\n'
     '                self._emit(ticket, "agent_action", _without_credentials(action), '
     'role="executor")\n',
     '            for action in fix.actions:\n'
     '                self._emit(ticket, "agent_action", action, role="executor")\n'),

    # ── what is posted on the ticket ───────────────────────────────────────────────────────────
    ("the executor's stop is posted on the ticket as written", MACHINE,
     'f"agent stopped: {_without_credentials(agent_result.summary)}"',
     'f"agent stopped: {agent_result.summary}"'),
    ("the CI repair's stop is posted on the ticket as written", MACHINE,
     'f"ci-repair agent stopped: {_without_credentials(rep.summary)}"',
     'f"ci-repair agent stopped: {rep.summary}"'),
    ("the executor's question is held on the ticket as written", MACHINE,
     '                        f"decision needed — {_without_credentials(dr.question)[:200]}",\n',
     '                        f"decision needed — {dr.question[:200]}",\n'),
    ("the executor's question is withheld after its cut", MACHINE,
     '                        f"decision needed — {_without_credentials(dr.question)[:200]}",\n',
     '                        f"decision needed — {_without_credentials(dr.question[:200])}",\n'),
    ("the planner's question is held on the ticket as written", MACHINE,
     'ticket, owner, f"decision needed — {_without_credentials(dr.question)[:200]}",',
     'ticket, owner, f"decision needed — {dr.question[:200]}",'),
    ("the planner's too-large verdict is held on the ticket as written", MACHINE,
     'f"ticket too large — {_without_credentials(split.group()).strip()[:400]}"',
     'f"ticket too large — {split.group().strip()[:400]}"'),
    ("the planner's assumption is posted and journalled as written", MACHINE,
     "            note = _without_credentials(note)",
     "            note = note"),
    ("the decision's options are posted on the ticket with its question whole", MACHINE,
     "        body = _without_credentials(body)\n",
     ""),

    # ── the review event's detail ──────────────────────────────────────────────────────────────
    ("a finding's description reaches the panel as written", MACHINE,
     '"description": _without_credentials(f.description or "")[:200],',
     '"description": (f.description or "")[:200],'),
    ("a finding's description is withheld after its cut", MACHINE,
     '"description": _without_credentials(f.description or "")[:200],',
     '"description": _without_credentials((f.description or "")[:200]),'),
    ("a finding's file reaches the panel as written", MACHINE,
     '"file": _without_credentials(f.file or ""),',
     '"file": f.file or "",'),
]
