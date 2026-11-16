"""A breakdown's card whose title the redrafts left too long is shortened, not lost (#476), proven
by breaking it.

Run:  .venv/bin/python tools/mutate.py \
          tools/mutations/476_a_long_card_title_is_shortened_not_lost.py

The claims, each a row:

  1. when the title's length is the only problem left, the card is shortened, not refused;
  2. any other problem still refuses it, and the shortened card is judged, with no redraft;
  3. the shortening keeps whole words, drops the trailing clause first, and never leaves less than
     half the limit by doing so;
  4. the shortening is said in the log.
"""

TEST = "tests/test_a_long_card_title_is_shortened_not_lost.py"

CARDS = "beeverforge/product/cards.py"

MUTATIONS = [
    # 1. the fallback
    ("TODAY'S DEFECT: a card the redrafts left too long is refused", CARDS,
     '    if problems and {getattr(p, "kind", "") for p in problems} == {"title_too_long"}:\n',
     "    if False:\n"),

    # 2. what still refuses it
    ("any problem left is shortened away", CARDS,
     '    if problems and {getattr(p, "kind", "") for p in problems} == {"title_too_long"}:\n',
     "    if problems:\n"),
    ("the shortened card skips the judge", CARDS,
     "                             rubric=rubric, judge=judge, redraft=None,\n",
     "                             rubric=rubric, judge=None, redraft=None,\n"),
    ("the shortened card is redrafted again", CARDS,
     "                             rubric=rubric, judge=judge, redraft=None,\n",
     "                             rubric=rubric, judge=judge, redraft=redraft,\n"),

    # 3. the shortening
    ("the trailing clause is never the cut", CARDS,
     "    for cut in sorted({m.start() for m in re.finditer("
     'r"\\s*(?:[,;]|\\s[—–-]\\s)", title)},\n',
     "    for cut in sorted(set(),\n"),
    ("a clause may leave almost nothing", CARDS,
     "        if limit // 2 <= len(head) <= limit:\n",
     "        if 0 < len(head) <= limit:\n"),
    ("the shortening cuts at the limit, mid-word", CARDS,
     '    return out.rstrip(" ,;—–-") or title[:limit].rstrip()\n',
     "    return title[:limit]\n"),
    ("the shortening keeps one word too many", CARDS,
     "        if len(longer) > limit:\n",
     "        if len(longer) > limit + 5:\n"),

    # 4. the log
    ("the shortening is not said", CARDS,
     '            log.info("BEEVERFORGE_CARD_TITLE_SHORTENED project=%s %d→%d characters: %r",\n',
     '            (lambda *a: None)("BEEVERFORGE_CARD_TITLE_SHORTENED project=%s %d→%d '
     'characters: %r",\n'),
]
