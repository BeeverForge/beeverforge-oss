"""The reviewer's own findings reach the pull request with any credential withheld (#196).

Claims:
  - every free-text field the reviewer writes (`_REVIEW_WORDS`, `_FINDING_WORDS`, `_CHECK_WORDS`)
    is withheld from by ONE helper, `_review_withheld`, on the model and on the dict `headline`
    reads; dropping any field or group of fields is red;
  - the body's review section (`_review_lines`, on the first publish and on every
    `_republish_review` rewrite) reads the reviewer's words only through it: the summary, a
    finding's description and `file`, and a `would_verify` pointer;
  - the ready-for-review announcement (`_review_sentence`) reads them only through it, before
    `headline` cuts them: a finding's description and `file`, a criterion, a pointer;
  - the scrub is on the raw words, BEFORE `_as_text` (the #885 order): moved outside it, a key of
    this process spanning a `## ` row is escaped first and published in halves. #323 changes the
    same `_review_lines` rows to make mentions inert; these rows pin that the scrub stays
    innermost under whatever it adds;
  - the review event posted on the pull request (`format_review`) withholds it.
"""

TEST = ("tests/test_the_reviewers_findings_reach_the_pull_request_with_any_credential_withheld"
        ".py")
MACHINE = "beeverforge/orchestrator/machine.py"

MUTATIONS = [
    # ── the call at each site ──
    ("the body's review section reads the reviewer's words as written", MACHINE,
     "        r = _review_withheld(review)\n",
     "        r = review\n"),

    ("the announcement reads the reviewer's words as written", MACHINE,
     "    verdict = _review_withheld(verdict)\n",
     ""),

    ("the review posted on the pull request withholds nothing", MACHINE,
     "                    body=_without_credentials(format_review(result.review)),",
     "                    body=format_review(result.review),"),

    # ── each group of fields ──
    ("the summary is not withheld from", MACHINE,
     '_REVIEW_WORDS = ("summary",)',
     "_REVIEW_WORDS = ()"),

    ("no word of a finding is withheld from", MACHINE,
     '_FINDING_WORDS = ("description", "file", "criterion")',
     "_FINDING_WORDS = ()"),

    ("no word of an acceptance check is withheld from", MACHINE,
     '_CHECK_WORDS = ("criterion", "evidence", "would_verify", "executed_by")',
     "_CHECK_WORDS = ()"),

    ("the helper skips findings and checks altogether", MACHINE,
     '    for key, fields in (("findings", _FINDING_WORDS), ("acceptance", _CHECK_WORDS)):',
     "    for key, fields in ():"),

    # ── each field ──
    ("a finding's description is not withheld from", MACHINE,
     '_FINDING_WORDS = ("description", "file", "criterion")',
     '_FINDING_WORDS = ("file", "criterion")'),

    ("a finding's file is not withheld from", MACHINE,
     '_FINDING_WORDS = ("description", "file", "criterion")',
     '_FINDING_WORDS = ("description", "criterion")'),

    ("a finding's criterion is not withheld from", MACHINE,
     '_FINDING_WORDS = ("description", "file", "criterion")',
     '_FINDING_WORDS = ("description", "file")'),

    ("a check's criterion is not withheld from", MACHINE,
     '_CHECK_WORDS = ("criterion", "evidence", "would_verify", "executed_by")',
     '_CHECK_WORDS = ("evidence", "would_verify", "executed_by")'),

    ("a check's evidence is not withheld from", MACHINE,
     '_CHECK_WORDS = ("criterion", "evidence", "would_verify", "executed_by")',
     '_CHECK_WORDS = ("criterion", "would_verify", "executed_by")'),

    ("a check's would_verify pointer is not withheld from", MACHINE,
     '_CHECK_WORDS = ("criterion", "evidence", "would_verify", "executed_by")',
     '_CHECK_WORDS = ("criterion", "evidence", "executed_by")'),

    ("a check's executed_by is not withheld from", MACHINE,
     '_CHECK_WORDS = ("criterion", "evidence", "would_verify", "executed_by")',
     '_CHECK_WORDS = ("criterion", "evidence", "would_verify")'),

    ("the model's words come back as written", MACHINE,
     "        return ReviewResult.model_validate(_review_withheld(review.model_dump()))",
     "        return review"),

    # ── the order: on the raw words, before `_as_text` (#885) ──
    ("the summary is withheld from after `_as_text` escaped it", MACHINE,
     "        out = [first, _as_text(r.summary)]",
     "        out = [first, _without_credentials(_as_text(review.summary))]"),

    ("a finding is withheld from after `_as_text` escaped it", MACHINE,
     '        for f in r.findings:\n'
     '            loc = f" ({f.file}:{f.line})" if f.file else ""\n'
     '            out.append(f"- **{f.severity}**{loc}: {_as_text(f.description)}")',
     '        for f, raw in zip(r.findings, review.findings):\n'
     '            loc = f" ({f.file}:{f.line})" if f.file else ""\n'
     '            out.append(f"- **{f.severity}**{loc}: "\n'
     '                       f"{_without_credentials(_as_text(raw.description))}")'),

    # ── and before `headline` cuts them ──
    ("the body's pointer is withheld from after `headline` cut it at 120", MACHINE,
     '            out += [f"> - {p}" for p in head["points"] if p.startswith("wire `")]',
     '            out += [f"> - {_without_credentials(p)}"\n'
     '                    for p in _verdict.headline(review.model_dump())["points"]\n'
     '                    if p.startswith("wire `")]'),

    ("the announcement is withheld from after `headline` cut it", MACHINE,
     "    verdict = _review_withheld(verdict)\n"
     "    head = headline(verdict if isinstance(verdict, dict) else {})\n"
     "    out = f\"\\n{head['word']} — {head['clause']}\"\n"
     "    for point in (head.get(\"points\") or [])[:3]:\n"
     "        out += f\"\\n· {point}\"\n",
     "    head = headline(verdict if isinstance(verdict, dict) else {})\n"
     "    out = _without_credentials(f\"\\n{head['word']} — {head['clause']}\")\n"
     "    for point in (head.get(\"points\") or [])[:3]:\n"
     "        out += _without_credentials(f\"\\n· {point}\")\n"),

    # the hold sentence of a review that did not complete quotes the reviewer's summary
    ("an unfinished review's summary reaches the hold sentence with its credential", MACHINE,
     "    summary = _review_withheld(r).summary\n",
     "    summary = r.summary\n"),
]
