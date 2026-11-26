"""A decision asked in one of a person's conversations is answered there, and nowhere else (#718).

The claims, each held by a test this plan cuts under:

  - a decision asked in a private conversation records which of its owner's conversations it was
    asked in — the session id, `FIRST` for the first conversation — and a room's records none;
  - the scope `record_decisions` deduplicates by reads that session, so the same label asked in
    two sessions is two decisions;
  - only the person's message in that conversation closes it: another of their sessions, their
    first conversation, or the room does not;
  - a row recorded before, with no session, closes as it always did (the plan's last cut shows the
    old reading is still the fallback, not deleted).
"""

TEST = "tests/test_a_person_has_more_than_one_conversation.py"
E2E = "tests/test_the_speaker_and_the_reply.py"
MODULE = "beeverforge/product/module.py"

MUTATIONS = [
    ("`_asked_of` stops recording the session, and a message in any of her conversations answers",
     MODULE,
     "        scope[\"asked_session\"] = session_of(conversation) or FIRST\n",
     "        pass\n"),

    ("…and the same through the turn engine: Ana's \"bom dia\" in another session closes it",
     MODULE,
     "        scope[\"asked_session\"] = session_of(conversation) or FIRST\n",
     "        pass\n", E2E),

    ("a room's decision is given a session it does not have",
     MODULE,
     "    if is_private(conversation):\n        scope[\"asked_session\"]",
     "    if True:\n        scope[\"asked_session\"]"),

    ("`_scope_of` drops the session, so the dedup folds two sessions' decisions into one", MODULE,
     "        scope[\"asked_session\"] = session\n",
     "        pass\n", E2E),

    ("`_answered_by` ignores the session it reads", MODULE,
     "    if session:\n        # a room in `where`",
     "    if False:\n        # a room in `where`"),

    ("her first conversation is read as every session", MODULE,
     "and (session_of(w) or FIRST) == session for w in where if w)",
     "and (session_of(w) or session) == session for w in where if w)"),

    ("a message of hers in any conversation whose session id matches, whoever owns it, answers",
     MODULE,
     "        return any(sealed(owner_of(w)) == scope[\"asked_in\"]\n                   and ",
     "        return any(True\n                   and "),

    ("another person's message answers a decision asked of Ana, in her session", MODULE,
     "    if scope[\"asked_of\"] != sealed(person):\n        return False\n",
     ""),

    ("a row with no session is left open for ever instead of keeping the owner's reading", MODULE,
     "    return scope[\"asked_in\"] in {sealed(owner_of(w)) for w in where if w}",
     "    return False"),
]
