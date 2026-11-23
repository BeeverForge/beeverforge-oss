"""The suite must pass the way CI RUNS it, not only the way a developer runs it.

FOUND 2026-08-05, with five commits already landed on a red `main`. `pytest -q` — the exact
command `.github/workflows/ci.yml` runs — died in COLLECTION:

    ImportError: Error importing plugin "tests.test_walking_skeleton": No module named 'tests'

`tests/test_a_failing_setup_is_not_silent.py` declares `pytest_plugins = [...]`, which pytest
imports by name, so the `tests` package must be importable. `python -m pytest` prepends the
current directory to `sys.path` and it was; the bare `pytest` console script does not. Every
developer ran the first form and saw 3599 green; CI ran the second and saw one error, on every
push, for days — the platform that enforces gates on other repositories shipping past its own.

That is `validate-in-the-cloud-not-just-local` in its cheapest possible form: the difference was
not the cloud, the OS or a dependency. It was the first two words of the command.

The fix is `pythonpath = ["."]` in the pytest config, so both invocations are identical. This
file is the guard that keeps them that way — it runs the CI invocation, in a subprocess, and
fails loudly when collection does.
"""

from __future__ import annotations

import ast
import fnmatch
import os
import re
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from tests.the_tree_read_once import parsed

ROOT = Path(__file__).resolve().parent.parent
CI = ROOT / ".github" / "workflows" / "ci.yml"

#: THIS PROCESS'S ENVIRONMENT, CAPTURED ONCE AT IMPORT (#1069). The conftest's `pytest_configure`
#: has already re-homed `HOME` and stripped `BEEVERFORGE_*` by now; what it sets per test
#: (`BEEVERFORGE_REGISTRY`, `BEEVERFORGE_LOG_DIR`, `PYTEST_CURRENT_TEST`) differs for every test, so
#: a key on the live environment would never repeat. Every collection below is handed this.
_ENV = dict(os.environ)

#: (argv, environment) → the collection that invocation produced, run once per process.
#: Never invalidated, by design: the tree does not change under a running suite, and it dies with it.
_RUNS: dict[tuple[tuple[str, ...], tuple[tuple[str, str], ...]],
            subprocess.CompletedProcess[str]] = {}


