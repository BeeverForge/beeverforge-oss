"""#585: a project's board column mapping is set through the catalogue, and only as the board reads it.

THE CLAIMS, each broken on purpose below:

  1. **The three refusals are real** — a column the board does not have, a stage the core does not
     define, and two stages on one column are each `INVALID` and write nothing.
  2. **A set is idempotent** — the second one says it changed nothing, and writes nothing.
  3. **The set is one audit record, allowed or refused** — the audit line belongs to the door every
     row goes through, so each half is cut separately.
  4. **What is written is what the doctor and the poller read next** — the write reaches the
     registry, merges into the options held (the board's coordinates are not the call's to lose),
     and the stages kept are merged with, not replaced by, what was asked.
  5. **The panel's strip says what the board says** — a stage with no column reads "unmapped", and
     the column names it draws are escaped.

The guard under test is `tests/test_a_projects_board_columns_are_read_and_set_through_the_catalogue.py`.
"""

TEST = "tests/test_a_projects_board_columns_are_read_and_set_through_the_catalogue.py"
CATALOG = "beeverforge/actions/catalog.py"
DOOR = "beeverforge/actions/__init__.py"
REGISTRY = "beeverforge/registry.py"
PANEL = "beeverforge/api/panel.html"

MUTATIONS = [
    ("a column the board does not have is mapped to anyway", CATALOG,
     "        if not spelled:\n            return no(f\"the board has no column {column!r} to map {stage!r} to\")",
     "        if False:\n            return no(f\"the board has no column {column!r} to map {stage!r} to\")"),

    ("a stage the core does not define is accepted", CATALOG,
     "        if stage not in BOARD_ORDER:\n            return no(",
     "        if False:\n            return no("),

    ("two stages are mapped to one column", CATALOG,
     "        if other:\n            return no(f\"{stage!r} and {other!r} cannot both be the column",
     "        if False:\n            return no(f\"{stage!r} and {other!r} cannot both be the column"),

    ("a pickup column the board does not have is accepted", CATALOG,
     "    if wanted_pickup and not (queue := on_the_board(wanted_pickup)):",
     "    if wanted_pickup and not (queue := on_the_board(wanted_pickup) or wanted_pickup):"),

    ("a set always says it changed something, though it was already so", CATALOG,
     "    changed = any(options.get(k) != v for k, v in write.items())",
     "    changed = True"),

    ("a set that changes nothing still writes", CATALOG,
     "    if changed:\n        try:\n            ProjectRegistry().set_tracker_options(project, write)",
     "    if True:\n        try:\n            ProjectRegistry().set_tracker_options(project, write)"),

    ("a set answers it was saved and writes nothing, so the doctor and the poller read the old one",
     CATALOG,
     "            ProjectRegistry().set_tracker_options(project, write)",
     "            pass"),

    ("a set replaces the stages already mapped instead of merging into them", CATALOG,
     "    merged = {**held, **chosen}",
     "    merged = dict(chosen)"),

    ("the registry replaces the tracker's options, so the board's own address is lost", REGISTRY,
     "            held.update({str(k): str(v) for k, v in options.items()})",
     "            held = {str(k): str(v) for k, v in options.items()}"),

    ("only a refused call leaves its audit record", DOOR,
     '        log.info("action=%s by=%s%s ok=%s code=%s params=%s", key, by,',
     '        (log.info if not outcome.ok else (lambda *a: None))("action=%s by=%s%s ok=%s code=%s params=%s", key, by,'),

    ("only an allowed call leaves its audit record", DOOR,
     '        log.info("action=%s by=%s%s ok=%s code=%s params=%s", key, by,',
     '        (log.info if outcome.ok else (lambda *a: None))("action=%s by=%s%s ok=%s code=%s params=%s", key, by,'),

    ("the panel's strip draws a stage with no column as an empty value", PANEL,
     """<b>${v?esc(v):'<span style="opacity:.55">unmapped</span>'}</b>""",
     """<b>${v?esc(v):''}</b>"""),

    ("the panel's strip draws a column name unescaped", PANEL,
     """<b>${v?esc(v):'<span style="opacity:.55">unmapped</span>'}</b>""",
     """<b>${v?v:'<span style="opacity:.55">unmapped</span>'}</b>"""),
]
