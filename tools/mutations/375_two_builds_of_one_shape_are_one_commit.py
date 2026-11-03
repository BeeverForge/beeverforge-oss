"""Two builds of one shape in the git bed are one commit, whatever the clock or the test's
environment says (#375): the bed's builders left the author's and committer's dates to the clock,
so two builds a second apart were two commits, and a test comparing commits across builds would
flake on a second boundary, as #371's did. The bed now sets `PINNED` on the `env` every builder is
handed, and its own builders run git with it; each row cuts one part of that.

ROW 1 is the pin itself: nothing is set on `env`, so a build commits with whatever the test's
environment and the clock hold.

ROWS 2-7 ARE THE PIN'S KEYS, one dropped at a time: the test builds under two ambient
environments in which every one of the six variables differs, so a key left out lets one through
and the two builds are two commits.

ROWS 8-9 ARE THE BUILDERS: the served tree's and the card repositories' git calls stop using the
`env` they are handed (the `GIT_AUTHOR_*` and `GIT_COMMITTER_*` variables stripped), so their
commits say the config identity (`fixture`, `t`) and the clock's date instead of the pin's.

NO ROW PUTS #371'S AMBIENT DATES BACK: that would cut the guard, not the code it guards. The
dependence was measured once instead: with the pin in and that test still setting its two dates
in the test's own environment, both builds were the commit 4e99fa5d, and its
`rev-parse HEAD` inequality failed, so the test now sets its dates through `env`.
"""

TEST = "tests/test_a_test_gets_its_repository_from_the_bed.py"

BED = "tests/the_git_bed.py"

#: The environment a builder that stopped using its `env` would run git in.
UNPINNED = ('{k: v for k, v in os.environ.items()'
            ' if not k.startswith(("GIT_AUTHOR_", "GIT_COMMITTER_"))}')

MUTATIONS = [
    ("the pin is never set on `env`: a build commits on the clock and the test's identity", BED,
     "                    for key, value in PINNED.items():\n"
     "                        env.setenv(key, value)\n",
     ""),

    ("the author's date is left out of the pin", BED,
     '    "GIT_AUTHOR_DATE": "2001-02-03T04:05:06+0000",\n', ""),

    ("the committer's date is left out of the pin", BED,
     '    "GIT_COMMITTER_DATE": "2001-02-03T04:05:06+0000",\n', ""),

    ("the author's name is left out of the pin", BED,
     '    "GIT_AUTHOR_NAME": "the git bed",\n', ""),

    ("the author's email is left out of the pin", BED,
     '    "GIT_AUTHOR_EMAIL": "bed@beeverforge.invalid",\n', ""),

    ("the committer's name is left out of the pin", BED,
     '    "GIT_COMMITTER_NAME": "the git bed",\n', ""),

    ("the committer's email is left out of the pin", BED,
     '    "GIT_COMMITTER_EMAIL": "bed@beeverforge.invalid",\n', ""),

    ("the served tree's builder runs git without the pinned `env`", BED,
     '        lazy = {**os.environ, "GIT_NO_LAZY_FETCH": "1"}\n',
     f'        lazy = {{**{UNPINNED}, "GIT_NO_LAZY_FETCH": "1"}}\n'),

    ("the card repositories' builder commits without the pinned `env`", BED,
     '         "commit", "-q", "-m", message)\n',
     f'         "commit", "-q", "-m", message, env={UNPINNED})\n'),
]
