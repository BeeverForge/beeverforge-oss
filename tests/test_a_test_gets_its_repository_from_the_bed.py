"""A test gets its git repository from the bed (`tests/the_git_bed.py`), and the count of the
repositories tests build by hand does not grow back (#337).

WHY THE BED. Measured in the 2026-11-01 unit run (main b5f2742, 8 cores): 2,058 s of the 4,246 s
summed call time was in files that run git, most of it building the same repository again for
every test — an `init -b main`, a commit, sometimes a clone and a second remote, 40 to 500 ms of
fork, exec and disk before the first assertion. The bed builds each shape once per run, shared
by every xdist worker, and hands every test a fresh copy (`shutil.copytree` of a small tree is a
few milliseconds).

What is pinned:

  1. a shape is built once — once for every process sharing the bed's root, as the xdist workers
     of one run do — and handed out as a copy: never the template, and a change in one copy
     reaches neither the next copy nor the template;
  2. a template a test changed in place is refused by name, at the next copy and at the end of
     the session — an order-dependent failure caught as what it is;
  3. a copy names its own path wherever the template named its own (a remote URL, a text file),
     and a shape that leaves its path inside a binary file is refused at build;
  4. the count of bare `git init` calls under `tests/` (the pattern is `_git_inits`' docstring)
     is held at or below `BASELINE`, with a refusal that names how to get a repository instead.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests import the_git_bed
from tests.the_git_bed import Bed, BedRefused

TESTS = Path(__file__).resolve().parent

#: The bare `git init` calls left under `tests/` once the four heaviest git-building files moved
#: onto the bed (#337: 130 on b5f2742, 126 after, counted by `count_git_inits`). Lower it when a
#: file moves; never raise it.
BASELINE = 126


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True).stdout.strip()


def _one_commit(where: Path, _env) -> None:
    where.mkdir()
    (where / "README.md").write_text("# shape\n")
    subprocess.run(["git", "-C", str(where), "init", "-q", "-b", "main"], check=True)
    _git(where, "add", "-A")
    _git(where, "commit", "-qm", "first")


# ── 1. built once, handed out as a copy ─────────────────────────────────────────────────────────

def test_a_shape_is_built_once_and_every_test_gets_a_copy(tmp_path):
    bed = Bed(tmp_path / "bed")
    built: list[Path] = []

    def build(where, env):
        built.append(where)
        _one_commit(where, env)

    one = bed.copy("one-commit", tmp_path / "one", build)
    two = bed.copy("one-commit", tmp_path / "two", build)

    assert len(built) == 1, "the shape was built again for the second copy"
    assert (one, two) == (tmp_path / "one", tmp_path / "two")
    assert built[0] not in (one, two)
    assert _git(one, "rev-parse", "HEAD") == _git(built[0], "rev-parse", "HEAD")
    assert _git(two, "rev-parse", "HEAD") == _git(built[0], "rev-parse", "HEAD")


def test_a_shape_another_worker_built_is_read_not_built_again(tmp_path):
    """Two beds on one root, as two xdist workers of one run hold: the second reads the template
    the first built and builds nothing."""
    built: list[Path] = []

    def build(where, env):
        built.append(where)
        _one_commit(where, env)

    one = Bed(tmp_path / "bed").copy("one-commit", tmp_path / "one", build)
    two = Bed(tmp_path / "bed").copy("one-commit", tmp_path / "two", build)

    assert len(built) == 1, "the second worker built the shape again"
    assert _git(two, "rev-parse", "HEAD") == _git(one, "rev-parse", "HEAD")


def test_a_manifest_that_does_not_parse_is_built_again_not_refused_forever(tmp_path):
    """A worker killed in the middle of a manifest write left it truncated: the next ask for the
    shape builds it again, instead of every later request failing on the JSON."""
    built: list[Path] = []

    def build(where, env):
        built.append(where)
        _one_commit(where, env)

    one = Bed(tmp_path / "bed").copy("one-commit", tmp_path / "one", build)
    [manifest] = (tmp_path / "bed").glob("*/manifest.json")
    manifest.write_text(manifest.read_text(encoding="utf-8")[:20], encoding="utf-8")

    two = Bed(tmp_path / "bed").copy("one-commit", tmp_path / "two", build)

    assert len(built) == 2, "the shape behind a truncated manifest was not built again"
    assert _git(two, "rev-parse", "HEAD") == _git(one, "rev-parse", "HEAD")
    assert Bed(tmp_path / "bed").copy("one-commit", tmp_path / "three", build).is_dir()
    assert len(built) == 2, "the rebuilt manifest was not read by the next worker"


def test_a_manifest_is_written_whole_or_not_at_all(tmp_path, monkeypatch):
    """A worker killed before its manifest is in place leaves none, never a part of one: the
    manifest is written beside itself and moved into place in one step."""
    def killed(*_args, **_kw):
        raise KeyboardInterrupt("the worker was killed")

    monkeypatch.setattr(os, "replace", killed)
    with pytest.raises(KeyboardInterrupt):
        Bed(tmp_path / "bed").copy("one-commit", tmp_path / "one", _one_commit)

    assert not list((tmp_path / "bed").glob("*/manifest.json")), "a part-written manifest is left"


def test_a_copy_is_the_shape_and_not_the_template(tmp_path):
    """A commit in one copy reaches neither the next copy nor the template."""
    bed = Bed(tmp_path / "bed")
    built: list[Path] = []

    def build(where, env):
        built.append(where)
        _one_commit(where, env)

    one = bed.copy("one-commit", tmp_path / "one", build)
    tip = _git(one, "rev-parse", "HEAD")
    (one / "more.txt").write_text("more\n")
    _git(one, "add", "-A")
    _git(one, "commit", "-qm", "more")
    two = bed.copy("one-commit", tmp_path / "two", build)

    assert _git(two, "rev-parse", "HEAD") == tip
    assert _git(built[0], "rev-parse", "HEAD") == tip
    assert not (two / "more.txt").exists()
    bed.verify_all()


def test_the_build_s_environment_is_undone(tmp_path, monkeypatch):
    """A shape that needs its own `HOME` or identity sets it through the `env` it is handed; the
    test that asked for the copy finds its own environment as it was — and so it does when the
    platform's code the build ran wrote `os.environ` itself, as `cli._load_environment` does."""
    monkeypatch.setenv("BEEVERFORGE_GIT_BED_PROBE", "the test's")
    monkeypatch.delenv("BEEVERFORGE_GIT_BED_WRITTEN", raising=False)
    bed = Bed(tmp_path / "bed")

    def build(where, env):
        env.setenv("BEEVERFORGE_GIT_BED_PROBE", "the build's")
        os.environ["BEEVERFORGE_GIT_BED_WRITTEN"] = "by the code the build ran"
        where.mkdir()
        (where / "seen.txt").write_text(os.environ["BEEVERFORGE_GIT_BED_PROBE"])

    copy = bed.copy("probe", tmp_path / "copy", build)

    assert (copy / "seen.txt").read_text() == "the build's"
    assert os.environ["BEEVERFORGE_GIT_BED_PROBE"] == "the test's"
    assert "BEEVERFORGE_GIT_BED_WRITTEN" not in os.environ