def _collected(argv: tuple[str, ...], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """`argv` run from the repository root under `env`, ONCE per distinct pair in this process.

    The questions below asked the same whole-suite collection up to three times, each ~7 s of
    CPU. The answer is shared: callers read it and never change it."""
    key = (argv, tuple(sorted(env.items())))
    if key not in _RUNS:
        _RUNS[key] = subprocess.run(list(argv), cwd=ROOT, capture_output=True, text=True,
                                    timeout=300, env=env)
    return _RUNS[key]


def _test_roots() -> list[Path]:
    """The directories pytest collects when it is named nothing: `testpaths`, kept to what the
    tree holds (`addons/*/tests` leaves with the public cut)."""
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    return sorted({p for pattern in config["tool"]["pytest"]["ini_options"]["testpaths"]
                   for p in ROOT.glob(pattern) if p.is_dir()})


def _console_script() -> str:
    """THIS environment's `pytest` console script, not whatever `PATH` happens to find.

    The point of these tests is one difference — console script vs `python -m` — so every OTHER
    difference has to be held still. A bare `"pytest"` picks up the system interpreter's copy,
    which has none of this project's dependencies, and then reports a pile of import errors that
    look exactly like the bug and are not it."""
    return str(Path(sys.executable).parent / "pytest")


def _text(path: Path) -> str:
    """The file's source, or "" for one that VANISHED between the listing and the open (see
    `_mentions_demo_projects` below for the sibling test that writes and deletes one)."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _relative(paths: set[Path]) -> tuple[str, ...]:
    return tuple(sorted(str(p.relative_to(ROOT)) for p in paths))


def _plugins_declared(source: str) -> list[str]:
    """The module names a module's top-level `pytest_plugins` assignment hands pytest."""
    for node in ast.parse(source).body:
        targets = node.targets if isinstance(node, ast.Assign) else (
            [node.target] if isinstance(node, ast.AnnAssign) else [])
        if any(isinstance(t, ast.Name) and t.id == "pytest_plugins" for t in targets):
            value = node.value
            items = value.elts if isinstance(value, (ast.List, ast.Tuple)) else [value]
            return [i.value for i in items
                    if isinstance(i, ast.Constant) and isinstance(i.value, str)]
    return []


def _plugin_subset() -> tuple[str, ...]:
    """What the console-script guards collect: every test module that declares `pytest_plugins`,
    and every module those declarations name.

    THE INCIDENT SITE, DERIVED. On 2026-08-05 the bare console script died importing a plugin by
    name (`tests.test_walking_skeleton`), because nothing put the repository root on `sys.path`;
    the declarers are where pytest imports `tests.` by name before any test runs, so a collection
    of them is a collection that hits it. Whoever adds the next declarer is covered without
    knowing this file exists. The whole tree is collected once per CI run by the lint job's
    `make test-collect`; asking it again here cost ~15 s a guard and found nothing more."""
    declarers: set[Path] = set()
    plugins: set[Path] = set()
    for root in _test_roots():
        for path in root.glob("test_*.py"):
            source = _text(path)
            named = _plugins_declared(source) if "pytest_plugins" in source else []
            if named:
                declarers.add(path)
                plugins |= {f for name in named
                            if (f := ROOT.joinpath(*name.split(".")).with_suffix(".py")).is_file()}
    assert declarers, (
        "no test module declares `pytest_plugins`, so the console-script guards collect nothing "
        "that imports `tests.` by name; re-aim them at whatever now does")
    return _relative(declarers | plugins)


def test_the_bare_pytest_console_script_can_COLLECT_the_suite():
    """THE regression, run for real. Collection is enough: an import-time failure (a plugin, a
    conftest, a missing package) is the whole class this guard exists for, and running the
    files would cost minutes.

    OF THE FILES THAT CAN HOLD IT (#336), not of the whole tree: `_plugin_subset` is every module
    that imports a plugin by name, the exact failure of 2026-08-05, and the conftest at the root
    of the tests loads for any subset."""
    proc = _collected((_console_script(), "-q", "--collect-only", *_plugin_subset()), _ENV)

    assert proc.returncode == 0, (
        "the suite does not COLLECT under the bare `pytest` console script — which is exactly "
        "what CI runs, so CI is red no matter how green this machine looks:\n"
        f"{(proc.stdout + proc.stderr)[-1500:]}"
    )


def test_that_invocation_sees_the_same_tests_this_one_does():
    """A collection that succeeds while seeing FEWER tests is the same failure wearing a green
    tick — `testpaths`, an import mode or a rootdir difference silently hiding a directory.

    THE SAME SUBSET UNDER BOTH INVOCATIONS (#336): what differs between them is `sys.path` at
    import, so the files to compare are the ones that import `tests.` by name before a test
    runs. Both read one config and start in one directory, so `testpaths` and the rootdir are
    held equal by construction and need no whole tree to show it."""
    subset = _plugin_subset()
    proc = _collected((_console_script(), "-q", "--collect-only", *subset), _ENV)
    match = re.search(r"(\d+) tests? collected", proc.stdout)
    assert match, f"could not read the collected count from:\n{proc.stdout[-800:]}"

    collected = int(match.group(1))
    # this process was itself started by pytest, so its own invocation is the reference
    mine = _collected((sys.executable, "-m", "pytest", "-q", "--collect-only", *subset), _ENV)
    mine_match = re.search(r"(\d+) tests? collected", mine.stdout)
    assert mine_match, "could not read the reference count"

    assert collected == int(mine_match.group(1)), (
        f"`pytest` collects {collected} tests and `python -m pytest` collects "
        f"{mine_match.group(1)} — CI and this machine are running different suites"
    )


def _mentions_demo_projects(path: Path) -> bool:
    """Whether this test module reads the toy projects — tolerating a file that VANISHES between
    the listing and the open.

    `tests/test__live_engine_probe__.py` is written and deleted by a sibling test while the suite
    runs, so any walk of `tests/` can list it and then fail to read it. Byte-for-byte the same
    tolerance `test_schedules_are_reachable.py::_callers_of` already applies to its own walk, and
    for the same reason: a `FileNotFoundError` here is a race, never a flake, and never evidence
    about the module the caller was actually asking about."""
    try:
        return "demo_projects" in path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False


def _imports(source: str) -> set[str]:
    """Every module name a source imports, at any depth, or names in `pytest_plugins`.

    `from tests import x` is counted as `tests.x` as well as `tests`, because that is the module
    it loads."""
    names = set(_plugins_declared(source))
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names |= {f"{node.module}.{alias.name}" for alias in node.names}
    return names


def _toy_project_subset() -> tuple[str, ...]:
    """What the toy-less guard collects: every test module that can reach the toy-project reader
    at import, directly or through a helper.

    THE ONE THING THE STRIPPED ENVIRONMENT CHANGES is `BEEVERFORGE_FIXTURES`, and the code that
    reads it is `tests/demo_projects.py`; a module that never imports it, at any depth, collects
    the same either way. So the subset starts at every module under the test roots that names the
    reader or the variable, then grows by import until it stops: a helper that imports a member
    joins, and so does every module importing that helper. `88139ad`'s module was a direct
    reader; a helper that breaks at import takes down modules that never name the reader, and the
    closure is what keeps those in."""
    sources = {p: _text(p) for root in _test_roots() for p in root.rglob("*.py")}

    def names(path: Path) -> set[str]:
        return {".".join(path.relative_to(ROOT).with_suffix("").parts), path.stem}

    reach = {p for p, source in sources.items()
             if "demo_projects" in source or "BEEVERFORGE_FIXTURES" in source}
    while True:
        known = {name for p in reach for name in names(p)}
        stems = {p.stem for p in reach}
        joined = {p for p, source in sources.items()
                  if p not in reach and any(stem in source for stem in stems)
                  and _imports(source) & known}
        if not joined:
            break
        reach |= joined
    return _relative({p for p in reach if p.name.startswith("test_")})


@pytest.mark.whole_tree
def test_collection_survives_a_machine_without_THE_OPTIONAL_TOY_PROJECTS():
    """AND IT HAPPENED AGAIN, for fifteen days — the two guards above ran in a subprocess but
    INHERITED THIS MACHINE'S ENVIRONMENT, where `~/Projects/…` holds the toy projects. So both
    collected fine, on the one machine where the missing piece is not missing.

    On 2026-08-06 `88139ad` added, at module scope, `FIXTURES = demo_projects()` followed by
    `FIXTURES / "fx-dsk-flows"`. `demo_projects()` answers None where there is nothing to read —
    correctly, and its docstring says so — and None divided by a string raises `TypeError` at
    IMPORT. One module raising during collection aborts the ENTIRE run: `Interrupted: 1 error
    during collection`. Every CI run from that commit until 2026-08-21 executed ZERO tests and
    reported failure. 253 of them. The platform that refuses to merge a client's red branch had
    been shipping past its own gate for a fortnight, and the tree was genuinely green here.

    THE PROPERTY, stated so it outlives the toy projects: collection must not depend on OPTIONAL
    WORKING STATE. A contributor with a fresh clone and none of the author's directories must
    collect the same suite this machine does — the tests that need those directories skip at RUN
    time, which is a decision each test makes, not one that deletes everybody else's.

    OF THE MODULES THAT CAN REACH THE TOY PROJECTS (#336), not of the whole tree: one module
    raising aborted the whole collection, and the module that raises is one that imports the
    reader, directly or through a helper. `_toy_project_subset` is that closure.
    """
    stripped = {**_ENV, "BEEVERFORGE_FIXTURES": str(ROOT / "no-such-toy-projects")}
    proc = _collected((_console_script(), "-q", "--collect-only", *_toy_project_subset()), stripped)

    assert proc.returncode == 0, (
        "collection needs optional working state that no other machine has — CI collects nothing "
        "and every run is red while this laptop stays green:\n"
        f"{(proc.stdout + proc.stderr)[-1500:]}"
    )

    #: THE POSITIVE TWIN, and the half that matters most. A module can also fail SOFTLY: wrap the
    #: import in a try/except, or call `pytest.skip(allow_module_level=True)`, and it stops raising
    #: — it just stops EXISTING, and the suite shrinks without a word. Absence read as compliance.
    #:
    #: ASKED OF THIS ONE COLLECTION, not of a second reference run. Comparing two collections taken
    #: seconds apart makes the guard depend on the tree holding still, and under `-n auto` it does
    #: not: the first version of this test failed once in three full runs and passed alone every
    #: time. A guard that flakes is a guard somebody deletes, and it would have taken the fifteen
    #: days of evidence above with it.
    #:
    #: THE MODULES ARE DERIVED, never listed by hand — whoever adds the fifth caller of
    #: `demo_projects_root` is covered without knowing this file exists.
    #:
    #: AND THE READ TOLERATES A FILE THAT VANISHES BETWEEN THE LISTING AND THE OPEN. A sibling
    #: test WRITES AND DELETES a real file under `tests/` (`test__live_engine_probe__.py`, the
    #: guard proving the live-engine barrier applies to an actual pytest run), so this glob can
    #: list a path that is gone by the time it is read — measured 2026-09-02, a full-suite-only
    #: `FileNotFoundError` on exactly that name. `test_schedules_are_reachable.py::_callers_of`
    #: already carries this same tolerance, with the same reasoning, for the same walk; this file
    #: had the identical glob-and-read and not the guard. Fixing one and leaving its neighbour is
    #: how a defect class survives being found.
    #:
    #: TOLERATED, NEVER FILTERED BY NAME: `glob` cannot list a file that does not exist, so the
    #: only way to reach the skip is a file that disappeared mid-walk. A module genuinely missing
    #: from the tree is still missing from `dependents`, and the count assertion below still
    #: catches it.
    dependents = sorted(p.name for p in (ROOT / "tests").glob("test_*.py")
                        if _mentions_demo_projects(p))
    assert len(dependents) >= 4, (
        f"only {dependents} read the toy projects — this guard has lost its subject")

    missing = [name for name in dependents if name not in proc.stdout]
    assert not missing, (
        f"{missing} vanish from collection on a machine without the toy projects, instead of "
        f"skipping at run time — every contributor and CI silently loses those tests, and the "
        f"suite reports green about coverage that did not run")


@pytest.mark.whole_tree
def test_no_guard_here_collects_the_whole_suite(monkeypatch: pytest.MonkeyPatch) -> None:
    """THE COST THESE GUARDS USED TO PAY, refused (#336). Each of the three above collected all
    885 test files in a child pytest, about 15 s apiece beside busy workers, and the slowest
    tests of every unit run were these three, re-asking what the lint job's `make test-collect`
    already asks once per CI run. Each failure they exist for lives in a SUBSET (an import error
    at collection), so each collects the subset that can hold it, and this keeps it that way.

    Driven with `subprocess.run` replaced: the guards are called as they are, every child they
    start is recorded instead of run, and each must name the files it collects."""
    every = {str(p.relative_to(ROOT)) for root in _test_roots() for p in root.rglob("test_*.py")}
    listing = "\n".join(sorted(every))
    runs: list[list[str]] = []

    def record(argv, **kwargs):
        runs.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, stdout=f"{listing}\n7 tests collected",
                                           stderr="")

    monkeypatch.setattr(sys.modules[__name__], "_RUNS", {})
    monkeypatch.setattr(subprocess, "run", record)
    test_the_bare_pytest_console_script_can_COLLECT_the_suite()
    test_that_invocation_sees_the_same_tests_this_one_does()
    test_collection_survives_a_machine_without_THE_OPTIONAL_TOY_PROJECTS()

    assert runs, "the guards started no collection at all, so this measures nothing"
    named: set[str] = set()
    for argv in runs:
        paths = argv[argv.index("--collect-only") + 1:]
        assert paths, (
            f"`{' '.join(argv)}` collects the whole suite again; name the test files whose "
            f"collection holds the failure that guard exists for")
        named |= set(paths)
    assert named < every, (
        f"the guards collect {len(named)} of {len(every)} test files, which is the whole suite "
        f"in pieces; collect only the files that can hold each guard's failure")



