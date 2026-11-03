"""#380: a GitHub repository typed in another case is one repository to the Projects board.

The first three cuts put each comparison back to spelling, one site at a time; the last three
attack the other edge of the same line, so a fix that matched every repository would go red too.

The two board sites carry byte-identical compare lines, so each anchor starts at the line that
only its own method has above the scan: `_item_id` logs a failed add, `_existing_item_id` goes
straight from its cache to the scan.
"""

TEST = "tests/test_a_github_repository_is_one_repository_in_any_case.py"
REFS = "beeverforge/contracts/refs.py"
BOARD = "beeverforge/adapters/tracker/github_project.py"

_MOVE = ('str(exc)[:160])\n'
         '        for it in self._board_items():\n'
         '            if it.get("number") != issue_number or not it.get("id"):\n'
         '                continue\n')
_RANK = ('            return self._item_ids[key]\n'
         '        for it in self._board_items():\n'
         '            if it.get("number") != issue_number or not it.get("id"):\n'
         '                continue\n')
_FOLDED = '            if repo and it.get("repo") and it["repo"].casefold() != repo.casefold():\n'
_SPELLED = '            if repo and it.get("repo") and it["repo"] != repo:\n'
_NONE = '            if False:\n'

MUTATIONS = [
    ("qualify_ref compares by spelling, so the project's own card leaves as `Acme/api#12`", REFS,
     '    if not repo or repo.casefold() == (default_repo or "").casefold():',
     "    if not repo or repo == default_repo:",
     f"{TEST}::test_a_card_in_the_projects_repository_spelled_otherwise_is_bare"),

    ("a move compares by spelling, so the card GitHub spells `Acme/api` is never found", BOARD,
     _MOVE + _FOLDED, _MOVE + _SPELLED,
     f"{TEST}::test_a_move_finds_the_card_github_spells_otherwise"),

    ("a rank compares its anchor by spelling, so the anchor GitHub spells `Acme/api` is not found",
     BOARD, _RANK + _FOLDED, _RANK + _SPELLED,
     f"{TEST}::test_a_rank_finds_the_anchor_github_spells_otherwise"),

    ("qualify_ref takes every repository for the project's own, so a foreign card is bare", REFS,
     '    if not repo or repo.casefold() == (default_repo or "").casefold():',
     "    if True:",
     f"{TEST}::test_a_card_in_another_repository_is_still_qualified"),

    ("a move stops comparing repositories, so another repository's card #12 is moved", BOARD,
     _MOVE + _FOLDED, _MOVE + _NONE,
     f"{TEST}::test_a_move_never_takes_another_repositorys_card"),

    ("a rank stops comparing repositories, so it anchors on another repository's card #7", BOARD,
     _RANK + _FOLDED, _RANK + _NONE,
     f"{TEST}::test_a_rank_never_anchors_on_another_repositorys_card"),
]
