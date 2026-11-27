"""The Pending tab's ↩ opens the conversation an item was asked in (#717).

ADR-0055 D11 says each item "opens where it is answered — the conversation or the card". The ↩
only focused the box of the conversation already open, which was the right conversation while a
person had one (#335 gave them several). An item asked in another session opened nothing: the
person pressed it, the cursor moved to a box at the bottom of an unrelated conversation, and the
question — with the proposal and its buttons — stayed where they could not find it.

The server now says where each item was asked (`agenda.Item.at`, `.session`, tested in
`test_a_person_has_more_than_one_conversation.py`); these tests EXECUTE the page's own handlers
with node, reading the functions out of `panel.html`, so a comment that describes the fix cannot
pass for it.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

PANEL = Path(__file__).resolve().parents[1] / "beeverforge/api/panel.html"


def _source() -> str:
    return PANEL.read_text(encoding="utf-8")


def _function(name: str) -> str:
    source = _source()
    start = source.index(f"function {name}(")
    body = source[start:]
    return body[:body.index("\n}\n") + 3]


def _const(name: str) -> str:
    """One `const name=…;` line of the page, as it is."""
    [line] = [x for x in _source().splitlines() if x.startswith(f"const {name}=")]
    return line


def _action(name: str) -> str:
    """The page's own entry for `name` in its click dispatch, as it is written there."""
    [line] = [x.strip() for x in _source().splitlines()
              if re.match(rf"\s+{name}:\s", x)]
    return line.rstrip(",")


def _run(body: str) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not on PATH — cannot execute the panel's JavaScript")
    program = "\n".join([_const("esc"), _function("pvSid"), _function("pvPendingTalk"),
                         _function("paintAgenda")])
    program += "\n" + body
    done = subprocess.run([node, "-e", program], capture_output=True, text=True, timeout=20)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


_STUBS = """
const opened=[], focused=[];
let _pc={room:false,session:"zz99"};
const box={focus:()=>focused.push(_pc.room?"room":(_pc.session||"first"))};
const els={"#prodAsk":box,"#pv":{},"#prodAgenda":{innerHTML:""},"#prodAgendaCount":{textContent:""},
           "#prodAgendaAbout":null};
function $(q){return els[q]||null}
function setScope(room){opened.push(room?"room":"mine");_pc.room=room;_pc.session=""}
function pvOpen(sid){opened.push("session:"+(sid||"first"));_pc.room=false;_pc.session=sid}
const toggled=[];
function pvToggle(cls,on){toggled.push([cls,on])}
"""


def test_on_a_narrow_screen_the_tab_is_put_away_so_the_conversation_shows():
    out = _run(_STUBS + f"""
const acts={{{_action("pvPendingTalk")}}};
acts.pvPendingTalk({{w:"own",s:"k3f9a2"}});
console.log(JSON.stringify({{toggled}}));
""")
    assert out["toggled"] == [["sideopen", False]]


@pytest.mark.parametrize(("at", "session", "opened", "focused"), [
    ("own", "k3f9a2", ["session:k3f9a2"], ["k3f9a2"]),
    ("own", "", ["session:first"], ["first"]),
    ("room", "", ["room"], ["room"]),
    # a row that does not say where: the open conversation's box, as before
    ("", "", [], ["zz99"]),
])
def test_the_return_opens_the_conversation_the_item_was_asked_in(at, session, opened, focused):
    out = _run(_STUBS + f"""
const acts={{{_action("pvPendingTalk")}}};
acts.pvPendingTalk({{w:{json.dumps(at)},s:{json.dumps(session)}}});
console.log(JSON.stringify({{opened,focused}}));
""")
    assert out == {"opened": opened, "focused": focused}


def test_the_return_does_not_reopen_the_conversation_already_open():
    """Reopening clears the thread and resubscribes: pressing ↩ on an item of the open session
    must only put the cursor in its box."""
    out = _run(_STUBS + f"""
const acts={{{_action("pvPendingTalk")}}};
acts.pvPendingTalk({{w:"own",s:"zz99"}});
console.log(JSON.stringify({{opened,focused}}));
""")
    assert out == {"opened": [], "focused": ["zz99"]}


def test_a_session_id_the_page_would_not_mint_opens_nothing_it_names():
    """The id comes back from the server into a click handler: anything that is not a session id
    is read as none, never put into a key (`pvSid`)."""
    out = _run(_STUBS + f"""
const acts={{{_action("pvPendingTalk")}}};
acts.pvPendingTalk({{w:"own",s:"../person:bruno"}});
console.log(JSON.stringify({{opened,focused}}));
""")
    assert out["opened"] == ["session:first"]


def test_each_item_s_return_carries_where_it_was_asked():
    out = _run(_STUBS + """
let _prod={agenda:[
  {direction:"awaited",what:"Which date?",said:"a decision from you",chip:"awaited from you",
   when:"since 2026-11-26",opens:"conversation",at:"own",session:"k3f9a2"},
  {direction:"awaited",what:"Did it work?",said:"",chip:"awaited from you",when:"",
   opens:"conversation",at:"room",session:""},
  {direction:"awaited",what:"Old",said:"",chip:"",when:"",opens:"conversation"}],
  agendaAbout:"",agendaEmpty:""};
paintAgenda();
console.log(JSON.stringify({html:els["#prodAgenda"].innerHTML}));
""")
    buttons = re.findall(r'<button[^>]*data-act="pvPendingTalk"[^>]*>', out["html"])
    assert len(buttons) == 3
    assert 'data-w="own"' in buttons[0] and 'data-s="k3f9a2"' in buttons[0]
    assert 'data-w="room"' in buttons[1] and 'data-s=""' in buttons[1]
    assert 'data-w=""' in buttons[2] and 'data-s=""' in buttons[2]