@pytest.mark.skipif(not CI.exists(), reason="no CI workflow in this checkout")
def test_ci_s_one_whole_collection_is_the_bare_console_script():
    """THE WHOLE-TREE HALF of the console-script guards above, held where it costs nothing (#350).
    Since #336 they collect a subset: the modules that declare `pytest_plugins`, and the modules
    those name. A module that fails only under the bare console script OUTSIDE that subset is
    seen by one collection alone: the lint job's `make test-collect`, the whole tree once per CI
    run. So CI must run that step, and its recipe must be the console script's.

    Read, not grepped: the step is one of CI's `run:` lines (a commented-out step is not), and the
    recipe is what `make -n test-collect` expands to, as the lines below are read. No toy-project
    setting is checked: tests/conftest.py strips every `BEEVERFORGE_*` variable before collection,
    so every collection is already toy-less, and
    tests/test_the_suite_reads_no_operators_beeverforge.py holds that strip."""
    runs = re.findall(r"^\s*(?:-\s*)?run:\s*(.+?)\s*$", CI.read_text(), re.M)
    assert "make test-collect" in runs, (
        "ci.yml runs no `make test-collect` step, so no job collects the whole tree under the "
        "console script; run it in the lint job again, or move this guard to what replaced it")
    shown = subprocess.run(["make", "-n", "test-collect"], cwd=ROOT, capture_output=True,
                           text=True, timeout=60)
    lines = [line for line in shown.stdout.splitlines() if "--collect-only" in line]
    assert len(lines) == 1, (
        f"`make test-collect` should run one collection, and `make -n` shows {len(lines)}: "
        f"{shown.stdout or shown.stderr}")
    words = shlex.split(lines[0])
    while words and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", words[0]):
        words.pop(0)
    assert words and Path(words[0]).name == "pytest", (
        f"`make test-collect` runs `{' '.join(words[:3])}`, not the bare `pytest` console script, "
        f"so a module that dies only under the console script outside the plugin subset is "
        f"collected nowhere; start the recipe with `pytest`")


