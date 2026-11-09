"""#415, proven by breaking it — the CPU guard on deriving the map measures a fixed input, and
still sees generation getting dearer per file.

Run:  .venv/bin/python tools/mutate.py tools/mutations/415_the_cost_guard_measures_a_fixed_input.py

THE CLAIM: `test_generating_is_fast_enough_to_do_every_time` times `generate_bundle_for` on a
repository of `FILES` files the test builds, against `FILES × PER_FILE_ALLOWANCE`, so this
repository's growth cannot fail it — and generation that costs several times more per file
still does. Every row is COST-ONLY: the map it produces is byte-identical (duplicate imports
land in a set, a re-parsed tree is the same tree), so only the cost guard can see it.

Pin it away from other measurements (`taskset -c 8-11 …`) on a shared machine: the guard reads
CPU time, which a loaded machine still inflates.
"""

TEST = "tests/test_knowledge_derived_not_cached.py::test_generating_is_fast_enough_to_do_every_time"

GENERATOR = "beeverforge/knowledge/generator.py"

MUTATIONS = [
    ("each tree's imports are walked 30 times",
     GENERATOR,
     "    for node in ast.walk(tree):\n        if isinstance(node, ast.Import):",
     "    for node in (n for _ in range(30) for n in ast.walk(tree)):\n"
     "        if isinstance(node, ast.Import):"),

    ("each Python file is parsed 25 times",
     GENERATOR,
     "                    tree = ast.parse(text)\n",
     "                    for _ in range(25):\n"
     "                        tree = ast.parse(text)\n"),

    ("each tree is unparsed and parsed again 10 times before its symbols are read",
     GENERATOR,
     "                public.update(_py_public_symbols(tree))\n",
     "                for _ in range(10):\n"
     "                    tree = ast.parse(ast.unparse(tree))\n"
     "                public.update(_py_public_symbols(tree))\n"),
]
