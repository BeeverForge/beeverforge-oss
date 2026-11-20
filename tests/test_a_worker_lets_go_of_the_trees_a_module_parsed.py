"""A worker lets go of the trees a test module parsed once that module is done (#619).

WHAT HAPPENED. `tests/the_tree_read_once.py` kept every tree it ever parsed until the worker
exited, and froze the whole heap after each new parse (`gc.freeze()`) with nothing ever unfreezing
it. Measured in one process on main at 2852852, with `-p no:xdist -p no:randomly -m "not
(owns_its_engine or slow or alone or whole_tree)"`: 749 MB after collection, 344 trees held from
the guards that parse at import, and 1,887 MB at the end. One file,
`test_ci_runs_every_test_exactly_once.py`, added 345 MB by itself: two of its guards parsed every
`tests/test_*.py` through the cache and left all 961 trees there. Two such workers do not fit in a
3.6 GiB box, so one was OOM-killed and every gate on that box failed.

WHAT HOLDS NOW, and is held here:

  - when the next test is in another file, or there is no next test, the trees go and the freeze is
    undone (`conftest.pytest_runtest_teardown` asks `the_tree_read_once.forget`); while the module
    goes on, the trees stay, so its tests still share one tree per content;
  - that hook is the one the session calls, after the runner's own teardown, so module fixtures
    holding a tree are already released when the cache lets go;
  - a guard that only needs a fact from every file asks `fact`, which keeps the fact and never the
    tree, and the two guards over every test file ask it.
"""

from __future__ import annotations

import gc
import types
import uuid
import weakref
from pathlib import Path

import conftest
import pytest
import test_ci_runs_every_test_exactly_once as once

from tests import the_tree_read_once as trees


def _a_tree(tmp_path: Path):
    path = tmp_path / f"m_{uuid.uuid4().hex}.py"
    path.write_text(f"x = {uuid.uuid4().int}\n", encoding="utf-8")
    return path, trees.parsed(path)


def _next_in(path: Path) -> types.SimpleNamespace:
    """The one thing the hook reads of the next item: the file it lives in."""
    return types.SimpleNamespace(path=path)


def _module_ends(request: pytest.FixtureRequest, nextitem: object) -> None:
    conftest.pytest_runtest_teardown(request.node, nextitem)


# ── the cache, at a module's end ────────────────────────────────────────────────────────────────

def test_the_trees_go_and_the_freeze_is_undone_when_the_next_test_is_in_another_file(
        request: pytest.FixtureRequest, tmp_path: Path) -> None:
    path, tree = _a_tree(tmp_path)
    gone = weakref.ref(tree)
    assert trees.cached() >= 1 and gc.get_freeze_count() > 0, "nothing was cached or frozen"

    _module_ends(request, _next_in(request.node.path.with_name("test_another_file.py")))

    assert trees.cached() == 0, f"{trees.cached()} trees outlived the module that parsed them"
    assert gc.get_freeze_count() == 0, (
        f"{gc.get_freeze_count()} objects are still frozen after the cache let go")
    del tree
    assert gone() is None, "the dropped tree is still alive: something else holds it"
    assert trees.parsed(path) is not None and trees.cached() == 1


def test_the_last_test_of_the_run_lets_go_too(request: pytest.FixtureRequest,
                                               tmp_path: Path) -> None:
    _a_tree(tmp_path)

    _module_ends(request, None)

    assert trees.cached() == 0 and gc.get_freeze_count() == 0


def test_while_the_module_goes_on_its_tests_share_one_tree(request: pytest.FixtureRequest,
                                                           tmp_path: Path) -> None:
    path, tree = _a_tree(tmp_path)

    _module_ends(request, _next_in(request.node.path))

    assert trees.parsed(path) is tree, "a tree was dropped while its module was still running"
    assert gc.get_freeze_count() > 0, "the tree the module still uses went back to the collector"


