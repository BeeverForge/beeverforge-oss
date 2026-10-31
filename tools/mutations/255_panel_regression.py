"""Prove the reported panel regression through the production handler."""

TEST = 'tests/test_panel_modals_use_the_native_dialog.py'
PANEL = "beeverforge/api/panel.html"

MUTATIONS = [
    ('dialog loses native focus containment', PANEL,
     '<dialog id="modal"',
     '<div id="modal"'),
    ('dialog is shown without modal mode', PANEL,
     'el.showModal()}',
     'el.show()}'),
    ('closing no longer dismisses the dialog', PANEL,
     'function closeModal(){$("#modal").close()}',
     'function closeModal(){}'),
    ('background redraw loses the focus return target', PANEL,
     'if(opener)opener.focus();',
     'if(false)opener.focus();'),
    ('live redraw chooses the first option instead of the focused one', PANEL,
     '(at>=0&&el.querySelectorAll(F)[at])||', ''),
    ('browser close no longer calls the cleanup handler', PANEL,
     '$("#modal").addEventListener("close",modalClosed);', ''),
    ('new project trigger loses its focus return id', PANEL,
     'id="registerProject" ', ''),
    ('focused id is not used on redraw', PANEL,
     '(active&&document.getElementById(active))||', ''),
    ('focused id is not captured on redraw', PANEL,
     'active=inside?a.id:""', 'active=""'),
    ('late close event empties a newly opened dialog', PANEL,
     'if(el.open)return;el.innerHTML="";', 'el.innerHTML="";'),
]
