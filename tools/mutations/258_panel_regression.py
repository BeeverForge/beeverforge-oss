"""Prove the reported panel regression through the production handler."""

TEST = 'tests/test_a_card_save_network_failure_is_visible.py'
PANEL = "beeverforge/api/panel.html"

MUTATIONS = [
    ('network rejection escapes without feedback', PANEL,
     '  } catch(e){\n    // A lost response',
     '  } catch(e){ throw e;\n    // A lost response'),
    ('lost response erases the draft', PANEL,
     '    r = {ok:false, unconfirmed:true,',
     '    _bd.form=null;r = {ok:false, unconfirmed:true,'),
    ('a new same-title card is not offered', PANEL,
     '          if(_bd.form === f && _bd.project === project && _bd.card === card){',
     '          if(false){',
     'tests/test_an_unconfirmed_create_offers_new_matching_cards.py'),
    ('an old same-title card is offered as newly appeared', PANEL,
     '!before.has(String(c.ref))', 'true',
     'tests/test_an_unconfirmed_create_offers_new_matching_cards.py'),
    ('the form forgets which cards existed when it opened', PANEL,
     'Array.isArray(cards) ? cards.map(c=>String(c.ref)) : null',
     'Array.isArray(cards) ? [] : null',
     'tests/test_an_unconfirmed_create_offers_new_matching_cards.py'),
    ('a late board read changes the former form', PANEL,
     'if(_bd.form === f && _bd.project === project && _bd.card === card){',
     'if(true){',
     'tests/test_an_unconfirmed_create_offers_new_matching_cards.py'),
    ('an unrelated title is offered', PANEL,
     '(c.title||"").trim() === title', 'true',
     'tests/test_an_unconfirmed_create_offers_new_matching_cards.py'),
    ('the candidate is opened without a choice', PANEL,
     '            f.candidates = candidates; f.candidateTitle = title;',
     '            if(candidates.length) boardOpenCard(String(candidates[0].ref));\n'
     '            f.candidates = candidates; f.candidateTitle = title;',
     'tests/test_an_unconfirmed_create_offers_new_matching_cards.py'),
]