# ── 2. a template a test changed is refused by name ─────────────────────────────────────────────

@pytest.mark.parametrize("change", ["a-file-written-into-it", "a-commit-made-in-it"])
def test_a_template_a_test_changed_is_refused_by_name(tmp_path, change):
    bed = Bed(tmp_path / "bed")
    built: list[Path] = []

    def build(where, env):
        built.append(where)
        _one_commit(where, env)

    bed.copy("one-commit", tmp_path / "one", build)
    template = built[0]
    if change == "a-file-written-into-it":
        (template / "stray.txt").write_text("written into the template\n")
    else:
        (template / "README.md").write_text("# changed\n")
        _git(template, "commit", "-qam", "in the template")

    with pytest.raises(BedRefused) as at_copy:
        bed.copy("one-commit", tmp_path / "two", build)
    with pytest.raises(BedRefused) as at_end:
        bed.verify_all()
    with pytest.raises(BedRefused) as in_another_worker:
        Bed(tmp_path / "bed").copy("one-commit", tmp_path / "three", build)
    for said in (str(at_copy.value), str(at_end.value), str(in_another_worker.value)):
        assert "'one-commit'" in said, said
        assert "changed in place" in said, said
        assert "change the copy" in said, said
    assert not (tmp_path / "two").exists(), "a changed template was handed out"
    assert not (tmp_path / "three").exists(), "a changed template was handed out"


def _session(tmp_path: Path, *, worker: bool):
    """The session fixture's own generator, on a stand-in for pytest's `request` and factory."""
    config = SimpleNamespace(stash={}, **({"workerinput": {"workerid": "gw0"}} if worker else {}))
    base = tmp_path / ("popen-gw0" if worker else "base")
    factory = SimpleNamespace(getbasetemp=lambda: base)
    return the_git_bed.git_bed.__wrapped__(SimpleNamespace(config=config), factory, None)


def test_the_session_s_bed_verifies_its_templates_when_the_session_ends(tmp_path):
    session = _session(tmp_path, worker=False)
    bed = next(session)
    built: list[Path] = []

    def build(where, env):
        built.append(where)
        _one_commit(where, env)

    bed.copy("one-commit", tmp_path / "one", build)
    (built[0] / "stray.txt").write_text("written into the template\n")
    with pytest.raises(BedRefused, match="'one-commit' was changed in place"):
        next(session)


def test_every_worker_of_a_run_shares_one_root(tmp_path):
    """A worker's base directory is `<run>/popen-gwN`; the bed is `<run>/git-bed` for all of them,
    and a run without xdist keeps it under its own base directory."""
    assert next(_session(tmp_path, worker=True)).root == tmp_path / "git-bed"
    assert next(_session(tmp_path, worker=False)).root == tmp_path / "base" / "git-bed"


# ── 3. a copy names its own path ────────────────────────────────────────────────────────────────

