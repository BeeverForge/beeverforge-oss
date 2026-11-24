"""#680, proven by breaking it — a map records its generator, and an older one is rebuilt.

THE CLAIMS:

  1. A new bundle's manifest records the running release.
  2. A map from an older generator, or one that names none, is stale; the same or a newer release
     is not.
  3. A refresh rewrites such a map even when the sources are unchanged.
"""

TEST = "tests/test_a_map_names_the_generator_that_wrote_it.py"

BUNDLE = "beeverforge/knowledge/bundle.py"
STALENESS = "beeverforge/knowledge/staleness.py"

MUTATIONS = [
    ("the build does not record the generator",
     BUNDLE, "        generator_version=__version__,\n", ""),

    ("an older generator is not stale",
     STALENESS, "    return pad(written) < pad(running)\n", "    return False\n"),

    ("a newer generator is stale too",
     STALENESS, "    return pad(written) < pad(running)\n", "    return pad(written) != pad(running)\n"),

    ("a manifest with no recorded version is trusted",
     STALENESS, "    if written is None or running is None:\n        return True\n",
     "    if written is None or running is None:\n        return False\n"),

    ("the staleness check ignores the generator",
     STALENESS, "    if generator_is_older(bundle.manifest):\n        return True\n", ""),

    ("a refresh leaves an older generator's map when the sources are unchanged",
     BUNDLE, "not generator_is_older(existing.manifest)\n                and ", ""),
]
