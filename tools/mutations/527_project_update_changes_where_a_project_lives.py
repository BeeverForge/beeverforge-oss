"""#527: `project_update` changes where a registered project's repository, tracker or CI is, and
only that.

THE CLAIMS, each broken on purpose below:

  1. **A call with nothing to change, or a field the row does not take, is refused** and writes
     nothing.
  2. **Every refusal `project_add` makes is made here** — the host, the coordinates, the second
     organisation, the shared slug — by the same functions, with the entry as it was.
  3. **An unregistered name is NOT_FOUND**, and nothing is written.
  4. **A call that matches what is held says `changed: false` and does not rewrite the file.**
  5. **The audit record is `perform`'s, one per call**.
  6. **Two calls on one project lose neither** — the entry is read under the registry's lock.

The guard under test is
`tests/test_a_registered_projects_repository_tracker_and_ci_are_changed_by_one_action.py`.
"""

TEST = "tests/test_a_registered_projects_repository_tracker_and_ci_are_changed_by_one_action.py"
CATALOG = "beeverforge/actions/catalog.py"
DOOR = "beeverforge/actions/__init__.py"
REGISTRY = "beeverforge/registry.py"

MUTATIONS = [
    ("a call with nothing to change is accepted", CATALOG,
     "    if not any(given.values()):\n        return refused(INVALID, f\"{project} was not updated",
     "    if False:\n        return refused(INVALID, f\"{project} was not updated"),

    ("a field the row does not take is let through", DOOR,
     "    unexpected = [p for p in params if p not in found.parameters]\n    if unexpected:",
     "    unexpected = [p for p in params if p not in found.parameters]\n    if False:"),

    ("a foreign host is accepted by an update", CATALOG,
     "        if foreign:\n            raise _Refusal(refused(INVALID, doors.foreign_refusal(foreign), project=name,",
     "        if False:\n            raise _Refusal(refused(INVALID, doors.foreign_refusal(foreign), project=name,"),

    ("missing coordinates are written as they are", CATALOG,
     "        except doors.MissingCoordinates as exc:\n            missing = [flag.lstrip(\"-\").replace(\"-\", \"_\") for flag in exc.missing]\n            them = \"it\" if len(missing) == 1 else \"them\"\n            raise _Refusal(",
     "        except doors.MissingCoordinates as exc:\n            return {}\n            missing = [flag.lstrip(\"-\").replace(\"-\", \"_\") for flag in exc.missing]\n            them = \"it\" if len(missing) == 1 else \"them\"\n            raise _Refusal("),

    ("a second GitHub organisation or a shared slug is not asked of the new entry", REGISTRY,
     "            _refused_as_registered([o for key, o in raw.items() if key != name], project)",
     "            pass"),

    ("a refusal the registry raises is answered as done", CATALOG,
     "    except ValueError as exc:\n        return refused(CONFLICT, f\"{project} was not updated — {exc}\", project=project)",
     "    except ValueError:\n        return done(f\"updated {project!r}\", project=project, changed=True, fields=[])"),

    ("an unregistered name is refused as invalid instead of not found", CATALOG,
     "    try:\n        ProjectRegistry().get(project)\n    except KeyError:\n        return _no_such_project(project, so=\"nothing was updated\")",
     "    try:\n        ProjectRegistry().get(project)\n    except KeyError:\n        return refused(INVALID, \"no such project\", project=project)"),

    ("an unregistered name is registered by the write", REGISTRY,
     "            if name not in raw:\n                raise KeyError(name)\n            held = Project(**raw[name])\n            fields = change(held)",
     "            raw.setdefault(name, {'repo_path': 'x'})\n            held = Project(**raw[name])\n            fields = change(held)"),

    ("a call that matches what is held says it changed something", CATALOG,
     "    if not fields:\n        return done(f\"{project} is already as asked — nothing was changed\", project=project,\n                    changed=False, fields=[])",
     "    if False:\n        return done(f\"{project} is already as asked — nothing was changed\", project=project,\n                    changed=False, fields=[])"),

    ("a call that matches what is held still rewrites the file", REGISTRY,
     "            if not differing:\n                return ()\n            entry = {**raw[name]",
     "            if not differing:\n                self._save_raw(raw)\n                return ()\n            entry = {**raw[name]"),

    ("every field is written, not only the ones that differ", REGISTRY,
     "            differing = [k for k, v in wanted.items() if have.get(k) != v]",
     "            differing = list(wanted)"),

    ("the update leaves a second audit record of its own", CATALOG,
     "    # THE AUDIT RECORD IS `perform`'s, ONE PER CALL:",
     "    log.info('project_update %s changed fields=%s by=%s', project, ','.join(fields), by)\n    # THE AUDIT RECORD IS `perform`'s, ONE PER CALL:"),

    ("the audit record of an allowed call is not written", DOOR,
     '        log.info("action=%s by=%s%s ok=%s code=%s params=%s", key, by,',
     '        (log.info if not outcome.ok else (lambda *a: None))("action=%s by=%s%s ok=%s code=%s params=%s", key, by,'),

    ("the entry is read before the lock is held, so two updates lose one", REGISTRY,
     "        with self._locked():\n            raw = self._load_raw()\n            if name not in raw:\n                raise KeyError(name)\n            held = Project(**raw[name])",
     "        raw = self._load_raw()\n        if name not in raw:\n            raise KeyError(name)\n        held = Project(**raw[name])\n        with self._locked():"),
]
