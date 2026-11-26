"""The shard-table refresh hands its branch to a maintainer and asks no workflow to open, approve
or merge a pull request, proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/656_the_shard_refresh_hands_off.py

The claims, each a row:
  1. no job of the refresh may write pull requests, and no step opens, approves or merges one,
     by `gh` or by an action;
  2. the hand-off job writes contents only, and runs no code from the tree;
  3. the hand-off step, run in a scratch clone, pushes `refresh-shard-durations/<run id>` holding
     the rebuilt table, writes the compare link and the label to the step summary, raises one
     warning naming the branch, and stays green; when main already holds the table it pushes
     nothing and links nothing.

The rows on the workflow's schedule, its other permissions, its shell expressions and the rebuild's
diff stay in ci_runs_every_test_exactly_once.py, re-pinned there for #656.
"""

TEST = "tests/test_ci_runs_what_we_run.py"
WORKFLOW = ".github/workflows/refresh-shard-durations.yml"
NO_PULL_REQUEST = f"{TEST}::test_no_step_of_the_refresh_opens_approves_or_merges_a_pull_request"
PRIVILEGE = (f"{TEST}::"
             "test_the_refresh_runs_weekly_and_on_demand_and_only_its_hand_off_job_may_write")
NO_CODE = f"{TEST}::test_the_hand_off_runs_no_code_from_the_tree"
HANDS_OFF = (f"{TEST}::"
             "test_the_hand_off_pushes_the_branch_and_links_the_form_that_opens_its_pull_request")
NOTHING = f"{TEST}::test_the_hand_off_pushes_nothing_when_main_already_holds_the_table"

PUSH = '          git push origin "$branch"\n'
WARNING = ("          echo \"::warning::the shard table changed: $branch is pushed; open its pull "
           "request from the link in this run's summary\"\n")

MUTATIONS = [
    # 1. no workflow opens, approves or merges a pull request
    ("the hand-off job may write pull requests", WORKFLOW,
     "      contents: write\n", "      contents: write\n      pull-requests: write\n",
     NO_PULL_REQUEST),
    ("the whole workflow may write", WORKFLOW,
     "permissions:\n  contents: read\n\nconcurrency", "permissions: write-all\n\nconcurrency",
     NO_PULL_REQUEST),
    ("the hand-off opens the pull request itself", WORKFLOW,
     PUSH, PUSH + '          gh pr create --base main --head "$branch" --fill\n',
     NO_PULL_REQUEST),
    ("the hand-off approves a pull request", WORKFLOW,
     PUSH, PUSH + '          gh pr review --approve "$branch"\n', NO_PULL_REQUEST),
    ("the hand-off merges a pull request through the API", WORKFLOW,
     PUSH, PUSH + '          gh api -X PUT "repos/$REPO/pulls/1/merge"\n', NO_PULL_REQUEST),
    ("the hand-off opens the pull request with an action", WORKFLOW,
     "      - env:\n          REPO:",
     "      - uses: peter-evans/create-pull-request@v6\n      - env:\n          REPO:",
     NO_PULL_REQUEST),

    # 2. the hand-off job writes contents only, and runs no code from the tree
    ("the hand-off job may write nothing", WORKFLOW,
     "      contents: write\n", "      contents: read\n", PRIVILEGE),
    ("the hand-off runs the tree's code", WORKFLOW,
     PUSH, PUSH + "          make lint\n", NO_CODE),
    ("the hand-off runs a script of the tree", WORKFLOW,
     PUSH, PUSH + "          ./scripts/release_notes.py preview next\n", NO_CODE),
    ("the hand-off sets up the tree's python", WORKFLOW,
     "      - env:\n          REPO:",
     "      - uses: actions/setup-python@v5\n      - env:\n          REPO:", NO_CODE),
    ("the hand-off checks out the rebuilt commit, not main", WORKFLOW,
     "        with:\n          ref: main\n", "        with:\n          ref: ${{ github.sha }}\n",
     NO_CODE),

    # 3. what the hand-off step does, run
    ("the hand-off pushes no branch", WORKFLOW, PUSH, "", HANDS_OFF),
    ("the hand-off pushes to main", WORKFLOW,
     PUSH, '          git push origin "$branch:main"\n', HANDS_OFF),
    ("the hand-off names the branch for something other than the run", WORKFLOW,
     'branch="refresh-shard-durations/$GITHUB_RUN_ID"',
     'branch="refresh-shard-durations/latest"', HANDS_OFF),
    ("the hand-off pushes the old table", WORKFLOW,
     '          cp "$RUNNER_TEMP/shard-durations/shard_durations.json"'
     ' tests/shard_durations.json\n', "", HANDS_OFF),
    ("the hand-off writes no compare link", WORKFLOW,
     'link="https://github.com/$REPO/compare/main...$branch?expand=1"',
     'link="https://github.com/$REPO/tree/$branch"', HANDS_OFF),
    ("the compare link opens no form", WORKFLOW,
     "compare/main...$branch?expand=1", "compare/main...$branch", HANDS_OFF),
    ("the summary never asks for the label", WORKFLOW,
     ", then add the label \\`no-release-note\\`.", ".", HANDS_OFF),
    ("the summary is written to the log, not the run's summary", WORKFLOW,
     '          } >> "$GITHUB_STEP_SUMMARY"\n', "          }\n", HANDS_OFF),
    ("the hand-off raises no warning", WORKFLOW, WARNING, "", HANDS_OFF),
    ("a changed table fails the run", WORKFLOW, WARNING, WARNING + "          exit 1\n",
     HANDS_OFF),
    ("the hand-off pushes when main already holds the table", WORKFLOW,
     'if git diff --quiet -- tests/shard_durations.json; then\n            echo "main already',
     'if false; then\n            echo "main already', NOTHING),
    ("main holding the table fails the run", WORKFLOW,
     '            echo "main already holds this table: nothing to hand off"\n            exit 0\n',
     '            echo "main already holds this table: nothing to hand off"\n            exit 1\n',
     NOTHING),
]
