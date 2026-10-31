"""Hold metrics and the optional CDN independently, including out-of-order visits."""

import re
from html.parser import HTMLParser

from tests.test_a_refusal_is_not_an_answer import CODE, run

STUBS = """
let _DASH=null,_dc={},_dashRead=0,_chartReady=null;
const window={},scripts=[],timers=[];let removed=0;
document.createElement=()=>({remove(){removed++}});
document.head={appendChild:s=>scripts.push(s)};
global.setTimeout=fn=>{timers.push(fn);return timers.length};global.clearTimeout=()=>{};
nodes['#dash']=node();nodes['#chartStatus']=node();
const requests=[];const applied=[];
function _renderDashShell(d){nodes['#dash'].innerHTML=d.project}
function _dashApply(){applied.push(_DASH.data.project)}
"""


def costs(scenario):
    return run(scenario, "openCosts", "closeCosts", "_ensureChart", stubs=STUBS)


def test_metrics_and_close_are_available_while_the_cdn_is_still_pending():
    got = costs("""
      routes={'/api/metrics?project=acme':[{status:200,body:{project:'acme'}}]};
      const first=openCosts('acme');const loading=nodes['#dash'].innerHTML;
      await first;const before={html:nodes['#dash'].innerHTML,applied:[...applied]};
      timers[0]();await settle();
      return {loading,before,status:nodes['#chartStatus'].textContent,removed};
    """)
    assert 'onclick="closeCosts()"' in got["loading"]
    assert got["before"] == {"html": "acme", "applied": ["acme"]}
    assert "Charts unavailable" in got["status"] and got["removed"] == 1


def test_a_late_chart_draws_the_current_data_without_another_metrics_read():
    got = costs("""
      routes={'/api/metrics':[{status:200,body:{project:'acme'}}]};
      await openCosts();window.Chart={};scripts[0].onload();await settle();
      return {calls,applied,status:nodes['#chartStatus'].textContent};
    """)
    assert got == {"calls": ["GET /api/metrics"], "applied": ["acme", "acme"], "status": ""}


def test_only_the_latest_open_dashboard_can_paint():
    got = costs("""
      const held=[];api=url=>new Promise(resolve=>held.push(resolve));
      const old=openCosts('old');const current=openCosts('current');
      held[1]({project:'current'});await current;
      held[0]({project:'old'});await old;
      closeCosts();window.Chart={};scripts[0].onload();await settle();
      return {html:nodes['#dash'].innerHTML,display:nodes['#dash'].style.display,applied,
              scripts:scripts.length};
    """)
    assert got == {"html": "current", "display": "none", "applied": ["current"], "scripts": 1}


def test_closing_while_metrics_are_pending_discards_the_response():
    got = costs("""
      let finish;api=()=>new Promise(resolve=>finish=resolve);
      const reading=openCosts();closeCosts();finish({project:'acme'});await reading;
      return {display:nodes['#dash'].style.display,applied};
    """)
    assert got == {"display": "none", "applied": []}


def test_escape_closes_cost_only_when_no_modal_is_open():
    got = run("""
      nodes['#dash'].style.display='block';nodes['#modal'].style.display='flex';
      costKeydown({key:'Escape'});const whileModal=nodes['#dash'].style.display;
      nodes['#modal'].style.display='none';nodes['#modal'].open=true;
      costKeydown({key:'Escape'});const whileNativeModal=nodes['#dash'].style.display;
      nodes['#modal'].open=false;costKeydown({key:'a'});
      const otherKey=nodes['#dash'].style.display;
      costKeydown({key:'Escape'});
      return {whileModal,whileNativeModal,otherKey,after:nodes['#dash'].style.display};
    """, "costKeydown", "closeCosts", stubs="""
      let _dashRead=0,_dc={};nodes['#dash']=node();nodes['#modal']=node();
    """)
    assert got == {"whileModal": "block", "whileNativeModal": "block", "otherKey": "block",
                   "after": "none"}


def test_the_page_wires_escape_to_close_cost():
    wiring = "\n".join(re.findall(r'^document\.addEventListener\("keydown",.*$', CODE, re.M))
    got = run(wiring + """
      nodes['#dash'].style.display='block';
      (listeners.keydown||[]).forEach(f=>f({key:'Escape'}));
      return {display:nodes['#dash'].style.display};
    """, "costKeydown", "closeCosts", stubs="""
      let _dashRead=0,_dc={};nodes['#dash']=node();nodes['#modal']=node();
      const listeners={};document.addEventListener=(t,f)=>(listeners[t]=listeners[t]||[]).push(f);
    """)
    assert got == {"display": "none"}


def test_the_real_shell_has_a_live_place_for_the_chart_fallback():
    got = run("""
      _renderDashShell({runs:[],projects:[]});return {html:nodes['#dash'].innerHTML};
    """, "_opt", "_renderDashShell", stubs="""
      const window={};nodes['#dash']=node();function _renderAutonomy(){}function _dashApply(){}
      for(const id of ["fModel","fHarness","fRole","fKnow","fFrom","fTo"])
        nodes['#'+id]={addEventListener(){}};
    """)

    class Status(HTMLParser):
        found = None

        def handle_starttag(self, tag, attrs):
            attributes = dict(attrs)
            if attributes.get("id") == "chartStatus":
                self.found = attributes.get("role")

    parser = Status()
    parser.feed(got["html"])
    assert parser.found == "status"
