"""A hook planted in the shared repo cache never runs on the host (#182, first half).

WHY. The worktree box adds its trees from the shared repo cache, and the repository cache syncs
that cache in place. Both run git on the host. The cache's hooks directory and its config survive
a job's `cleanup`, and a pass can write either: a `pre-push` hook, or a `core.hooksPath` naming a
directory of hooks. Before this fix `publish_branch` pushed without `--no-verify`, and the hook
ran on the host and was handed the authenticated remote URL.

THE RULE THIS FILE HOLDS:
  1. `publish_branch` pushes with `-c core.hooksPath=/dev/null` and `--no-verify`, and the push
     still lands;
  2. every git call the worktree box runs on the host, and every git call of the repository
     cache, carries `-c core.hooksPath=/dev/null` before its subcommand;
  3. a host-side call added to the box later goes through the box's one runner, or names the
     override itself (the source guard).

No assertion message prints an argv's remote or a URL: only hook names and subcommands.
"""

from __future__ import annotations

import ast
import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from beeverforge import gitpin
from beeverforge.adapters import gitworktrees
from beeverforge.adapters.sandbox import worktree
from beeverforge.adapters.sandbox.worktree import WorktreeSandbox
from beeverforge.runtime import repo_cache
from beeverforge.runtime.repo_cache import RepoCache
from tests import the_git_bed
from tests.the_git_bed import a_card_repository
from tests.the_tree_read_once import parsed

ROOT = Path(__file__).resolve().parents[1]
BOX_SOURCES = ("beeverforge/adapters/sandbox/worktree.py", "beeverforge/adapters/gitworktrees.py")
OVERRIDE = ["-c", "core.hooksPath=/dev/null"]
HOOKS = ("pre-push", "reference-transaction", "post-checkout", "post-rewrite", "post-merge",
         "post-index-change")
PLACEMENTS = ("hooks_dir", "hooks_path")
REAL_RUN = subprocess.run


def _git(*args: str, cwd: Path) -> str:
    """Test setup, never through the code under test, and with hooks off so setup fires none."""
    return REAL_RUN(["git", *OVERRIDE, *args], cwd=cwd, capture_output=True, text=True,
                    check=True, timeout=60).stdout.strip()


def _plant(repo: Path, placement: str, markers: Path) -> None:
    """Write a hook for each of `HOOKS` that touches `markers/<hook>`, where git of `repo` finds
    it: its own hooks directory, or a directory its config names as `core.hooksPath`."""
    if placement == "hooks_dir":
        # resolved here, not with `--path-format=absolute`: that flag is Git 2.31, and 2.28 is
        # the floor (CONTRIBUTING.md). Git 2.30 echoes it back as a path (#384's second review).
        hooks = repo / _git("rev-parse", "--git-common-dir", cwd=repo) / "hooks"
    else:
        hooks = repo.parent / f"planted-hooks-{repo.name}"
        _git("config", "core.hooksPath", str(hooks), cwd=repo)
    hooks.mkdir(parents=True, exist_ok=True)
    markers.mkdir(parents=True, exist_ok=True)
    for name in HOOKS:
        script = hooks / name
        script.write_text(f"#!/bin/sh\ntouch '{markers / name}'\nexit 0\n", encoding="utf-8")
        script.chmod(0o755)


def _fired(markers: Path) -> list[str]:
    return sorted(p.name for p in markers.iterdir()) if markers.is_dir() else []


#: The worker's repository bed (`tests/the_git_bed.py`), this module's fixture as well.
git_bed = the_git_bed.git_bed


@pytest.fixture
def cache(tmp_path, git_bed) -> Path:
    """A bare `origin` holding `main`, and a clone of it: the shared cache."""
    seed = a_card_repository(git_bed, tmp_path / "seed")
    _git("clone", "-q", "--bare", str(seed), str(tmp_path / "origin.git"), cwd=tmp_path)
    _git("clone", "-q", str(tmp_path / "origin.git"), str(tmp_path / "cache"), cwd=tmp_path)
    return tmp_path / "cache"


