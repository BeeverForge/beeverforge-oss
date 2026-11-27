"""The Pending tab's ↩ opens the conversation the item was asked in (#717).

The claims, each held by a test this plan cuts under:

  - the server says, on each item, which conversation it opens: the room, one of the viewer's own
    by session id ("" for the first), or "" when the row cannot say (`agenda._asked_at`) — and it
    reaches the page (`Item.as_dict`);
  - the page's ↩ carries that, and its handler opens the room or the session, never reopens the
    one already open, puts a narrow screen's tab away, and passes the id through `pvSid` first.
"""

TEST = "tests/test_a_pending_item_opens_where_it_was_asked.py"
AGENDA_TESTS = "tests/test_a_person_has_more_than_one_conversation.py"
AGENDA = "beeverforge/product/agenda.py"
PANEL = "beeverforge/api/panel.html"

MUTATIONS = [
    ("a delivery announced in a session opens the room", AGENDA,
     "        return (OWN, session_of(where)) if is_private(where) else (ROOM, \"\")\n",
     "        return ROOM, \"\"\n", AGENDA_TESTS),

    ("a decision asked in a session opens no session", AGENDA,
     "        return OWN, \"\" if session == FIRST else session\n",
     "        return OWN, \"\"\n", AGENDA_TESTS),

    ("the first conversation's marker reaches the page as if it were a session id", AGENDA,
     "        return OWN, \"\" if session == FIRST else session\n",
     "        return OWN, session\n", AGENDA_TESTS),

    ("a private decision with no session is sent to the room", AGENDA,
     "    return \"\", \"\"\n\n\ndef _answered_at",
     "    return ROOM, \"\"\n\n\ndef _answered_at", AGENDA_TESTS),

    ("the item says where, and the page is never told", AGENDA,
     ",\n                \"at\": self.at, \"session\": self.session}",
     "}", AGENDA_TESTS),

    ("the ↩ stops carrying where it was asked", PANEL,
     " data-w=\"${esc(String(i.at||\"\"))}\" data-s=\"${esc(String(i.session||\"\"))}\"",
     ""),

    ("the click hands the handler nothing, and ↩ only focuses the open box again", PANEL,
     "  pvPendingTalk: d=>pvPendingTalk(d.w,d.s),",
     "  pvPendingTalk: d=>pvPendingTalk(),"),

    ("the room is never opened", PANEL,
     "  if(at===\"room\"){if(!_pc.room)setScope(true)}",
     "  if(at===\"room\"){}"),

    ("the session already open is reopened, clearing its thread", PANEL,
     "if(_pc.room||String(_pc.session||\"\")!==s)pvOpen(s)}",
     "pvOpen(s)}"),

    ("an id the page would not mint reaches `pvOpen` as it came", PANEL,
     "else if(at===\"own\"){const s=pvSid(sid);",
     "else if(at===\"own\"){const s=String(sid||\"\");"),

    ("on a narrow screen the tab stays over the conversation it opened", PANEL,
     "  pvToggle(\"sideopen\",false);\n  const a=$(\"#prodAsk\");if(a)a.focus();\n}",
     "  const a=$(\"#prodAsk\");if(a)a.focus();\n}"),
]
