"""The Opus review is the merge gate, so its workflow is read and run here, not only by hand.

`.github/workflows/opus-semantic-review.yml` decides which pull requests are reviewed, whose words
count as their scope, and which verdicts let a merge through. `opus/semantic-review` is a required
status on `main` and on the release branches, and no person's approval is required: a mistake in
this file either blocks every merge or lets one through unreviewed. Until now every check of it
was a run somebody made by hand and reported (#709, #714, #720).

WHAT IS RUN IS THE WORKFLOW'S OWN SHELL, taken from the YAML as GitHub would run it
(`bash -eo pipefail`), with a `gh` of this file's own first on the PATH that answers from a table
and writes down every call. No network, no token, no model.

WHAT THIS DOES NOT PROVE: the two Opus calls, GitHub's own reading of the triggers, and the
rulesets. Those are GitHub's and the model's; a hosted run shows them.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "opus-semantic-review.yml"
CI = ROOT / ".github" / "workflows" / "ci.yml"
REPO = "acme/forge"
FACTORY = "beeverforge-oss[bot]"
HEAD = "a" * 40
OLDER = "b" * 40

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("jq") is None,
    reason="the workflow's steps are bash and jq, as on the runner")

#: A `gh` that answers `gh api <path>` from `answers.json` (a missing path is a 404), applies
#: `--jq` with the machine's jq, and appends every call to `calls.jsonl`.
FAKE_GH = '''#!{python}
import json, os, subprocess, sys
here = os.path.dirname(os.path.abspath(__file__))
args = sys.argv[1:]
with open(os.path.join(here, "calls.jsonl"), "a", encoding="utf-8") as log:
    log.write(json.dumps(args) + "\\n")
if args[:1] != ["api"]:
    sys.exit(1 if os.environ.get("NO_RUN_CAN_BE_STARTED") else 0)
rest, method, jq, path = args[1:], "GET", None, None
while rest:
    word = rest.pop(0)
    if word == "--method":
        method = rest.pop(0)
    elif word == "--jq":
        jq = rest.pop(0)
    elif word in ("-f", "-F"):
        rest.pop(0)
    elif word in ("--paginate", "--silent"):
        continue
    elif path is None:
        path = word
if method != "GET":
    sys.exit(0)
answers = json.load(open(os.path.join(here, "answers.json"), encoding="utf-8"))
if path not in answers:
    sys.stderr.write("gh: Not Found (HTTP 404)\\n")
    sys.exit(1)
body = json.dumps(answers[path])
if jq is None:
    sys.stdout.write(body + "\\n")
    sys.exit(0)
sys.exit(subprocess.run(["jq", "-r", jq], input=body, text=True).returncode)
'''


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _triggers(workflow: dict) -> dict:
    # YAML 1.1 reads the key `on` as the boolean True
    return workflow[True] if True in workflow else workflow["on"]


def _step(job: str, name: str) -> str:
    for step in _workflow()["jobs"][job]["steps"]:
        if step.get("name", "").startswith(name):
            return step["run"]
    raise AssertionError(f"the job {job!r} has no step named {name!r}")


class Runner:
    """One step of the workflow, run as the runner runs it, against a table of API answers."""

    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.bin = tmp / "bin"
        self.bin.mkdir()
        gh = self.bin / "gh"
        gh.write_text(FAKE_GH.format(python=sys.executable), encoding="utf-8")
        gh.chmod(0o755)
        self.work = tmp / "work"
        self.work.mkdir()
        self.answers: dict[str, object] = {}

    def run(self, script: str, **env: str) -> subprocess.CompletedProcess:
        (self.bin / "answers.json").write_text(json.dumps(self.answers), encoding="utf-8")
        (self.bin / "calls.jsonl").write_text("", encoding="utf-8")
        output = self.tmp / "github-output"
        output.write_text("", encoding="utf-8")
        temp = self.tmp / "runner-temp"
        temp.mkdir(exist_ok=True)
        return subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", script],
            cwd=self.work, capture_output=True, text=True, timeout=60, check=False,
            env={"PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}", "GITHUB_REPOSITORY": REPO,
                 "GITHUB_OUTPUT": str(output), "RUNNER_TEMP": str(temp),
                 "GITHUB_SERVER_URL": "https://github.example", "GITHUB_RUN_ID": "1",
                 "REVIEW_MARKER": "<!-- beeverforge-opus-semantic-review -->",
                 "FACTORY_APP": FACTORY, **env})

    @property
    def outputs(self) -> dict[str, str]:
        lines = (self.tmp / "github-output").read_text(encoding="utf-8").splitlines()
        return dict(line.split("=", 1) for line in lines if "=" in line)

    @property
    def calls(self) -> list[list[str]]:
        text = (self.bin / "calls.jsonl").read_text(encoding="utf-8")
        return [json.loads(line) for line in text.splitlines()]


@pytest.fixture
def runner(tmp_path: Path) -> Runner:
    return Runner(tmp_path)


def _pull(number: int, *, state: str = "open", draft: bool = False, repo: str = REPO,
          author: str = "ana", head: str = HEAD, base: str = "main") -> dict:
    return {"number": number, "state": state, "draft": draft, "user": {"login": author},
            "head": {"sha": head, "repo": {"full_name": repo}}, "base": {"ref": base}}


# ── every pull request, whatever its base ───────────────────────────────────────────────────────

def test_the_review_starts_from_ci_which_runs_on_every_pull_request():
    """`pull_request_target` is read from the BASE branch, so a pull request into a release branch
    started no review (#716). A `workflow_run` workflow is read from `main`, and `ci` runs on a
    pull request into any branch: the pair is what makes "every pull request" true."""
    triggers = _triggers(_workflow())
    assert triggers["workflow_run"] == {"workflows": ["ci"], "types": ["requested"]}
    assert set(triggers) == {"workflow_run", "pull_request_target", "workflow_dispatch"}
    assert triggers["pull_request_target"] == {"types": ["ready_for_review"]}

    ci = yaml.safe_load(CI.read_text(encoding="utf-8"))
    assert ci["name"] == "ci", "the review names the workflow it starts from"
    on_pull_request = _triggers(ci)["pull_request"]
    assert not on_pull_request, f"ci must run on a pull request into ANY branch: {on_pull_request}"


def test_a_ci_rerun_or_a_push_to_main_is_not_a_review():
    condition = " ".join(_workflow()["jobs"]["target"]["if"].split())
    assert "github.event.workflow_run.event == 'pull_request'" in condition
    assert "github.event.workflow_run.run_attempt == 1" in condition
    assert "github.event.workflow_run.head_repository.full_name == github.repository" in condition


def test_a_pull_request_into_a_release_branch_is_found_by_its_head(runner):
    """The event of a `ci` run does not always name the pull request; its head does."""
    runner.answers = {f"repos/{REPO}/commits/{HEAD}/pulls": [_pull(712, base="release/0.2")],
                      f"repos/{REPO}/pulls/712": _pull(712, base="release/0.2")}

    ran = runner.run(_step("target", "Resolve"), ASKED="", RUN_HEAD_SHA=HEAD, BY_HAND="false")

    assert ran.returncode == 0, ran.stderr
    assert runner.outputs == {"pr": "712", "head_sha": HEAD, "eligible": "true"}
    assert "into release/0.2" in ran.stdout


def test_every_pull_request_of_one_head_gets_a_review(runner):
    """One branch open into `main` and into a release branch: this run reviews one, and starts a
    run by number for the other."""
    runner.answers = {f"repos/{REPO}/commits/{HEAD}/pulls":
                          [_pull(10), _pull(11, base="release/0.2"), _pull(12, state="closed")],
                      f"repos/{REPO}/pulls/10": _pull(10)}

    ran = runner.run(_step("target", "Resolve"), ASKED="10", RUN_HEAD_SHA=HEAD, BY_HAND="false")

    assert ran.returncode == 0, ran.stderr
    assert runner.outputs["pr"] == "10" and runner.outputs["eligible"] == "true"
    started = [call for call in runner.calls if call[:2] == ["workflow", "run"]]
    assert started == [["workflow", "run", "opus-semantic-review.yml", "--repo", REPO,
                        "-f", "pr=11", "-f", "started_by_workflow=true"]], \
        "the workflow's own run: a refusal there is a notice, and it always reviews (#726)"
    listed = [call for call in runner.calls if call[-1].endswith(f"/commits/{HEAD}/pulls")]
    assert len(listed) == 1, "the head's pull requests are asked for once"


def test_another_pull_request_that_would_only_be_refused_is_not_started(runner):
    """Started by number, a draft or a fork is refused as an ERROR (somebody asked): red runs
    for pull requests nobody asked about."""
    runner.answers = {f"repos/{REPO}/commits/{HEAD}/pulls":
                          [_pull(10), _pull(11, draft=True), _pull(12, repo="stranger/forge"),
                           _pull(13, author="dependabot[bot]")],
                      f"repos/{REPO}/pulls/10": _pull(10)}

    ran = runner.run(_step("target", "Resolve"), ASKED="10", RUN_HEAD_SHA=HEAD, BY_HAND="false")

    assert ran.returncode == 0 and runner.outputs["eligible"] == "true"
    assert [call for call in runner.calls if call[:2] == ["workflow", "run"]] == []


def test_a_review_that_cannot_be_started_for_another_costs_this_one_nothing(runner):
    runner.answers = {f"repos/{REPO}/commits/{HEAD}/pulls": [_pull(10), _pull(11)],
                      f"repos/{REPO}/pulls/10": _pull(10)}

    ran = runner.run(_step("target", "Resolve"), ASKED="10", RUN_HEAD_SHA=HEAD, BY_HAND="false",
                     NO_RUN_CAN_BE_STARTED="1")

    assert ran.returncode == 0, ran.stderr
    assert runner.outputs == {"pr": "10", "head_sha": HEAD, "eligible": "true"}
    assert "::warning::#11 has the same head and its review could not be started" in ran.stdout
    assert "-f pr=11" in ran.stdout, "the warning carries the command that starts it"


@pytest.mark.parametrize("pull, why", [
    (_pull(5, state="closed"), "#5 is closed"),
    (_pull(5, draft=True), "#5 is a draft"),
    (_pull(5, repo="stranger/forge"), "#5 comes from another repository"),
    (_pull(5, author="dependabot[bot]"), "#5 is from dependabot"),
], ids=["closed", "draft", "fork", "dependabot"])
def test_a_pull_request_that_is_not_reviewed_is_named_with_its_reason(runner, pull, why):
    """A fork must never reach the job that holds the Claude credential; and nothing is skipped
    in silence. Asked by a person, the refusal fails the run; started by an event, it is a notice."""
    runner.answers = {f"repos/{REPO}/pulls/5": pull}

    by_event = runner.run(_step("target", "Resolve"), ASKED="5", RUN_HEAD_SHA="", BY_HAND="false")
    assert by_event.returncode == 0 and runner.outputs == {"eligible": "false"}
    assert f"::notice::Not reviewed: {why}" in by_event.stdout

    by_hand = runner.run(_step("target", "Resolve"), ASKED="5", RUN_HEAD_SHA="", BY_HAND="true")
    assert by_hand.returncode == 1 and runner.outputs == {"eligible": "false"}
    assert f"::error::Not reviewed: {why}" in by_hand.stdout


def test_a_ci_run_for_a_head_the_pull_request_has_left_reviews_nothing(runner):
    runner.answers = {f"repos/{REPO}/commits/{OLDER}/pulls": [],
                      f"repos/{REPO}/pulls/5": _pull(5, head=HEAD)}

    ran = runner.run(_step("target", "Resolve"), ASKED="5", RUN_HEAD_SHA=OLDER, BY_HAND="false")

    assert ran.returncode == 0 and runner.outputs == {"eligible": "false"}
    assert "#5 has moved past bbbbbbbbbbbb" in ran.stdout


@pytest.mark.parametrize("asked", ["1.5", "", "0", "7; echo pwned"])
def test_what_is_not_a_pull_request_number_asks_the_api_nothing(runner, asked):
    ran = runner.run(_step("target", "Resolve"), ASKED=asked, RUN_HEAD_SHA="", BY_HAND="true")

    assert ran.returncode == 1 and "::error::Not reviewed: no open pull request number" in ran.stdout
    assert runner.calls == [] and "pwned" not in ran.stdout.replace(asked, "")


# ── one review per pull request ─────────────────────────────────────────────────────────────────

def test_one_review_at_a_time_per_pull_request_and_the_next_one_waits():
    """Keyed by the number on the REVIEW job. On the workflow, the number is not known yet, a run
    by hand and an event's run had two keys, and a `ci` re-run cancelled a review it did not
    replace (#714's review, findings B and 3).

    AND IT WAITS RATHER THAN CANCELS (#723's review): jobs enter the group in the order they
    start, so with cancelling the review of an older head could cancel the newer head's and leave
    the pull request with no status."""
    workflow = _workflow()
    assert "concurrency" not in workflow
    assert workflow["jobs"]["review"]["concurrency"] == {
        "group": "opus-semantic-review-pr-${{ needs.target.outputs.pr }}",
        "cancel-in-progress": False}
    assert "concurrency" not in workflow["jobs"]["target"]
    publish = workflow["jobs"]["publish"]["if"]
    assert "needs.review.result != 'cancelled'" in publish, "a replaced review publishes nothing"
    assert "needs.review.result != 'skipped'" in publish


def test_a_model_call_that_hangs_ends_as_a_failure_that_is_published():
    """`publish` says nothing for a CANCELLED review, which is what a replaced one is. A job
    stopped by its own time limit ends cancelled too, so the model's step carries a shorter limit
    of its own: the step fails, the job fails, and "Review unavailable" is published."""
    review = _workflow()["jobs"]["review"]
    opus = next(step for step in review["steps"] if step.get("id") == "opus")
    assert opus["timeout-minutes"] < review["timeout-minutes"]


def test_no_job_holds_more_than_it_needs():
    workflow = _workflow()
    assert workflow["permissions"] == {}
    jobs = workflow["jobs"]
    assert jobs["review"]["permissions"] == {"contents": "read", "issues": "read",
                                             "pull-requests": "read", "statuses": "read"}
    assert jobs["ensure"]["permissions"] == {"actions": "write", "pull-requests": "read",
                                             "statuses": "read"}
    assert jobs["publish"]["permissions"] == {"pull-requests": "write", "statuses": "write"}
    assert jobs["target"]["permissions"] == {"actions": "write", "contents": "read",
                                             "pull-requests": "read"}
    holders = [name for name, job in jobs.items() if "CLAUDE_CODE_OAUTH_TOKEN" in json.dumps(job)]
    assert holders == ["review"], "only the job that can write nothing holds the Claude credential"


# ── no pull request is left without a status ───────────────────────────────────────────────────

def _status(context: str = "opus/semantic-review") -> dict:
    return {"context": context, "state": "failure"}


#: This run's jobs, as the last job asks for them (`GITHUB_RUN_ID` is 1 in `Runner`).
JOBS = f"repos/{REPO}/actions/runs/1/jobs"


def _jobs(*, review_steps: int) -> dict:
    return {"jobs": [{"name": "target", "steps": [{"name": "Resolve"}]},
                     {"name": "review", "steps": [{"name": f"step {n}"}
                                                  for n in range(review_steps)]}]}


def _started(runner: Runner) -> list[list[str]]:
    return [call for call in runner.calls if call[:2] == ["workflow", "run"]]


def test_at_the_end_of_every_run_a_head_with_no_status_gets_a_review(runner):
    """The status is required for merging, and a run can end without one: a waiting review
    replaced by one that entered the group later, a head the pull request left meanwhile. So the
    last job asks about the head AS IT IS NOW, whatever this run was reviewing."""
    runner.answers = {f"repos/{REPO}/pulls/9": _pull(9, head=HEAD),
                      f"repos/{REPO}/commits/{HEAD}/statuses": [_status("ci/lint")]}

    ran = runner.run(_step("ensure", "Start a review"), PR_NUMBER="9", ATTEMPT="1",
                     REVIEW_RESULT="failure")

    assert ran.returncode == 0, ran.stderr
    assert _started(runner) == [["workflow", "run", "opus-semantic-review.yml", "--repo", REPO,
                                 "-f", "pr=9", "-f", "only_if_missing=true", "-f", "attempt=2"]]
    assert "::notice::#9 at aaaaaaaaaaaa had no status" in ran.stdout


def test_a_review_replaced_while_it_waited_leaves_the_head_to_the_run_that_replaced_it(runner):
    """A run it started would enter the group and replace the review that is waiting there, whose
    own last job would start another: two pushes during one review made four runs and a false
    "no status after 3 tries" (#723's review). REPLACED WHILE WAITING MEANS NO STEP OF IT RAN."""
    runner.answers = {f"repos/{REPO}/pulls/9": _pull(9, head=HEAD),
                      f"repos/{REPO}/commits/{HEAD}/statuses": [],
                      JOBS: _jobs(review_steps=0)}

    ran = runner.run(_step("ensure", "Start a review"), PR_NUMBER="9", ATTEMPT="1",
                     REVIEW_RESULT="cancelled")

    assert ran.returncode == 0 and _started(runner) == []
    assert [call[1] for call in runner.calls] == [JOBS], "it asks only whether it ever started"
    assert "the run that replaced it answers for the head" in ran.stdout


def test_a_review_cancelled_after_it_started_is_answered_for(runner):
    """Cancelled by a person, or by the job's time limit outside the model's step: nothing
    replaced it, so reading it as "replaced" left the head with no status and nobody to notice
    (#726)."""
    runner.answers = {f"repos/{REPO}/pulls/9": _pull(9, head=HEAD),
                      f"repos/{REPO}/commits/{HEAD}/statuses": [],
                      JOBS: _jobs(review_steps=3)}

    ran = runner.run(_step("ensure", "Start a review"), PR_NUMBER="9", ATTEMPT="1",
                     REVIEW_RESULT="cancelled")

    assert ran.returncode == 0, ran.stderr
    assert len(_started(runner)) == 1 and "cancelled after it started" in ran.stdout


def _two_pushes_during_one_review() -> list[str]:
    """Which runs start a run, in #723's scenario, by the workflow's own last step: R0 reviews H0;
    H1 waits and is replaced by H2; R0 ends, H2 runs and publishes; every run's last job then
    asks. Each entry is (name, the review's result, whether the head has its status by then)."""
    return [("H1, replaced while waiting", "cancelled", False),
            ("R0, whose head the pull request left", "failure", False),
            ("H2, which published", "success", True)]


def test_two_pushes_during_one_review_start_one_extra_run_and_no_alarm(runner):
    started, alarms = [], []
    for name, result, has_status in _two_pushes_during_one_review():
        runner.answers = {f"repos/{REPO}/pulls/9": _pull(9, head=HEAD),
                          f"repos/{REPO}/commits/{HEAD}/statuses": [_status()] * has_status,
                          JOBS: _jobs(review_steps=0)}
        ran = runner.run(_step("ensure", "Start a review"), PR_NUMBER="9", ATTEMPT="1",
                         REVIEW_RESULT=result)
        assert ran.returncode == 0, name
        started += [name] * len(_started(runner))
        alarms += [name] * ran.stdout.count("::error::")

    assert started == ["R0, whose head the pull request left"] and alarms == []


def test_a_head_that_has_its_status_starts_nothing(runner):
    runner.answers = {f"repos/{REPO}/pulls/9": _pull(9, head=HEAD),
                      f"repos/{REPO}/commits/{HEAD}/statuses": [_status()]}

    ran = runner.run(_step("ensure", "Start a review"), PR_NUMBER="9", ATTEMPT="1")

    assert ran.returncode == 0 and _started(runner) == []


@pytest.mark.parametrize("pull", [_pull(9, state="closed"), _pull(9, draft=True),
                                  _pull(9, repo="stranger/forge")],
                         ids=["closed", "draft", "fork"])
def test_a_pull_request_no_longer_reviewed_is_not_chased(runner, pull):
    runner.answers = {f"repos/{REPO}/pulls/9": pull,
                      f"repos/{REPO}/commits/{HEAD}/statuses": []}

    ran = runner.run(_step("ensure", "Start a review"), PR_NUMBER="9", ATTEMPT="1")

    assert ran.returncode == 0 and _started(runner) == []


@pytest.mark.parametrize("attempt", ["5", "7", "not a number"])
def test_a_gap_five_tries_do_not_fill_is_said_and_not_chased(runner, attempt):
    """A status that cannot be posted at all would otherwise start runs for ever."""
    runner.answers = {f"repos/{REPO}/pulls/9": _pull(9, head=HEAD),
                      f"repos/{REPO}/commits/{HEAD}/statuses": []}

    ran = runner.run(_step("ensure", "Start a review"), PR_NUMBER="9", ATTEMPT=attempt)

    assert ran.returncode == 1 and _started(runner) == []
    assert "::error::#9 at aaaaaaaaaaaa has no opus/semantic-review status" in ran.stdout
    assert "gh workflow run opus-semantic-review.yml -f pr=9" in ran.stdout


def test_the_last_job_runs_whatever_happened_to_the_review():
    jobs = _workflow()["jobs"]
    assert jobs["ensure"]["needs"] == ["target", "review", "publish"]
    condition = jobs["ensure"]["if"]
    assert "always()" in condition and "needs.target.outputs.eligible == 'true'" in condition


@pytest.mark.parametrize("current, statuses, needed", [
    (HEAD, [], "true"),
    (HEAD, [_status("ci/lint")], "true"),
    (HEAD, [_status()], "false"),
    (OLDER, [], "false"),
], ids=["no status yet", "another check's status", "already reviewed", "the head has moved"])
def test_a_run_started_to_fill_a_gap_reviews_only_if_the_gap_is_still_there(
        runner, current, statuses, needed):
    """Asked after the wait in the group: by then the review it was started for may have
    published, and a second Opus call would buy nothing."""
    runner.answers = {f"repos/{REPO}/pulls/9": _pull(9, head=current),
                      f"repos/{REPO}/commits/{HEAD}/statuses": statuses}

    ran = runner.run(_step("review", "Is this review still needed"), PR_NUMBER="9",
                     HEAD_SHA=HEAD, ONLY_IF_MISSING="true")

    assert ran.returncode == 0, ran.stderr
    assert runner.outputs == {"needed": needed}


def test_a_run_a_person_starts_by_number_reviews_without_asking(runner):
    ran = runner.run(_step("review", "Is this review still needed"), PR_NUMBER="9",
                     HEAD_SHA=HEAD, ONLY_IF_MISSING="false")

    assert ran.returncode == 0 and runner.outputs == {"needed": "true"} and runner.calls == []


def test_only_a_person_asking_by_number_reviews_a_head_that_has_its_review():
    """A push that lands as a review ends can bring two runs to the new head, its own and the one
    the last job starts: whichever comes second finds the status and does nothing (#726). A
    person's run by number is the way to ask for a second look, so it never asks first."""
    need = next(step for step in _workflow()["jobs"]["review"]["steps"] if step.get("id") == "need")
    asked = need["env"]["ONLY_IF_MISSING"]
    assert asked == "${{ github.event_name != 'workflow_dispatch' || inputs.only_if_missing }}"
    # …and the run started for ANOTHER pull request of the same head is not one of the skipped:
    # the two share a commit, so the first to publish would otherwise stand in for the other,
    # whose base and scope are its own
    assert "started_by_workflow" not in asked


def test_a_review_that_was_not_needed_does_nothing_and_publishes_nothing():
    jobs = _workflow()["jobs"]
    steps = jobs["review"]["steps"]
    assert steps[0]["id"] == "need"
    assert [step.get("if") for step in steps[1:]] == ["steps.need.outputs.needed == 'true'"] * 4
    assert "needs.review.outputs.needed != 'false'" in jobs["publish"]["if"]
    target = json.dumps(jobs["target"])
    assert ("github.event_name == 'workflow_dispatch' && !inputs.only_if_missing "
            "&& !inputs.started_by_workflow") in target, \
        "a run the workflow started is not somebody asking: its refusal is a notice"


# ── whose words are the scope ───────────────────────────────────────────────────────────────────

def _scope_block() -> str:
    """The part of the collecting step that decides who sets scope, from its own comment on."""
    script = _step("review", "Collect")
    return script[script.index("# WHO MAY SET SCOPE"):]


def _issue(number: int, login: str, kind: str = "User") -> dict:
    return {"number": number, "title": f"title {number}", "body": f"body {number}",
            "author_association": "CONTRIBUTOR", "user": {"login": login, "type": kind}}


def _comment(login: str, body: str, kind: str = "User") -> dict:
    return {"body": body, "author_association": "CONTRIBUTOR",
            "user": {"login": login, "type": kind}}


def _closing(runner: Runner, *numbers: int) -> None:
    (runner.work / "context").mkdir(exist_ok=True)
    (runner.work / "context" / "pr.json").write_text(json.dumps({"closingIssuesReferences": [
        {"number": n, "url": f"https://github.com/{REPO}/issues/{n}"} for n in numbers]}))


def _read(runner: Runner, name: str):
    return json.loads((runner.work / "context" / name).read_text(encoding="utf-8"))


def test_whoever_can_write_to_the_repository_sets_scope_whatever_their_profile_shows(runner):
    """`author_association` said CONTRIBUTOR for a maintainer whose organisation membership is
    private, so nothing they filed counted and their pull request could not merge (#719). Every
    author here is a CONTRIBUTOR to that field; what differs is what the repository answers."""
    _closing(runner, 1, 2)
    runner.answers = {
        f"repos/{REPO}/issues/1": _issue(1, "maintainer"),
        f"repos/{REPO}/issues/1/comments": [_comment("maintainer", "agreed"),
                                            _comment("admin", "also this"),
                                            _comment("reader", "and my wish")],
        f"repos/{REPO}/issues/2": _issue(2, "reader"),
        f"repos/{REPO}/issues/2/comments": [],
        f"repos/{REPO}/collaborators/maintainer/permission": {"permission": "write"},
        f"repos/{REPO}/collaborators/admin/permission": {"permission": "admin"},
        f"repos/{REPO}/collaborators/reader/permission": {"permission": "read"},
    }

    ran = runner.run(_scope_block())

    assert ran.returncode == 0, ran.stderr
    assert _read(runner, "issue-1.json") == {"number": 1, "trusted_author": True,
                                             "title": "title 1", "body": "body 1"}
    assert _read(runner, "issue-1-comments.json") == [{"body": "agreed"}, {"body": "also this"}]
    outsider = _read(runner, "issue-2.json")
    assert outsider["trusted_author"] is False
    assert "title" not in outsider and "body" not in outsider, "an outsider's text is left out"


def test_the_factorys_issue_is_scope_and_what_a_bot_comments_is_not(runner):
    _closing(runner, 3, 4)
    runner.answers = {
        f"repos/{REPO}/issues/3": _issue(3, FACTORY, "Bot"),
        f"repos/{REPO}/issues/3/comments": [_comment(FACTORY, "On hold", "Bot")],
        f"repos/{REPO}/issues/4": _issue(4, "another-app[bot]", "Bot"),
        f"repos/{REPO}/issues/4/comments": [],
    }

    ran = runner.run(_scope_block())

    assert ran.returncode == 0, ran.stderr
    assert _read(runner, "issue-3.json")["trusted_author"] is True
    assert _read(runner, "issue-3-comments.json") == []
    assert _read(runner, "issue-4.json")["trusted_author"] is False
    asked = [call for call in runner.calls if "/collaborators/" in " ".join(call)]
    assert asked == [], "a bot is matched by its login, never asked about"


def test_a_user_named_like_the_factory_is_not_the_factory(runner):
    _closing(runner, 5)
    runner.answers = {f"repos/{REPO}/issues/5": _issue(5, FACTORY, "User"),
                      f"repos/{REPO}/issues/5/comments": []}

    ran = runner.run(_scope_block())

    assert ran.returncode == 0, ran.stderr
    assert _read(runner, "issue-5.json")["trusted_author"] is False


def test_each_person_is_asked_about_once_and_a_question_that_fails_is_said(runner):
    """A cached "no" is an answer (the first cut asked a non-writer again every time), and a call
    that fails is not a quiet "no": the run says it could not ask."""
    _closing(runner, 6, 7)
    runner.answers = {
        f"repos/{REPO}/issues/6": _issue(6, "reader"),
        f"repos/{REPO}/issues/6/comments": [_comment("reader", "one"), _comment("ghost", "two")],
        f"repos/{REPO}/issues/7": _issue(7, "reader"),
        f"repos/{REPO}/issues/7/comments": [_comment("ghost", "three")],
        f"repos/{REPO}/collaborators/reader/permission": {"permission": "read"},
    }

    ran = runner.run(_scope_block())

    assert ran.returncode == 0, ran.stderr
    asked = [call[1].rsplit("/", 2)[1] for call in runner.calls if "/collaborators/" in call[1]]
    assert sorted(asked) == ["ghost", "reader"]
    assert ran.stdout.count("::warning::Could not ask whether ghost can write") == 1
    assert "HTTP 404" in ran.stdout
    assert _read(runner, "issue-7-comments.json") == []


@pytest.mark.parametrize("pull_request", ['{"closingIssuesReferences": ', "{}"],
                         ids=["cut short", "no list"])
def test_a_list_of_issues_that_cannot_be_read_stops_the_step(runner, pull_request):
    """Inside `< <(…)` a failing `jq` is invisible, and the review would run against no issue."""
    (runner.work / "context").mkdir()
    (runner.work / "context" / "pr.json").write_text(pull_request)

    assert runner.run(_scope_block()).returncode != 0


def test_a_pull_request_that_closes_no_issue_collects_no_scope(runner):
    _closing(runner)

    ran = runner.run(_scope_block())

    assert ran.returncode == 0, ran.stderr
    assert [p.name for p in (runner.work / "context").iterdir()] == ["pr.json"]


# ── which verdicts let a merge through ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("result, verdict, state, title", [
    ("success", "pass", "success", "Passed"),
    ("success", "changes_requested", "failure", "Changes requested"),
    ("success", "inconclusive", "failure", "Inconclusive"),
    ("failure", "", "failure", "Review unavailable"),
    ("success", "approved", "failure", "Review unavailable"),
])
def test_only_a_pass_is_a_green_status(runner, result, verdict, state, title):
    """The status is required for merging. Code without an issue is not merged, so INCONCLUSIVE
    IS RED; and a review that did not run, or said a word nobody defined, is red too."""
    runner.answers = {f"repos/{REPO}/pulls/9": _pull(9),
                      f"repos/{REPO}/issues/9/comments": []}

    ran = runner.run(_step("publish", "Update the PR"), PR_NUMBER="9", HEAD_SHA=HEAD,
                     REVIEW_RESULT=result, VERDICT=verdict,
                     REPORT_JSON=json.dumps("## A heading\n@someone see [this](http://x)"))

    assert (ran.returncode == 0) == (state == "success"), ran.stdout + ran.stderr
    statuses = [call for call in runner.calls if call[-1:] and f"statuses/{HEAD}" in " ".join(call)]
    assert len(statuses) == 1
    assert f"state={state}" in statuses[0] and "context=opus/semantic-review" in statuses[0]
    assert f"description={title}" in statuses[0]
    posted = (runner.tmp / "runner-temp" / "review.md").read_text(encoding="utf-8")
    assert f"## Opus semantic review — {title}" in posted
    if result == "success" and title != "Review unavailable":
        # the model's words are published as an indented block: no mention, link or heading lives
        assert "\n    ## A heading\n    @someone see [this](http://x)" in posted


def test_a_review_of_a_head_the_pull_request_has_left_publishes_nothing(runner):
    # the comments answer too, so that the head is the ONLY thing that can stop this step
    runner.answers = {f"repos/{REPO}/pulls/9": _pull(9, head=OLDER),
                      f"repos/{REPO}/issues/9/comments": []}

    ran = runner.run(_step("publish", "Update the PR"), PR_NUMBER="9", HEAD_SHA=HEAD,
                     REVIEW_RESULT="success", VERDICT="pass", REPORT_JSON='"fine"')

    assert ran.returncode == 1
    assert [call for call in runner.calls if "--method" in call] == []
