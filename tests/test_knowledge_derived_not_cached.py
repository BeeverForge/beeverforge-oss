"""The map is DERIVED, so it is derived where the checkout is (ADR-0023).

The defect that forced this: #478 — the very ticket the A/B existed to measure — ran with no map.
The map was published on factory merges only, a person merged PR #508 at 22:40 on 2026-07-26, and
for TWENTY-TWO HOURS the published map described the previous commit. Every job in that window
found the checksums mismatched and degraded to no injection. The degradation was right; the trigger
was incomplete.

The reflex fix — an hourly refresh — shrinks the window from 22h to 1h and does not close it. Each
such fix makes the cache *more correct* without making it *correct*.

The question nobody had asked: generating the map costs **0.24s for 215 files** (measured). The
manifest that exists solely to tell whether the cache is still valid is **186 KB**. A cache is only
worth its machinery when computing is expensive.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from beeverforge.knowledge.bundle import read_bundle_dir
from beeverforge.knowledge.pipeline import discard_fetched_bundle, generate_bundle_for
from beeverforge.knowledge.service import load_agent_knowledge
from beeverforge.knowledge.staleness import is_stale, is_trustworthy

REPO = Path(".")


@pytest.fixture()
def generated():
    d = generate_bundle_for(REPO)
    yield d
    discard_fetched_bundle(d)


# ── fresh by construction ───────────────────────────────────────────────────────────────────────

def test_a_map_generated_from_a_tree_is_never_stale_against_it():
    """The whole architecture in one assertion: there is no window in which it can drift, because
    it is derived from the tree it describes."""
    d = generate_bundle_for(REPO)
    try:
        bundle = read_bundle_dir(d)
        assert bundle is not None, "the bundle could not even be read back"
        assert is_stale(bundle, REPO) is False
        assert is_trustworthy(bundle, REPO) is True
    finally:
        discard_fetched_bundle(d)


def test_the_generated_map_is_actually_INJECTED(generated):
    """`is_trustworthy` passing is not the same as the agent receiving text — the first version of
    this returned a directory one level off the established layout, so the injection read nothing
    and reported an empty map while everything "passed"."""
    text = load_agent_knowledge(REPO, enabled=True, bundle_dir=generated)
    assert text, "the freshly generated map was rejected at injection"
    assert len(text) > 500, f"suspiciously small injection: {len(text)} chars"


def test_it_lands_OUTSIDE_the_workspace(generated):
    """A bundle inside the agent's tree would be swept into the ticket's commit by `git add -A`,
    and every client pull request would carry a copy of the map."""
    assert REPO.resolve() not in generated.resolve().parents


def test_the_temp_directory_is_reclaimed():
    """A leaked directory per job fills the worker's disk. The discard contract computes the temp
    root from the returned path, which is why the layout must match the fetched path's exactly."""
    d = generate_bundle_for(REPO)
    root = d.parent.parent
    assert root.exists()
    discard_fetched_bundle(d)
    assert not root.exists(), "the temp root survived — this leaks once per job"


# ── cheap enough that the cache was never justified ─────────────────────────────────────────────

PACKAGES = 20
FILES_PER_PACKAGE = 20
FILES = PACKAGES * FILES_PER_PACKAGE
FUNCTIONS_PER_FILE = 11  # ~1,340 AST nodes a file; this repository averaged 1,365 (2026-11-03)
PER_FILE_ALLOWANCE = 0.008  # seconds of CPU a file may cost; see the guard's docstring


