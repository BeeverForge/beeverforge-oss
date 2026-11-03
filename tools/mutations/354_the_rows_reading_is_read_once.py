"""The installation's reading is read once per function per process, and reads exactly what the
plain walk reads (#354), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/354_the_rows_reading_is_read_once.py

`_reached` keeps every walk state's closure, found by a Tarjan visit, where the plain `_walk`
re-walked every shared function once per catalogue row; and the tables both read through are each
read once, more narrowly than a full walk. Each row below is a wrong cache aimed at the test that
must see it. The claims, each a group of rows:

  1. the closure cache reads what the plain walk reads, row by row and command by command
     (`test_the_cached_reading_reads_exactly_what_the_plain_walk_reads`): a cache keyed without
     what a caller hands the callee's parameters, and a member of a component given only its own
     part, are each seen there;
  2. and round cycles the package's graph does not trip
     (`test_the_cached_reading_is_the_plain_walk_round_every_cycle`): a state kept before its
     component is finished (a closure cut by a cycle), a cycle back onto the stack that does not
     hold the component open, and a member given its own part again, are each seen on a graph of
     four functions read in every order. The first two SURVIVED the row and command test on
     c24f871 — every row's and command's closure came out right through both, because no later
     reading started inside a component one had kept early — so they are aimed at the graph
     made to show them;
  3. what the tables read once is what a full walk reads
     (`test_what_the_reading_reads_once_is_what_a_full_walk_reads`): a function's nodes that skip
     its lists, imports read off statements that skip an `except` clause, and the writers' names
     counted in too few modules, are each seen.
"""

TEST = "tests/test_the_installation_is_changed_through_its_rows.py"
SAME = TEST + "::test_the_cached_reading_reads_exactly_what_the_plain_walk_reads"
CYCLES = TEST + "::test_the_cached_reading_is_the_plain_walk_round_every_cycle"
ONCE = TEST + "::test_what_the_reading_reads_once_is_what_a_full_walk_reads"

MUTATIONS = [
    # ── 1 and 2. the closure cache is the plain walk's reading ──────────────────────────────────
    ("the cache is keyed on the callee alone: what its caller handed its parameters is dropped",
     TEST,
     "            nxt = (door, *callee)\n",
     "            nxt = (door, callee[0], callee[1], frozenset())\n",
     SAME),
    ("a state's closure is kept the moment its own visit ends, though a cycle cut it short", TEST,
     "    partial[state] = (writers, entered)\n",
     "    partial[state] = (writers, entered)\n"
     "    _CLOSURES[state] = (frozenset(writers), frozenset(entered))\n",
     CYCLES),
    ("each member of a component is given its own part, not the component's union", TEST,
     "        for m in members:\n            _CLOSURES[m] = closure\n",
     "        for m in members:\n"
     "            _CLOSURES[m] = (frozenset(partial[m][0]), frozenset(partial[m][1]))\n",
     SAME),
    ("each member of a component is given its own part, read round a cycle", TEST,
     "        for m in members:\n            _CLOSURES[m] = closure\n",
     "        for m in members:\n"
     "            _CLOSURES[m] = (frozenset(partial[m][0]), frozenset(partial[m][1]))\n",
     CYCLES),
    ("a callee still on the stack is skipped, and does not hold the component open", TEST,
     "                low[state] = min(low[state], low[nxt])\n",
     "                pass\n",
     CYCLES),

    # ── 3. the tables read once read what a full walk reads ─────────────────────────────────────
    ("a function's nodes skip what its fields hold in lists", TEST,
     "                out += [item for item in field if isinstance(item, ast.AST)]\n",
     "                pass\n",
     ONCE),
    ("imports are read off statements that skip an `except` clause", TEST,
     "_STATEMENTS = (ast.stmt, ast.excepthandler, ast.match_case)\n",
     "_STATEMENTS = (ast.stmt, ast.match_case)\n",
     ONCE),
    ("the writers' names are counted only in the modules that hold a writer", TEST,
     '        if every_module or _could_define(path.read_text(encoding="utf-8"), said)\n',
     '        if every_module or path.name in ("registry.py", "people.py")\n',
     ONCE),
]
