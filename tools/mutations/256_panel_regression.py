"""Prove the reported panel regression through the production handler."""

TEST = 'tests/test_cost_does_not_wait_for_charts.py'
PANEL = "beeverforge/api/panel.html"

MUTATIONS = [
    ('charts block local metrics', PANEL,
     'const chart=_ensureChart();',
     'const chart=await _ensureChart();'),
    ('an older dashboard can paint after a later visit', PANEL,
     'if(request!==_dashRead)return;\n  if(!d)',
     'if(false)return;\n  if(!d)'),
    ('close no longer invalidates pending reads', PANEL,
     'function closeCosts(){ ++_dashRead;',
     'function closeCosts(){'),
    ('late charts repaint the dismissed dashboard', PANEL,
     '    if(request!==_dashRead)return;\n    const status=',
     '    if(false)return;\n    const status='),
    ('Escape closes Cost behind an open modal', PANEL,
     '!modal.open && modal.style.display!=="flex"',
     'true'),
    ('Escape is wired to nothing', PANEL,
     'document.addEventListener("keydown",costKeydown);', ''),
    ('chart fallback has no live status element', PANEL,
     '  <div id="chartStatus" class="sub" role="status">${window.Chart?"":"Loading charts — '
     'totals and task details are available below."}</div>\n', ''),
]
