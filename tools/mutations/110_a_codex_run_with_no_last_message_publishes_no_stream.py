"""#110: a Codex run with no last message publishes no event stream as the agent's words.

The cuts put the stream back where the summary is read: the whole tail, as it was, and a shorter
tail, so the guard does not hold only for one slice length. The same fallback in Kimi and OpenCode
(review of #306) gets a row each that restores it.
"""

TEST = "tests/test_a_codex_run_with_no_last_message_publishes_no_stream.py"
CODEX = "beeverforge/adapters/agent/codex.py"
KIMI = "beeverforge/adapters/agent/kimi.py"
OPENCODE = "beeverforge/adapters/agent/opencode.py"

MUTATIONS = [
    ("the raw stream is the summary again when the last-message file is empty", CODEX,
     "            summary=summary,\n",
     '            summary=summary or (out or "")[-2000:],\n'),

    ("…a shorter tail of the stream still becomes the agent's account", CODEX,
     "            summary=summary,\n",
     '            summary=summary or (out or "")[-200:],\n'),

    ("the stream stands in for the last-message file when the file is empty", CODEX,
     '        summary = (last or "").strip()\n',
     '        summary = (last or out or "").strip()\n'),

    ("Kimi's raw JSONL is the summary again when no line is the assistant's", KIMI,
     '            summary=_final_text(events) or ("" if events else _plain_tail(out)),\n',
     "            summary=_final_text(events) or _plain_tail(out),\n"),

    ("OpenCode's failure summary ends with the stream's tail again", OPENCODE,
     "        return (_scrub(out) or \"\").strip()[-4000:] or _NO_FINAL_MESSAGE\n"
     "    return _NO_FINAL_MESSAGE\n",
     "        return (_scrub(out) or \"\").strip()[-4000:] or _NO_FINAL_MESSAGE\n"
     "    return (_scrub(out) or \"\").strip()[-4000:]\n"),
]