@pytest.mark.skipif(not CI.exists(), reason="no CI workflow in this checkout")
def test_ci_still_runs_the_command_this_guard_protects():
    """If CI's command changes, this guard is protecting the wrong thing — and would keep
    passing while saying nothing, which is the failure shape it was written against.

    THROUGH THE MAKEFILE, since CI runs the suite as parallel jobs (`make test-unit`,
    `make test-integration`): the line read is the one make itself expands, as the linter's
    below is, so a target that stopped running pytest is seen."""
    assert any(re.search(r"\bpytest\b", line) for line in _lines_ci_runs()), (
        "ci.yml no longer runs pytest, directly or through a Makefile target — update this guard "
        "to whatever it runs now, or it is asserting a property nobody depends on"
    )


def _lines_ci_runs() -> list[str]:
    """Every command CI runs: each `run:` line, and each Makefile target one names as make
    expands it (`make -n`), with the variables CI's jobs pass left empty."""
    lines = []
    for run in re.findall(r"^\s*(?:-\s*)?run:\s*(.+?)\s*$", CI.read_text(), re.M):
        lines.append(run)
        m = re.fullmatch(r"make\s+(\S+)", run)
        if m:
            shown = subprocess.run(["make", "-n", m.group(1)], cwd=ROOT, capture_output=True,
                                   text=True, timeout=60)
            lines += shown.stdout.splitlines()
    return lines


