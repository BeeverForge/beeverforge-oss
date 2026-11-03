"""#363, proven by breaking it — the worker image runs the worker and the panel in one container.

SIX CLAIMS:

  1. **`beeverforge worker --with-panel` plans the worker and the panel**, with nothing but the
     engine's variables, and refuses by name when nobody said where the engine is.
  2. **The set ends with the status of the child that ended it** — 128+N for a death by signal N —
     and the command exits with it; SIGTERM stops both children.
  3. **The panel's bind is the operator's**: `--panel-host 127.0.0.1` keeps it on the loopback.
  4. **`docs/operations.md` shows the container command** beside the compose stack's, passing a
     panel token and publishing on the host's loopback.
  5. **It cannot start an open panel off the loopback** (review of #406): with no panel sign-in,
     a non-loopback `--panel-host` — the default `0.0.0.0` included — is refused by name; on the
     loopback it starts, for a sidecar.
  6. **The supervisor's own lines are the log's** (review of #406): its log is configured, and
     with JSON lines what it and `host.run` say are JSON lines, the `✗` one at ERROR.

The guard is `tests/test_the_worker_image_runs_the_worker_and_the_panel.py`: fake children and a
fake clock, nothing started and nothing waited for. A plain write put back in the supervisor is
caught by the package's sweep, `tests/test_the_logs_can_be_json_lines_that_say_the_project.py`.
"""

TEST = "tests/test_the_worker_image_runs_the_worker_and_the_panel.py"
LOGS = "tests/test_the_logs_can_be_json_lines_that_say_the_project.py"

HOST = "beeverforge/runtime/host.py"
CLI = "beeverforge/cli.py"
DOCS = "docs/operations.md"

MUTATIONS = [
    ("THE DEFECT ITSELF: the supervisor returns 0 whatever ended the set, so a dead worker's "
     "container exits clean", HOST,
     "    return ended\n",
     "    return 0\n"),

    ("a child killed by a signal reports a negative status instead of 128+N", HOST,
     "    return 128 - returncode if returncode < 0 else returncode\n",
     "    return returncode\n"),

    ("the worker is left out of `--with-panel`'s plan, so the container serves a panel that "
     "takes no cards", HOST,
     '    plan = [("worker", [sys.executable, "-m", "beeverforge.runtime.temporal.worker"]),\n'
     '            ("panel",',
     '    plan = [("panel",'),

    ("`--panel-host` is ignored and the panel always binds every interface", HOST,
     '"serve", "--host", panel_host,\n',
     '"serve", "--host", "0.0.0.0",\n'),

    ("the command drops the supervisor's status, so the container exits 0 after a death", CLI,
     "    code = host.run(planned.plan, say=say, env=planned.env)\n"
     "    if code:\n        raise typer.Exit(code)\n",
     "    code = host.run(planned.plan, say=say, env=planned.env)\n"),

    ("the children are not handed the resolved environment", CLI,
     "    code = host.run(planned.plan, say=say, env=planned.env)\n",
     "    code = host.run(planned.plan, say=say)\n"),

    ("with no engine declared the set starts anyway, and the worker's first dial ends it", CLI,
     "    if not listeners.ENGINE.declared():\n",
     "    if False:\n"),

    ("SIGTERM reaches neither child: the stop never asks them to terminate", HOST,
     "    for _, child in started:\n        with contextlib.suppress(Exception):\n"
     "            child.terminate()\n",
     "    for _, child in started:\n        with contextlib.suppress(Exception):\n"
     "            pass\n"),

    ("the operations page names a flag the command does not have", DOCS,
     "  python -m beeverforge.cli worker --with-panel\n",
     "  python -m beeverforge.cli worker --with-panels\n"),

    ("the operations page's loopback variant names a flag the command does not have", DOCS,
     "  python -m beeverforge.cli worker --with-panel --panel-host 127.0.0.1\n",
     "  python -m beeverforge.cli worker --with-panel --panel-bind 127.0.0.1\n"),

    ("the operations page shows the container command apart from the compose stack's", DOCS,
     "own container:\n\n```bash\ndocker compose --env-file .env.compose up -d --build\n```\n",
     "own container.\n"),

    ("a panel flag without --with-panel is dropped, and the worker runs alone with no panel",
     "beeverforge/cli.py",
     "    if panel_host is not None or panel_port is not None:\n",
     "    if False:\n",
     f"{TEST}::test_a_panel_flag_without_with_panel_is_refused_not_dropped"),

    ("THE REVIEW'S FINDING: the open-panel refusal is dropped, and the documented command serves an "
     "open panel on every interface", CLI,
     "    if panel_host not in listeners.THIS_MACHINE and _the_panel_would_be_open():\n",
     "    if False:\n"),

    ("the loopback is treated as open too, and the sidecar's panel cannot start without a token",
     CLI,
     "    if panel_host not in listeners.THIS_MACHINE and _the_panel_would_be_open():\n",
     "    if _the_panel_would_be_open():\n"),

    ("the operations page drops the panel token, documenting a command that is refused", DOCS,
     "  -e TEMPORAL_ADDRESS -e TEMPORAL_NAMESPACE -e TEMPORAL_API_KEY -e BEEVERFORGE_PANEL_TOKEN \\\n"
     "  ghcr.io/beeverforge/beeverforge-worker:main \\\n"
     "  python -m beeverforge.cli worker --with-panel\n",
     "  -e TEMPORAL_ADDRESS -e TEMPORAL_NAMESPACE -e TEMPORAL_API_KEY \\\n"
     "  ghcr.io/beeverforge/beeverforge-worker:main \\\n"
     "  python -m beeverforge.cli worker --with-panel\n"),

    ("the operations page publishes the panel on every interface of the host", DOCS,
     "docker run -d --restart on-failure -p 127.0.0.1:8787:8787 \\\n",
     "docker run -d --restart on-failure -p 8787:8787 \\\n"),

    ("THE REVIEW'S SECOND FINDING: the supervisor's say is `typer.echo` again, and its lines are "
     "plain among the JSON ones", CLI,
     "    code = host.run(planned.plan, say=say, env=planned.env)\n",
     "    code = host.run(planned.plan, say=typer.echo, env=planned.env)\n",
     f"{TEST}::test_with_json_lines_the_supervisors_own_lines_are_json"),

    ("the supervisor never configures its log, so `announce` prints plain lines whatever the "
     "deployment asked", CLI,
     "    logs.configure()\n    planned = _the_set_or_a_refusal(",
     "    planned = _the_set_or_a_refusal(",
     f"{TEST}::test_with_json_lines_the_supervisors_own_lines_are_json"),

    ("the line that says a child ended the set is logged at INFO, not ERROR", CLI,
     "            logs.announce(log, f\"✗ {line.removeprefix('✗ ')}\", logging.ERROR)\n",
     "            logs.announce(log, f\"✗ {line.removeprefix('✗ ')}\")\n",
     f"{TEST}::test_with_json_lines_the_supervisors_own_lines_are_json"),

    ("a plain `typer.echo` is put back in the supervisor, and the package's sweep must name it",
     CLI,
     "    for line in planned.said:\n        say(f\"! {line}\")\n",
     "    for line in planned.said:\n        typer.echo(f\"! {line}\")\n",
     f"{LOGS}::test_nothing_the_worker_or_the_panel_runs_writes_past_the_log"),
]
