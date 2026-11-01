"""The panel's header controls and project grid fit a phone in a real browser."""

TEST = "tests/test_the_panel_fits_a_phone.py"
PANEL = "beeverforge/api/panel.html"

MUTATIONS = [
    ("the header row stops wrapping", PANEL,
     ".brand-row{display:flex;flex-wrap:wrap;", ".brand-row{display:flex;"),
    ("the project column is 300px whatever the screen", PANEL,
     "minmax(min(300px,100%),1fr)", "minmax(300px,1fr)"),
]