# ── the linter, too ─────────────────────────────────────────────────────────────────────────────
#
# FOUND 2026-08-26 by the review of the chat cut: the gate ran `ruff check beeverforge/ tests/
# addons/` and CI ran `ruff check beeverforge/ tests/` — the add-on packages were never linted
# where it counts. Same class as the collection defect above: the command differed by one word.
# The roots are DERIVED (the package by its installed name, the first segment of every pytest
# testpath, kept to what the tree holds — `addons/` leaves the export), and the line CI runs is
# resolved the way CI resolves it: `make -n <target>` when CI names a Makefile target, so the
# Makefile's own expansion (`$(wildcard addons)`) is what gets read, not our guess at it.


def _lint_roots_the_suite_covers() -> set[str]:
    import beeverforge

    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    roots = {Path(beeverforge.__file__).resolve().parent.name}
    roots |= {p.split("/", 1)[0] for p in config["tool"]["pytest"]["ini_options"]["testpaths"]}
    return {r for r in roots if (ROOT / r).is_dir()}


def _ruff_line_ci_runs() -> str:
    """The `ruff check …` CI ends up running: a `run:` line of its own, or the Makefile target
    it names, expanded by make itself."""
    runs = re.findall(r"^\s*-\s*run:\s*(.+?)\s*$", CI.read_text(), re.M)
    direct = [r for r in runs if re.search(r"\bruff check\b", r)]
    if direct:
        return direct[0]
    for run in runs:
        m = re.fullmatch(r"make\s+(\S+)", run)
        if not m:
            continue
        shown = subprocess.run(["make", "-n", m.group(1)], cwd=ROOT, capture_output=True,
                               text=True, timeout=60)
        for line in shown.stdout.splitlines():
            if re.search(r"\bruff check\b", line):
                return line.strip()
    return ""


def _ruff_targets(line: str) -> set[str]:
    words = line.split()
    assert words[:2] == ["ruff", "check"], line
    return {w.rstrip("/") for w in words[2:] if not w.startswith("-")}


@pytest.mark.skipif(not CI.exists(), reason="no CI workflow in this checkout")
def test_ci_lints_every_root_the_suite_covers():
    line = _ruff_line_ci_runs()
    assert line, "ci.yml runs no `ruff check` — directly or through a Makefile target"
    roots = _lint_roots_the_suite_covers()
    assert {"beeverforge", "tests"} <= roots, roots
    missing = sorted(roots - _ruff_targets(line))
    assert not missing, (
        f"CI lints {sorted(_ruff_targets(line))} and the suite covers {sorted(roots)} — {missing} "
        f"are never linted where it counts (`ruff check` runs as `{line}`)")


def test_the_roots_follow_the_tree_and_the_line_reader_can_SEE_a_target():
    """Verify the verifier: the derived set holds the add-on packages exactly when the tree does,
    and the reader distinguishes a target from a flag."""
    roots = _lint_roots_the_suite_covers()
    assert ("addons" in roots) == (ROOT / "addons").is_dir()
    assert _ruff_targets("ruff check beeverforge/ tests/ --fix addons") == {"beeverforge", "tests",
                                                                            "addons"}


# ── the shard table's refresh ───────────────────────────────────────────────────────────────────
#
# #649: the table was built once and never rebuilt, and a per-change check on its staleness failed
# whichever change added the file that crossed 10%. The share moved to the refresh workflow, which
# rebuilds the table from CI's four unit reports. So its command must stay the builder's own, with
# the share, and read exactly the reports CI's unit jobs write. Read from the parsed YAML, never by
# matching text: a comment that quotes the command must not pass for the command.

