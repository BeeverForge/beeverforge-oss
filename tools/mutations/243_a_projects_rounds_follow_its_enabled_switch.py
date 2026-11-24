"""#243: a project's three rounds are made when it is enabled, deleted when it is disabled, and a
boot retires a registered disabled project's.

Each cut is a way the rounds drift from the switch: enabling waits for a deploy again, disabling
leaves them firing for ever, or the boot stops converging the registry's way.
"""

TEST = "tests/test_a_project_s_rounds_follow_its_enabled_switch.py"
CATALOG = "beeverforge/actions/catalog.py"
SCHED = "beeverforge/runtime/temporal/schedule.py"

MUTATIONS = [
    ("enabling a project schedules nothing until the worker restarts", CATALOG,
     "            await schedule.schedule_project_rounds(found.name)\n",
     "            pass\n"),

    ("disabling a project leaves its rounds firing", CATALOG,
     "            await schedule.retire_project_rounds(found.name)\n",
     "            pass\n"),

    ("an engine that cannot be reached raises and undoes the switch's answer", CATALOG,
     "    except Exception as exc:  # the registry write stands; the boot",
     "    except KeyError as exc:  # the registry write stands; the boot"),

    ("the watch is left out of a project's rounds", SCHED,
     "            (WATCH_SCHEDULE_PREFIX, OKF_SCHEDULE_PREFIX, CARD_QUESTION_SCHEDULE_PREFIX)]",
     "            (OKF_SCHEDULE_PREFIX, CARD_QUESTION_SCHEDULE_PREFIX)]"),

    ("a round already gone is an error rather than the state wanted", SCHED,
     "            if exc.status != RPCStatusCode.NOT_FOUND:\n"
     "                raise\n            continue\n",
     "            raise\n"),

    ("a round that already exists is left as it was instead of updated", SCHED,
     "            made.append(f\"created {sid}\")\n"
     "        except ScheduleAlreadyRunningError:\n"
     "            handle = client.get_schedule_handle(sid)\n"
     "            await handle.update(lambda _, sch=schedule: ScheduleUpdate(schedule=sch))\n"
     "            made.append(f\"updated {sid}\")\n"
     "    return made\n\n\n"
     "async def retire_project_rounds",
     "            made.append(f\"created {sid}\")\n"
     "        except ScheduleAlreadyRunningError:\n"
     "            pass\n"
     "    return made\n\n\n"
     "async def retire_project_rounds"),

    ("the boot stops retiring a disabled project's rounds", SCHED,
     "    out += await retire_disabled_rounds()\n",
     ""),

    ("the boot retires an ENABLED project's rounds", SCHED,
     "disabled = [p.name for p in ProjectRegistry().list() if not p.enabled]",
     "disabled = [p.name for p in ProjectRegistry().list()]"),
]
