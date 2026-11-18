"""#236: a forge token a rotating credential store answers is read again during a job.

Each cut breaks one claim `tests/test_a_forge_token_a_store_rotates_is_read_again.py` holds: the
re-read itself and where each runner is handed it; the short interval it comes on, not the
lifetime's end; held between reads, one read for eight callers, and a first use after the interval
reading again; the lifetime, its setting, and a setting that is not a finite number; the fake clock
reaching the machinery; one read per axis while composing; and what must not change — the
environment, a vendor that reads its own credential, a PAT, the App trio, a refusal or a store
that answers nothing said by name, each read's own answer, and no value in a log.

The review of ebf9c9d found three cuts that survived (an unchecked lifetime, the expired token
handed out when the store answers nothing, a sticky refusal), and the review of a6a8e4e two more
(a lifetime under ten minutes, a harness's replaced pair reader) and a store that fails asked at
every call; each is a row here and red.
"""

TEST = "tests/test_a_forge_token_a_store_rotates_is_read_again.py"
CRED = "beeverforge/credentials.py"
FACTORY = "beeverforge/factory.py"
SHORT = "beeverforge/adapters/credential/short_lived.py"
REG = "beeverforge/adapters/credential_store/registry.py"

MUTATIONS = [
    # ── the re-read, and where it is handed ────────────────────────────────────────────────────
    ("the re-read is cut: the store is never asked again, the first token is answered", CRED,
     "        again = axis_answer_for(project, axis, announce=False, quiet=True)\n",
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
     "    if math.isfinite(ttl) and 0 < ttl <= STORED_TOKEN_TTL_MAX_SECONDS:\n",
     "    if ttl > 0:\n"),

    ("any lifetime is accepted unchecked (review: survived)", CRED,
     "    if math.isfinite(ttl) and 0 < ttl <= STORED_TOKEN_TTL_MAX_SECONDS:\n",
     "    if True:\n"),

    ("a finite but huge lifetime is accepted: 1e20 turns the refresh off", CRED,
     "    if math.isfinite(ttl) and 0 < ttl <= STORED_TOKEN_TTL_MAX_SECONDS:\n",
     "    if math.isfinite(ttl) and ttl > 0:\n"),

    ("a lifetime under ten minutes is still read again every five (review: survived)", CRED,
     "    interval = min(STORED_TOKEN_REREAD_SECONDS, ttl / 2)\n",
     "    interval = STORED_TOKEN_REREAD_SECONDS\n"),

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
     "        if again.value:\n            good_at = clock()\n",
     "        log.info(\"re-read %s\", again.value)\n"
     "        if again.value:\n            good_at = clock()\n"),

    # ── a store that fails (review of a6a8e4e) ─────────────────────────────────────────────────
    ("a failed re-read is retried at every call", CRED,
     "        if clock() < retry_at:\n            return None",
     "        if False:\n            return None"),

    ("the re-read asks the store loudly: its \"nothing is used\" lines beside the held token", CRED,
     "        again = axis_answer_for(project, axis, announce=False, quiet=True)\n",
     "        again = axis_answer_for(project, axis, announce=False, quiet=False)\n"),

    ("a failed re-read is not said: the provider's sentence is dropped", CRED,
     "        log.warning(\"the %s credential `%s` %s when it was read again",
     "        log.debug(\"the %s credential `%s` %s when it was read again"),

    ("a harness's replaced pair reader is bypassed (review: survived)", CRED,
     "        if reader is not _PAIR_READERS[axis]:\n",
     "        if False:\n"),

    # ── review of e8138e9 ───────────────────────────────────────────────────────────────────────
    ("a store's failure is said without what it raised", REG,
     "type(exc).__name__, exc,\n", "type(exc).__name__, \"\",\n"),

    ("the store's reason dropped from the provider's warning (review: survived)", CRED,
     "f\"was refused ({refused})\" if refused else \"answered nothing\"",
     "\"was refused\" if refused else \"answered nothing\""),

    ("`_axis_answer`'s second pair read made loud on the re-read (review: survived)", CRED,
     "    found = credential_store.chain(_GENERIC[axis], quiet=quiet)\n    return _refused_at(",
     "    found = credential_store.chain(_GENERIC[axis])\n    return _refused_at("),

    ("`axis_answer_for`'s pair reader made loud on the re-read (review: survived)", CRED,
     "        found = credential_store.chain(_GENERIC[axis], quiet=quiet)\n        pair.append(",
     "        found = credential_store.chain(_GENERIC[axis])\n        pair.append("),

    ("`axis_answer_for` quiet by default, so composition asks quietly (review: survived)", CRED,
     "def axis_answer_for(project, axis: str, *, announce: bool = True, quiet: bool = False):",
     "def axis_answer_for(project, axis: str, *, announce: bool = True, quiet: bool = True):"),

    ("`chain` quiet by default for every caller (review: survived)", REG,
     "def chain(names: Iterable[str], *, quiet: bool = False) -> Answer:",
     "def chain(names: Iterable[str], *, quiet: bool = True) -> Answer:"),

    ("the retry floor ignores the interval: always a minute (review: survived)", CRED,
     "        retry_at = clock() + min(60.0, interval)\n",
     "        retry_at = clock() + 60.0\n"),

    ("the warning says the held token is used past its lifetime", CRED,
     "                     f\"since it was read\" if clock() < good_at + ttl\n",
     "                     f\"since it was read\" if True\n"),

    ("a good re-read does not move the lifetime on: the warning counts from composition", CRED,
     "            good_at = clock()\n            return again.value, good_at + ttl\n",
     "            return again.value, clock() + ttl\n"),

    ("the retry is said as a minute whatever it is", CRED,
     "                    int(retry_at - clock()))\n",
     "                    60)\n"),
]