def _advance(origin: Path, tmp_path: Path, name: str) -> str:
    """Push a new commit on `main` to `origin` from a clone of its own; the new tip."""
    other = tmp_path / f"other-{name}"
    _git("clone", "-q", str(origin), str(other), cwd=tmp_path)
    (other / f"{name}.txt").write_text(f"{name}\n")
    _git("add", "-A", cwd=other)
    _git("commit", "-qm", name, cwd=other)
    _git("push", "-q", "origin", "main", cwd=other)
    return _git("rev-parse", "HEAD", cwd=other)


def _commit_in(ws: Path, name: str) -> str:
    (ws / name).write_text("y = 2\n")
    _git("add", "-A", cwd=ws)
    _git("commit", "-qm", f"add {name}", "--no-verify", cwd=ws)
    return _git("rev-parse", "HEAD", cwd=ws)


class _Recorder:
    """Records each argv handed to `subprocess.run`, then runs it for real."""

    def __init__(self) -> None:
        self.argvs: list[list[str]] = []

    def __call__(self, args, *a, **kw):
        if isinstance(args, list | tuple):
            self.argvs.append([str(w) for w in args])
        return REAL_RUN(args, *a, **kw)

    def gits(self) -> list[list[str]]:
        return [argv for argv in self.argvs if argv[:1] == ["git"]]


@pytest.fixture
def recorder(monkeypatch) -> Iterator[_Recorder]:
    rec = _Recorder()
    monkeypatch.setattr(subprocess, "run", rec)
    yield rec


def _hookless(argv: list[str]) -> bool:
    """Whether `argv` carries `-c core.hooksPath=/dev/null` before its subcommand."""
    sub = gitpin.subcommand(argv)
    head = argv[:argv.index(sub)] if sub in argv else argv
    return any(head[i:i + 2] == OVERRIDE for i in range(len(head) - 1))


def _offenders(argvs: list[list[str]]) -> list[str]:
    """The subcommand of each argv without the override: never the argv, which may hold a URL."""
    return [str(gitpin.subcommand(argv)) for argv in argvs if not _hookless(argv)]


def test_the_override_counts_only_before_the_subcommand():
    """After the subcommand `-c` is the subcommand's own option, and git keeps the hooks on."""
    assert _hookless(["git", *gitpin.PIN, *OVERRIDE, "-C", "/x", "push", "--", "origin", "b"])
    assert not _hookless(["git", "-C", "/x", "push", *OVERRIDE, "--", "origin", "b"])
    assert not _hookless(["git", "-c", "core.hooksPath=/somewhere", "status"])



def test_the_recording_guard_names_every_call_without_the_override():
    """Every subcommand is checked, not only the push, and only its name is reported."""
    argvs = [["git", "-C", "/x", "status"], ["git", *OVERRIDE, "push", "--", "origin", "b"],
             ["git", "fetch", "--", "origin", "main"]]
    assert _offenders(argvs) == ["status", "fetch"]


# ── the control: the planted hooks are live ──────────────────────────────────────────────────


@pytest.mark.parametrize("placement", PLACEMENTS)
def test_the_planted_hook_is_live(tmp_path, cache, placement):
    """Without this the proofs below prove nothing: a plain push from a worktree of the cache
    runs the planted `pre-push`, in both placements."""
    wt = tmp_path / "plain"
    _git("worktree", "add", "-q", "-b", "plain", str(wt), cwd=cache)
    _commit_in(wt, "plain.py")
    markers = tmp_path / "markers"
    _plant(cache, placement, markers)
    REAL_RUN(["git", "push", "-q", "origin", "plain"], cwd=wt, capture_output=True, check=True,
             timeout=60)
    assert "pre-push" in _fired(markers), "the planted pre-push hook did not run in the control"


# ── 1. the push ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("placement", PLACEMENTS)
def test_publish_branch_runs_no_hook_and_the_push_lands(tmp_path, cache, placement):
    box = WorktreeSandbox(root=tmp_path / "jobs")
    ws = box.prepare(repo_path=cache, base_branch="main", branch="job-1")
    head = _commit_in(ws.path, "job.py")
    markers = tmp_path / "markers"
    _plant(cache, placement, markers)

    box.publish_branch(workspace=ws)

    assert _fired(markers) == [], f"hooks ran on the host: {_fired(markers)}"
    assert _git("rev-parse", "job-1", cwd=tmp_path / "origin.git") == head, \
        "the push did not land on origin"


