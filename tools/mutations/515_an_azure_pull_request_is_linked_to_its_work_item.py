"""The pull request the factory opens on Azure Repos is attached to its card, proven by cutting it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/515_an_azure_pull_request_is_linked_to_its_work_item.py

The pull request used to be created with no work item reference, so every card waited for a person
to add the link by hand. Each row breaks one claim of
`tests/test_an_azure_pull_request_is_linked_to_its_work_item.py` and must turn that guard red:

  1. the Azure forge never sends the references;
  2. it sends the key even when it has nothing to send;
  3. it sends a Jira key as if it were a work item;
  4. it sends the same work item twice, or twice in another spelling;
  5. it sends a work item `0`;
  6. an item dropped for not being a number goes unsaid;
  7. a blank is said as if it were a drop;
  8. a refused link stops the pull request from opening;
  9. a create with no references is retried as if a link had been refused;
 10. a create whose outcome is not known (no answer, a 5xx) is repeated blind;
 11. a 401 or a 409 is repeated as if the references could have caused it;
 12. a 404 is not repeated although the item may be one the identity cannot read;
 13. the retry keeps the references that were refused;
 14. the retry is silent;
 15. the link is blamed before the repeat without it is known to have worked;
 16. the vendor's sentence is cut at 160 characters;
 17. the Azure row stops declaring that it links;
 18. a mock or a truthy string counts as a declaration;
 19. the job hands the card to a row that never declared it;
 20. the job hands a card the forge does not own;
 21. the job never hands the card at all;
 22. the client forgets the status the server answered with.
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

    ("a Jira key is sent as a work item", AZURE,
     "        if number < 1:\n",
     "        if False:\n",
     TEST + "::test_only_a_number_is_a_work_item"),

    ("the same work item is sent twice, or twice in another spelling", AZURE,
     "        elif number not in found:\n            found.append(number)\n",
     "        else:\n            found.append(number)\n",
     TEST + "::test_a_work_item_is_compared_as_a_number_and_sent_in_its_canonical_form"),

    ("a work item 0 is sent", AZURE,
     "        if number < 1:\n",
     "        if number < 0:\n",
     TEST + "::test_zero_is_not_a_work_item"),

    ("an item dropped for not being a number goes unsaid", AZURE,
     'log.warning("BEEVERFORGE_PR_LINK_SKIPPED work_item=%r',
     'log.warning("PR_LINK work_item=%r',
     TEST + "::test_an_item_dropped_for_not_being_a_number_is_said"),

    ("a blank is said as if it were a drop", AZURE,
     "        if not text:\n            continue\n",
     "",
     TEST + "::test_a_blank_and_a_repeat_are_not_drops"),

    ("a refused link stops the pull request from opening", AZURE,
     '                if not refs or getattr(refused, "status", None) not in _LINK_REFUSAL_STATUSES:\n'
     "                    raise\n",
     "                raise\n",
     TEST + "::test_a_refused_link_does_not_stop_the_pull_request"),

    ("a create with no references is retried as if a link had been refused", AZURE,
     '                if not refs or getattr(refused, "status", None) not in _LINK_REFUSAL_STATUSES:\n',
     '                if getattr(refused, "status", None) not in _LINK_REFUSAL_STATUSES:\n',
     TEST + "::test_a_create_with_no_work_items_is_not_retried"),

    ("a create whose outcome is not known is repeated blind", AZURE,
     '                if not refs or getattr(refused, "status", None) not in _LINK_REFUSAL_STATUSES:\n',
     "                if not refs:\n",
     TEST + "::test_a_create_that_dropped_after_the_vendor_made_it_finds_the_pull_request"),

    ("a 401 or a 409 is repeated as if the references could have caused it", AZURE,
     "_LINK_REFUSAL_STATUSES = frozenset({400, 403, 404})\n",
     "_LINK_REFUSAL_STATUSES = frozenset({400, 401, 403, 404, 409})\n",
     TEST + "::test_a_refusal_the_references_cannot_have_caused_is_not_repeated"),

    ("a 404 is not repeated although the item may be one the identity cannot read", AZURE,
     "_LINK_REFUSAL_STATUSES = frozenset({400, 403, 404})\n",
     "_LINK_REFUSAL_STATUSES = frozenset({400, 403})\n",
     TEST + "::test_a_refused_link_does_not_stop_the_pull_request"),

    ("the retry keeps the references the vendor refused", AZURE,
     '                    body={k: v for k, v in payload.items() if k != "workItemRefs"})\n',
     "                    body=payload)\n",
     TEST + "::test_a_refused_link_does_not_stop_the_pull_request"),

    ("the retry is silent", AZURE,
     'log.warning("BEEVERFORGE_PR_LINK_REFUSED head=%s',
     'log.warning("PR_LINK head=%s',
     TEST + "::test_a_refused_link_does_not_stop_the_pull_request"),

    ("the link is blamed whether or not the repeat without it went through", AZURE,
     '                created = client.call(\n'
     '                    "POST", route,\n'
     '                    body={k: v for k, v in payload.items() if k != "workItemRefs"})\n'
     "                # SAID ONLY NOW:",
     '                log.warning("BEEVERFORGE_PR_LINK_REFUSED head=%s", head)\n'
     '                created = client.call(\n'
     '                    "POST", route,\n'
     '                    body={k: v for k, v in payload.items() if k != "workItemRefs"})\n'
     "                # SAID ONLY NOW:",
     TEST + "::test_a_link_is_not_blamed_when_the_repeat_without_it_is_refused_too"),

    ("the vendor's sentence is cut at 160 characters", AZURE,
     "head, \",\".join(r[\"id\"] for r in refs), _redact(str(refused)))",
     "head, \",\".join(r[\"id\"] for r in refs), _redact(str(refused))[:160])",
     TEST + "::test_a_refused_link_is_said_with_everything_the_vendor_said"),

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

    ("the client forgets the status the server answered with", "beeverforge/adapters/azure_devops.py",
     "                status=exc.code,\n",
     "",
     TEST + "::test_the_client_carries_the_status_the_server_answered_with"),
]
