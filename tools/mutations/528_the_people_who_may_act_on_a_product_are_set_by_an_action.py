"""The guards of `product_people_set` (#528), proven by cutting each one.

Run:  .venv/bin/python tools/mutate.py tools/mutations/528_*.py

Each row removes one guard the review asked for and names the test that must go red.
"""

TEST = "tests/test_the_people_who_may_act_on_a_product_are_set_and_read_by_an_action.py"
ROW = "beeverforge/actions/catalog.py"
PEOPLE = "beeverforge/product/people.py"
CLI = "beeverforge/cli.py"

MUTATIONS = [
    ("the row no longer refuses a person asking from a room", ROW,
     "    if by.via not in _INSTALLATION_DOORS:\n",
     "    if False:\n",
     TEST + "::test_nobody_asking_from_a_room_adds_another_person"),
    ("an id is trimmed before it is stored", PEOPLE,
     "        assert isinstance(who, str)\n",
     "        assert isinstance(who, str)\n        who = who.strip()\n",
     TEST + "::test_the_bound_is_a_thousand_and_ids_are_stored_as_given"),
    ("the bound is two hundred again", PEOPLE,
     "BOUND = 1000\n", "BOUND = 200\n",
     TEST + "::test_the_bound_is_a_thousand_and_ids_are_stored_as_given"),
    ("an over-long id is accepted", PEOPLE,
     "    if len(who) > ID_BOUND:\n", "    if False:\n",
     TEST + "::test_a_malformed_entry_is_refused_naming_it_and_writes_nothing"),
    ("a control character in an id is accepted", PEOPLE,
     '    if any(unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp") for c in who):\n',
     "    if False:\n",
     TEST + "::test_a_malformed_entry_is_refused_naming_it_and_writes_nothing"),
    ("the list is answered in the order it was set", ROW,
     'for p in sorted(admins)),', "for p in admins),",
     TEST + "::test_the_list_answers_sorted_by_role_then_person"),
    ("the audit line forgets the people changed", "beeverforge/actions/__init__.py",
     "        said = outcome.data if outcome is not None and outcome.ok else {}\n",
     "        said = {}\n",
     TEST + "::test_one_audit_record_with_counts_and_digest_and_the_ids_changed"),
    ("the command writes without --yes", CLI,
     "    if not yes:\n        from beeverforge.product import people as the_people\n",
     "    if False:\n        from beeverforge.product import people as the_people\n",
     TEST + "::test_the_command_shows_the_change_and_writes_only_with_yes"),
    ("the command with nobody named goes on", CLI,
     "    if not given:\n", "    if False:\n",
     TEST + "::test_the_command_with_nothing_given_is_refused_and_empties_nothing"),
]