def test_the_push_argv_carries_no_verify_and_the_override(tmp_path, cache, recorder):
    """The override alone already silences pre-push, so this is the row that keeps
    `--no-verify` in the push."""
    box = WorktreeSandbox(root=tmp_path / "jobs")
    ws = box.prepare(repo_path=cache, base_branch="main", branch="job-1")
    _commit_in(ws.path, "job.py")
    recorder.argvs.clear()
    box.publish_branch(workspace=ws)
    pushes = [argv for argv in recorder.gits() if gitpin.subcommand(argv) == "push"]
    assert len(pushes) == 1, f"expected one push, saw {len(pushes)}"
    push = pushes[0]
    # each answer is taken first, so a failure prints no part of the argv and none of its remote
    hookless = _hookless(push)
    no_verify = "--no-verify" in push[push.index("push"):]
    assert hookless, "the push runs without core.hooksPath=/dev/null"
    assert no_verify, "the push runs without --no-verify"


def test_the_runner_puts_the_override_first(recorder):
    worktree._run(["git", "-C", "/nonexistent-182", "status"])
    worktree._run(["true"])
    assert recorder.argvs == [
        ["git", "-c", "core.hooksPath=/dev/null", "-C", "/nonexistent-182", "status"],
        ["true"],
    ]


# ── 2. every git call of the box, recorded ───────────────────────────────────────────────────


def test_every_git_call_of_the_box_runs_without_hooks(tmp_path, cache, recorder):
    """Drives each host-side door of the box against a real cache with hooks planted, recording
    every git argv: each carries the override, and no hook runs."""
    markers = tmp_path / "markers"
    _plant(cache, "hooks_path", markers)
    _plant(cache, "hooks_dir", markers)
    origin = tmp_path / "origin.git"
    box = WorktreeSandbox(root=tmp_path / "jobs")
    seen: dict[str, int] = {}

    def door(name: str, call):
        before = len(recorder.gits())
        result = call()
        seen[name] = len(recorder.gits()) - before
        return result

    ws = door("prepare", lambda: box.prepare(repo_path=cache, base_branch="main",
                                             branch="job-1"))
    _commit_in(ws.path, "job.py")
    door("diff_paths", lambda: box.diff_paths(workspace=ws))
    door("publish_branch", lambda: box.publish_branch(workspace=ws))
    _advance(origin, tmp_path, "newer")
    outcome = door("rebase_onto_base", lambda: box.rebase_onto_base(workspace=ws, base="main"))
    door("cleanup", lambda: box.cleanup(workspace=ws))
    tip = door("prepare_tip", lambda: box.prepare_tip(repo_path=cache, base_branch="main",
                                                      branch="job-1"))
    door("cleanup of the tip", lambda: box.cleanup(workspace=tip))

    assert outcome == "rebased", "the rebase door was not exercised"
    assert all(seen.values()), f"doors that ran no git: {[k for k, v in seen.items() if not v]}"
    assert _offenders(recorder.gits()) == [], "git calls of the box run with hooks on"
    assert _fired(markers) == [], f"hooks ran on the host: {_fired(markers)}"


# ── 3. the source guard ──────────────────────────────────────────────────────────────────────

SPAWNERS = {"run", "Popen", "call", "check_call", "check_output"}


def _carries_override(call: ast.Call) -> bool:
    """Whether the call's first argument is a list literal `["git", *HOOKLESS, ...]`."""
    if not call.args or not isinstance(call.args[0], ast.List):
        return False
    elts = call.args[0].elts
    if len(elts) < 2 or not (isinstance(elts[0], ast.Constant) and elts[0].value == "git"):
        return False
    star = elts[1]
    if not isinstance(star, ast.Starred):
        return False
    v = star.value
    return (isinstance(v, ast.Name) and v.id == "HOOKLESS") or (
        isinstance(v, ast.Attribute) and v.attr == "HOOKLESS"
        and isinstance(v.value, ast.Name) and v.value.id == "gitpin")


