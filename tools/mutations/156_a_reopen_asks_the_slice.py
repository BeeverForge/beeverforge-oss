"""#156, proven by breaking it — a reopen asks the board's slice before it reopens a card by key.

`_card_reopen` reached a closed card by key through the door's closed-card row and never went
through `_stage`, so a board that reads only its project's slice (Jira's `scope_jql`, Azure's
`scope_epic`) was never asked `holds`: under a scope, api reopened web's closed card (review of
openfactory-core#884, point 3). The row now asks `holds` alone (`_reopen_refusal`) before the door,
never `columns()`: a reopen needs only "is it in the slice", not where the card sits (#378's
review).

SIX CLAIMS:

  1. **The reopen asks.** Without the check, web's closed `DAR-2` is reopened from api, and
     another Epic's closed card from an Azure project scoped to one Epic.
  2. **The question reaches `holds`.** A check that never calls it lets the reopen through.
  3. **`False` refuses by name.** Ignored, another project's card is reopened.
  4. **`None` refuses as an unreadable board.** Ignored, a slice that could not be asked reads as
     holding the card; swapped with `False`, each refusal says the other's sentence.
  5. **An unscoped board asks nothing more.** A `holds` that searches without a scope makes a
     `key =` search for every reopen.
  6. **The reopen reads no columns.** Asked through `_stage` again, an unscoped reopen reads the
     whole board, and refuses when that read fails (#378's review measured both).

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
NO_COLUMNS = f"{SLICE}::test_an_unscoped_reopen_does_not_wait_on_a_board_that_cannot_be_read"
EPIC = f"{AZURE}::test_a_card_under_another_epic_is_not_reopened_from_this_project"

ASK = "    inside = holds(issue)\n"
FALSE = "    if inside is False:\n        named = getattr(board, \"scope_named\", None)\n"
NONE = "    if inside is None:\n        return (f\"{proj.name}'s board could not be asked"
THROUGH_STAGE = ("    refusal = await asyncio.to_thread(_reopen_refusal, proj, _board, issue)\n"
                 "    if refusal:\n        return refused(CONFLICT, refusal)\n")
NOT_ASKED = ("    refusal = await asyncio.to_thread(_reopen_refusal, proj, _board, issue)\n"
             "    if False:\n        return refused(CONFLICT, refusal)\n")
STAGED = ("    place = await asyncio.to_thread(_stage, proj, _board, issue)\n"
          "    if place.cannot_tell and not place.column:\n"
          "        return refused(CONFLICT, place.cannot_tell)\n")

MUTATIONS = [
    ("the reopen never asks the slice, so another project's closed card is reopened", CATALOG,
     THROUGH_STAGE, NOT_ASKED, OUTSIDE),

    ("…and a slice that could not be asked reads as holding the card", CATALOG,
     THROUGH_STAGE, NOT_ASKED, UNREADABLE),

    ("…and another Epic's closed card is reopened from an Azure project", CATALOG,
     THROUGH_STAGE, NOT_ASKED, EPIC),

    ("`holds` is never called, so the reopen reads another project's card as this one's", CATALOG,
     ASK, "    inside = True\n", OUTSIDE),

    ("`False` is ignored, and another project's closed card is reopened", CATALOG,
     FALSE, "    if False:\n        named = getattr(board, \"scope_named\", None)\n", OUTSIDE),

    ("`None` is ignored, and a slice that could not be asked reads as holding the card", CATALOG,
     NONE, "    if False:\n        return (f\"{proj.name}'s board could not be asked", UNREADABLE),

    ("an unscoped board searches the slice for every card it reopens", BOARD,
     "        if not self._scope():\n            return True\n        key = canonical_ref(ref)\n",
     "        key = canonical_ref(ref)\n",
     UNSCOPED),

    ("the reopen goes through `_stage` again, so an unscoped reopen reads the whole board",
     CATALOG, THROUGH_STAGE, STAGED, UNSCOPED),

    ("…and refuses when that read fails, though a closed card's reopen never needed it", CATALOG,
     THROUGH_STAGE, STAGED, NO_COLUMNS),
]
