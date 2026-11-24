"""#591 — one board view reads a GitHub project board once per page, proven by breaking it.

Run:
  .venv/bin/python tools/mutate.py tools/mutations/591_the_board_view_reads_a_github_board_once.py

THREE CUTS, each required to go red:

  1. The view asks for the names before the placement: the names' read then runs on an instance
     that has learned nothing yet, and pays for the project's metadata a second time.
  2. The items read stops learning the project's metadata: `_ensure_meta` fetches it again, two
     reads beside the pages.
  3. The items read learns the project but not its Status options: the read count holds, and the
     view shows no columns, which is the board the guard exists to keep correct.

The guard under test: `tests/test_the_board_view_reads_a_github_board_once.py`.
"""

TEST = "tests/test_the_board_view_reads_a_github_board_once.py"

APP = "beeverforge/api/app.py"
BOARD = "beeverforge/adapters/tracker/github_project.py"

# The items read's Status options line, told apart from `_meta_via_graphql`'s by its indent.
_PAD = " " * 50

MUTATIONS = [
    ("the view asks for the column names before the placement", APP,
     "    placed = board.columns()\n    names = board.column_names()\n",
     "    names = board.column_names()\n    placed = board.columns()\n",
     TEST),

    ("the items read no longer learns the project's metadata", BOARD,
     "            if project.get(\"id\") and not self._project_id:\n",
     "            if False:\n",
     TEST),

    ("the items read learns the project but drops the Status options", BOARD,
     _PAD + "\"options\": status.get(\"options\") or []}]\n",
     _PAD + "\"options\": []}]\n",
     TEST),
]
