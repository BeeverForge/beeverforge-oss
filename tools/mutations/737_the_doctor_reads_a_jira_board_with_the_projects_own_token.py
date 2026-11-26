"""The doctor's board and tracker probes hand the Jira tracker the token the project names (#737),
proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/737_the_doctor_reads_a_jira_board_with_the_projects_own_token.py

Each probe builds its own board or tracker, so each one resolves the token on its own; a cut puts
one probe back to the provider alone — what it was before the fix — and must turn the test red.
"""

TEST = "tests/test_the_doctor_reads_a_jira_board_with_the_projects_own_token.py"
DOCTOR = "beeverforge/doctor.py"

_PROVIDER_ONLY_BOARD = "board = build_board(project, token_provider=_board_credential(project))"

MUTATIONS = [
    ("board_columns builds its board with the provider alone", DOCTOR,
     "        board = build_board(project, token=tracker_token_for(project),\n"
     "                            token_provider=_board_credential(project))\n"
     "        if board is None:\n"
     "            return None  # no board configured",
     f"        {_PROVIDER_ONLY_BOARD}\n"
     "        if board is None:\n"
     "            return None  # no board configured"),
    ("pickup_column builds its board with the provider alone", DOCTOR,
     "        board = build_board(project, token=tracker_token_for(project),\n"
     "                            token_provider=_board_credential(project))\n"
     "        return board.pickup_column()",
     f"        {_PROVIDER_ONLY_BOARD}\n"
     "        return board.pickup_column()"),
    ("board_intake builds its board with the provider alone", DOCTOR,
     "        board = build_board(project, token=tracker_token_for(project),\n"
     "                            token_provider=_board_credential(project))\n"
     '        if board is None or not callable(getattr(board, "intake_column", None)):',
     f"        {_PROVIDER_ONLY_BOARD}\n"
     '        if board is None or not callable(getattr(board, "intake_column", None)):'),
    ("board_intake builds its tracker with the provider alone", DOCTOR,
     "        born = intake(build_tracker(project, token=tracker_token_for(project),\n"
     "                                   token_provider=_board_credential(project)), board)",
     "        born = intake(build_tracker(project, token_provider=_board_credential(project)), "
     "board)"),
    ("board_stages builds its board with the provider alone", DOCTOR,
     "        board = build_board(project, token=tracker_token_for(project),\n"
     "                            token_provider=_board_credential(project))\n"
     "        if board is None:\n"
     "            return None\n"
     "        names = board.column_names()",
     f"        {_PROVIDER_ONLY_BOARD}\n"
     "        if board is None:\n"
     "            return None\n"
     "        names = board.column_names()"),
    ("api_budget builds its tracker with the provider alone", DOCTOR,
     "            return build_tracker(project, token=tracker_token_for(project),\n"
     "                                 token_provider=_board_credential(project)).budget()",
     "            return build_tracker(project, token_provider=_board_credential(project))"
     ".budget()"),
]
