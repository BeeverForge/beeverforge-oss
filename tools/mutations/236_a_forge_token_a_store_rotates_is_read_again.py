"""#236: a forge token a rotating credential store answers is read again before it expires.

Each cut breaks one claim `tests/test_a_forge_token_a_store_rotates_is_read_again.py` holds: the
re-read itself and where each runner is handed it, the lifetime it is held for and its setting,
the fake clock reaching the machinery, and what must not change — the environment, a PAT, the App
trio, a refusal that is final, and no value in a log.
"""

TEST = "tests/test_a_forge_token_a_store_rotates_is_read_again.py"
CRED = "beeverforge/credentials.py"
FACTORY = "beeverforge/factory.py"
SHORT = "beeverforge/adapters/credential/short_lived.py"

MUTATIONS = [
    ("the re-read is cut: the store is never asked again, the first token is answered", CRED,
     "        found = _axis_answer(project, axis, generic, announce=False)\n"
     "        refused = found.refused\n",
     "        found = credential_store.Answer(reference=reference, value=first)\n"
     "        refused = found.refused\n"),

    ("the job runner's forge is composed with no provider beside a stored token, as on main",
     FACTORY,
     "        # expired one. `stored_token_provider` is None for the environment and a PAT, as "
     "before.\n"
     "        forge=build_forge(project, token=forge_token_for(project),\n"
     "                          token_provider=(stored_token_provider(project, \"forge\")\n",
     "        # expired one. `stored_token_provider` is None for the environment and a PAT, as "
     "before.\n"
     "        forge=build_forge(project, token=forge_token_for(project),\n"
     "                          token_provider=(None\n"),

    ("the job runner's tracker keeps the token it was composed with", FACTORY,
     "                              token_provider=(stored_token_provider(project, \"tracker\")\n"
     "                                              if tracker_token_for(project)\n"
     "                                              else deployment_tracker_provider(project))),\n"
     "        # A TOKEN A ROTATING",
     "                              token_provider=(None\n"
     "                                              if tracker_token_for(project)\n"
     "                                              else deployment_tracker_provider(project))),\n"
     "        # A TOKEN A ROTATING"),

    ("the promotion runner's forge keeps the token it was composed with", FACTORY,
     "        # …and here, for the same reason (#236): see `build_runner`\n"
     "        forge=build_forge(project, token=forge_token_for(project),\n"
     "                          token_provider=(stored_token_provider(project, \"forge\")\n",
     "        # …and here, for the same reason (#236): see `build_runner`\n"
     "        forge=build_forge(project, token=forge_token_for(project),\n"
     "                          token_provider=(None\n"),

    ("held no longer: every use reads the store again", CRED,
     "        token = held()\n",
     "        held.forget()\n        token = held()\n"),

    ("the lifetime setting is ignored", CRED,
     "    raw = (os.environ.get(STORED_TOKEN_TTL_VAR) or \"\").strip()\n",
     "    raw = \"\"\n"),

    ("the machinery measures by the wall clock, whatever clock it is handed", SHORT,
     "        self._clock = clock or time.time\n",
     "        self._clock = time.time\n"),

    ("the environment is wrapped too", CRED,
     "    reference = _held_in_a_store(project, axis)\n"
     "    if not reference:\n        return None\n",
     "    reference = _held_in_a_store(project, axis) or \"env:\"\n"),

    ("a PAT is read again like an installation token", CRED,
     "    if not first or first.startswith(_NO_LIFETIME):\n",
     "    if not first:\n"),

    ("a stored token beside the App trio is wrapped", CRED,
     "    if _deployment_provider(getattr(project, axis, None)) is not None:\n"
     "        return None\n",
     ""),

    ("a refusal at the re-read is answered by the stale token", CRED,
     "        if refused:\n            from beeverforge.adapters.github_cli import LoginRefused\n",
     "        if False:\n            from beeverforge.adapters.github_cli import LoginRefused\n"),

    ("the re-read token reaches a log", CRED,
     "        last = found.value\n",
     "        last = found.value\n        log.info(\"re-read %s\", last)\n"),
]
