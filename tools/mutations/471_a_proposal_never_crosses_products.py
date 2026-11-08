"""A proposal staged on one product is never read, confirmed or set aside on another (#471),
proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/471_a_proposal_never_crosses_products.py

`staging._PENDING` holds one entry per key, and a person's own conversation key is the same on
every product page. The claims, each a row:

  1. `remember` stamps the product on the entry, and `_ours` compares it — an entry with no
     product, or a caller with no project, is read as before;
  2. `pending_for` neither believes, overwrites, drops nor expires another product's copy;
  3. `remember` sets aside only this product's own earlier proposal;
  4. `consume` refuses another product's proposal by name, never takes another product's copy for
     the one confirmed, and never pops it;
  5. the scan behind a bare yes lists this product's proposals only, dated by their own staging.
"""

TEST = "tests/test_a_proposal_never_crosses_products.py"

STAGING = "beeverforge/product/staging.py"

MUTATIONS = [
    # 1. the stamp and the comparison
    ("TODAY'S DEFECT: an entry carries no product", STAGING,
     '        entry["product"] = _product_of(project)  '
     "# which product's yes may perform it (#471)\n",
     '        pass\n'),
    ("every entry is every product's", STAGING,
     "    return not theirs or not mine or theirs == mine\n",
     "    return True\n"),
    ("an entry staged with no product is nobody's", STAGING,
     "    return not theirs or not mine or theirs == mine\n",
     "    return not mine or theirs == mine\n"),
    ("a caller with no project reads nothing", STAGING,
     "    return not theirs or not mine or theirs == mine\n",
     "    return not theirs or theirs == mine\n"),

    # 2. pending_for
    ("another product's copy is believed", STAGING,
     "        local = held if _ours(held, project) else None\n",
     "        local = held\n"),
    ("another product's copy is dropped when this product has nothing", STAGING,
     "            if local is not None:\n"
     "                _PENDING.pop(thread, None)\n"
     "            return None\n",
     "            _PENDING.pop(thread, None)\n"
     "            return None\n"),
    ("another product's copy is overwritten by this product's read", STAGING,
     "        if held is None or local is not None:\n",
     "        if True:\n"),
    ("this product's expiry drops another product's copy", STAGING,
     "            if _PENDING.get(thread) is entry:\n"
     "                _PENDING.pop(thread, None)\n",
     "            if True:\n"
     "                _PENDING.pop(thread, None)\n"),

    # 3. remember
    ("another product's proposal is set aside", STAGING,
     "        if previous is not None and not _ours(previous, project):\n",
     "        if False:\n"),

    # 4. consume
    ("another product's proposal is not refused by name", STAGING,
     "    if project is not None and not _ours(verified, project):\n",
     "    if False:\n"),
    ("another product's copy is taken for the one confirmed", STAGING,
     "        if current is not None and not _ours(current, project):\n",
     "        if False:\n"),
    ("a yes pops another product's copy", STAGING,
     "        if _PENDING.get(key) is current:  # not another product's copy under the same key\n",
     "        if True:\n"),

    # 5. the scan
    ("the scan lists another product's copies", STAGING,
     "if here(k, e) and _ours(e, project)}\n",
     "if here(k, e)}\n"),
]
