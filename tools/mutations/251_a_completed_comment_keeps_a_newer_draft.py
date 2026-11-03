"""A completed comment owns its submitted draft and the drawer that submitted it."""

TEST = "tests/test_a_completed_comment_keeps_a_newer_draft.py"
PANEL = "beeverforge/api/panel.html"

MUTATIONS = [
    ("a successful comment erases text typed while it was pending", PANEL,
     '     board.selection === selection && board.draft === draft) board.draft = "";',
     '     true) board.draft = "";'),
    ("a completed comment clears a different drawer's draft", PANEL,
     "  if(_bd === board && board.project === project && board.card === card &&\n",
     "  if(\n"),
    ("leaving and reopening a card keeps an older comment's ownership", PANEL,
     "  board.selection = selection;",
     "  void selection;"),
    ("a reopened drawer loses its own draft if its text matches the submitted draft", PANEL,
     "     board.selection === selection && board.draft === draft)",
     "     board.draft === draft)"),
    ("a comment's refresh is skipped when the board showing its card was reopened", PANEL,
     "  if(_bd.project === project && _bd.card === card) await refreshBoard();",
     "  if(_bd === board && _bd.project === project && _bd.card === card) await refreshBoard();"),
    ("a comment refreshes a board that now shows another card", PANEL,
     "  if(_bd.project === project && _bd.card === card) await refreshBoard();",
     "  await refreshBoard();"),
]
