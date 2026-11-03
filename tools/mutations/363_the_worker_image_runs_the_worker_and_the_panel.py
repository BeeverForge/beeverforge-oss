"""#363, proven by breaking it — the worker image runs the worker and the panel in one container.

FOUR CLAIMS:

  1. **`beeverforge worker --with-panel` plans the worker and the panel**, with nothing but the
     engine's variables, and refuses by name when nobody said where the engine is.
  2. **The set ends with the status of the child that ended it** — 128+N for a death by signal N —
     and the command exits with it; SIGTERM stops both children.
  3. **The panel's bind is the operator's**: `--panel-host 127.0.0.1` keeps it on the loopback.
  4. **`docs/operations.md` shows the container command** beside the compose stack's.

The guard is `tests/test_the_worker_image_runs_the_worker_and_the_panel.py`: fake children and a
fake clock, nothing started and nothing waited for.
"""

TEST = "tests/test_the_worker_image_runs_the_worker_and_the_panel.py"

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
     "    code = host.run(planned.plan, say=typer.echo, env=planned.env)\n"
     "    if code:\n        raise typer.Exit(code)\n",
     "    code = host.run(planned.plan, say=typer.echo, env=planned.env)\n"),

    ("the children are not handed the resolved environment", CLI,
     "    code = host.run(planned.plan, say=typer.echo, env=planned.env)\n",
     "    code = host.run(planned.plan, say=typer.echo)\n"),

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
]
