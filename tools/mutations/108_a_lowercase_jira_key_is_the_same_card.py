"""A Jira key typed in lowercase is the same card as the one the board spells in capitals (#108).

The claims, each held by a test this plan cuts under:

  - a board read files `dar-1` under the key it returned, `DAR-1` (`contracts/refs.py::board_key`),
    so the edit/close/remove gate refuses a running card typed in lowercase as it refuses it in
    capitals, scoped or not;
  - the gate hands every row behind it the board's own spelling (`_Stage.ref`), and its refusal
    names the card that way;
  - the door reads, records and names the card as the board spells it (`Ports.seen` -> `Seen.ref`
    -> `transition`), so one card keeps one history;
  - a CLOSED card, read from its tracker and not its board, is named by the tracker's own key, so a
    reopen of `dar-1` is recorded under `DAR-1` and answered as `reopened DAR-1` (review 3, point 2);
  - the product role's queueing resolves `dar-2` to the read's spelling, and its answer echoes that
    one spelling (review 3, point 3).

K1 of #108 (`holds` comparing keys without folding case) is a row of the #752 plan, beside the
rest of `holds`'s claims.
"""

TEST = "tests/test_a_lowercase_jira_key_is_the_same_card.py"
REFS = "beeverforge/contracts/refs.py"
PORTS = "beeverforge/lifecycle/ports.py"
CARD = "beeverforge/lifecycle/card.py"
CATALOG = "beeverforge/actions/catalog.py"
PRODUCT = "beeverforge/product/module.py"

MUTATIONS = [
    ("`board_key` matches a read's key only as typed, and `dar-1` reads as a card nobody moved",
     REFS,
     "if column and str(k).upper() == folded), \"\")",
     "if column and str(k) == bare), \"\")"),

    ("`Ports.seen` names an open card as it was typed, and the door keeps a second history",
     PORTS,
     "        ref = found if found and found not in (canonical_ref(card), str(card)) else \"\"\n",
     "        ref = \"\"\n"),

    ("the door ignores the board's spelling, and records `dar-1` beside `DAR-1`", CARD,
     "        if seen.ref and seen.ref != card and card == asked:\n",
     "        if False:\n"),

    ("`_stage` hands the rows behind it the ref as typed, not the board's spelling", CATALOG,
     "    ref = found if found and found not in (canonical_ref(issue), str(issue)) else \"\"\n",
     "    ref = \"\"\n"),

    ("`_stage_refusal` names the card as it was typed, and `dar-1`'s refusal differs from "
     "`DAR-1`'s", CATALOG,
     "    issue = at.ref or issue\n",
     "    pass\n"),

    ("the queueing hands the door `dar-2` as typed, and the answer echoes a second spelling",
     PRODUCT,
     "                number = board_key(where, number) or number\n",
     "                pass\n"),

    ("a closed card is named as it was typed, and its reopen is recorded under `dar-1`", PORTS,
     "            ref = own if own != asked and own.upper() == asked.upper() else \"\"\n",
     "            ref = \"\"\n"),

    ("the reopen echoes the card as it was typed, `reopened dar-1`", CATALOG,
     "    if moved.card != canonical_ref(issue) and moved.card.upper() == canonical_ref(issue).upper():\n"
     "        issue = moved.card\n",
     "    if moved.card != canonical_ref(issue) and moved.card.upper() == canonical_ref(issue).upper():\n"
     "        pass\n"),
]
