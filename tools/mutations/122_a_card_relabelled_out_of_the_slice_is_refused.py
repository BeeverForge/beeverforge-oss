"""#122, proven by breaking it — a card relabelled out of the slice is refused before the sweep.

The product role's board snapshot is refreshed with `list_tickets(updated_since=…)` within the
project's scope, so a card relabelled out of a shared Jira project's slice stays in it until the
full sweep. `_close_one` (and `withdraw_card` through it) and `correct_card` now ask the board's
`holds` for the card, through `ProductModule._outside_the_slice`, as `promote` does.

THREE CLAIMS:

  1. **The close asks.** Without the question, a card another project now owns is closed.
  2. **The correction asks.** Without it, that card's text is rewritten.
  3. **Two answers, not one.** `False` is refused by name; `None` is a failure, never "inside";
     `True` goes on.

The guard is `tests/test_a_card_relabelled_out_of_the_slice_is_refused_before_the_next_sweep.py`.
"""

TEST = "tests/test_a_card_relabelled_out_of_the_slice_is_refused_before_the_next_sweep.py"

MODULE = "beeverforge/product/module.py"

MUTATIONS = [
    ("the close never asks the slice, so another project's card is closed", MODULE,
     '        outside = self._outside_the_slice(number, act=f"close #{number}", language=lang)\n',
     "        outside = None\n"),

    ("the correction never asks the slice, so another project's card is rewritten", MODULE,
     '        outside = self._outside_the_slice(number, act=f"correct #{number}", language=lang)\n',
     "        outside = None\n"),

    ("a board that could not say is read as inside the slice", MODULE,
     "        if inside is True:\n            return None\n        if inside is False:\n",
     "        if inside is not False:\n            return None\n        if inside is False:\n"),

    ("another project's card is answered as an unreadable board", MODULE,
     "        if inside is True:\n            return None\n        if inside is False:\n",
     "        if inside is True:\n            return None\n        if False:\n"),

    ("the guard refuses every card, also one still in the slice", MODULE,
     "        if inside is True:\n            return None\n        if inside is False:\n",
     "        if False:\n            return None\n        if inside is False:\n"),

    ("a board without `holds` is read as outside the slice", MODULE,
     "        inside = holds(str(number)) if callable(holds) else True\n"
     "        if inside is True:\n",
     "        inside = holds(str(number)) if callable(holds) else False\n"
     "        if inside is True:\n"),
]
