"""#681, proven by breaking it — a refresh does not publish a map over the read ceiling.

THE CLAIMS:

  1. A document over `yaml_io.MAX_BYTES` is refused, and the refresh treats the map as unchanged.
  2. The refusal is logged once, naming the document, its size, the ceiling and the largest module.
"""

TEST = "tests/test_a_map_over_the_ceiling_is_not_published.py"

BUNDLE = "beeverforge/knowledge/bundle.py"
ACTIVITIES = "beeverforge/runtime/temporal/activities.py"

MUTATIONS = [
    ("the writer does not refuse an over-ceiling document",
     BUNDLE, "    if size > yaml_io.MAX_BYTES:\n        raise BundleOverCeiling(",
     "    if False:\n        raise BundleOverCeiling("),

    ("the refresh lets the refusal escape as a failed round",
     ACTIVITIES, "        except BundleOverCeiling as exc:",
     "        except KeyboardInterrupt as exc:"),

    ("the refresh counts the refused map as changed",
     ACTIVITIES, "            map_changed = False\n", "            map_changed = True\n"),

    ("the refusal does not name the largest module",
     BUNDLE,
     'f"read back, it would be refused and the map ignored; largest module: "\n'
     '            f"{_largest_module(bundle)}")',
     '"read back, it would be refused and the map ignored")'),

    ("the refusal is not logged",
     ACTIVITIES,
     '            activity.logger.warning("knowledge refresh for %s: %s", inp.project, exc)\n',
     ""),
]
