"""The reviewer's own findings reach the pull request with any credential withheld (#196).

Claims:
  - the body's review section (`_review_lines`, on the first publish and on every
    `_republish_review` rewrite) withholds a credential in the summary and in each finding, on the
    raw text before `_as_text`;
  - the review event posted on the pull request (`format_review`) withholds it;
  - the ready-for-review announcement withholds it from a finding before `headline` cuts it.
"""

TEST = ("tests/test_the_reviewers_findings_reach_the_pull_request_with_any_credential_withheld"
        ".py")
MACHINE = "beeverforge/orchestrator/machine.py"

MUTATIONS = [
    ("the review summary in the body withholds nothing", MACHINE,
     "        out = [first, _as_text(_without_credentials(r.summary))]",
     "        out = [first, _as_text(r.summary)]"),

    ("a finding in the body withholds nothing", MACHINE,
     '                       f"{_as_text(_without_credentials(f.description))}")',
     '                       f"{_as_text(f.description)}")'),

    ("the review posted on the pull request withholds nothing", MACHINE,
     "                    body=_without_credentials(format_review(result.review)),",
     "                    body=format_review(result.review),"),

    ("the announcement withholds nothing from a finding", MACHINE,
     '            {**f, "description": _without_credentials(f.get("description") or "")}',
     '            {**f, "description": f.get("description") or ""}'),
]
