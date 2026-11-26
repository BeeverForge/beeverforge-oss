"""The Opus review workflow reviews every pull request, trusts whoever can write, and lets only a
pass through (#716, #719), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py \
          tools/mutations/716_the_opus_review_runs_on_every_pull_request.py

`opus/semantic-review` is a required status and no person's approval is, so this workflow is the
merge gate. The claims, each a group of rows:

  1. every pull request is reviewed, into any branch, and what is not reviewed is named;
  2. one review per pull request, and a replaced one publishes nothing;
  3. scope is set by whoever can write to the repository, and by the factory's own issue;
  4. only a pass is green, and what is published is the head that was reviewed, as plain text;
  5. no pull request is left without a status, and filling a gap is bounded.
"""

TEST = "tests/test_the_opus_review_runs_on_every_pull_request.py"
REVIEW = ".github/workflows/opus-semantic-review.yml"
CI = ".github/workflows/ci.yml"

MUTATIONS = [
    # 1. every pull request, and the ones that are not reviewed
    ("#716'S DEFECT: the review no longer starts from ci", REVIEW,
     "  workflow_run:\n    workflows: [ci]\n    types: [requested]\n", ""),
    ("ci runs only on pull requests into main", CI,
     "  pull_request:\n", "  pull_request:\n    branches: [main]\n"),
    ("a ci re-run is reviewed again", REVIEW,
     "        github.event.workflow_run.run_attempt == 1 &&\n", ""),
    ("a fork reaches the job that holds the credential", REVIEW,
     '            elif .head.repo.full_name != $repo then '
     '"#\\(.number) comes from another repository"\n',
     ""),
    ("a draft is reviewed", REVIEW,
     '            elif .draft then "#\\(.number) is a draft"\n', ""),
    ("a head the pull request has left is reviewed", REVIEW,
     '            elif $sha != "" and .head.sha != $sha then '
     '"#\\(.number) has moved past \\($sha[0:12])"\n',
     ""),
    ("a refusal asked by a person ends green", REVIEW,
     '              echo "::error::Not reviewed: $1"\n              exit 1\n',
     '              echo "::error::Not reviewed: $1"\n              exit 0\n'),
    ("anything typed is sent to the API as a number", REVIEW,
     '[[ "$pr" =~ ^[1-9][0-9]*$ ]] || skip', '[[ -n "$pr" ]] || skip'),
    ("the second pull request of one head gets no review", REVIEW,
     '              if gh workflow run opus-semantic-review.yml --repo "$GITHUB_REPOSITORY" '
     '-f pr="$other"; then\n',
     "              if true; then\n"),
    ("a draft with the same head is started, to be refused in red", REVIEW,
     '            done <<< "$reviewed"\n', '            done <<< "$heads"\n'),
    ("a start that fails for another stops this one's review", REVIEW,
     "              else\n                echo \"::warning::#$other has the same head",
     "              else\n                exit 1; echo \"::warning::#$other has the same head"),

    # 2. one review per pull request
    ("the review is keyed by something other than the number", REVIEW,
     "      group: opus-semantic-review-pr-${{ needs.target.outputs.pr }}\n",
     "      group: opus-semantic-review-${{ github.run_id }}\n"),
    ("the next review cancels the one running, whichever head is newer", REVIEW,
     "      cancel-in-progress: false\n", "      cancel-in-progress: true\n"),
    ("a model call that hangs is stopped by the job's limit and nothing is said", REVIEW,
     "        timeout-minutes: 15\n", ""),
    ("a replaced review publishes `Review unavailable`", REVIEW,
     " && needs.review.result != 'cancelled' && needs.review.outputs.needed",
     " && needs.review.outputs.needed"),
    ("the job that resolves the number can start no run", REVIEW,
     "      actions: write\n      contents: read\n", "      contents: read\n"),

    # 3. whose words are the scope
    ("#719'S DEFECT: the issue's author is judged by author_association", REVIEW,
     '                if (.user.type == "User" and (.user.login | IN($trusted[])))\n',
     '                if (.author_association | IN("OWNER", "MEMBER", "COLLABORATOR"))\n'),
    ("read access sets scope", REVIEW,
     'if [[ "$permission" == admin || "$permission" == write ]]; then',
     'if [[ "$permission" == admin || "$permission" == write || "$permission" == read ]]; then'),
    ("everybody's comments are scope", REVIEW,
     '[.[] | select(.user.type == "User" and (.user.login | IN($trusted[]))) | {body}]',
     "[.[] | {body}]"),
    ("a user named like the factory is the factory", REVIEW,
     '                  or (.user.type == "Bot" and .user.login == $factory) then\n',
     "                  or (.user.login == $factory) then\n"),
    ("a cached no is asked again", REVIEW,
     ".writes | select(. != null) | tostring'", ".writes // empty'"),
    ("a question that failed is a quiet no", REVIEW,
     '                echo "::warning::Could not ask whether $login can write',
     '                : "::warning::Could not ask whether $login can write'),
    ("a list of issues that cannot be read is no issue", REVIEW,
     """closing="$(jq -c '.closingIssuesReferences[]' context/pr.json)\"""",
     """closing="$(jq -c '.closingIssuesReferences[]' context/pr.json || true)\""""),

    # 4. what is published
    ("an inconclusive review is green: code with no issue merges", REVIEW,
     '          if [[ "$REVIEW_RESULT:$VERDICT" == "success:pass" ]]; then\n',
     '          if [[ "$REVIEW_RESULT" == success && "$VERDICT" != changes_requested ]]; then\n'),
    ("a review of an older head is published on the pull request", REVIEW,
     '            echo "A newer commit is available."\n            exit 1\n',
     '            echo "A newer commit is available."\n'),
    ("the model's words are published as Markdown", REVIEW,
     'map("    " + .)', "map(.)"),

    # 5. no pull request is left without a status
    ("the last job starts nothing for a head with no status", REVIEW,
     '          gh workflow run opus-semantic-review.yml --repo "$GITHUB_REPOSITORY" \\\n'
     '            -f pr="$PR_NUMBER" -f only_if_missing=true',
     '          : gh workflow run opus-semantic-review.yml --repo "$GITHUB_REPOSITORY" \\\n'
     '            -f pr="$PR_NUMBER" -f only_if_missing=true'),
    ("any status at all counts as the review's", REVIEW,
     """          statuses="$(gh api "repos/$GITHUB_REPOSITORY/commits/$head/statuses" \\
            | jq '[.[] | select(.context == "opus/semantic-review")] | length')\"""",
     """          statuses="$(gh api "repos/$GITHUB_REPOSITORY/commits/$head/statuses" \\
            | jq 'length')\""""),
    ("a gap is chased for ever", REVIEW,
     "(( ATTEMPT >= 5 ))", "(( ATTEMPT >= 500 ))"),
    ("a review replaced while it waited starts a run that replaces the one waiting", REVIEW,
     '          if [[ "$REVIEW_RESULT" == cancelled ]]; then\n',
     '          if [[ "$REVIEW_RESULT" == never ]]; then\n'),
    ("a closed pull request is chased", REVIEW,
     """              .state == "open" and (.draft | not) and .head.repo.full_name == $repo' \\
              "$RUNNER_TEMP/now.json\"""",
     """              true' \\
              "$RUNNER_TEMP/now.json\""""),
    ("the last job is skipped when the review was cancelled", REVIEW,
     "    if: ${{ always() && needs.target.outputs.eligible == 'true' }}\n",
     "    if: ${{ needs.target.outputs.eligible == 'true' }}\n"),
    ("a run started to fill a gap reviews a head that already has its review", REVIEW,
     "            elif (( statuses > 0 )); then\n              needed=false\n",
     "            elif (( statuses > 0 )); then\n              needed=true\n"),
    ("a run started to fill a gap reviews a head the pull request has left", REVIEW,
     '            if [[ "$current" != "$HEAD_SHA" ]]; then\n              needed=false\n',
     '            if [[ "$current" != "$HEAD_SHA" ]]; then\n              needed=true\n'),
    ("a review that was not needed publishes `Review unavailable`", REVIEW,
     " && needs.review.outputs.needed != 'false' }}", " }}"),
    ("a refusal in a run the workflow started is an error, as if somebody had asked", REVIEW,
     "github.event_name == 'workflow_dispatch' && !inputs.only_if_missing }}",
     "github.event_name == 'workflow_dispatch' }}"),
]