REFRESH = ROOT / ".github" / "workflows" / "refresh-shard-durations.yml"
BUILDER = ROOT / "tests" / "shard_durations.py"


def _workflow(path: Path) -> dict:
    import yaml

    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if True in loaded:  # YAML 1.1 reads the bare key `on` as true
        loaded["on"] = loaded.pop(True)
    return loaded


def _steps(workflow: dict) -> list[tuple[str, dict]]:
    return [(name, step) for name, job in workflow["jobs"].items() for step in job.get("steps", [])]


def _documented_refresh() -> list[str]:
    """The refresh command `tests/shard_durations.py` documents, up to its first placeholder."""
    doc = ast.get_docstring(parsed(BUILDER)) or ""
    lines = [line.strip() for line in doc.splitlines()
             if line.strip().startswith("python -m tests.shard_durations --max-unlisted")]
    assert len(lines) == 1, f"{BUILDER.name} documents the refresh command {len(lines)} times"
    words = shlex.split(lines[0])
    return words[:next(i for i, word in enumerate(words) if word.startswith("<"))]


def test_the_refresh_runs_the_builders_command_on_the_four_reports_ci_writes():
    import yaml

    documented = _documented_refresh()
    assert documented == ["python", "-m", "tests.shard_durations", "--max-unlisted", "0.1"], documented
    workflow = _workflow(REFRESH)
    lines = [line.strip() for _job, step in _steps(workflow)
             for line in step.get("run", "").splitlines()
             if re.match(r"\s*(\S+/)?python\S*\s+-m\s+tests\.shard_durations\b", line)]
    assert len(lines) == 1, lines
    words = shlex.split(lines[0])
    assert words[:len(documented)] == documented, (words, documented)

    unit = yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"]["unit"]
    env = next(step["env"] for step in unit["steps"] if step.get("run") == "make test-unit")
    shards = range(1, int(env["TEST_SHARDS"]) + 1)
    assert list(shards) == unit["strategy"]["matrix"]["shard"]
    wanted = [Path(env["TEST_JUNIT"]).name.replace("${{ matrix.shard }}", str(n)) for n in shards]
    reports = words[len(documented):]
    assert [Path(report).name for report in reports] == wanted, (reports, wanted)
    folder = {str(Path(report).parent) for report in reports}
    assert len(folder) == 1, folder

    # the reports are the newest attempt of each unit artifact of the run, picked by the proof's rule
    upload = next(step for step in unit["steps"]
                  if str(step.get("uses", "")).startswith("actions/upload-artifact@"))
    names = [upload["with"]["name"].replace("${{ matrix.shard }}", str(n)) for n in shards]
    downloads = [step for _job, step in _steps(workflow)
                 if str(step.get("uses", "")).startswith("actions/download-artifact@")
                 and step["with"].get("run-id")]
    assert len(downloads) == 1, downloads
    pattern = downloads[0]["with"]["pattern"]
    assert all(fnmatch.fnmatch(name.replace("${{ github.run_attempt }}", "1"), pattern)
               for name in names), (pattern, names)
    assert not fnmatch.fnmatch("test-ids-integration-attempt-1", pattern), pattern
    picks = [line for _job, step in _steps(workflow) for line in step.get("run", "").splitlines()
             if "--newest-attempts" in line]
    assert len(picks) == 1, picks
    pick = shlex.split(picks[0])
    assert pick[:3] == ["python", "scripts/every_test_ran_once.py", "--newest-attempts"], pick
    assert pick[4] == folder.pop(), (pick, reports)


# #656: the last job opened the pull request itself, with `gh pr create` and GITHUB_TOKEN. That
# needs the repository setting "Allow GitHub Actions to create and approve pull requests", which is
# off here and is one switch for creating AND approving: with it on, any workflow step holding
# `pull-requests: write` could approve a pull request, and main's one required approval would count
# it. A pull request GITHUB_TOKEN opens starts no workflow either, so it got no `ci` run. So the job
# pushes a branch with `contents: write` only and hands a maintainer the link that opens the pull
# request; the person's pull request is the person's event, and `ci` runs on it.

#: a command that opens, approves or merges a pull request on GitHub, by its CLI or its API
_PULL_REQUEST_BY_WORKFLOW = re.compile(
    r"\bgh\s+pr\s+(create|merge|review)\b|\bgh\s+api\b.*\bpulls\b")
#: an action that does the same from a `uses:`
_PULL_REQUEST_ACTION = re.compile(r"pull-request|approve|merge", re.IGNORECASE)
#: a command that runs code: an interpreter, a build tool, or a script by its path
_RUNS_CODE = re.compile(
    r"(^|[;&|(]\s*)(python\S*|pip\S*|pytest|make|npm|npx|node|uv|bash|sh|source|\.)\s|(^|\s)\./")


