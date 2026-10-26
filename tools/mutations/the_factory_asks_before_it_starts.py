"""The factory asks before it spends (ADR-0048) — the cuts that would make the gather a toll, a
guess, or a silence."""

TEST = "tests/test_the_factory_asks_before_it_starts.py"

MUTATIONS = [
    ("gather defaults to true — a manifest break, and every un-onboarded project bounces",
     "beeverforge/contracts/manifest.py",
     "    gather: bool = False\n",
     "    gather: bool = True\n"),

    ("the gather ignores okf_gate and runs under advise",
     "beeverforge/runtime/temporal/activities.py",
     '    if mode != "enforce":\n',
     '    if False:\n'),

    ("an unreadable context repository is read as an absence",
     "beeverforge/runtime/temporal/activities.py",
     "    if fetched.unreadable:\n",
     "    if False:\n"),

    ("a directory is handed to the gate as it is",
     "beeverforge/knowledge/gather.py",
     "        if here.is_dir():\n",
     "        if False:\n"),

    ("an answer graded on its evidence's grade, not its verification",
     "beeverforge/knowledge/gather.py",
     "    if not concepts and not requirements:\n        return False\n",
     "    if not concepts and not requirements:\n        return True\n"),

    ("a stale citation still establishes",
     "beeverforge/knowledge/gather.py",
     '    return (all(v == "fresh" for v in concepts.values())\n',
     '    return (all(v in ("fresh", "stale", "missing") for v in concepts.values())\n'),

    # re-pinned 2026-10-04: the park is the card door's `question_asked` (#414), read back from
    # its outcome
    ("a park that did not land is treated as a park",
     "beeverforge/runtime/temporal/activities.py",
     '        if parked.startswith("failed"):\n',
     "        if False:\n"),

    ("the bot that opened the card is asked the question",
     "beeverforge/contracts/ticket.py",
     '    if chat and chat.lower() not in NOBODY:\n        return ""\n',
     '    if chat and chat.lower() not in NOBODY:\n        pass\n'),

    ("the question is asked again while the first one is still waiting",
     "beeverforge/runtime/temporal/activities.py",
     "        if already:\n",
     "        if False:\n"),

    ("the marker is not the first line",
     "beeverforge/techlead/voice.py",
     '        "en": "{marker}\\n{mention} — to move on I need to know:\\n{questions}\\n\\nAnswer '
     'here, "\n'
     '              "on the card. I will record the answer in the product\'s context and pick the '
     'card "\n'
     '              "up again; nothing is being built until then.",\n',
     '        "en": "{mention} — to move on I need to know:\\n{questions}\\n\\nAnswer here, "\n'
     '              "on the card. I will record the answer in the product\'s context and pick the '
     'card "\n'
     '              "up again; nothing is being built until then.\\n{marker}",\n'),

    ("the fetched checkout leaks on the ask path",
     "beeverforge/runtime/temporal/activities.py",
     "    finally:\n        discard_fetched_bundle(bundle)\n\n\n@activity.defn\n"
     "async def gather_context",
     "    finally:\n        pass\n\n\n@activity.defn\nasync def gather_context"),

    # ADR-0048 §7, wired after the slice shipped: the answer retires the bundle's questions
    ("the open questions' keys do not travel with the loop — nothing can retire them",
     "beeverforge/runtime/temporal/activities.py",
     '                     "gap_keys": "\\n".join(gp.key for gp in open_qs),\n',
     '                     "gap_keys": "",\n'),

    ("the answer retires nothing in the bundle",
     "beeverforge/runtime/temporal/activities.py",
     "        for key in retired:\n"
     "            manifest = retire(manifest, key, answer=answer, by=by, at=at)\n",
     "        for key in retired:\n"
     "            pass\n",
     "tests/test_a_question_reaches_the_person_who_asked.py"),
]
