"""A slow card save sends once, recovers after failure, and stays with its original form."""

TEST = "tests/test_a_pending_card_save_is_one_submission.py"
PANEL = "beeverforge/api/panel.html"

MUTATIONS = [
    ("a second click sends the same pending card again", PANEL,
     "  const f = _bd.form; if(!f || f.saving) return;",
     "  const f = _bd.form; if(!f) return;"),
    ("save stays visibly enabled while the request is pending", PANEL,
     '  const save = $("#b_save"); if(save) save.disabled = true;',
     '  const save = $("#b_save"); if(save) save.disabled = false;'),
    ("repainting a pending form enables its save button", PANEL,
     'onclick="boardSaveCard()"${f.saving ? " disabled" : ""}>save</button>',
     'onclick="boardSaveCard()">save</button>'),
    ("a failed request leaves the form permanently pending", PANEL,
     "  f.saving = false;\n  // Always report the answer",
     "  f.saving = true;\n  // Always report the answer"),
    ("an old save closes a different form or navigates away from the selected card", PANEL,
     "  const current = _bd.form === f && _bd.project === project && _bd.card === card;",
     "  const current = true;"),
    ("a failed request leaves its save control disabled", PANEL,
     '  if(current){ const currentSave = $("#b_save"); '
     'if(currentSave) currentSave.disabled = false; }',
     '  if(current){ const currentSave = $("#b_save"); '
     'if(currentSave) currentSave.disabled = true; }'),
    ('the save button loses the id its handler disables', PANEL,
     'class="btn" id="b_save" onclick', 'class="btn" onclick'),
    ('a stale save answer is not announced', PANEL,
     '  // Always report the answer, but only alter the form it belongs to.',
     '  if(!(_bd.form === f && _bd.project === project && _bd.card === card)) return;'),
    ("a network failure escapes without keeping a retryable form", PANEL,
     '  } catch(e){ r = {ok:false, message:e.message||"the card could not be saved"}; }',
     "  } catch(e){ throw e; }"),
]