def test_a_copy_names_its_own_path_where_the_template_named_its_own(tmp_path):
    """A clone's `remote.origin.url` and a text file holding the shape's root read the copy's
    path in the copy: a test that pushed to the template's remote would change the template."""
    bed = Bed(tmp_path / "bed")

    def build(where, env):
        where.mkdir()
        _one_commit(where / "origin", env)
        subprocess.run(["git", "clone", "-q", str(where / "origin"), str(where / "clone")],
                       check=True)
        (where / "where.txt").write_text(f"root={where}\n")

    copy = bed.copy("a-clone", tmp_path / "copy", build)

    assert _git(copy / "clone", "config", "--get", "remote.origin.url") == str(copy / "origin")
    assert (copy / "where.txt").read_text() == f"root={copy}\n"
    _git(copy / "clone", "fetch", "-q")
    bed.verify_all()


def test_a_shape_that_leaves_its_path_in_a_binary_file_is_refused_at_build(tmp_path):
    bed = Bed(tmp_path / "bed")

    def build(where, env):
        where.mkdir()
        (where / "blob.bin").write_bytes(b"\xff\xfe" + str(where).encode() + b"\x00")

    with pytest.raises(BedRefused) as refused:
        bed.copy("binary", tmp_path / "copy", build)
    said = str(refused.value)
    assert "'binary'" in said and "blob.bin" in said, said
    assert "build that state from the copy" in said, said
    assert not (tmp_path / "copy").exists()
    with pytest.raises(BedRefused):
        Bed(tmp_path / "bed").copy("binary", tmp_path / "copy", build)


# ── 4. the count of bare `git init` calls ───────────────────────────────────────────────────────

FORMS = {
    "a-list-handed-to-a-process": 'subprocess.run(["git", "init", "-q", str(d)])\n',
    "a-list-with-the-repository-first": 'subprocess.run(["git", "-C", str(d), "init"])\n',
    "a-git-helper-given-init": '_git(d, "init", "-q", "-b", "main")\n',
    "a-git-helper-on-a-module": 'om.git(repo, "init")\n',
    "a-git-helper-given-a-list": '_git(["init", "-q", "-b", "main"], repo)\n',
    "a-git-helper-after-an-option": '_git("-C", str(d), "init")\n',
    "a-command-line-in-a-string": 'run("git init -q -b main", shell=True)\n',
}


@pytest.mark.parametrize("form", FORMS)
def test_the_counter_sees_each_form_a_test_writes_git_init_in(tmp_path, form):
    planted = tmp_path / "test_planted.py"
    planted.write_text(f"def test_it(d, repo, om, run, subprocess, _git):\n    {FORMS[form]}")
    assert the_git_bed.count_git_inits(tmp_path) == 1, form


NOT_INITS = {
    "the-cli-s-own-init": 'om.cli("project", "init", "myapp", str(repo))\n',
    "init-in-a-call-that-is-not-git": 'helper(d, "init")\n',
    "a-commit-whose-message-is-init": '_git(repo, "commit", "-m", "init")\n',
    "a-list-whose-subcommand-is-not-init": 'subprocess.run(["git", "commit", "-m", "init"])\n',
    "a-list-not-starting-with-git": 'subprocess.run(["make", "init"])\n',
    "git-init-in-a-docstring": '"""Runs git init over the bed."""\n',
    "git-init-in-a-comment": '# git init -q -b main\n',
    "a-word-containing-it": 'run("git initialise", shell=True)\n',
}


@pytest.mark.parametrize("text", NOT_INITS)
def test_the_counter_takes_nothing_else_for_a_git_init(tmp_path, text):
    planted = tmp_path / "test_planted.py"
    planted.write_text(f"def test_it(d, repo, om, run, subprocess, helper):\n    {NOT_INITS[text]}"
                       "    pass\n")
    assert the_git_bed.count_git_inits(tmp_path) == 0, text


def test_the_bed_and_this_guard_are_not_counted(tmp_path):
    for name in ("the_git_bed.py", "test_a_test_gets_its_repository_from_the_bed.py"):
        (tmp_path / name).write_text('_git(d, "init")\n')
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "test_x.py").write_text('_git(d, "init")\n')
    assert the_git_bed.count_git_inits(tmp_path) == 1


def test_tests_build_no_more_repositories_than_the_bed_left():
    said = the_git_bed.over_the_line(the_git_bed.count_git_inits(TESTS), BASELINE)
    assert not said, said


def test_one_repository_over_the_line_is_refused_and_the_line_itself_is_not():
    assert the_git_bed.over_the_line(BASELINE + 1, BASELINE)
    assert not the_git_bed.over_the_line(BASELINE, BASELINE)


def test_the_refusal_names_the_count_the_baseline_and_the_bed():
    said = the_git_bed.over_the_line(BASELINE + 2, BASELINE)
    assert f"{BASELINE + 2}" in said and f"{BASELINE}" in said, said
    assert "git_bed" in said and "tests/the_git_bed.py" in said and "CONTRIBUTING.md" in said
    assert said.endswith(".") and "\n" not in said, said