def _bypasses(tree: ast.AST) -> list[str]:
    """`<function>:<line>` for every process spawn in `tree` that is neither inside the runner
    `_run`, nor the workload's shell `Popen` inside `run`, nor a git argv naming the override;
    and for every `from subprocess import` or `os.system`/`os.popen`, which this rule cannot read."""
    found: list[str] = []

    def visit(node: ast.AST, fn: str) -> None:
        for child in ast.iter_child_nodes(node):
            name = child.name if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef) else fn
            if isinstance(child, ast.ImportFrom) and child.module == "subprocess":
                found.append(f"{fn}:{child.lineno}")
            elif isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                f = child.func
                owner = f.value.id if isinstance(f.value, ast.Name) else None
                if owner == "os" and f.attr in ("system", "popen"):
                    found.append(f"{fn}:{child.lineno}")
                elif owner == "subprocess" and f.attr in SPAWNERS:
                    shell = any(k.arg == "shell" and isinstance(k.value, ast.Constant)
                                and k.value.value is True for k in child.keywords)
                    allowed = (fn == "_run" or (fn == "run" and f.attr == "Popen" and shell)
                               or _carries_override(child))
                    if not allowed:
                        found.append(f"{fn}:{child.lineno}")
            visit(child, name)

    visit(tree, "<module>")
    return found


def test_the_hook_guard_sees_each_shape():
    """THE GUARD CALLS ITS OWN RULE on the shapes a host-side git call is written in."""
    caught = ('def f():\n    subprocess.run(["git", "-C", d, "push", "--", u])\n'
              'def g():\n    subprocess.check_output(["git", "rev-parse", "HEAD"])\n'
              'def h():\n    subprocess.Popen(["git", "fetch"])\n'
              'def run():\n    subprocess.Popen(["git", "push"])\n'
              'def k():\n    subprocess.run(["git", "-c", "x=y", "status"])\n'
              'def m():\n    subprocess.run(argv)\n'
              'def n():\n    os.system("git push")\n'
              'from subprocess import run\n')
    passed = ('def _run(cmd):\n    subprocess.run(cmd)\n'
              'def run():\n    subprocess.Popen(c, shell=True)\n'
              'def f():\n    subprocess.run(["git", *gitpin.HOOKLESS, "-C", d, "status"])\n'
              'def g():\n    subprocess.run(["git", *HOOKLESS, "status"])\n')
    assert _bypasses(ast.parse(caught)) == ["f:2", "g:4", "h:6", "run:8", "k:10", "m:12",
                                            "n:14", "<module>:15"]
    assert _bypasses(ast.parse(passed)) == []


@pytest.mark.parametrize("source", BOX_SOURCES)
def test_no_host_git_call_in_the_box_bypasses_the_runner(source):
    assert _bypasses(parsed(ROOT / source)) == [], \
        f"{source} spawns a process outside `_run` without the hooks override"


#: Host code outside the box that runs git with a literal argv in a `RepoCache` path (#384's
#: review: the knowledge refresh's `checkout -- knowledge` fired a planted `post-checkout`; its
#: second review: the bundle build's `status` fired a planted `post-index-change`; and the
#: concept renewal reads the cache's history through `history._git`; and the system layer reads
#: each source checkout's commit through `refresh._head`).
CACHE_CALLERS = ("beeverforge/runtime/temporal/activities.py",
                 "beeverforge/knowledge/generator.py", "beeverforge/onboarding/history.py",
                 "beeverforge/knowledge/system/refresh.py")


def _literal_git_calls(tree: ast.AST) -> list[ast.Call]:
    """Every `subprocess.run([...])` whose argv is a literal list starting with "git"."""
    return [n for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == "run" and isinstance(n.func.value, ast.Name)
            and n.func.value.id == "subprocess" and n.args and isinstance(n.args[0], ast.List)
            and n.args[0].elts and isinstance(n.args[0].elts[0], ast.Constant)
            and n.args[0].elts[0].value == "git"]


