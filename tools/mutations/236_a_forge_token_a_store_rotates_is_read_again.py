"""#236: a forge token a rotating credential store answers is read again during a job.

Each cut breaks one claim `tests/test_a_forge_token_a_store_rotates_is_read_again.py` holds: the
re-read itself and where each runner is handed it; the short interval it comes on, not the
lifetime's end; held between reads, one read for eight callers, and a first use after the interval
reading again; the lifetime, its setting, and a setting that is not a finite number; the fake clock
reaching the machinery; one read per axis while composing; and what must not change — the
environment, a vendor that reads its own credential, a PAT, the App trio, a refusal or a store
that answers nothing said by name, each read's own answer, and no value in a log.

The review of ebf9c9d found three cuts that survived (an unchecked lifetime, the expired token
handed out when the store answers nothing, a sticky refusal); each is a row here and red.
"""

TEST = "tests/test_a_forge_token_a_store_rotates_is_read_again.py"
CRED = "beeverforge/credentials.py"
FACTORY = "beeverforge/factory.py"
SHORT = "beeverforge/adapters/credential/short_lived.py"

MUTATIONS = [
    # ── the re-read, and where it is handed ────────────────────────────────────────────────────
    ("the re-read is cut: the store is never asked again, the first token is answered", CRED,
     "        again = axis_answer_for(project, axis, announce=False)\n",
     "        again = credential_store.Answer(reference=reference, value=first)\n"),

    ("the job runner's forge is composed with no provider beside a stored token, as on main",
     FACTORY,
     "        # expired one. `stored_token_provider` is None for the environment and a PAT, as "
     "before.\n"
     "        forge=build_forge(project, token=forge_tok,\n"
     "                          token_provider=(stored_token_provider(project, \"forge\", "
     "forge_found)\n",
     "        # expired one. `stored_token_provider` is None for the environment and a PAT, as "
     "before.\n"
     "        forge=build_forge(project, token=forge_tok,\n"
     "                          token_provider=(None\n"),

    ("the job runner's tracker keeps the token it was composed with", FACTORY,
     "                              token_provider=(stored_token_provider(project, \"tracker\",\n"
     "                                                                    tracker_found)\n"
     "                                              if tracker_tok\n"
     "                                              else deployment_tracker_provider(project))),\n"
     "        # A TOKEN A ROTATING",
     "                              token_provider=(None\n"
     "                                              if tracker_tok\n"
     "                                              else deployment_tracker_provider(project))),\n"
     "        # A TOKEN A ROTATING"),

    ("the promotion runner's forge keeps the token it was composed with", FACTORY,
     "        # …and here, for the same reason (#236): see `build_runner`\n"
     "        forge=build_forge(project, token=forge_tok,\n"
     "                          token_provider=(stored_token_provider(project, \"forge\", "
     "forge_found)\n",
     "        # …and here, for the same reason (#236): see `build_runner`\n"
     "        forge=build_forge(project, token=forge_tok,\n"
     "                          token_provider=(None\n"),

    # ── when it is read ────────────────────────────────────────────────────────────────────────
    ("the re-read comes five minutes before the lifetime ends, not every five minutes", CRED,
     "    held = ShortLivedToken(read, margin=ttl - interval, clock=clock)\n",
     "    held = ShortLivedToken(read, margin=interval, clock=clock)\n"),

    ("held no longer: every use reads the store again", CRED,
     "        token = held()\n",
     "        held.forget()\n        token = held()\n"),

    ("a first use after the interval hands out the composed token without reading", CRED,
     "        if clock() < read_at + interval:\n",
     "        if True:\n"),

    ("a first read that fails evicts the composed token still in its lifetime", CRED,
     "        return fresh() or ((first, read_at + ttl) if clock() < read_at + ttl else None)\n",
     "        return fresh()\n"),

    ("the machinery measures by the wall clock, whatever clock it is handed", SHORT,
     "        self._clock = clock or time.time\n",
     "        self._clock = time.time\n"),

    # ── the lifetime ───────────────────────────────────────────────────────────────────────────
    ("the lifetime setting is ignored", CRED,
     "    raw = (os.environ.get(STORED_TOKEN_TTL_VAR) or \"\").strip()\n",
     "    raw = \"\"\n"),

    ("an infinite lifetime is accepted (review: survived)", CRED,
     "    if math.isfinite(ttl) and ttl > 0:\n",
     "    if ttl > 0:\n"),

    ("any lifetime is accepted unchecked (review: survived)", CRED,
     "    if math.isfinite(ttl) and ttl > 0:\n",
     "    if True:\n"),

    # ── what composing costs ───────────────────────────────────────────────────────────────────
    ("the provider reads the token again instead of taking the one the runner read", FACTORY,
     "        forge=build_forge(project, token=forge_tok,\n"
     "                          token_provider=(stored_token_provider(project, \"forge\", "
     "forge_found)\n"
     "                                          if forge_tok\n"
     "                                          else deployment_forge_provider(project))),\n"
     "        # WHICH",
     "        forge=build_forge(project, token=forge_tok,\n"
     "                          token_provider=(stored_token_provider(project, \"forge\")\n"
     "                                          if forge_tok\n"
     "                                          else deployment_forge_provider(project))),\n"
     "        # WHICH"),

    ("the job runner resolves its forge credential with no project in the ask", FACTORY,
     "(`credentials.axis_answer_for`).\n"
     "    forge_found = axis_answer_for(project, \"forge\")\n"
     "    tracker_found = axis_answer_for(project, \"tracker\")\n",
     "(`credentials.axis_answer_for`).\n"
     "    forge_found = tracker_found = the_deployments_one_answer()\n",
     "tests/test_the_forge_credential_is_per_project.py"),

    # ── what must not change ───────────────────────────────────────────────────────────────────
    ("the environment is wrapped too", CRED,
     "    if not first or reference.startswith(\"env:\") or not _stored_secret(reference):\n",
     "    if not first or not _stored_secret(reference):\n"),

    ("a vendor that reads its own credential is handed a provider it ignores", CRED,
     "    if row is not None and (row.env or row.source is not None):\n        return None\n",
     ""),

    ("a PAT is read again like an installation token", CRED,
     "    if first.startswith(_NO_LIFETIME):\n        return None\n",
     ""),

    ("a stored token beside the App trio is wrapped", CRED,
     "    if _deployment_provider(ref) is not None:\n        return None\n",
     ""),

    ("a refusal at the re-read is answered by nothing, and `gh` runs on the machine's login", CRED,
     "        token = held()\n        if token:\n",
     "        token = held()\n        if token or refused:\n"),

    ("a store that answers nothing hands out the expired token (review: survived)", CRED,
     "        from beeverforge.adapters.github_cli import LoginRefused\n\n        why = (",
     "        if not refused:\n            return first\n"
     "        from beeverforge.adapters.github_cli import LoginRefused\n\n        why = ("),

    ("a refusal is sticky: later reads are said as it (review: survived)", CRED,
     "        refused = again.refused\n",
     "        refused = refused or again.refused\n"),

    ("the re-read token reaches a log", CRED,
     "        return (again.value, clock() + ttl) if again.value else None\n",
     "        log.info(\"re-read %s\", again.value)\n"
     "        return (again.value, clock() + ttl) if again.value else None\n"),
]
