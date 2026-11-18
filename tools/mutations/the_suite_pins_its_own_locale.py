"""Mutation plan: the suite pins its own locale for every test and every subprocess it starts.

Run:  .venv/bin/python tools/mutate.py tools/mutations/the_suite_pins_its_own_locale.py

Each row takes away one part of the pin in `tests/conftest.py`; every row must turn the guard red.
Row 1 removes the pin outright, row 2 leaves the shell's `LANGUAGE` in place (gettext reads it
ahead of `LC_ALL`), row 3 pins a locale that is not the suite's.
"""

TEST = "tests/test_the_suite_pins_its_own_locale.py"
CONFTEST = "tests/conftest.py"

MUTATIONS = [
    ("the shell's LC_ALL reaches every subprocess", CONFTEST,
     '    os.environ["LC_ALL"] = SUITE_LOCALE\n',
     ""),
    ("the shell's LANGUAGE reaches every subprocess", CONFTEST,
     '    os.environ.pop("LANGUAGE", None)\n',
     ""),
    ("the suite pins a non-English locale", CONFTEST,
     'SUITE_LOCALE = "C.UTF-8"\n',
     'SUITE_LOCALE = "pt_BR.UTF-8"\n'),
]
