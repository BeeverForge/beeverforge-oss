"""CI runs the suite as parallel jobs, and proves that every collected test ran exactly once.

WHY. One job running all ~17,400 tests took 22–26 minutes on every pull request. The jobs that
replace it (`.github/workflows/ci.yml`) are cut by marker and by slice, and that is exactly where a
test slips through: a marker expression one job reads and the other does not, or a slice rule that
two processes compute differently. A test no job selected would leave the gate green over nothing.

THE RULES THIS FILE HOLDS:
  1. the slices of one selection (`--shard I/N`) hold every test exactly once, whatever process
     computes them, and an xdist run writes each test it started once (`--record-ids`). A slice
     is whole test files, balanced by the committed duration table and by CRC32 of the path for a
     file the table does not list, and a shard never imports a file another shard owns (#356);
  2. the proof (`scripts/every_test_ran_once.py`) fails on a test missing, doubled or unknown, and
     names it;
  3. CI wires it: the `test` job needs every other job and runs the proof; the unit job's slices
     are the matrix's; the unit, integration and alone runs select markers that split the suite
     without overlap;
  4. a test that asserts its own CPU time is marked `alone`, so CI runs it with no neighbours on
     its cores;
  5. a test on the real Docker daemon is in the `docker` xdist group, and the integration run
     distributes by group, so two of them never share the daemon's compose projects at once.

Driven as real pytest runs over a probe outside the tree, with this suite's conftest copied beside
it, as `test_the_suite_cannot_reach_a_live_engine.py` does: only pytest applies the hooks.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import tomllib
import uuid
from collections import Counter
from pathlib import Path

import pytest
import yaml

from tests.the_tree_read_once import parsed

ROOT = Path(__file__).resolve().parent.parent
CI = ROOT / ".github" / "workflows" / "ci.yml"
SLICES = 3


def _test_roots() -> list[Path]:
    """The directories pytest collects when it is named nothing: `testpaths`, kept to what the
    tree holds (`addons/*/tests` leaves with the public cut)."""
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return sorted({p for pattern in config["tool"]["pytest"]["ini_options"]["testpaths"]
                   for p in ROOT.glob(pattern) if p.is_dir()})

#: Every probe module says when it is imported, into the file `PROBE_IMPORTS` names: the guard that
#: a shard imports only the files it owns reads it.
IMPORTED = textwrap.dedent("""\
    import os

    if os.environ.get("PROBE_IMPORTS"):
        with open(os.environ["PROBE_IMPORTS"], "a", encoding="utf-8") as log:
            log.write(__file__ + "\\n")
""")

PROBE = IMPORTED + textwrap.dedent("""\
    import pytest


    @pytest.mark.parametrize("n", range(30))
    def test_one_of_many(n):
        assert n >= 0


    @pytest.mark.skip(reason="a skipped test still counts as started")
    def test_skipped():
        pass


    @pytest.mark.xdist_group("together")
    @pytest.mark.parametrize("who", ["a@b", "c"])
    def test_grouped(who):
        assert who
""")

SMALL = IMPORTED + textwrap.dedent("""\


    def test_first():
        pass


    def test_second():
        pass
""")

#: Run through a fixture of its own conftest and a helper beside it: a shard that skipped either
#: would error these, or never collect them.
IN_SUB = IMPORTED + textwrap.dedent("""\
    import helper


    def test_the_fixture_resolves(from_the_sub_conftest):
        assert from_the_sub_conftest == "sub"


    def test_the_helper_imports():
        assert helper.WHO == "helper"
