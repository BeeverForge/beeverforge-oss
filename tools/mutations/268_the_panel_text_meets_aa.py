"""Every text colour on the panel reads at WCAG AA (4.5:1) on every ground, in both themes.

The first eight cuts put a failing colour back into the panel, one per way the palette has gone
wrong or could: a dark token this change raised, a light text token, the ink on the gold fill at
either end of its gradient, a state colour on its own wash, and a token that stops being a flat
colour. The rest attack the GUARD itself: with a palette that already passes, a weakened check
stays green, so each of those cuts is caught by a planted colour the checker must still name.
"""

TEST = "tests/test_the_panel_reads_as_a_control_room.py"
PANEL = "beeverforge/api/panel.html"

MUTATIONS = [
    ("the dark --dim goes back to the grey that read 3.92:1 on --card2", PANEL,
     "--muted:#D4D4D9;--dim:#9B9BA4;", "--muted:#D4D4D9;--dim:#8E8E97;"),

    ("the dark --err goes back to the red that read 4.24:1 on --card2", PANEL,
     "--ok:#3ddc84;--err:#ff7f8b;", "--ok:#3ddc84;--err:#ff5c6c;"),

    ("the dark --err goes back to the red that passed bare --card2 and read 4.11:1 on its wash", PANEL,
     "--ok:#3ddc84;--err:#ff7f8b;", "--ok:#3ddc84;--err:#ff6b79;"),

    ("the dark gradient's dim end goes back to the gold the ink read 4.06:1 on", PANEL,
     "--amber-dim:#B07F29;", "--amber-dim:#A47626;"),

    ("the light --ok goes back to the green that read 4.49:1 on its wash", PANEL,
     "--ok:#047655;", "--ok:#047857;"),

    ("the light --cyan turns a pale blue nobody reads on white", PANEL,
     "--cyan:#1D4ED8;", "--cyan:#7FA8F8;"),

    ("the light ink on the gold fill turns a tan that melts into it", PANEL,
     "--on-amber:#FFFFFF;", "--on-amber:#C0A080;"),

    ("a dark text token becomes a var() the checker cannot measure", PANEL,
     "--err:#ff7f8b;--purple:#a78bfa;", "--err:#ff7f8b;--purple:var(--cyan);"),

    # ── and the guard itself, which a passing palette cannot prove ──────────────────────────────
    ("the floor drops to 4.0, so a 4.24:1 red passes", TEST,
     "FLOOR = 4.5\n", "FLOOR = 4.0\n"),

    ("the lightest dark ground leaves the list", TEST,
     'GROUNDS = ("bg", "panel", "card", "card2")', 'GROUNDS = ("bg", "panel", "card")'),

    ("the error colour leaves the text tokens", TEST,
     '"cyan", "ok", "err", "purple")\nGROUNDS', '"cyan", "ok", "purple")\nGROUNDS'),

    ("the ink on the gold fill is no longer checked", TEST,
     'INK_ON_FILL = (("on-amber", "amber"), ("on-amber", "amber-dim"))', "INK_ON_FILL = ()"),

    ("the ink is checked against the gradient's bright end only", TEST,
     'INK_ON_FILL = (("on-amber", "amber"), ("on-amber", "amber-dim"))',
     'INK_ON_FILL = (("on-amber", "amber"),)'),

    ("the error colour on its wash is no longer checked", TEST,
     'WASHED = (("amber", "amber-wash"), ("err", "err-wash"), ("ok", "ok-wash"))',
     'WASHED = (("amber", "amber-wash"), ("ok", "ok-wash"))'),

    ("a washed pair is measured against the bare ground, as if the wash were not there", TEST,
     '            ratio = None if blend is None else _contrast(tokens.get(name, ""), blend)\n',
     '            ratio = _contrast(tokens.get(name, ""), tokens.get(ground, ""))\n'),

    ("a token that is not a flat colour is skipped instead of reported", TEST,
     "        if ratio is None or ratio < FLOOR:\n",
     "        if ratio is not None and ratio < FLOOR:\n"),

    ("the message stops naming the ground", TEST,
     'f"--{name} on --{ground} in the {theme} theme is {ratio:.2f}:1',
     'f"--{name} in the {theme} theme is {ratio:.2f}:1'),

    ("the message stops naming the ratio", TEST,
     "theme is {ratio:.2f}:1, below {FLOOR}:1.", "theme is below {FLOOR}:1."),
]
