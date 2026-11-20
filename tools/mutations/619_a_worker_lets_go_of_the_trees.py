"""#619, proven by breaking it — a worker lets go of the trees a test module parsed.

THE CLAIMS:

  1. **The cache lives as long as the module that filled it.** When the next test is in another
     file, or there is none, `forget()` drops every tree and undoes the freezes; while the module
     goes on, its tests share one tree per content and it stays frozen.
  2. **The session calls that hook, and after the runner's own teardown** (`trylast`), so module
     fixtures holding a tree have let go when the cache does.
  3. **A fact keeps the answer, not the tree.** `fact()` parses a content once per reader, serves
     a tree the cache already holds without parsing again, reads the bytes read this time, and is
     forgotten with the trees.
  4. **A memo keyed on a tree goes with the trees** (`per_module`): it walks a tree once, and
     `forget()` empties it, so it holds no tree the cache dropped.
  5. **The two guards over every test file keep no tree**: they ask `fact`, not `parsed`.
"""

TEST = "tests/test_a_worker_lets_go_of_the_trees_a_module_parsed.py"

HELPER = "tests/the_tree_read_once.py"
CONFTEST = "tests/conftest.py"
GUARDS = "tests/test_ci_runs_every_test_exactly_once.py"

MUTATIONS = [
    # ── 1. the module's end ────────────────────────────────────────────────────────────────────
    ("forget() keeps the trees: the cache grows for the worker's whole life again",
     HELPER, "        _trees.clear()\n", ""),

    ("forget() keeps the heap frozen for the rest of the worker's life",
     HELPER, "        gc.unfreeze()\n", ""),

    ("the hook never forgets: nothing at a module's end lets go",
     CONFTEST, "        forget_the_trees()\n", "        pass\n"),

    ("the hook forgets after every test, so a module's tests parse the same file again",
     CONFTEST, "    if nextitem is None or nextitem.path != item.path:\n", "    if True:\n"),

    ("the hook forgets only between files, so the last module's trees are never dropped",
     CONFTEST, "    if nextitem is None or nextitem.path != item.path:\n",
     "    if nextitem is not None and nextitem.path != item.path:\n"),

    # ── 2. the session calls it, last ──────────────────────────────────────────────────────────
    ("the hook runs before the runner's teardown, while module fixtures still hold trees",
     CONFTEST, "@pytest.hookimpl(trylast=True)\ndef pytest_runtest_teardown(",
     "@pytest.hookimpl\ndef pytest_runtest_teardown("),

    ("the hook is renamed, so the session never calls it",
     CONFTEST, "def pytest_runtest_teardown(item, nextitem) -> None:\n",
     "def _runtest_teardown(item, nextitem) -> None:\n"),

    # ── 3. a fact, not the tree ────────────────────────────────────────────────────────────────
    ("a fact goes through parsed(), so the tree stays in the cache",
     HELPER,
     "            held if held is not None else ast.parse(text, filename=os.fspath(path)))\n",
     "            parsed(path))\n"),

    ("a fact is not kept: the same content is parsed and read again",
     HELPER, "    if (key, read) not in _facts:\n", "    if True:\n"),

    ("a fact is keyed on the reader only, so new bytes are answered from the old ones",
     HELPER, "    if (key, read) not in _facts:\n",
     "    key = b''\n    if (key, read) not in _facts:\n"),

    ("a fact ignores the tree the cache holds and parses the content again",
     HELPER, "        held = _trees.get(key)\n", "        held = None\n"),

    ("forget() keeps the facts",
     HELPER, "    _facts.clear()\n", ""),

    ("forget() leaves the per-module memos, so they keep the dropped trees alive",
     HELPER, "    for memo in _memos:\n        memo.cache_clear()\n", ""),

    ("a per-module memo is not registered, so forget() never empties it",
     HELPER, "    _memos.append(memo)\n", ""),

    ("a per-module memo memoises nothing",
     HELPER, "    memo = functools.cache(fn)\n",
     "    memo = fn\n    memo.cache_clear = lambda: None\n"),

    # ── 4. the two guards over every test file ─────────────────────────────────────────────────
    ("the CPU-time guard reads every test file through the cache again",
     GUARDS, "            for name in fact(path, _cpu_readers_unmarked_in)]\n",
     "            for name in _cpu_readers_unmarked_in(parsed(path))]\n"),

    ("the real-daemon guard reads every test file through the cache again",
     GUARDS, "            for name, grouped in fact(path, _daemon_tests_in)}\n",
     "            for name, grouped in _daemon_tests_in(parsed(path))}\n"),
]
