"""#156, proven by breaking it — a reopen asks the board's slice before it reopens a card by key.

`_card_reopen` reached a closed card by key through the door's closed-card row and never went
through `_stage`, so a board that reads only its project's slice (Jira's `scope_jql`, Azure's
`scope_epic`) was never asked `holds`: under a scope, api reopened web's closed card (review of
openfactory-core#884, point 3). The row now reads `_stage` before the door and refuses on its
"unreadable" and "outside the slice" answers.

FIVE CLAIMS:

  1. **The reopen asks.** Without the check, web's closed `DAR-2` is reopened from api, and
     another Epic's closed card from an Azure project scoped to one Epic.
  2. **The question reaches `holds`.** A `_stage` that reads every card `columns()` left out as
     "nobody moved it" lets the reopen through.
  3. **`False` refuses by name.** Ignored, another project's card is reopened.
  4. **`None` refuses as an unreadable board.** Ignored, a slice that could not be asked reads as
     holding the card; swapped with `False`, each refusal says the other's sentence.
  5. **An unscoped board asks nothing more.** A `holds` that searches without a scope makes a
     `key =` search for every reopen.

The guards are the four reopen tests named per row, in
`tests/test_several_projects_on_one_jira_project_read_only_their_own_slice.py` and
`tests/test_an_azure_board_can_be_scoped_to_one_epic.py`.
"""

TEST = "tests/test_several_projects_on_one_jira_project_read_only_their_own_slice.py"

CATALOG = "beeverforge/actions/catalog.py"
BOARD = "beeverforge/adapters/board/jira.py"
SLICE = TEST
AZURE = "tests/test_an_azure_board_can_be_scoped_to_one_epic.py"

OUTSIDE = f"{SLICE}::test_another_projects_closed_card_is_not_reopened_from_this_one"
UNREADABLE = f"{SLICE}::test_a_slice_that_cannot_be_asked_about_a_card_refuses_to_reopen_it"
UNSCOPED = f"{SLICE}::test_an_unscoped_reopen_asks_the_slice_nothing"
EPIC = f"{AZURE}::test_a_card_under_another_epic_is_not_reopened_from_this_project"

CHECK = "    if place.cannot_tell and not place.column:\n"

MUTATIONS = [
    ("the reopen never asks the slice, so another project's closed card is reopened", CATALOG,
     CHECK, "    if False:\n", OUTSIDE),

    ("…and a slice that could not be asked reads as holding the card", CATALOG,
     CHECK, "    if False:\n", UNREADABLE),

    ("…and another Epic's closed card is reopened from an Azure project", CATALOG,
     CHECK, "    if False:\n", EPIC),

    ("`_stage` ignores `holds`, so the reopen reads another project's card as nobody's", CATALOG,
     "inside = holds(issue) if callable(holds) else True",
     "inside = True",
     OUTSIDE),

    ("`False` is ignored, and another project's closed card is reopened", CATALOG,
     "        if inside is False:\n            # ANOTHER PROJECT'S CARD",
     "        if False:\n            # ANOTHER PROJECT'S CARD",
     OUTSIDE),

    ("`None` is ignored, and a slice that could not be asked reads as holding the card", CATALOG,
     "        if inside is None:\n            return unreadable\n        if inside is False:\n",
     "        if inside is False:\n",
     UNREADABLE),

    ("`False` and `None` swapped: another project's card is answered as an unreadable board",
     CATALOG,
     "        if inside is None:\n            return unreadable\n        if inside is False:\n",
     "        if inside is False:\n            return unreadable\n        if inside is None:\n",
     OUTSIDE),

    ("…and an unreadable slice is answered as another project's card", CATALOG,
     "        if inside is None:\n            return unreadable\n        if inside is False:\n",
     "        if inside is False:\n            return unreadable\n        if inside is None:\n",
     UNREADABLE),

    ("an unscoped board searches the slice for every card it reopens", BOARD,
     "        if not self._scope():\n            return True\n        key = canonical_ref(ref)\n",
     "        key = canonical_ref(ref)\n",
     UNSCOPED),
]
