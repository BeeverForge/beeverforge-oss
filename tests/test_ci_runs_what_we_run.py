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
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

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