def _a_source_file(package: int, module: int) -> str:
    """One deterministic, valid Python file the size of this repository's average one: a module
    docstring, two absolute imports of sibling packages and one relative import (so the import
    resolver does real work), top-level functions with branches, and a class with methods."""
    first, second = (package + 1) % PACKAGES, (package + 7) % PACKAGES
    lines = [
        f'"""Package {package}, module {module}: a fixed-size stand-in for one source file."""',
        "",
        "from __future__ import annotations",
        "",
        "import os",
        "from pathlib import Path",
        "",
        f"from pkg{first:02d}.mod{module:02d} import f0 as _a",
        f"from pkg{second:02d}.mod{(module + 3) % (FILES_PER_PACKAGE - 1):02d} import f1 as _b",
        f"from .mod{(module + 1) % (FILES_PER_PACKAGE - 1):02d} import f2 as _c",
        "",
        f"LIMIT = {package * FILES_PER_PACKAGE + module}",
        "",
    ]
    for i in range(FUNCTIONS_PER_FILE):
        lines += [
            f"def f{i}(x: int, y: int = {i}) -> int:",
            f'    """Step {i}."""',
            "    total = 0",
            "    for k in range(x):",
            "        if k % 2 and y > LIMIT:",
            "            total += k * y - (k // 3)",
            "        elif k in (1, 2, 3):",
            "            total -= len(str(k)) + len(os.sep)",
            "        else:",
            "            total = max(total, k, y)",
            '    return total if Path(".").name != "x" else -total',
            "",
        ]
    lines += [
        f"class Thing{module}:",
        '    """A class with methods."""',
        "",
        "    def __init__(self, n: int) -> None:",
        "        self.n = n",
        "",
        "    def twice(self) -> int:",
        "        return _a(self.n, 1) + _b(self.n, 2) + _c(self.n, 3)",
        "",
    ]
    return "\n".join(lines)


def _a_repository_of_fixed_size(root: Path) -> None:
    """`PACKAGES` packages of `FILES_PER_PACKAGE` files each. Nothing here reads REPO.

    A plain directory, not a repository: the generator's two git reads (`ignored_by_git`, the HEAD
    stamp) still run, and answer "not a repository". A bare `git init` here would be one over the
    line `test_a_test_gets_its_repository_from_the_bed.py` holds, and the bed's fixture would
    change this guard's signature, which `ci_runs_every_test_exactly_once.py` anchors on."""
    for package in range(PACKAGES):
        pkg = root / f"pkg{package:02d}"
        pkg.mkdir()
        (pkg / "__init__.py").write_text(f'"""Package {package}."""\n', encoding="utf-8")
        for module in range(FILES_PER_PACKAGE - 1):
            (pkg / f"mod{module:02d}.py").write_text(
                _a_source_file(package, module), encoding="utf-8")


