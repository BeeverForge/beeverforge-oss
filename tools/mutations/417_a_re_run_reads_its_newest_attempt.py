"""After a re-run, the proof that every test ran once reads each job's newest attempt alone (#417),
proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/417_a_re_run_reads_its_newest_attempt.py

The claims, each a row:
  1. `--newest-attempts` keeps each job's highest attempt, compared as a number;
  2. it refuses an artifact without its attempt, and two jobs writing one file name;
  3. CI wires it: every upload names `github.run_attempt`, the `test` job downloads the artifacts
     apart and picks the newest before `make test-ran-once`.
"""

TEST = "tests/test_ci_runs_every_test_exactly_once.py"
PROOF = "scripts/every_test_ran_once.py"
CI = ".github/workflows/ci.yml"

MUTATIONS = [
    # 1. the newest attempt
    ("the oldest attempt wins", PROOF,
     "        if job not in newest or n > newest[job][0]:",
     "        if job not in newest or n < newest[job][0]:"),
    ("the last attempt read wins, whatever its number", PROOF,
     "        if job not in newest or n > newest[job][0]:",
     "        if True:"),
    ("attempts compare as text, so attempt 10 is older than attempt 2", PROOF,
     '        job, n = named["job"], int(named["n"])',
     '        job, n = named["job"], named["n"]'),

    # 2. the refusals
    ("an artifact without its attempt is skipped unseen", PROOF,
     "            refusals.append(f\"{artifact.name} does not end in -attempt-<n>",
     "            (f\"{artifact.name} does not end in -attempt-<n>"),
    ("two jobs writing one file name overwrite each other", PROOF,
     "            if file.name in owner:",
     "            if False:"),

    # 3. CI wires it
    ("the integration upload names no attempt", CI,
     "          name: test-ids-integration-attempt-${{ github.run_attempt }}",
     "          name: test-ids-integration"),
    ("the test job merges every attempt into one directory again", CI,
     "          path: ${{ runner.temp }}/test-id-artifacts\n",
     "          path: ${{ runner.temp }}/test-id-artifacts\n          merge-multiple: true\n"),
    ("the proof runs on the downloads without picking the newest", CI,
     "        run: python scripts/every_test_ran_once.py --newest-attempts",
     "        run: echo scripts/every_test_ran_once.py"),
]