""")

#: The table the probe's conftest reads: two files of equal seconds (the path breaks the tie), and
#: one that is gone (a stale entry takes a share of nothing). Every other probe file is unlisted.
#: THE NAMES ARE CHOSEN, not arbitrary: under 3 slices `test_new_1.py` and `test_new_7.py` are the
#: files whose CRC32 lands on index 4 when the fallback is cut `% (count + 1)`, and the directory
#: `sub` hashes to slice 3 while `sub/test_in_sub.py` hashes to slice 1, so a rule that skipped a
#: directory by its own key would lose the sub tests.
TABLE = {"test_heavy.py": 5.0, "test_gone.py": 4.0, "test_probe.py": 3.0, "test_tie_b.py": 2.0,
         "test_tie_a.py": 2.0, "test_light.py": 1.0}
LISTED = ["test_heavy.py", "test_tie_a.py", "test_tie_b.py", "test_light.py"]
UNLISTED = [f"test_new_{n}.py" for n in range(1, 8)]


def _the_proof():
    spec = importlib.util.spec_from_file_location("every_test_ran_once",
                                                  ROOT / "scripts" / "every_test_ran_once.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ids(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def _write_probe(where: Path) -> None:
    (where / "test_probe.py").write_text(PROBE, encoding="utf-8")
    for name in [*LISTED, *UNLISTED]:
        (where / name).write_text(SMALL, encoding="utf-8")
    (where / "sub").mkdir()
    (where / "sub" / "conftest.py").write_text(textwrap.dedent("""\
        import pytest


        @pytest.fixture
        def from_the_sub_conftest():
            return "sub"
    """), encoding="utf-8")
    (where / "sub" / "helper.py").write_text('WHO = "helper"\n', encoding="utf-8")
    (where / "sub" / "test_in_sub.py").write_text(IN_SUB, encoding="utf-8")
    (where / "conftest.py").write_text(
        (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8"), encoding="utf-8")
    (where / "shard_durations.json").write_text(json.dumps(TABLE), encoding="utf-8")


@pytest.fixture(scope="module")
def probe(tmp_path_factory):
    """The probe DIRECTORY, collected as pytest walks it, so every file but the directory itself
    is asked about (pytest never ignores a path it was named). Keyed from its own root, as the
    tree's files are keyed from the repository's; `own_root=False` keeps the tree's root."""
    where = tmp_path_factory.mktemp("ci-slices")
    assert ROOT not in where.resolve().parents, "the probe is inside the tree under test"
    _write_probe(where)

    def run(*args: str, own_root: bool = True, imports: Path | None = None,
            seed: int = 0) -> subprocess.CompletedProcess:
        env = {**os.environ, "PYTHONHASHSEED": str(seed)}
        env.pop("PROBE_IMPORTS", None)
        if imports is not None:
            env["PROBE_IMPORTS"] = str(imports)
        return subprocess.run(
            [sys.executable, "-m", "pytest", str(where),
             "-c", str(ROOT / "pyproject.toml"), "-q", "-p", "no:cacheprovider", "--no-header",
             *([f"--rootdir={where}"] if own_root else []), *args],
            capture_output=True, text=True, cwd=str(ROOT), timeout=300, env=env)

    run.dir = where
    run.out = tmp_path_factory.mktemp("ci-slices-out")
    return run


@pytest.fixture(scope="module")
def sliced(probe):
    """The whole collection, then each slice in a process of its own, with a hash seed of its own:
    a rule salted per process puts a file in two slices, or in none."""
    collected = probe.out / "collected.txt"
    done = probe("--collect-only", f"--record-ids={collected}",
                 imports=probe.out / "imported-all.txt")
    assert done.returncode == 0, done.stdout[-1500:]
    ran = []
    for index in range(1, SLICES + 1):
        path = probe.out / f"ran-{index}.txt"
        done = probe(f"--shard={index}/{SLICES}", f"--record-ids={path}",
                     imports=probe.out / f"imported-{index}.txt", seed=index)
        assert done.returncode == 0, done.stdout[-1500:]
        ran.append(path)
    return collected, ran


def _files_of(ids: list[str], where: Path) -> set[str]:
    return {str(where / nodeid.partition("::")[0]) for nodeid in ids}


# ── 1. the slices ───────────────────────────────────────────────────────────────────────────────

def test_the_slices_hold_every_collected_test_exactly_once(sliced):
    collected, ran = sliced
    every = [nodeid for path in ran for nodeid in _ids(path)]

    assert len(_ids(collected)) == 57, _ids(collected)
    assert Counter(every) == Counter(_ids(collected)), "a test fell between the slices, or in two"
    assert all(_ids(path) for path in ran), "a slice is empty: the rule does not spread the tests"


