"""The `openfactory` command: OpenFactory 0.7's name for `beeverforge`, kept until 1.1 (#264).

A 0.7 installation's cron lines and scripts call `openfactory <command>` and parse what it prints.
The rename removed that console script outright in 0.1.0, so an upgrade in place answered them
with "command not found" before anybody read a release note. This is the same app under the old
name, and it says so.

STDOUT AND THE EXIT CODE ARE THE APP'S, UNTOUCHED. The warning is one line on stderr, said before
the app runs — a script that reads stdout or tests `$?` reads exactly what `beeverforge` gives it
(`tests/test_the_openfactory_command_and_import_still_work_until_1_1.py` runs both rows of
`[project.scripts]` on the same arguments and compares them).

ONE PLAIN LINE, OR ONE RECORD WHERE THE DEPLOYMENT LOGS JSON. A 0.7 compose file runs
`openfactory worker`, and that process's stderr is a log store's input: where
`BEEVERFORGE_LOG_FORMAT` asks for JSON lines (read after the environment is loaded the way the app
loads it, so a `.env` that sets it counts), the log is configured now — the same `configure` the
worker and the panel call, which then finds it done — and the warning is a WARNING record of it.
Anywhere else it is printed, as the CLI prints to a person at a terminal: logging is configured
only by the commands that become a deployment's processes, and before that a record would reach
stderr through `logging.lastResort`, in another module's format.
"""

from __future__ import annotations

import logging
import sys

from beeverforge.observability import logs

log = logging.getLogger("beeverforge.former_command")

#: The release that removes the `openfactory` command.
REMOVED_IN = "1.1"

WARNING = (f"warning: `openfactory` is now `beeverforge`; run `beeverforge` instead — the "
           f"`openfactory` command is removed in BeeverForge {REMOVED_IN}.")


def main() -> object:
    """The `openfactory` console script: one warning on stderr, then `beeverforge` itself."""
    from beeverforge.cli import _load_environment, app

    _load_environment()
    if logs.structured():
        logs.configure()
        log.warning(WARNING)
    else:
        print(WARNING, file=sys.stderr, flush=True)
    return app()