def _shell_lines(step: dict) -> list[str]:
    """The commands of a step's `run:`, comment lines left out: a comment is not a command."""
    return [line.strip() for line in step.get("run", "").splitlines()
            if line.strip() and not line.strip().startswith("#")]


def _hand_off(workflow: dict) -> tuple[str, dict, dict]:
    """The one job that pushes, and its one step that does."""
    pushes = [(name, step) for name, step in _steps(workflow)
              if any(line.startswith("git push") for line in _shell_lines(step))]
    assert len(pushes) == 1, f"the refresh should push from exactly one step: {pushes}"
    name, step = pushes[0]
    return name, workflow["jobs"][name], step


def test_the_refresh_runs_weekly_and_on_demand_and_only_its_hand_off_job_may_write():
    workflow = _workflow(REFRESH)

    assert set(workflow["on"]) == {"workflow_dispatch", "schedule"}, workflow["on"]
    assert [entry.get("cron") for entry in workflow["on"]["schedule"]], workflow["on"]["schedule"]
    assert workflow["permissions"] == {"contents": "read"}, workflow["permissions"]
    hand_off, _job, _step = _hand_off(workflow)
    for name, job in workflow["jobs"].items():
        granted = job.get("permissions")
        assert isinstance(granted, dict), f"{name} inherits instead of naming its permissions"
        if name == hand_off:
            assert granted == {"contents": "write"}, (name, granted)
        else:
            assert set(granted.items()) <= {("contents", "read"), ("actions", "read")}, (name, granted)
    for job, step in _steps(workflow):
        assert "${{" not in step.get("run", ""), (
            f"{job} interpolates an expression into a shell; hand it over in `env:`", step)
    text = REFRESH.read_text(encoding="utf-8")
    assert "pull_request_target" not in workflow["on"] and "secrets." not in text


def test_no_step_of_the_refresh_opens_approves_or_merges_a_pull_request():
    workflow = _workflow(REFRESH)

    for name, scope in [("the workflow", workflow), *workflow["jobs"].items()]:
        granted = scope.get("permissions") or {}
        assert not isinstance(granted, str) or "write" not in granted, (name, granted)
        assert isinstance(granted, str) or granted.get("pull-requests") != "write", (
            f"{name} may write pull requests; the hand-off needs `contents: write` only", granted)
    for job, step in _steps(workflow):
        for line in _shell_lines(step):
            assert not _PULL_REQUEST_BY_WORKFLOW.search(line), (
                f"{job} opens, approves or merges a pull request; push a branch and link its form",
                line)
        assert not _PULL_REQUEST_ACTION.search(str(step.get("uses", ""))), (job, step["uses"])


def test_the_refresh_hands_off_only_when_the_table_changed():
    workflow = _workflow(REFRESH)
    hand_off, job, push = _hand_off(workflow)
    (rebuild,) = job["needs"] if isinstance(job["needs"], list) else [job["needs"]]

    assert job.get("if") == f"needs.{rebuild}.outputs.changed == 'true'", job.get("if")
    output = workflow["jobs"][rebuild]["outputs"]["changed"]
    step_id = re.fullmatch(r"\$\{\{ steps\.([\w-]+)\.outputs\.changed \}\}", output)
    assert step_id, output
    diff = next(step for step in workflow["jobs"][rebuild]["steps"] if step.get("id") == step_id[1])
    assert "git diff --quiet -- tests/shard_durations.json" in diff["run"], diff
    # and the job that pushes asks again, against main as it is by then
    lines = _shell_lines(push)
    asks = next(i for i, line in enumerate(lines)
                if "git diff --quiet -- tests/shard_durations.json" in line)
    pushes = next(i for i, line in enumerate(lines) if line.startswith("git push"))
    assert asks < pushes, (hand_off, lines)


def test_the_hand_off_runs_no_code_from_the_tree():
    _name, job, _step = _hand_off(_workflow(REFRESH))

    uses = [str(step["uses"]).split("@")[0] for step in job["steps"] if "uses" in step]
    assert set(uses) <= {"actions/checkout", "actions/download-artifact"}, uses
    checkout = next(step for step in job["steps"]
                    if str(step.get("uses", "")).startswith("actions/checkout@"))
    assert checkout["with"]["ref"] == "main", checkout
    for step in job["steps"]:
        for line in _shell_lines(step):
            assert not _RUNS_CODE.search(line), f"the hand-off runs code: {line}"