def test_a_shard_imports_only_the_files_it_owns(sliced, probe):
    """THE POINT OF SPLITTING BY FILE (#356): a shard that imports every file and deselects three
    quarters of the tests pays the whole suite's collection in every worker of every job."""
    collected, ran = sliced
    imported = [_ids(probe.out / f"imported-{index}.txt") for index in range(1, SLICES + 1)]

    for index, (path, names) in enumerate(zip(ran, imported, strict=True), start=1):
        assert sorted(names) == sorted(_files_of(_ids(path), probe.dir)), (
            f"slice {index} imported {sorted(names)}: a file it does not run, or one twice")
    assert Counter(name for names in imported for name in names) == Counter(
        _files_of(_ids(collected), probe.dir)), "a probe file was imported by two slices, or none"
    assert sorted(_ids(probe.out / "imported-all.txt")) == sorted(
        _files_of(_ids(collected), probe.dir)), "a run without --shard skipped a file"


def test_a_shard_never_skips_a_conftest_or_a_helper(sliced):
    """`sub/test_in_sub.py` runs on its own directory's conftest fixture and a helper beside it,
    in the one slice that owns it, and passes there (`sliced` requires every slice green). A rule
    that skipped the directory or the conftest by its own key would lose those tests, or error
    them."""
    _, ran = sliced
    owners = [path for path in ran if any(n.startswith("sub/test_in_sub.py::") for n in _ids(path))]

    assert len(owners) == 1, f"sub/test_in_sub.py ran in {len(owners)} slices"
    assert sorted(n for n in _ids(owners[0]) if n.startswith("sub/")) == [
        "sub/test_in_sub.py::test_the_fixture_resolves", "sub/test_in_sub.py::test_the_helper_imports"]


def test_the_longest_file_goes_to_the_least_loaded_shard_ties_by_path():
    """In process, on a table whose order is not its paths' order: `b.py` and `a.py` weigh the
    same, so the path decides, and `c.py` meets two shards of equal load and takes the lower."""
    from tests.conftest import _shard_owners

    table = {"c.py": 1.0, "b.py": 2.0, "a.py": 2.0, "big.py": 5.0}

    assert _shard_owners(table, 3) == {"big.py": 1, "a.py": 2, "b.py": 3, "c.py": 2}
    assert _shard_owners(dict(reversed(table.items())), 3) == _shard_owners(table, 3)


def test_every_file_of_the_tree_lands_in_one_shard_for_any_n():
    """Every test file of every test root, a file added tomorrow that the table does not list,
    and a listed file that is gone: each in exactly one shard of 1..N, with the committed table."""
    from tests.conftest import SHARD_TABLE, _shard_of, _shard_owners, _shard_table

    table = _shard_table(SHARD_TABLE)
    assert table, f"{SHARD_TABLE} is empty: every file goes by CRC32, balanced only by luck"
    patterns = ["test_*.py", "*_test.py"]
    files = sorted({p.relative_to(ROOT).as_posix() for root in _test_roots()
                    for pattern in patterns for p in root.rglob(pattern)})
    keys = [*files, "tests/test_added_tomorrow_and_never_measured.py", "tests/test_gone_since.py"]

    for count in range(1, 7):
        owners = _shard_owners({**table, "tests/test_gone_since.py": 9.9}, count)
        for key in keys:
            assert _shard_of(key, owners, count) in range(1, count + 1), (key, count)
    assert sum(key not in table for key in files) < len(files) / 10, (
        f"{SHARD_TABLE} lists too few of the tree's test files to balance them; rebuild it with "
        f"`python -m tests.shard_durations <junit.xml>`")


@pytest.mark.skipif(importlib.util.find_spec("xdist") is None, reason="pytest-xdist not installed")
def test_under_xdist_a_slice_runs_what_one_process_runs(probe, sliced):
    """Every worker of a `--shard` run computes the shard for itself: workers that disagreed
    would collect different suites, and xdist refuses that, or runs the wrong one."""
    _, ran = sliced
    path = probe.out / "ran-xdist-slice.txt"
    done = probe("-n", "2", f"--shard=2/{SLICES}", f"--record-ids={path}", seed=7)
    assert done.returncode == 0, done.stdout[-1500:]

    assert sorted(_ids(path)) == sorted(_ids(ran[1])), "xdist ran another slice than one process"


