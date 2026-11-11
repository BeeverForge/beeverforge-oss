"""A matching card is a choice, not proof that an unconfirmed create succeeded."""

import json

import pytest

from tests.test_a_refusal_is_not_an_answer import run

STUBS = """
let _bd={project:'acme',card:null,form:null,data:{cards:[{ref:'1',title:'Retain this title'}]}};
const opened=[],requests=[];
async function act(name,params){requests.push({name,params});throw new TypeError('Failed to fetch')}
function _bbody(){return _bd.form.raw}
function _bgate(){}
function _bpaintGate(){}
async function boardOpenCard(ref){opened.push(ref);_bd.form=null}
async function refreshBoard(){}
nodes['#boardview .drawer']={innerHTML:'',classList:{add(){}},setAttribute(){}};
nodes['#b_candidates']={innerHTML:''};nodes['#b_save']={disabled:false};
"""


def scenario(code):
    return run(code, "_blank", "boardNewCard", "paintForm", "_bpaintCandidates",
               "boardOpenCandidate", "boardSaveCard", stubs=STUBS)


@pytest.mark.parametrize("new_cards", [[], [{"ref": "2", "title": "Retain this title"}]])
def test_a_lost_create_keeps_the_draft_and_offers_only_new_matching_cards(new_cards):
    board = {"cards": [{"ref": "1", "title": "Retain this title"}, *new_cards,
                       {"ref": "3", "title": "Another title"}]}
    got = scenario(f"""
      routes={{'/api/board/acme':[{{status:200,body:{json.dumps(board)}}}]}};
      await boardNewCard();const draft=_bd.form;
      draft.title='Retain this title';draft.raw='Entire draft';
      await boardSaveCard();
      const before={{same:_bd.form===draft,title:draft.title,body:draft.raw,
                    html:nodes['#b_candidates'].innerHTML,opened:opened.slice(),
                    disabled:nodes['#b_save'].disabled,candidates:draft.candidates||[]}};
      if(before.candidates.length) boardOpenCandidate(0);
      return {{before,opened,form:_bd.form,toasts,requests,calls}};
    """)
    before = got["before"]
    assert before["same"] and before["body"] == "Entire draft"
    assert before["title"] == "Retain this title" and not before["disabled"]
    assert before["opened"] == [] and len(got["requests"]) == 1
    assert "GET /api/board/acme" in got["calls"]
    assert got["toasts"][0][0] == "Save not confirmed"
    if new_cards:
        assert before["candidates"] == new_cards
        assert "may not be yours" in before["html"]
        assert 'data-act="boardOpenCandidate" data-i="0"' in before["html"]
        assert "keep editing" in before["html"] and "closes your draft" in before["html"]
        assert got["opened"] == ["2"] and got["form"] is None
    else:
        assert before["candidates"] == [] and before["html"] == ""
        assert got["opened"] == [] and got["form"]["raw"] == "Entire draft"


def test_a_failed_board_read_does_not_claim_there_were_no_matches():
    got = scenario("""
      await boardNewCard();_bd.form.title='Keep it';_bd.form.raw='Draft';
      await boardSaveCard();
      return {form:_bd.form,toasts,opened,html:nodes['#b_candidates'].innerHTML};
    """)
    assert got["form"]["raw"] == "Draft" and got["opened"] == []
    assert got["html"] == "" and got["toasts"][0][0] == "Save not confirmed"


def test_new_matches_are_escaped_and_can_be_repainted_without_losing_the_draft():
    got = scenario("""
      routes={'/api/board/acme':[{status:200,body:{cards:[
        {ref:'2<evil>',title:'<draft>'},{ref:'3',title:'<draft>'}]}}]};
      await boardNewCard();_bd.form.title='<draft>';_bd.form.raw='Draft';
      await boardSaveCard();nodes['#b_candidates'].innerHTML='';paintForm();
      return {html:nodes['#b_candidates'].innerHTML,form:_bd.form,opened};
    """)
    assert "&lt;draft&gt;" in got["html"] and "2&lt;evil&gt;" in got["html"]
    assert 'data-act="boardOpenCandidate" data-i="1"' in got["html"]
    assert got["form"]["raw"] == "Draft" and got["opened"] == []


def test_a_candidate_cannot_be_opened_while_a_retry_is_in_flight():
    got = scenario("""
      routes={'/api/board/acme':[{status:200,body:{cards:[{ref:'1',title:'Retain this title'},
                                                          {ref:'2',title:'Keep it'}]}}]};
      await boardNewCard();_bd.form.title='Keep it';_bd.form.raw='Draft';
      await boardSaveCard();_bd.form.saving=true;boardOpenCandidate(0);
      return {opened,form:!!_bd.form};
    """)
    assert got["opened"] == [] and got["form"]


def test_the_unconfirmed_save_is_said_before_the_board_is_read_again():
    got = scenario("""
      api=()=>new Promise(()=>{});
      await boardNewCard();_bd.form.title='Keep it';_bd.form.raw='Draft';
      boardSaveCard();for(let i=0;i<20;i++) await Promise.resolve();
      return {toasts,saving:_bd.form.saving};
    """)
    assert [t[0] for t in got["toasts"]] == ["Save not confirmed"]
    assert got["saving"]


def test_a_stalled_board_read_times_out_and_reenables_save():
    got = scenario("""
      let timeoutMs;AbortSignal.timeout=ms=>{timeoutMs=ms;const c=new AbortController();
        setImmediate(()=>c.abort());return c.signal};
      api=(url,o)=>new Promise((resolve,reject)=>o.signal.addEventListener('abort',()=>reject(Error('timeout'))));
      await boardNewCard();_bd.form.title='Keep it';_bd.form.raw='Draft';
      await boardSaveCard();
      return {timeoutMs,saving:_bd.form.saving,disabled:nodes['#b_save'].disabled,toasts};
    """)
    assert got["timeoutMs"] == 8000
    assert not got["saving"] and not got["disabled"]
    assert [t[0] for t in got["toasts"]] == ["Save not confirmed"]


@pytest.mark.parametrize("navigation", ["form", "project", "card"])
def test_a_late_board_read_does_not_change_a_newer_selection(navigation):
    change = {
        "form": "_bd.form=_blank('new');_bd.form.title='New draft'",
        "project": "_bd.project='other'",
        "card": "_bd.card='9'",
    }[navigation]
    got = scenario(f"""
      let answer;api=()=>new Promise(resolve=>{{answer=resolve}});
      await boardNewCard();const old=_bd.form;old.title='Keep it';old.raw='Old draft';
      const saving=boardSaveCard();await Promise.resolve();{change};
      const selected=_bd.form;
      answer({{cards:[{{ref:'2',title:'Keep it'}}]}});await saving;
      return {{same:_bd.form===selected,oldCandidates:old.candidates||[],
               html:nodes['#b_candidates'].innerHTML,opened,toasts}};
    """)
    assert got["same"] and got["oldCandidates"] == []
    assert got["html"] == "" and got["opened"] == []
    assert got["toasts"][0][0] == "Save not confirmed"