@pytest.mark.alone
def test_generating_is_fast_enough_to_do_every_time(capsys):
    """0.24s for 215 files, measured 2026-07-29. The assertion is generous — it guards the
    ARCHITECTURE (deriving beats caching) rather than a benchmark: if this ever failed, the answer
    would not be to raise the number, it would be to revisit ADR-0023.

    CPU TIME, NOT WALL-CLOCK (2026-08-26). Measured by the clock on the wall this took 19s with
    three suites sharing the cores and 0.3s alone — the same work, and the assertion is about
    the WORK. `os.times()` counts this process and the children it waited for (the pipeline
    shells out), which is what generation costs wherever it runs; a loaded machine is not a
    finding about the architecture.

    AND NOT BESIDE OTHER WORKERS (2026-10-12). CPU time is not immune to neighbours either: with
    CI's suite split across xdist workers on a four-core runner, this read 13.1 s, against 7.6–8.0 s
    for the same generation alone on a loaded laptop. So it is marked `alone`, and runs in a process
    of its own.

    A FIXED INPUT, NOT THIS REPOSITORY (2026-11-03, #415). Until then the guard generated the map
    of REPO, this repository, under a flat 10.0 s. Every PR added files, so every PR moved the
    guard closer to red without generation getting any dearer: CI's `integration` job read
    10.03 s on main and 11.2 s on a PR that touched nothing in the generator. Now it generates
    the map of a repository the test builds — `FILES` Python files, each about the size of this
    repository's average one — and its budget is `FILES × PER_FILE_ALLOWANCE`. What it guards is
    the PER-FILE cost, which is what ADR-0023 rests on (a map of N files costs N small, linear
    pieces of work), and adding files to this repository cannot fail it. MEASURED 2026-11-03 on
    this input, alone: 0.83 s (2.08 ms a file, median of 5) on a laptop, and 0.760 to 1.320 s
    (1.90 to 3.30 ms a file, two runs the same day) in CI's `integration` job. So the 8 ms
    allowance leaves about 3.9 times of margin on the laptop and 2.4 to 4.2 times on CI, against
    the 11 to 14 times dearer per file that `tools/mutations/415_*` makes it, and about 1.0 times
    the old guard had left by then. (The 2.5 times CI was slower on the whole repository does not carry over: git and the
    size of the tree differ between machines, and this input has neither.) A heavily loaded
    machine can still eat the margin, as it could the old one. If generation gets several times
    dearer per file, this goes red — and the answer is still not to raise the allowance."""
    def cpu() -> float:
        t = os.times()
        return t.user + t.system + t.children_user + t.children_system

    budget = FILES * PER_FILE_ALLOWANCE
    with tempfile.TemporaryDirectory(prefix="beeverforge-fixed-input-") as tmp:
        root = Path(tmp)
        _a_repository_of_fixed_size(root)

        started = cpu()
        d = generate_bundle_for(root)
        elapsed = cpu() - started

        assert d is not None, "the fixed input produced no map — nothing was measured"
        try:
            bundle = read_bundle_dir(d)
        finally:
            discard_fetched_bundle(d)
    assert bundle is not None, "the bundle could not be read back — nothing was measured"
    assert len(bundle.module_map.modules) >= PACKAGES, (
        f"{len(bundle.module_map.modules)} modules from {PACKAGES} packages — the generation "
        f"did not read the input it was timed on"
    )
    per_file_ms = elapsed / FILES * 1000
    with capsys.disabled():  # in CI's log even when it passes: the margin is read there (#415)
        print(f"\nknowledge generation: {elapsed:.3f}s of CPU for {FILES} files "
              f"({per_file_ms:.2f} ms a file), budget {budget:.1f}s")
    assert elapsed < budget, (
        f"generation cost {elapsed:.2f}s of CPU for {FILES} files ({per_file_ms:.2f} ms a file, "
        f"budget {budget:.1f}s) — if this is real, the cache ADR-0023 removed may have been "
        f"justified after all"
    )


# ── the A/B stays an experiment ─────────────────────────────────────────────────────────────────

def test_the_control_arm_GENERATES_and_discards():
    """Decision (b), 2026-07-29. Skipping generation for the control is cheaper and makes the arms
    differ in TWO variables — the injection and the CPU — so any measured difference would have two
    explanations and the convenient one would be chosen. The A/B exists to support a commercial
    claim; one that cannot support it is worse than none."""
    import ast

    src = Path("beeverforge/orchestrator/machine.py").read_text()
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_knowledge_bundle")
    body = ast.unparse(fn)
    assert "generate_bundle_for" in body
    assert "discard_fetched_bundle" in body, "the control arm no longer discards — it leaks"
    # generation must NOT sit behind the arm check, or the control stops paying the same CPU
    assert body.index("treated = self._experiment_arm()") < body.index("generate_bundle_for"), (
        "the arm check moved above generation — the control stopped generating, and the two arms "
        "now differ in CPU as well as in injection"
    )


def test_the_control_arm_receives_NO_bundle():
    """Generated, measured, thrown away: the control must run exactly as a project with the map
    switched off does."""
    import ast

    src = Path("beeverforge/orchestrator/machine.py").read_text()
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_knowledge_bundle")
    body = ast.unparse(fn)
    assert "self._bundle_dir = None" in body, "the control arm would be handed the map"
