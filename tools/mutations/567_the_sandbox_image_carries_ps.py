"""The sandbox image installs procps and records `ps` in its toolchain file (#567), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/567_the_sandbox_image_carries_ps.py

The guard parses the RUN instructions, so text a comment can satisfy does not count. The claims:

  1. procps is dropped from the install (row 1);
  2. procps is dropped from the install but still named in a comment (row 2);
  3. procps moves to a different command of the block, not `apt-get install` (row 3);
  4. the toolchain record no longer names `ps` (row 4).
"""

TEST = "tests/test_the_sandbox_image_carries_ps.py"

SANDBOX = "docker/sandbox.Dockerfile"

MUTATIONS = [
    ("TODAY'S DEFECT: the image installs no procps", SANDBOX,
     "--no-install-recommends gh tini procps \\\n",
     "--no-install-recommends gh tini \\\n"),
    ("procps is not installed but a comment still names it", SANDBOX,
     "--no-install-recommends gh tini procps \\\n",
     "--no-install-recommends gh tini \\\n    # apt-get install procps\n"),
    ("procps is only echoed, not installed", SANDBOX,
     "--no-install-recommends gh tini procps \\\n",
     "--no-install-recommends gh tini \\\n    && echo apt-get install procps \\\n"),
    ("the toolchain record no longer names ps", SANDBOX,
     '      echo "ps=$(ps --version 2>&1 | head -1 || echo none)"; \\\n',
     ""),
]