def test_the_session_calls_the_hook_after_the_runners_own_teardown(
        request: pytest.FixtureRequest) -> None:
    """`trylast`: the runner's `pytest_runtest_teardown` finalises the module's fixtures first, so
    a module fixture that holds a tree has let go of it when the cache does."""
    ours = [impl for impl in request.config.hook.pytest_runtest_teardown.get_hookimpls()
            if impl.function is conftest.pytest_runtest_teardown]

    assert ours, "the session does not call the hook that empties the tree cache"
    assert ours[0].trylast, "the cache lets go before the module's fixtures are torn down"


# ── a fact, not the tree ────────────────────────────────────────────────────────────────────────

def test_a_fact_keeps_no_tree(tmp_path: Path) -> None:
    trees.forget()
    path = tmp_path / "m.py"
    path.write_text("def test_one(): ...\ndef test_two(): ...\n", encoding="utf-8")
    asked = []

    def names(tree):
        asked.append(tree)
        return tuple(n.name for n in tree.body)

    assert trees.fact(path, names) == ("test_one", "test_two")
    assert trees.fact(path, names) == ("test_one", "test_two")
    assert len(asked) == 1, "the same content was parsed and read again for the same fact"
    assert trees.cached() == 0, "asking a fact left the tree in the cache"
    gone = weakref.ref(asked.pop())
    assert gone() is None, "the tree a fact was read from is still alive"


def test_a_fact_reads_the_bytes_read_this_time(tmp_path: Path) -> None:
    path = tmp_path / "m.py"
    path.write_text("x = 1\n", encoding="utf-8")

    def first(tree):
        return tree.body[0].value.value

    assert trees.fact(path, first) == 1
    path.write_text("x = 2\n", encoding="utf-8")
    assert trees.fact(path, first) == 2, "a stale fact was served for new bytes"


def test_a_fact_is_forgotten_with_the_trees(tmp_path: Path) -> None:
    path = tmp_path / "m.py"
    path.write_text(f"x = {uuid.uuid4().int}\n", encoding="utf-8")
    asked = []

    def count(tree):
        asked.append(1)
        return len(tree.body)

    trees.fact(path, count)
    trees.forget()
    trees.fact(path, count)

    assert len(asked) == 2, "a fact outlived the module that asked it"


def test_a_cached_tree_answers_a_fact_without_a_second_parse(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path, tree = _a_tree(tmp_path)
    real, parses = trees.ast.parse, []

    def counted(*args, **kwargs):
        parses.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(trees.ast, "parse", counted)
    read = trees.fact(path, lambda t: t is tree)
    monkeypatch.undo()

    assert read and not parses, "a tree the cache holds was parsed again for a fact"


# ── the two guards over every test file ─────────────────────────────────────────────────────────

_TIMED = ("import time\n"
          "def test_unmarked():\n    assert time.process_time() < 1\n"
          "@pytest.mark.alone\ndef test_marked():\n    assert time.process_time() < 1\n")
_DAEMON = ("import pytest\n"
           "@pytest.mark.skipif(not _docker_and_compose(), reason='no daemon')\n"
           "def test_outside():\n    pass\n"
           "@pytest.mark.skipif(not _docker_and_compose(), reason='no daemon')\n"
           "@pytest.mark.xdist_group('docker')\ndef test_inside():\n    pass\n")


def test_the_guards_over_every_test_file_keep_no_tree(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_timed.py").write_text(_TIMED, encoding="utf-8")
    (tmp_path / "tests" / "test_daemon.py").write_text(_DAEMON, encoding="utf-8")
    trees.forget()

    unmarked = once._unmarked_cpu_readers(tmp_path)
    daemon = once._real_daemon_tests(tmp_path)

    assert unmarked == ["tests/test_timed.py::test_unmarked"], unmarked
    assert daemon == {"tests/test_daemon.py::test_outside": False,
                      "tests/test_daemon.py::test_inside": True}, daemon
    assert trees.cached() == 0, "a guard over every test file left its trees in the cache"