@pytest.mark.parametrize("source", CACHE_CALLERS)
def test_every_literal_git_call_in_a_cache_caller_turns_hooks_off(source):
    calls = _literal_git_calls(parsed(ROOT / source))
    assert calls, f"{source} has no literal git call left to hold: drop it from CACHE_CALLERS"
    missing = [c.lineno for c in calls if not _carries_override(c)]
    assert missing == [], f"{source}: git calls without the hooks override at lines {missing}"


# ── the knowledge build, run by the refresh in the shared cache ─────────────────────────────


def _stale_index(repo: Path) -> None:
    """Make the next `git status` in `repo` refresh the index and write it: the tracked files'
    stat data no longer matches what the index recorded."""
    for path in _git("ls-files", cwd=repo).splitlines():
        (repo / path).touch()
        os.utime(repo / path, (1_000_000_000, 1_000_000_000))


@pytest.mark.parametrize("placement", PLACEMENTS)
def test_the_planted_index_hook_is_live_at_a_plain_status(tmp_path, cache, placement):
    """The control: a plain `git status` over a stale index runs a planted `post-index-change`."""
    markers = tmp_path / "markers"
    _plant(cache, placement, markers)
    _stale_index(cache)
    REAL_RUN(["git", "status", "--porcelain"], cwd=cache, capture_output=True, check=True,
             timeout=60)
    assert "post-index-change" in _fired(markers), "the planted hook did not run in the control"


@pytest.mark.parametrize("placement", PLACEMENTS)
def test_the_knowledge_build_runs_no_hook_of_the_cache(tmp_path, cache, placement, recorder):
    """`build_bundle` is what the knowledge refresh runs in the cache; its `status` (through
    `ignored_by_git`) still reads what git ignores, and runs no planted hook."""
    from beeverforge.knowledge.bundle import build_bundle

    (cache / ".gitignore").write_text("secret.env\n")
    (cache / "secret.env").write_text("x\n")
    markers = tmp_path / "markers"
    _plant(cache, placement, markers)
    _stale_index(cache)

    build_bundle(cache, commit="", generated_at="")

    from beeverforge.knowledge.generator import ignored_by_git

    assert "secret.env" in ignored_by_git(cache), "the build no longer reads what git ignores"
    assert _fired(markers) == [], f"hooks ran on the host: {_fired(markers)}"
    assert recorder.gits(), "the build ran no git"
    assert _offenders(recorder.gits()) == [], "git calls of the knowledge build run with hooks on"


# ── the repository cache, the same shared cache ─────────────────────────────────────────────


@pytest.mark.parametrize("placement", PLACEMENTS)
def test_a_hook_planted_in_the_cache_never_runs_at_its_sync(tmp_path, cache, placement,
                                                           recorder):
    origin = tmp_path / "origin.git"
    rc = RepoCache(root=tmp_path / "repo-cache")
    assert rc.sync("p", str(origin), "main") is not None, "the first sync failed"
    master = tmp_path / "repo-cache" / repo_cache._MASTERS_DIRNAME / "p"
    markers = tmp_path / "markers"
    _plant(master, placement, markers)
    tip = _advance(origin, tmp_path, "newer")
    recorder.argvs.clear()

    served = rc.sync("p", str(origin), "main")

    assert served is not None, "the second sync failed"
    assert _git("rev-parse", "HEAD", cwd=master) == tip, "the second sync did not reach the tip"
    assert recorder.gits(), "the second sync ran no git"
    assert _offenders(recorder.gits()) == [], "git calls of the cache run with hooks on"
    assert _fired(markers) == [], f"hooks ran on the host: {_fired(markers)}"


def test_the_cache_runners_put_the_override_first(recorder):
    repo_cache._git(["-C", "/nonexistent-182", "status"])
    repo_cache._git_out(["-C", "/nonexistent-182", "status"], None, {})
    assert [argv[:4] for argv in recorder.argvs] == [["git", *OVERRIDE, "-C"]] * 2


def test_the_mark_runs_with_hooks_off(tmp_path, cache, recorder):
    wt = tmp_path / "wt"
    _git("worktree", "add", "-q", "--detach", str(wt), cwd=cache)
    gitworktrees.mark_as_job(wt)
    assert _offenders(recorder.gits()) == [], "the job mark's rev-parse runs with hooks on"
