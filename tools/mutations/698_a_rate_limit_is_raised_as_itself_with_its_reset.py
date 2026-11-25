"""#698: a forge or tracker call that fails on a rate limit raises `RateLimited` with its reset.

One cut per seam: the detection (the reset read from a header), the tracker's close (which wrapped
every `RuntimeError`, so a `RateLimited` lost its type), and the forge's reads (`_gh_read` folded a
spent limit into None). Each is killed by a named test.
"""

TEST = "tests/test_a_rate_limit_is_raised_as_itself_with_its_reset.py"
RATE_LIMIT = "beeverforge/adapters/rate_limit.py"
TRACKER = "beeverforge/adapters/tracker/github.py"
FORGE = "beeverforge/adapters/forge/github.py"

MUTATIONS = [
    ("detection: a reset header is no longer read, so reset_at is the default wait "
     "(test_a_reset_header_gives_the_reset_epoch)", RATE_LIMIT,
     "    found = _RESET_HEADER.search(text)\n    if found:\n"
     "        return float(found.group(1))\n",
     "    found = None\n"),

    ("detection: a refusal in stderr is no longer recognised "
     "(test_the_trackers_write_raises_rate_limited)", RATE_LIMIT,
     "    if not refused:\n        return None\n",
     "    if True:\n        return None\n"),

    ("the tracker close wraps a RateLimited as a plain RuntimeError "
     "(test_a_close_that_hits_the_limit_after_its_reason_keeps_its_type_and_reset)", TRACKER,
     "        except RateLimited:\n"
     "            raise  # its type and its reset are what a caller waits on (#698)\n",
     ""),

    ("a forge read folds a spent limit into an unreadable answer "
     "(test_every_forge_read_and_the_repo_creation_raise_rate_limited)", FORGE,
     "        self._raise_if_limited(answered)\n        return answered\n",
     "        return answered\n"),

    ("repo creation reads a limited owner probe as a personal account "
     "(test_an_owner_probe_that_hits_the_limit_is_not_read_as_a_personal_account)", FORGE,
     "            self._raise_if_limited(kind)\n", ""),

    ("repo creation reports a limited org creation as a missing permission "
     "(test_a_repo_creation_refused_for_its_limit_after_the_app_refusal_is_rate_limited)", FORGE,
     "                    self._raise_if_limited(rest)\n", ""),
]