def test_a_skipped_test_counts_as_started(sliced):
    _, ran = sliced

    assert any(nodeid.endswith("::test_skipped") for path in ran for nodeid in _ids(path))


@pytest.mark.skipif(importlib.util.find_spec("xdist") is None, reason="pytest-xdist not installed")
def test_under_xdist_each_started_test_is_written_once(probe):
    """The workers run the hooks too: a recorder registered on them would write every test twice,
    and a slice rule salted per process would make the workers collect different suites. And
    under `--dist loadgroup`, as CI's integration job runs, xdist suffixes a grouped test's id
    with `@<group>`, which the collection does not carry."""
    path = probe.out / "ran-xdist.txt"
    done = probe("-n", "2", "--dist", "loadgroup", f"--record-ids={path}")
    assert done.returncode == 0, done.stdout[-1500:]
    alone = probe.out / "ran-alone.txt"
    assert probe(f"--record-ids={alone}").returncode == 0

    assert sorted(_ids(path)) == sorted(_ids(alone)), "xdist and one process ran different tests"
    assert any("test_grouped[a@b]" in nodeid for nodeid in _ids(path)), "the grouped test ran nowhere"
    assert len(_ids(path)) == len(set(_ids(path))), "a test was written twice under xdist"


def test_ids_written_inside_the_tree_are_refused(probe):
    """A test that scans the tree read the ids file while the run was writing it, and failed on a
    test id that named a maintainer: in one CI slice and not the next.

    THE DIRECTORY IS REMOVED WHATEVER THE OUTCOME. With the refusal broken, the run writes there,
    and a guard that leaves a file in the tree while failing hands the scan its next red."""
    inside = ROOT / f"test-ids-probe-{uuid.uuid4().hex[:8]}" / "ran.txt"
    try:
        done = probe(f"--record-ids={inside}", own_root=False)
        wrote = inside.parent.exists()
    finally:
        shutil.rmtree(inside.parent, ignore_errors=True)

    assert done.returncode != 0
    assert "outside the tree" in done.stdout + done.stderr
    assert not wrote, "the refused run still wrote into the tree"


def test_a_slice_that_does_not_exist_is_refused(probe):
    done = probe(f"--shard={SLICES + 1}/{SLICES}")

    assert done.returncode != 0
    assert "expected I/N" in done.stdout + done.stderr


def test_a_malformed_table_is_refused_naming_the_file_and_the_command(tmp_path):
    """A table that is not path to seconds cannot be split by; the refusal says which file and
    how to rebuild it. A missing table is not refused: a copied conftest has none."""
    (tmp_path / "conftest.py").write_text(
        (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "test_one.py").write_text("def test_one():\n    pass\n", encoding="utf-8")

    def run() -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "pytest", str(tmp_path), "-c", str(ROOT / "pyproject.toml"),
             f"--rootdir={tmp_path}", "-q", "-p", "no:cacheprovider", "--shard=1/1"],
            capture_output=True, text=True, cwd=str(ROOT), timeout=300)

    assert run().returncode == 0, "a conftest with no table beside it refused to shard"
    (tmp_path / "shard_durations.json").write_text('{"test_one.py": "slow"}', encoding="utf-8")
    done = run()

    said = done.stdout + done.stderr
    assert done.returncode != 0
    assert str(tmp_path / "shard_durations.json") in said, said
    assert "python -m tests.shard_durations <junit.xml>" in said, said