#: the expressions a hand-off step may read through `env:`, and what the run below hands each
_CONTEXT = {"${{ github.repository }}": "example-owner/example-repo"}
_MAIN_TABLE = '{\n  "tests/test_a.py": 1.0\n}\n'
_REBUILT_TABLE = '{\n  "tests/test_a.py": 2.5,\n  "tests/test_b.py": 0.5\n}\n'
_RUN_ID = "4242"


def _run_hand_off(tmp_path: Path, rebuilt: str) -> tuple[subprocess.CompletedProcess[str], Path, str]:
    """The hand-off step's own shell, run as the runner runs it, in a clone of a `main` that holds
    `_MAIN_TABLE`, with `rebuilt` as the artifact the rebuild job uploaded. Returns the run, the
    bare remote it pushes to, and what it wrote to the step summary."""
    _name, job, step = _hand_off(_workflow(REFRESH))
    runner = tmp_path / "runner"
    runner.mkdir()
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path), "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": os.devnull, "GITHUB_RUN_ID": _RUN_ID, "RUNNER_TEMP": str(runner),
           "GITHUB_STEP_SUMMARY": str(runner / "summary.md"),
           "GITHUB_OUTPUT": str(runner / "output"),
           "GITHUB_REPOSITORY": _CONTEXT["${{ github.repository }}"]}
    for key, value in (step.get("env") or {}).items():
        assert value in _CONTEXT, f"the hand-off reads {key}={value}, which this test does not hand"
        env[key] = _CONTEXT[value]

    def git(*argv: str, cwd: Path) -> str:
        return subprocess.run(["git", *argv], cwd=cwd, env=env, check=True, capture_output=True,
                              text=True).stdout

    remote, tree = tmp_path / "origin.git", tmp_path / "tree"
    git("init", "-q", "--bare", "-b", "main", str(remote), cwd=tmp_path)
    git("init", "-q", "-b", "main", str(tree), cwd=tmp_path)
    (tree / "tests").mkdir()
    (tree / "tests" / "shard_durations.json").write_text(_MAIN_TABLE, encoding="utf-8")
    git("add", "-A", cwd=tree)
    git("-c", "user.name=main", "-c", "user.email=main@example.invalid", "commit", "-q", "-m",
        "main", cwd=tree)
    git("remote", "add", "origin", str(remote), cwd=tree)
    git("push", "-q", "origin", "main", cwd=tree)

    download = next(step for step in job["steps"]
                    if str(step.get("uses", "")).startswith("actions/download-artifact@"))
    folder = Path(download["with"]["path"].replace("${{ runner.temp }}", str(runner)))
    folder.mkdir(parents=True)
    (folder / "shard_durations.json").write_text(rebuilt, encoding="utf-8")

    script = runner / "step.sh"
    script.write_text(step["run"], encoding="utf-8")
    ran = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", str(script)],
                         cwd=tree, env=env, capture_output=True, text=True)
    summary = runner / "summary.md"
    return ran, remote, summary.read_text(encoding="utf-8") if summary.exists() else ""


def _in_remote(remote: Path, *argv: str) -> str:
    return subprocess.run(["git", "--git-dir", str(remote), *argv], capture_output=True, text=True,
                          check=True).stdout


def _branches(remote: Path) -> list[str]:
    return _in_remote(remote, "for-each-ref", "--format=%(refname:short)", "refs/heads").split()


def test_the_hand_off_pushes_the_branch_and_links_the_form_that_opens_its_pull_request(tmp_path):
    ran, remote, summary = _run_hand_off(tmp_path, _REBUILT_TABLE)
    branch = f"refresh-shard-durations/{_RUN_ID}"

    # green: a changed table is the outcome the run exists for, not a failure
    assert ran.returncode == 0, (ran.stdout, ran.stderr)
    assert _branches(remote) == ["main", branch], _branches(remote)
    assert _in_remote(remote, "show", f"{branch}:tests/shard_durations.json") == _REBUILT_TABLE
    touched = _in_remote(remote, "diff", "--name-only", "main", branch).split()
    assert touched == ["tests/shard_durations.json"], touched
    link = (f"https://github.com/{_CONTEXT['${{ github.repository }}']}"
            f"/compare/main...{branch}?expand=1")
    assert link in summary, summary
    assert "no-release-note" in summary, summary
    warnings = [line for line in ran.stdout.splitlines() if line.startswith("::warning")]
    assert len(warnings) == 1 and branch in warnings[0], ran.stdout


def test_the_hand_off_pushes_nothing_when_main_already_holds_the_table(tmp_path):
    ran, remote, summary = _run_hand_off(tmp_path, _MAIN_TABLE)

    assert ran.returncode == 0, (ran.stdout, ran.stderr)
    assert _branches(remote) == ["main"], _branches(remote)
    assert "/compare/" not in summary, summary
    assert "::warning" not in ran.stdout, ran.stdout
