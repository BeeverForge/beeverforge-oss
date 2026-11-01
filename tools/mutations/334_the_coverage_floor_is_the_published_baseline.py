"""#334: the suite's coverage is a floor CI holds, and docs/STATUS.md publishes that floor.

The reverses are the published figure parting from `fail_under`, the floor gone, what is measured
widened or narrowed, CI measuring nothing or holding nothing, CI measuring or holding a pull request
(the floor is held on pushes to main only), a slice held to the whole floor, a
stale slice combined into a fresh figure, and a failure that stops naming its remedy.
"""

TEST = "tests/test_the_coverage_floor_is_the_published_baseline.py"
PYPROJECT = "pyproject.toml"
STATUS = "docs/STATUS.md"
MAKEFILE = "Makefile"
CI = ".github/workflows/ci.yml"

MUTATIONS = [
    # ── the published figure is the floor ───────────────────────────────────────────────────────
    # RE-PINNED (#344 review): the floor moved to 89.36, set from CI's measurement less its spread,
    # and STATUS publishes that floor beside the measurement rather than as the measured total.
    ("STATUS's floor drifts from fail_under — the page publishes a floor CI does not hold", STATUS,
     "floor **89.36%**", "floor **89.35%**"),

    ("fail_under drifts from STATUS's floor — the floor moves and the page does not", PYPROJECT,
     "fail_under = 89.36", "fail_under = 89.35"),

    ("fail_under removed — there is no floor", PYPROJECT, "fail_under = 89.36\n", ""),

    ("the floor is set above what CI measured — the measured code fails it", PYPROJECT,
     "fail_under = 89.36", "fail_under = 89.40"),

    ("…and on the page too, so only the measurement can say it is wrong", STATUS,
     "floor **89.36%**", "floor **89.40%**"),

    ("the measured total is re-typed upward and the floor left — a stale, lenient floor", STATUS,
     "total **89.3785%**", "total **89.5785%**"),

    ("a figure is mistyped — the total no longer lies between its line and branch", STATUS,
     "branch **85.5513%**", "branch **95.5513%**"),

    ("the baseline names a commit this history does not hold", STATUS,
     "measured on `b5f2742`", "measured on `0000000`"),

    # ── what is measured ────────────────────────────────────────────────────────────────────────
    ("branch coverage off — a line figure is green over an arm that never ran", PYPROJECT,
     "branch = true\nrelative_files", "branch = false\nrelative_files"),

    ("source not limited to beeverforge — a test file is covered by running it", PYPROJECT,
     'source = ["beeverforge"]', 'source = ["beeverforge", "tests"]'),

    ("absolute paths in the data — four runners' slices do not combine", PYPROJECT,
     "relative_files = true\n", ""),

    # ── CI measures every slice and holds the combined data — on pushes to main only ───────────
    ("the unit slices run without TEST_COVERAGE — the floor is held over nothing", CI,
     "          TEST_COVERAGE: ${{ github.event_name == 'push' && '1' || '' }}\n", ""),

    ("the unit slices measure on pull requests too — every pull request pays the cost", CI,
     "          TEST_COVERAGE: ${{ github.event_name == 'push' && '1' || '' }}\n",
     '          TEST_COVERAGE: "1"\n'),

    ("the unit slices measure on pull requests INSTEAD of pushes", CI,
     "github.event_name == 'push' && '1' || ''", "github.event_name == 'pull_request' && '1' || ''"),

    ("the slices upload coverage on pull requests too", CI,
     "        if: github.event_name == 'push'\n        with:\n          name: coverage-unit-",
     "        with:\n          name: coverage-unit-"),

    ("the test job no longer holds the combined coverage to the floor", CI,
     "      - if: github.event_name == 'push' && needs.unit.result == 'success'\n"
     "        run: make coverage-report\n", ""),

    ("the report's push condition is dropped — it would hold pull requests, over no data", CI,
     "      - if: github.event_name == 'push' && needs.unit.result == 'success'\n"
     "        run: make coverage-report\n",
     "      - if: needs.unit.result == 'success'\n        run: make coverage-report\n"),

    ("the download's push condition is dropped", CI,
     "        if: github.event_name == 'push' && needs.unit.result == 'success'\n"
     "        with:\n          pattern: coverage-unit-*",
     "        if: needs.unit.result == 'success'\n        with:\n          pattern: coverage-unit-*"),

    ("the install's push condition is dropped", CI,
     "      - if: github.event_name == 'push' && needs.unit.result == 'success'\n"
     "        run: pip install",
     "      - if: needs.unit.result == 'success'\n        run: pip install"),

    ("the report runs on pull requests only — main is never held", CI,
     "      - if: github.event_name == 'push' && needs.unit.result == 'success'\n"
     "        run: make coverage-report\n",
     "      - if: github.event_name == 'pull_request' && needs.unit.result == 'success'\n"
     "        run: make coverage-report\n"),

    ("a slice that wrote no data uploads nothing, and three slices pass for four", CI,
     "          if-no-files-found: error\n", ""),

    ("a slice is held to the whole suite's floor — every CI slice is red", MAKEFILE,
     "COVERAGE_ARGS := --cov --cov-report= --cov-fail-under=0",
     "COVERAGE_ARGS := --cov --cov-report="),

    ("a whole run keeps last run's slices — a stale figure combines into a fresh one", MAKEFILE,
     "$(if $(TEST_SHARDS),,rm -rf $(COVERAGE_DIR) && )", ""),

    ("every slice writes one file name — the downloads overwrite one another", MAKEFILE,
     "/coverage.unit$(if $(TEST_SHARDS),-$(TEST_SHARD)-of-$(TEST_SHARDS))", "/coverage.unit"),

    ("the report overrides the floor on its command line", MAKEFILE,
     "python -m coverage report --skip-covered --sort=cover;",
     "python -m coverage report --skip-covered --sort=cover --fail-under=0;"),

    # ── below the floor, the failure says so ────────────────────────────────────────────────────
    ("the failure below the floor stops naming its remedy", MAKEFILE,
     '	    echo "make $@: coverage of beeverforge/ fell below the floor', '	    true "'),

    ("the report's failure is swallowed — below the floor reads green", MAKEFILE,
     "	  fi; exit $$rc\n", "	  fi; exit 0\n"),

    ("no data reads as a figure instead of a refusal", MAKEFILE,
     "python -m coverage combine --keep $(COVERAGE_DIR) \\",
     "python -m coverage combine --keep $(COVERAGE_DIR) 2>/dev/null; true \\"),
]
