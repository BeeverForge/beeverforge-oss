"""The configuration reference names every variable the worker reads for its floor, its limits and
its state directory, with the code's own defaults (#365).

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/365_the_floor_the_limits_and_the_state_directory_are_documented.py

Rows 1-3 break the table: a row dropped, a default that is not the code's, a name the code does not
read. Rows 4-6 move the code away from the table: a default changed, a variable renamed, and an
`OPENFACTORY_*` spelling read while the table says none is.
"""

TEST = "tests/test_the_floor_the_limits_and_the_state_directory_are_documented.py"

DOC = "docs/reference/configuration.md"

MUTATIONS = [
    ("the state directory's row is dropped from the table", DOC,
     "| `BEEVERFORGE_STATE_DIR` | the directory the halves of a deployment share:",
     "| STATE_DIR | the directory the halves of a deployment share:"),

    ("the table gives the floor a default the code does not have", DOC,
     "The poller and a manual scan start at most this many minus those running. `0` pauses pickup "
     "| `1` |",
     "The poller and a manual scan start at most this many minus those running. `0` pauses pickup "
     "| `2` |"),

    ("the table names a variable the code does not read", DOC,
     "| `BEEVERFORGE_PREVIEW_MAX` | how many previews run at once | `4` |",
     "| `BEEVERFORGE_PREVIEWS_MAX` | how many previews run at once | `4` |"),

    ("the code's preview default moves away from the table", "beeverforge/preview/demand.py",
     "DEFAULT_MAX = 4\n",
     "DEFAULT_MAX = 6\n"),

    ("the code renames a turn ceiling the table names", "beeverforge/product/cap.py",
     'PER_PRODUCT_ENV = "BEEVERFORGE_PRODUCT_TURNS_PER_PRODUCT"',
     'PER_PRODUCT_ENV = "BEEVERFORGE_PRODUCT_TURNS_PER_ROOM"'),

    ("the code reads an OPENFACTORY_* spelling the table says is not read",
     "beeverforge/preview/demand.py",
     '    raw = (os.environ.get("BEEVERFORGE_PREVIEW_MAX") or "").strip()',
     '    raw = (os.environ.get("BEEVERFORGE_PREVIEW_MAX")\n'
     '           or os.environ.get("OPENFACTORY_PREVIEW_MAX") or "").strip()'),
]
