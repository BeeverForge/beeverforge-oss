"""#569, proven by breaking it — a project's box image is set through the catalogue.

FOUR CLAIMS:

  1. **The same image set again writes nothing.** `set_box_image` returns before saving when the
     image is the one held.
  2. **A changed image marks the recorded proof stale**, and a stale proof holds pickup.
  3. **An image that does not parse, or that the sandbox cannot honour, is refused** before anything
     is written.
  4. **The stale reason survives the file** a proof is recorded in.

The guard under test is `tests/test_a_projects_box_image_is_set_through_the_catalogue.py`.
"""

TEST = "tests/test_a_projects_box_image_is_set_through_the_catalogue.py"

REGISTRY = "beeverforge/registry.py"
PROVE = "beeverforge/box_prove.py"
CATALOG = "beeverforge/actions/catalog.py"

MUTATIONS = [
    ("the registry rewrites the file when the image is the one it holds",
     REGISTRY,
     "            if (box.get(\"image\") or \"\") == wanted:\n                return False\n",
     "            if False:\n                return False\n"),

    ("a changed image no longer marks the proof stale",
     CATALOG,
     "        marked = box_prove.mark_stale(found.name,\n"
     "                                      f\"the box image was changed ({previous} → {now})\")\n",
     "        marked = 0\n"),

    ("the gate ignores a stale proof",
     PROVE,
     "    if proof.stale:\n        return Expired(",
     "    if False:\n        return Expired("),

    ("an image that does not parse, or the sandbox cannot honour, is no longer refused",
     CATALOG,
     "    why = image_refused(wanted) if wanted else \"\"\n"
     "    if not why and wanted:\n",
     "    why = \"\"\n    if False:\n"),

    ("a proof is saved without its stale reason",
     PROVE,
     "\"toolchain\": proof.toolchain, \"stale\": proof.stale,",
     "\"toolchain\": proof.toolchain, \"stale\": \"\","),

    ("a proof is loaded without its stale reason",
     PROVE,
     "                 stale=str(data.get(\"stale\", \"\") or \"\"))",
     "                 stale=\"\")"),
]
