"""The pull request the factory opens on Azure Repos is attached to its card, proven by cutting it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/515_an_azure_pull_request_is_linked_to_its_work_item.py

The pull request used to be created with no work item reference, so every card waited for a person
to add the link by hand. Each row breaks one claim of
`tests/test_an_azure_pull_request_is_linked_to_its_work_item.py` and must turn that guard red:

  1. the Azure forge never sends the references;
  2. it sends the key even when it has nothing to send;
  3. it sends a Jira key or a blank as if it were a work item;
  4. it sends the same work item twice;
  5. a refused link stops the pull request from opening;
  6. a create with no references is retried as if a link had been refused;
  7. the retry keeps the references that were refused;
  8. the retry is silent;
  9. the Azure row stops declaring that it links;
 10. a mock or a truthy string counts as a declaration;
 11. the job hands the card to a row that never declared it;
 12. the job hands a card the forge does not own;
 13. the job never hands the card at all.
"""

TEST = "tests/test_an_azure_pull_request_is_linked_to_its_work_item.py"

AZURE = "beeverforge/adapters/forge/azure_devops.py"
SPACE = "beeverforge/contracts/item_space.py"
MACHINE = "beeverforge/orchestrator/machine.py"

MUTATIONS = [
    ("the Azure forge never sends the work item references", AZURE,
     '        if refs:\n            payload["workItemRefs"] = refs\n',
     '        if False:\n            payload["workItemRefs"] = refs\n',
     TEST + "::test_the_pull_request_is_created_with_its_work_item"),

    ("the Azure forge sends the key even when it has no work items", AZURE,
     '        if refs:\n            payload["workItemRefs"] = refs\n',
     '        payload["workItemRefs"] = refs\n',
     TEST + "::test_a_call_with_no_work_items_posts_the_payload_it_always_did"),

    ("a Jira key or a blank is sent as a work item", AZURE,
     "        if number.isascii() and number.isdigit() and number not in found:\n",
     "        if number and number not in found:\n",
     TEST + "::test_only_a_number_is_a_work_item"),

    ("the same work item is sent twice", AZURE,
     "        if number.isascii() and number.isdigit() and number not in found:\n",
     "        if number.isascii() and number.isdigit():\n",
     TEST + "::test_only_a_number_is_a_work_item"),

    ("a refused link stops the pull request from opening", AZURE,
     "                if not refs:\n                    raise\n",
     "                raise\n",
     TEST + "::test_a_refused_link_does_not_stop_the_pull_request"),

    ("a create with no references is retried as if a link had been refused", AZURE,
     "                if not refs:\n                    raise\n",
     "                if False:\n                    raise\n",
     TEST + "::test_a_create_with_no_work_items_is_not_retried"),

    ("the retry keeps the references the vendor refused", AZURE,
     '                    body={k: v for k, v in payload.items() if k != "workItemRefs"})\n',
     "                    body=payload)\n",
     TEST + "::test_a_refused_link_does_not_stop_the_pull_request"),

    ("the retry is silent", AZURE,
     'log.warning("BEEVERFORGE_PR_LINK_REFUSED head=%s',
     'log.warning("PR_LINK head=%s',
     TEST + "::test_a_refused_link_does_not_stop_the_pull_request"),

    ("the Azure row stops declaring that it links work items", AZURE,
     "    links_work_items = True\n",
     "    links_work_items = False\n",
     TEST + "::test_the_azure_forge_declares_the_capability_and_no_other_shipped_row_does"),

    ("a mock or a truthy string counts as a declaration", SPACE,
     '    return getattr(forge, "links_work_items", False) is True\n',
     '    return bool(getattr(forge, "links_work_items", False))\n',
     TEST + "::test_the_azure_forge_declares_the_capability_and_no_other_shipped_row_does"),

    ("the job hands the card to a row that never declared it", MACHINE,
     "            linked = [card.work_item] if card.work_item and links_work_items(self.forge) else []\n",
     "            linked = [card.work_item] if card.work_item else []\n",
     TEST + "::test_a_forge_that_does_not_declare_the_capability_is_not_handed_the_argument"),

    ("the job hands a card the forge does not own", MACHINE,
     '                         lead=f"Automated by BeeverForge for card {words}{where}{tail}")\n',
     '                         lead=f"Automated by BeeverForge for card {words}{where}{tail}",\n'
     "                         work_item=bare)\n",
     TEST + "::test_a_card_the_forge_does_not_own_is_never_handed_over"),

    ("the job never hands the card at all", MACHINE,
     "            linked = [card.work_item] if card.work_item and links_work_items(self.forge) else []\n",
     "            linked = []\n",
     TEST + "::test_a_card_the_forge_owns_is_handed_to_a_forge_that_links"),
]