def test_the_table_is_rebuilt_from_a_junit_report(tmp_path):
    """Seconds summed per file, a class's tests credited to the file that holds the class, rounded
    to 0.1 s with a floor of 0.1 s, and a classname that names no file left out."""
    from tests.shard_durations import main

    root = tmp_path / "root"
    (root / "tests").mkdir(parents=True)
    for name in ("test_a.py", "test_b.py", "test_c.py"):
        (root / "tests" / name).write_text("", encoding="utf-8")
    report = tmp_path / "run.xml"
    report.write_text(
        '<testsuites><testsuite name="pytest">'
        '<testcase classname="tests.test_a" name="test_one" time="0.84"/>'
        '<testcase classname="tests.test_a" name="test_two[x]" time="0.42"/>'
        '<testcase classname="tests.test_b.TestThing" name="test_in_a_class" time="2.06"/>'
        '<testcase classname="tests.test_c" name="test_instant" time="0.001"/>'
        '<testcase classname="tests.test_gone" name="test_moved_away" time="9.0"/>'
        '</testsuite></testsuites>', encoding="utf-8")
    out = tmp_path / "table.json"

    assert main([str(report), "--out", str(out), "--root", str(root)]) == 0
    assert out.read_text(encoding="utf-8") == json.dumps(
        {"tests/test_a.py": 1.3, "tests/test_b.py": 2.1, "tests/test_c.py": 0.1},
        indent=1, sort_keys=True) + "\n"


# ── 2. the proof ────────────────────────────────────────────────────────────────────────────────

def test_the_proof_passes_the_slices_and_fails_what_is_missing_doubled_or_unknown(sliced, tmp_path,
                                                                                 capsys):
    collected, ran = sliced
    proof = _the_proof()
    assert proof.main([str(collected), *map(str, ran)]) == 0

    every = [nodeid for path in ran for nodeid in _ids(path)]
    for kind, lines in (("MISSING", every[1:]),
                        ("DOUBLED", [*every, every[0]]),
                        ("UNKNOWN", [*every, "tests/test_gone.py::test_not_collected"])):
        broken = tmp_path / f"{kind}.txt"
        broken.write_text("\n".join(lines) + "\n", encoding="utf-8")
        capsys.readouterr()

        assert proof.main([str(collected), str(broken)]) == 1, kind
        said = capsys.readouterr().err
        assert kind in said, said


def test_an_empty_collection_is_a_failure_not_a_pass(tmp_path):
    empty = tmp_path / "collected.txt"
    empty.write_text("", encoding="utf-8")

    assert _the_proof().main([str(empty), str(empty)]) == 1


# ── 3. CI wires it ──────────────────────────────────────────────────────────────────────────────

def _jobs() -> dict:
    return yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"]


def _runs(job: dict) -> list[str]:
    return [step.get("run", "") for step in job.get("steps", [])]


def _env_of(job: dict, command: str) -> dict:
    return next(step.get("env") or {} for step in job["steps"] if step.get("run") == command)


def test_the_job_named_test_needs_every_other_job_and_runs_the_proof():
    jobs = _jobs()

    assert set(jobs["test"]["needs"]) == set(jobs) - {"test"}, jobs["test"]["needs"]
    assert jobs["test"].get("if") == "always()", "a failed job would skip the proof"
    assert "make test-ran-once" in _runs(jobs["test"])
    assert "make test-collect" in _runs(jobs["lint"])
    assert _env_of(jobs["lint"], "make test-collect")["TEST_IDS"].endswith("/collected.txt")


def test_the_unit_slices_are_the_matrixs_and_each_job_records_what_it_ran():
    jobs = _jobs()
    unit = _env_of(jobs["unit"], "make test-unit")

    assert jobs["unit"]["strategy"]["matrix"]["shard"] == list(range(1, int(unit["TEST_SHARDS"]) + 1))
    assert jobs["unit"]["strategy"]["fail-fast"] is False
    for name, command in (("unit", "make test-unit"), ("integration", "make test-integration"),
                          ("integration", "make test-alone")):
        assert re.fullmatch(r"\$\{\{ runner\.temp \}\}/beeverforge-test-ids/ran-[\w${}. -]+\.txt",
                            _env_of(jobs[name], command)["TEST_IDS"])


def _make_n(target: str) -> str:
    return subprocess.run(["make", "-n", target], cwd=ROOT, capture_output=True, text=True,
                          timeout=60).stdout


def test_the_unit_integration_and_alone_runs_split_the_suite_without_overlap():
    """One marker list per run, read by the others: a marker added to one side only would drop
    its tests from every job, or run them twice."""
    def expression(target: str) -> str:
        return re.search(r'-m "([^"]+)"', _make_n(target)).group(1)

    integration, unit = expression("test-integration"), expression("test-unit")
    alone = re.fullmatch(r"(\w+) and not \((.+)\)", expression("test-alone"))

    assert alone and alone.group(2) == integration, expression("test-alone")
    assert unit == f"not ({integration} or {alone.group(1)})", (unit, integration)
    assert "-p no:xdist" in _make_n("test-alone"), "the alone run has neighbours on its cores"


