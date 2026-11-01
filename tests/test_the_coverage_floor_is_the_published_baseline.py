"""The suite's coverage is a floor CI holds, and the figure docs/STATUS.md publishes is that floor.

WHY (#334). The suite had no coverage measurement at all. Its cost was being audited — 25,195 tests,
the unit set 11 min 22 s on 8 cores — under the rule "coverage stays as it is or goes up", and
nothing could hold that rule without a number: a test could be deleted and nobody could say what
it had been the only one to reach.

THE RULES THIS FILE HOLDS:
  1. docs/STATUS.md publishes the baseline (line, branch, total, the commit it was measured on),
     and its TOTAL is `fail_under` in pyproject.toml — the one place the floor is read. Editing one
     without the other is red here, so a stale baseline cannot be a green one;
  2. the floor measures `beeverforge/` alone, with branches;
  3. CI measures in every unit slice and holds the COMBINED data to the floor, in the job the
     rulesets know (`test`) — on pushes to main only, never on a pull request (measuring costs the
     unit tests 1.4x to 1.9x their wall clock); no slice is held to the whole suite's floor alone;
  4. below the floor the report fails, with coverage.py's sentence naming the figure and the floor,
     and ours naming the remedy — run for real, over a measurement of one import.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import textwrap
import tomllib
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
CI = ROOT / ".github" / "workflows" / "ci.yml"
STATUS = ROOT / "docs" / "STATUS.md"

#: The sentence on docs/STATUS.md that carries the baseline. Its three figures are read in order,
#: and the commit after them is the one they were measured on. `\s+` between words, because the
#: page is prose wrapped at 100 columns and a re-wrap must not read as a missing baseline.
BASELINE = re.compile(
    r"coverage\s+of\s+`beeverforge/`.*?line\s+\*\*(\d+\.\d{2})%\*\*,\s+branch\s+"
    r"\*\*(\d+\.\d{2})%\*\*,\s+total\s+\*\*(\d+\.\d{2})%\*\*.*?measured\s+on\s+"
    r"`([0-9a-f]{7,40})`", re.S | re.I)


def _coverage_config() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["coverage"]


def _published() -> tuple[float, float, float, str]:
    found = BASELINE.search(STATUS.read_text(encoding="utf-8"))
    assert found, ("docs/STATUS.md no longer publishes the coverage baseline (line, branch and total "
                   "of `beeverforge/`, and the commit they were measured on)")
    line, branch, total, sha = found.groups()
    return float(line), float(branch), float(total), sha


def _make_n(*args: str) -> str:
    """`make -n` with only the variables named here. This suite runs INSIDE `make coverage`, whose
    MAKEFLAGS carry TEST_COVERAGE=1, and inside CI's unit slices, whose environment does: read
    with either, the plain unit run expands as the measured one and the difference is unseeable."""
    return subprocess.run(["make", "-n", *args], cwd=ROOT, capture_output=True, text=True,
                          timeout=60, env=_env()).stdout


# ── 1. the published figure is the floor ────────────────────────────────────────────────────────

def test_the_total_status_publishes_is_the_floor_pyproject_holds():
    _, _, total, _ = _published()
    floor = _coverage_config()["report"].get("fail_under")

    assert floor == total, (
        f"docs/STATUS.md publishes a coverage total of {total:.2f}% and pyproject.toml's "
        f"[tool.coverage.report] fail_under is {floor} — the floor CI holds and the figure the page "
        f"states have parted; edit both in the pull request that moved one")


def test_the_published_figures_are_a_measurement_and_not_a_typo():
    """A total is the lines and branches counted together, so it lies between the two — a total
    outside them was typed, not measured. And the commit is one this history holds."""
    line, branch, total, sha = _published()

    assert 0 < min(line, branch) <= total <= max(line, branch) <= 100, (
        f"line {line}%, branch {branch}%, total {total}%: a total of lines and branches lies "
        f"between the two")
    shallow = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT,
                             capture_output=True, text=True, timeout=60)
    if shallow.stdout.strip() != "false":
        pytest.skip("shallow clone, or no git history: absence of a commit here means nothing")
    known = subprocess.run(["git", "cat-file", "-e", f"{sha}^{{commit}}"], cwd=ROOT,
                           capture_output=True, timeout=60)
    assert known.returncode == 0, (
        f"docs/STATUS.md says the coverage baseline was measured on `{sha}`, which is not a commit "
        f"in this repository — nobody can reproduce the figure")


# ── 2. what is measured ─────────────────────────────────────────────────────────────────────────

def test_the_floor_measures_the_package_alone_with_branches():
    config = _coverage_config()

    assert config["run"].get("source") == ["beeverforge"], (
        f"coverage measures {config['run'].get('source')}: a test file is covered by running it, "
        f"so anything beside the package lets a deleted test raise the figure")
    assert config["run"].get("branch") is True, (
        "branch coverage is off: a line figure is green over an `if` whose other arm never ran")
    assert config["run"].get("relative_files") is True, (
        "the data names absolute paths: four runners' slices do not combine onto one tree")
    floor = config["report"].get("fail_under")
    assert isinstance(floor, (int, float)) and 0 < floor <= 100, (
        f"fail_under is {floor!r}: there is no floor")
    assert config["report"].get("precision") == 2 and round(floor, 2) == floor, (
        "the floor and the report disagree on how many decimals a figure has")


# ── 3. CI measures every unit slice and holds the combined data ────────────────────────────────

def _jobs() -> dict:
    return yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"]


def _step(job: dict, **match: str) -> dict:
    return next((s for s in job["steps"]
                 if all(str(s.get(k, "")).startswith(v) for k, v in match.items())), {})


#: The context CI's coverage conditions may read, beside quoted literals and `== != && || ! ( )`.
#: Anything else is refused rather than guessed at, so a condition this reader cannot judge is red.
_CONTEXT = {"github.event_name", "needs.unit.result"}


def _holds(expression: object, event: str) -> bool:
    """Whether a CI condition — an `if:`, or an env value written as `${{ … }}` — is true on
    `event` with every job before it green. These few operators mean what Python's do over truthy
    strings: GitHub's `a && b || c` is Python's `a and b or c`."""
    text = str(expression or "").strip()
    if not text.startswith("${{"):
        if not re.search(r"[=&|!]|github\.|needs\.", text):
            return bool(text)          # a plain value: "1" measures, "" does not
        text = "${{ " + text + " }}"   # an `if:` is an expression without the braces
    body = text.removeprefix("${{").removesuffix("}}").strip()
    unquoted = re.sub(r"'[^']*'", "''", body)
    names = set(re.findall(r"[A-Za-z_]\w*(?:\.\w+)*", unquoted))
    assert names <= _CONTEXT, f"a coverage condition reads {sorted(names - _CONTEXT)}: {text}"
    assert re.fullmatch(r"(?:''|[\w.]+|==|!=|&&|\|\||!|\(|\)|\s)+", unquoted), text
    python = (body.replace("github.event_name", repr(event))
              .replace("needs.unit.result", "'success'")
              .replace("&&", " and ").replace("||", " or ")
              .replace("!=", " __NE__ ").replace("!", " not ").replace(" __NE__ ", " != "))
    return bool(eval(python, {"__builtins__": {}}, {}))  # noqa: S307 — every token checked above


def _coverage_steps() -> dict[str, dict]:
    """The steps that measure, carry or hold coverage, found by what they do."""
    jobs = _jobs()
    upload = next((s for s in jobs["unit"]["steps"]
                   if s.get("uses", "").startswith("actions/upload-artifact")
                   and str(s["with"]["name"]).startswith("coverage-unit-")), None)
    download = next((s for s in jobs["test"]["steps"]
                     if s.get("uses", "").startswith("actions/download-artifact")
                     and s["with"].get("pattern") == "coverage-unit-*"), None)
    install = next((s for s in jobs["test"]["steps"]
                    if re.search(r"\bpip install\b.*\bcoverage\b", s.get("run", ""))), None)
    report = _step(jobs["test"], run="make coverage-report")
    assert upload, "the unit slices measure and upload nothing for the test job to combine"
    assert download, "the test job does not gather the slices' coverage data"
    assert install, "the test job installs no coverage.py to read the slices' data"
    assert report, "the job named `test` no longer holds the combined coverage to the floor"
    return {"measure": _step(jobs["unit"], run="make test-unit"), "upload": upload,
            "install": install, "download": download, "report": report}


def test_every_unit_slice_measures_and_hands_its_data_to_the_test_job():
    steps = _coverage_steps()
    upload, download = steps["upload"], steps["download"]

    assert "${{ matrix.shard }}" in upload["with"]["name"], "the four slices upload under one name"
    assert upload["with"]["path"].startswith("${{ runner.temp }}/beeverforge-coverage")
    assert upload["with"].get("if-no-files-found") == "error", (
        "a slice that wrote no data would upload nothing and the floor would be held over three")
    assert download["with"]["path"] == "${{ runner.temp }}/beeverforge-coverage", (
        "the test job does not gather the slices' data where `make coverage-report` reads it")
    assert download["with"].get("merge-multiple") is True


def test_a_push_to_main_is_measured_and_held_and_a_pull_request_is_neither():
    """The choice made for #334: measuring costs the unit tests 1.4x to 1.9x their wall clock, so a
    pull request is not slowed by it, and the floor is held on every push to main — right after
    each merge, where a red names the merge that lowered it. Judged by evaluating each condition on
    both events, so a rewording that means the same stays green and one that does not is red."""
    steps = _coverage_steps()
    conditions = {"measure": (steps["measure"].get("env") or {}).get("TEST_COVERAGE")}
    conditions |= {name: steps[name].get("if")
                   for name in ("upload", "install", "download", "report")}

    off_on_push = sorted(name for name, cond in conditions.items() if not _holds(cond, "push"))
    assert not off_on_push, (
        f"on a push to main the coverage steps {off_on_push} do not run: the floor is held over "
        f"nothing after the merge it exists to catch")
    on_for_pull_requests = sorted(name for name, cond in conditions.items()
                                  if _holds(cond, "pull_request"))
    assert not on_for_pull_requests, (
        f"on a pull request the coverage steps {on_for_pull_requests} run: every pull request pays "
        f"the 1.4x to 1.9x of the unit wall clock the measurement costs")


def test_the_condition_reader_judges_both_events_and_refuses_what_it_cannot_read():
    """Verify the verifier on the shapes CI uses, and on one it must not guess at."""
    measured = "${{ github.event_name == 'push' && '1' || '' }}"
    held = "github.event_name == 'push' && needs.unit.result == 'success'"

    assert _holds(measured, "push") and not _holds(measured, "pull_request")
    assert _holds(held, "push") and not _holds(held, "pull_request")
    assert _holds("1", "pull_request") and not _holds("", "push") and not _holds(None, "push")
    assert _holds("needs.unit.result == 'success'", "pull_request")
    assert _holds("github.event_name != 'pull_request'", "push")
    assert not _holds("!(github.event_name == 'push')", "push")
    with pytest.raises(AssertionError):
        _holds("contains(github.ref, 'main')", "push")


def test_a_measured_run_is_the_unit_selection_and_no_slice_is_held_to_the_floor():
    plain = _make_n("test-unit")
    measured = _make_n("test-unit", "TEST_COVERAGE=1")
    sliced = _make_n("test-unit", "TEST_COVERAGE=1", "TEST_SHARD=2", "TEST_SHARDS=4")

    marker = re.search(r'-m "([^"]+)"', plain).group(1)
    assert f'-m "{marker}"' in measured, "the measured run selects other tests than the unit run"
    assert "--cov" not in plain, "every unit run pays for the measurement"
    for run in (measured, sliced):
        assert "--cov-fail-under=0" in run, (
            "pytest-cov reads fail_under from the config, so a slice is held to the whole suite's "
            "floor and every CI slice is red")
    assert re.search(r"rm -rf \S+beeverforge-coverage", measured), (
        "a whole run leaves last run's slices beside its own, and the report combines a stale "
        "figure into a fresh one")
    assert "rm -rf" not in sliced, "a slice deletes the slices measured before it"
    assert re.search(r"coverage\.unit-2-of-4\b", sliced), "the slices write one file name"

    report = _make_n("coverage-report")
    assert "coverage report" in report and "--fail-under" not in report, (
        "the report overrides the floor on its command line, so pyproject.toml is not where it is "
        "read")


# ── 4. below the floor, the report fails and says so ────────────────────────────────────────────

def _env() -> dict[str, str]:
    """This environment without coverage's own variables or CI's slice variables: the measurement
    below is of one import, written where this test says, whatever run this test is part of."""
    return {k: v for k, v in os.environ.items()
            if not k.startswith(("COVERAGE_", "TEST_", "MAKE")) and k != "MFLAGS"
            } | {"PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ.get('PATH', '')}"}


@pytest.fixture(scope="module")
def one_import(tmp_path_factory):
    """A real measurement of `beeverforge/`, far below any floor: one import, one slice."""
    where = tmp_path_factory.mktemp("coverage-floor")
    assert ROOT not in where.resolve().parents, "the measurement is inside the tree under test"
    script = where / "one_import.py"
    script.write_text("import beeverforge  # noqa: F401\n", encoding="utf-8")
    ran = subprocess.run(
        [sys.executable, "-m", "coverage", "run", f"--rcfile={ROOT / 'pyproject.toml'}",
         f"--data-file={where / 'coverage.unit-1-of-1'}", str(script)],
        cwd=ROOT, capture_output=True, text=True, timeout=300, env=_env())
    assert ran.returncode == 0, ran.stdout[-800:] + ran.stderr[-800:]
    return where


def _report(where: Path, **env: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["make", "--no-print-directory", "coverage-report",
                           f"COVERAGE_DIR={where}"], cwd=ROOT, capture_output=True, text=True,
                          timeout=300, env=_env() | env)


def test_below_the_floor_the_report_fails_naming_the_figure_the_floor_and_the_remedy(one_import):
    done = _report(one_import)
    said = done.stdout + done.stderr
    floor = _coverage_config()["report"]["fail_under"]

    assert done.returncode != 0, f"one import of the package passed the floor:\n{said[-1500:]}"
    failure = re.search(r"Coverage failure: total of (\d+\.\d{2}) is less than "
                        r"fail-under=(\d+\.\d{2})", said)
    assert failure, f"the failure does not name the figure and the floor:\n{said[-1500:]}"
    assert float(failure.group(2)) == floor and float(failure.group(1)) < floor
    assert "fell below the floor in pyproject.toml" in said and "docs/STATUS.md" in said, (
        f"the failure does not say what to do about it:\n{said[-1500:]}")


def test_the_floor_is_what_fails_it(one_import, tmp_path):
    """The twin: the same data under a floor of zero passes, so the red above is the floor's and
    not a report that cannot run."""
    config = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    zero = tmp_path / "pyproject.toml"
    zero.write_text(re.sub(r"(?m)^fail_under = .*$", "fail_under = 0", config), encoding="utf-8")

    done = _report(one_import, COVERAGE_RCFILE=str(zero))

    assert done.returncode == 0, (done.stdout + done.stderr)[-1500:]
    assert "fell below the floor" not in done.stdout + done.stderr


def test_no_data_is_refused_by_name_and_not_reported_as_a_low_figure(tmp_path):
    done = _report(tmp_path)

    assert done.returncode != 0
    assert "there is no coverage data to combine" in done.stderr, done.stderr[-800:]
    assert "Coverage failure" not in done.stdout + done.stderr


def test_the_reader_of_the_page_reads_a_sentence_of_the_shape_it_expects():
    """Verify the verifier: the pattern reads the three figures in order and the commit."""
    text = textwrap.dedent("""\
        The coverage of `beeverforge/` by the unit tests is line **81.20%**, branch **70.05%**,
        total **78.40%**, measured on `b5f2742` with `make coverage`.""")

    assert BASELINE.search(text).groups() == ("81.20", "70.05", "78.40", "b5f2742")
