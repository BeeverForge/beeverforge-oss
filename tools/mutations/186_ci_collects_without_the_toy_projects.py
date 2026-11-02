"""#186: collection does not depend on the author's optional working state.

The defect these cuts restore ran CI on ZERO tests for fifteen days (253 red runs, last green
2026-08-06) while this machine stayed green — so the only interesting question about the new guard
is whether it goes red when the defect comes back. Each cut below is a real shape it arrived in.
"""

TEST = "tests/test_ci_runs_what_we_run.py"
D = "tests/demo_projects.py"
E = "tests/test_env_proposes_before_it_verifies.py"

MUTATIONS = [
    # THE DEFECT ITSELF, verbatim as `88139ad` wrote it: a module-scope constant built by dividing
    # an Option by a name. Raises TypeError at import, which aborts the whole collection.
    ("the module divides None by a name at import again", E,
     "FIXTURES = demo_projects_root()",
     "from tests.demo_projects import demo_projects  # noqa\nFIXTURES = demo_projects()"),

    # THE SOFT HALF, and the reason the count assertion exists. A module that swallows the import
    # error stops raising — it just stops existing, and the suite silently shrinks.
    ("the module vanishes from collection instead of raising", E,
     "FIXTURES = demo_projects_root()",
     "import pytest as _p\nfrom tests.demo_projects import demo_projects\n"
     "if demo_projects() is None:\n    _p.skip('no fixtures', allow_module_level=True)\n"
     "FIXTURES = demo_projects_root()"),

    # THE HELPER GOING BACK TO BEING A LANDMINE. If `demo_projects_root` can answer None, every
    # caller is one edit away from the original defect and the guard must say so.
    ("the module-scope helper starts answering None again", D,
     "    return demo_projects() or _NOWHERE",
     "    return demo_projects()"),
]

#: #336: THE THREE COLLECTIONS ABOVE NO LONGER TAKE THE WHOLE TREE, each a subset derived from the
#: failure it exists for. These rows prove each narrowed run still holds its incident, on the
#: node that asks.
PYPROJECT = "pyproject.toml"
CONSOLE = f"{TEST}::test_the_bare_pytest_console_script_can_COLLECT_the_suite"
SAME = f"{TEST}::test_that_invocation_sees_the_same_tests_this_one_does"
TOYLESS = f"{TEST}::test_collection_survives_a_machine_without_THE_OPTIONAL_TOY_PROJECTS"
WHOLE = f"{TEST}::test_no_guard_here_collects_the_whole_suite"

MUTATIONS += [
    # THE INCIDENT OF 2026-08-05: nothing puts the root on `sys.path`, so the console script
    # cannot import `tests.test_walking_skeleton` by name. The plugin subset must still hit it.
    ("pytest's config drops pythonpath, and the console script's subset collection dies", PYPROJECT,
     'pythonpath = ["."]\n', "", CONSOLE),
    ("pytest's config drops pythonpath, and the two invocations' subset counts part", PYPROJECT,
     'pythonpath = ["."]\n', "", SAME),

    # THE SOFT SHAPE of the same split: a declarer vanishes under the console script alone, with
    # exit code 0. Only the count comparison can see it.
    ("a plugin declarer vanishes under the console script only", "tests/test_a_failing_setup_is_not_silent.py",
     "",
     "\nimport sys as _sys\nif _sys.argv[0].endswith('/pytest'):\n"
     "    import pytest as _p\n    _p.skip('console script only', allow_module_level=True)\n", SAME),

    # THE TRANSITIVE HALF of the toy-project closure: a helper no test names as a toy-project
    # reader breaks at import, and every module importing it aborts the toy-less collection.
    # None of `tests/dockerfiles.py`'s importers names the reader, so only the closure reaches them.
    ("a helper reaches the toy projects at import and breaks without them", "tests/dockerfiles.py",
     "",
     "\nfrom tests.demo_projects import demo_projects as _dp\n_X = _dp() / 'x'\n", TOYLESS),

    # CRITERION 3: a guard that goes back to collecting the whole tree is refused by name.
    ("the toy-less guard collects the whole tree again", TEST,
     '"--collect-only", *_toy_project_subset()), stripped)',
     '"--collect-only"), stripped)', WHOLE),
]

#: The SECOND defect the same accident exposed, in the same file it lives in. Kept here rather
#: than in its own plan because it is one commit's worth of repair: the marker that went dark is
#: the marker `.gitignore` now refuses.
OWNER = "tests/test_the_product_carries_no_owners_name.py"

MUTATIONS += [
    ("a tracked file missing from disk is skipped into silence again", OWNER,
     "    except OSError:\n        pass",
     "    except OSError:\n        return None", OWNER),

    ("…and the index fallback stops carrying the content", OWNER,
     "        return out.stdout.decode(\"utf-8\")",
     "        return \"\"", OWNER),

    ("a file staged for deletion is resurrected and judged anyway", OWNER,
     "    if out.returncode != 0:\n        return None",
     "    if out.returncode != 0:\n        return \"\"", OWNER),
]

#: RETIRED 2026-09-07 — the docs header that must name a REAL commit, in the one form that is
#: checked. `test_the_works_today_page_carries_the_commit_it_describes` verifies `main at <sha>`
#: with `git cat-file` and SKIPS `cut from <sha>` by name: a fresh-history export cannot hold the
#: source tree's commit, and a guard demanding it "would be red on the first commit of every public
#: clone" (its own words). The row here was re-pinned onto the `cut from` text when the page was
#: re-cut — the anchor followed the words and lost the claim — and, run for the first time since,
#: it survived. The guard says what earns it back: the first maintainer who edits this page in the
#: public repository writes the strict form against a commit that exists here, and on that day the
#: row is worth writing again.