# ── 4. a test that asserts its own CPU time runs alone ─────────────────────────────────────────

#: The calls that read a process's own CPU time. Neighbours on the same cores inflate all of them.
CPU_CLOCKS = {("os", "times"), ("time", "process_time"), ("time", "thread_time"),
              ("resource", "getrusage")}


def _reads_cpu_time(node: ast.AST) -> bool:
    return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
               and isinstance(n.func.value, ast.Name)
               and (n.func.value.id, n.func.attr) in CPU_CLOCKS for n in ast.walk(node))


def _marked_alone(decorators: list[ast.expr]) -> bool:
    return any("alone" in ast.unparse(d) for d in decorators)


def test_every_test_that_asserts_its_own_cpu_time_is_marked_alone():
    unmarked = []
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        tree = parsed(path)
        module_alone = any(isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "pytestmark" for t in n.targets)
            and "alone" in ast.unparse(n.value) for n in tree.body)
        for node in tree.body:
            if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name.startswith("test_") and _reads_cpu_time(node)
                    and not (module_alone or _marked_alone(node.decorator_list))):
                unmarked.append(f"{path.relative_to(ROOT)}::{node.name}")

    assert not unmarked, (f"{unmarked} read their own CPU time beside xdist neighbours, where it "
                          f"is inflated: mark them `alone`")


def test_the_reader_sees_a_cpu_clock_and_a_mark():
    """Verify the verifier on the one test that carries both today."""
    tree = parsed(ROOT / "tests" / "test_knowledge_derived_not_cached.py")
    [timed] = [n for n in tree.body if isinstance(n, ast.FunctionDef)
               and n.name == "test_generating_is_fast_enough_to_do_every_time"]

    assert _reads_cpu_time(timed) and _marked_alone(timed.decorator_list)


# ── 5. the real-daemon tests run one at a time ─────────────────────────────────────────────────

def _needs_the_daemon(decorators: list[ast.expr]) -> bool:
    return any("skipif" in ast.unparse(d) and "_docker_and_compose" in ast.unparse(d)
               for d in decorators)


def _in_the_docker_group(decorators: list[ast.expr]) -> bool:
    return any(ast.unparse(d) in ("pytest.mark.xdist_group('docker')",
                                  'pytest.mark.xdist_group("docker")') for d in decorators)


def _real_daemon_tests() -> dict[str, bool]:
    """Every test gated on a real Docker daemon, and whether it is in the `docker` group: by the
    module's `pytestmark`, or by its own decorators."""
    found = {}
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        tree = parsed(path)
        marks = next((n.value.elts for n in tree.body if isinstance(n, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in n.targets)
                      and isinstance(n.value, ast.List)), [])
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                every = [*marks, *node.decorator_list]
                if _needs_the_daemon(every):
                    found[f"{path.relative_to(ROOT)}::{node.name}"] = _in_the_docker_group(every)
    return found


def test_every_test_on_the_real_daemon_is_in_the_docker_group():
    outside = sorted(name for name, grouped in _real_daemon_tests().items() if not grouped)

    assert not outside, (f"{outside} drive the real Docker daemon outside the `docker` group: under "
                         f"xdist two of them can bring up the same compose project at once")


def test_the_integration_run_distributes_by_group():
    assert "--dist loadgroup" in _make_n("test-integration"), (
        "the integration run ignores xdist groups, so the real-daemon tests run side by side")


def test_the_reader_finds_the_real_daemon_tests_by_module_and_by_function():
    """Verify the verifier: the module-level gate and the one on a single function are both seen."""
    found = _real_daemon_tests()

    assert any(name.startswith("tests/test_a_preview_runs_on_a_real_daemon.py::") for name in found)
    assert ("tests/test_a_preview_reaches_nothing_of_the_host.py::"
            "test_on_a_real_engine_a_unit_network_reaches_nothing_of_the_host") in found
