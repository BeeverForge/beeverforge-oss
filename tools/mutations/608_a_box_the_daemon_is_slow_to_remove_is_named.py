"""#608: a `docker rm -f` the daemon does not finish in time is retried once, then named.

At the start of a run the leftover box's removal raised `TimeoutExpired`, a traceback before any
work; at the end, the same timeout in `run()`'s `finally` replaced the run's own outcome. Each row
undoes one part of the guard: the retry, its wait from the injected clock, the named refusal and
its remedy, every other start step's timeout, the clone a refused start leaves, the cleanup's own
clone and handle, and, in the machine, the park at each door and the report that keeps the
run's result.
"""

TEST = "tests/test_a_box_the_daemon_is_slow_to_remove_is_named.py"
BOX = "beeverforge/adapters/sandbox/container.py"
MACHINE = "beeverforge/orchestrator/machine.py"

MUTATIONS = [
    # ── the removal ──
    ("a removal that times out is not tried again", BOX,
     "    except subprocess.TimeoutExpired:\n"
     '        log.warning("the Docker daemon did not remove the box %s within %d s; trying once '
     'more in "',
     "    except subprocess.TimeoutExpired:\n"
     "        raise\n"
     '        log.warning("the Docker daemon did not remove the box %s within %d s; trying once '
     'more in "'),

    ("the retry does not wait", BOX,
     "    sleep(REMOVE_RETRY_WAIT)\n", ""),

    ("the second timeout escapes as a traceback", BOX,
     "        raise DaemonTimedOut(\n"
     "            f\"the Docker daemon did not remove the {'leftover ' * at_start}box",
     "        raise\n"
     "        raise DaemonTimedOut(\n"
     "            f\"the Docker daemon did not remove the {'leftover ' * at_start}box"),

    ("the sentence gives no remedy", BOX,
     'then = ("so this job could not start; run `docker rm -f {name}`, then resume" if at_start',
     'then = ("so this job could not start" if at_start'),

    # ── the rest of the start ──
    ("another start step's timeout escapes as a traceback", BOX,
     "        except (subprocess.TimeoutExpired, DaemonTimedOut) as exc:\n",
     "        except DaemonTimedOut as exc:\n"),

    ("a start that timed out keeps its clone", BOX,
     "                shutil.rmtree(self._starting, ignore_errors=True)\n",
     "                pass\n"),

    ("the start never records the clone it made", BOX,
     "        self._starting = host_clone\n", ""),

    # ── the cleanup ──
    ("a cleanup that could not remove the box keeps its clone", BOX,
     "        finally:\n"
     "            if self._host_clone and self._host_clone.exists():\n"
     "                shutil.rmtree(self._host_clone, ignore_errors=True)\n"
     "            self._host_clone = None",
     "        except ZeroDivisionError:\n"
     "            pass\n"
     "        if self._host_clone and self._host_clone.exists():\n"
     "            shutil.rmtree(self._host_clone, ignore_errors=True)\n"
     "        self._host_clone = None"),

    ("a cleanup that could not remove the box keeps its handle", BOX,
     "        name, self._container = self._container, None\n",
     "        name = self._container\n"),

    # ── the machine ──
    ("a cleanup that times out replaces the run's outcome", MACHINE,
     "        except DaemonTimedOut as exc:\n            said = str(exc)\n",
     "        except ZeroDivisionError as exc:\n            said = str(exc)\n"),

    ("the box left behind is not told on the card", MACHINE,
     "            self._say_on_ticket(ticket.id, said)\n\n    def _say_on_ticket(",
     "\n    def _say_on_ticket("),

    ("the box left behind is not in the log", MACHINE,
     '            log.warning("BEEVERFORGE_BOX_LEFT_BEHIND ticket=%s %s", ticket.id, said)\n', ""),

    ("a run's start that timed out is not parked", MACHINE,
     "        except DaemonTimedOut as exc:\n"
     "            # THE HOST'S DAEMON DID NOT ANSWER IN TIME (#608)",
     "        except ZeroDivisionError as exc:\n"
     "            # THE HOST'S DAEMON DID NOT ANSWER IN TIME (#608)"),

    ("a CI repair's start that timed out is not parked", MACHINE,
     "        except DaemonTimedOut as exc:\n"
     "            # The daemon did not answer in time (#608): nothing was written, as above.",
     "        except ZeroDivisionError as exc:\n"
     "            # The daemon did not answer in time (#608): nothing was written, as above."),

    ("a re-review's start that timed out is not parked", MACHINE,
     "        except DaemonTimedOut as exc:\n"
     "            # The daemon did not answer in time (#608): nothing was read, as above.",
     "        except ZeroDivisionError as exc:\n"
     "            # The daemon did not answer in time (#608): nothing was read, as above."),
]
