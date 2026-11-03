"""#199 and #166, proven by breaking them — the board file waits out a lock another connection
holds, for a bound the code states, and then refuses in one sentence.

THREE CLAIMS, EACH WITH RED TWINS:

  1. **The opening sequence is asked again as one** (#166). The WAL conversion, the schema, the
     columns and the triggers are retried on `database is locked` until `BUSY_TIMEOUT_MS` has
     passed, with SQLite's busy handler off while they run. The failure measured under load was
     the SCHEMA step losing the lock after a conversion that went through, so a row puts that step
     outside the retry and the deterministic schema test goes red.
  2. **`BEGIN IMMEDIATE` is asked again** (#199): `_BEGIN_TRIES` tries of one full busy timeout
     each, so a writer that loses one busy timeout under load keeps its card.
  3. **Both bounds end in `BoardLocked`, logged, in one sentence naming the file** — never an
     endless wait, never a silent return, never a refusal a wait cannot cure dressed up as a lock.

WHY EVERY ROW IS AIMED AT A NODE ID. The two race tests in the slice file
(`test_two_writers_never_take_the_same_number`, `test_two_openers_of_a_BRAND_NEW_file_both_get_in`)
are probabilistic — the opening race failed once in 920 measured runs — so a row aimed at them is
red one run in a few hundred. Each row here is aimed at the deterministic test that holds the lock
from a second connection for a COUNTED number of the board's own pauses (`_Pauses` replaces
`board_db.time`), and asserts an outcome rather than a time.

NOT A ROW: the busy handler switched back on during the opening (`timeout=0` in `connect`). With
it on, each refused try waits a real busy timeout before the same outcome, so the deterministic
tests would only get slower; the cause it removes (two openers each waiting out the other's lock,
5.004 s for one conversion, 6.389 s for the schema statement that lost) is held by the
measurement in the PR, not by a test.
"""

TEST = "tests/test_the_board_lives_in_one_file.py"

_T = TEST + "::"
WAL = _T + "test_a_brand_new_file_waits_out_a_neighbour_holding_it_before_WAL"
SCHEMA = _T + "test_the_schema_step_waits_out_a_writer_that_took_the_file_after_WAL"
HELD = _T + "test_a_file_held_past_the_bound_is_refused_in_one_sentence_naming_it"
CURE = _T + "test_a_refusal_a_wait_cannot_cure_is_raised_at_once_and_as_itself"
WAITS = _T + "test_a_writer_waits_out_a_lock_held_past_one_busy_timeout"
NEVER = _T + "test_a_writer_that_never_gets_the_lock_fails_in_one_sentence_and_is_logged"

DB = "beeverforge/adapters/board_db.py"

MUTATIONS = [
    # ── 1. the opening sequence is asked again as one ──────────────────────────────────────────
    ("a locked opening is raised at once, so a brand-new file a neighbour is reading cannot be "
     "put in WAL", DB,
     "            if not _locked(exc):\n                raise\n            last = exc\n"
     "        time.sleep(_OPEN_WAIT_S)",
     "            raise\n        time.sleep(_OPEN_WAIT_S)", WAL),

    ("THE MEASURED CAUSE, PUT BACK: the schema step is outside the retry, so an opener whose "
     "conversion went through loses `CREATE TABLE` to the other one", DB,
     "    for statement in _SCHEMA:\n        conn.execute(statement)\n",
     "    for statement in _SCHEMA:\n        try:\n            conn.execute(statement)\n"
     "        except sqlite3.OperationalError as exc:\n"
     "            raise sqlite3.DatabaseError(str(exc)) from exc\n", SCHEMA),

    ("the opening waits the old 0.4 s instead of the board's busy timeout", DB,
     "    deadline = time.monotonic() + BUSY_TIMEOUT_MS / 1000",
     "    deadline = time.monotonic() + 0.4", WAL),

    ("the opening never gives up, so a wedged neighbour hangs every caller", DB,
     "    while time.monotonic() < deadline:", "    while True:", HELD),

    ("an opening that ran out of time returns over a file it never prepared", DB,
     '    raise _refused(target, f"{BUSY_TIMEOUT_MS} ms while it was being opened") from last',
     "    return", HELD),

    ("an opening that ran out of time leaves nothing in the log", DB,
     '    log.warning("%s stayed locked through the whole opening wait (%d ms): %s",\n'
     "                target, BUSY_TIMEOUT_MS, last)\n",
     "", HELD),

    ("a refusal a wait cannot cure is asked again until the deadline and then called a lock", DB,
     "        except sqlite3.OperationalError as exc:\n            if not _locked(exc):\n"
     "                raise\n            last = exc\n        time.sleep(_OPEN_WAIT_S)",
     "        except sqlite3.OperationalError as exc:\n            if False:\n"
     "                raise\n            last = exc\n        time.sleep(_OPEN_WAIT_S)", CURE),

    # ── 2. `BEGIN IMMEDIATE` is asked again ────────────────────────────────────────────────────
    ("a writer that loses one busy timeout loses its card: the write lock is asked for once", DB,
     "            if not _locked(exc):\n                raise\n            last = exc\n"
     "        time.sleep(_BEGIN_WAIT_S)",
     "            raise\n        time.sleep(_BEGIN_WAIT_S)", WAITS),

    ("the write lock's bound is cut to one try", DB,
     "    for _ in range(_BEGIN_TRIES):", "    for _ in range(1):", WAITS),

    # ── 3. the bounds end in one logged sentence ───────────────────────────────────────────────
    ("the write lock is asked for forever, so a wedged neighbour hangs the writer", DB,
     "    for _ in range(_BEGIN_TRIES):", "    for _ in iter(int, 1):", NEVER),

    ("a writer that never got the lock goes on without a transaction, and its card is written "
     "unguarded", DB,
     '    raise _refused(target, f"{_BEGIN_TRIES} tries of {BUSY_TIMEOUT_MS} ms") from last',
     "    return", NEVER),

    ("a writer that never got the lock leaves nothing in the log", DB,
     '    log.warning("%s: no write lock after %d tries of %d ms each: %s",\n'
     "                target, _BEGIN_TRIES, BUSY_TIMEOUT_MS, last)\n",
     "", NEVER),

    ("the refusal stops naming the file, so a person with three processes on it cannot tell "
     "which file to look at", DB,
     '        f"The board file {target} stayed locked',
     '        f"The board file stayed locked', HELD),

    ("the refusal stops saying what to do", DB,
     'f"worker, panel or CLI command that is holding it and try again.")',
     'f"worker, panel or CLI command.")', NEVER),

    ("the refusal is a bare `OperationalError`, so a caller cannot tell a wedged file from any "
     "other SQLite failure", DB,
     "    return BoardLocked(\n", "    return sqlite3.OperationalError(\n", NEVER),
]
