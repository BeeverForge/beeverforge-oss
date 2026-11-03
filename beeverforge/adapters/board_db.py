"""`board.db` — the one file the local rows share (ADR-0049 D5).

THE SHAPE OF THIS MODULE IS `adapters/azure_devops.py`'s. That file is the client three rows on
three axes share so one vendor is spelled once; this is the same thing for a vendor that happens to
be the machine itself. The tracker row, the board row and — from slice 3 — the forge row all read
and write here, and none of them owns the file.

WHY SQLITE AND NOT THE REGISTRY'S DISCIPLINE. `ProjectRegistry` rewrites a YAML file under a flock
and swaps it in with `os.replace`, which is right for a document a person edits and wrong for this:
`os.replace` on a WAL database DETACHES the journal, so a reader mid-transaction is left holding a
file the writer has stopped extending. This is a database with three processes on it — the worker
polling, the panel serving and a CLI verb in a shell — so it uses a database's own answers: WAL, a
busy timeout, and `BEGIN IMMEDIATE` around anything that reads a value and writes it back.

WHY NOT THE METRICS SINK, which is also SQLite and also on the state volume: an event written there
without `expires_at` evicts the registered accounts (`identity/people.py`). A card is not an event
and must not age out of the board because a sweep decided it was old.

WHAT IS DELIBERATELY NOT HERE. No ORM, no migration framework and no schema version: every open
runs `CREATE TABLE IF NOT EXISTS`, which is idempotent, costs microseconds and makes a new TABLE in
a later slice one more statement rather than a migration to write, test and run.

A NEW COLUMN IS NOT FREE, and this paragraph used to say it was. `IF NOT EXISTS` skips a table that
is already there, so a column added to `_SCHEMA` exists only in files created after it — and on
every deployment that had been running, the first INSERT naming it fails with `table pull_requests
has no column named repo` (#140). `_ADDED_COLUMNS` is the whole answer: a column that APPEARS,
added once per file, guarded and idempotent. The day a column has to CHANGE rather than appear,
that is a migration and it will need saying out loud.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

log = logging.getLogger(__name__)

#: Where the file is, when the deployment names it. Compose points the worker AND the panel at the
#: state volume they already share, exactly as it does for the registry; a host installation names
#: nothing and gets the operator's own directory.
PATH_ENV = "BEEVERFORGE_BOARD_DB"

#: SQLite's busy timeout for this file, and the unit of the module's two bounds. Five seconds is
#: the registry's own flock timeout. It bounds two different waits, and they are NOT the same on
#: purpose (#199, #383's review):
#:   - the OPENING (`_open`): `BUSY_TIMEOUT_MS` in all, with the busy handler off, because two
#:     openers each waiting out the other's busy timeout is what failed #166 (one conversion waited
#:     5.004 s, the schema statement that then lost waited 6.389 s, measured under load);
#:   - the WRITE LOCK (`_begin`): `_BEGIN_TRIES` x `BUSY_TIMEOUT_MS`, about 15 s, because one lost
#:     busy timeout under load is a slow neighbour, not a wedged one. Measured under load, the
#:     other writer held the lock 2.315 s at most and `BEGIN IMMEDIATE` waited 1.833 s at most;
#:     #199's loss was not reproduced in 920 runs, so tries two and three are headroom, not a cure.
BUSY_TIMEOUT_MS = 5000

#: THE OPENING SEQUENCE'S BOUND — the WAL conversion, the schema, the columns and the triggers,
#: asked again as one while another connection holds the file (`_open`). The TOTAL is
#: `BUSY_TIMEOUT_MS` on the monotonic clock, the same five seconds as every other write here, and
#: it cannot multiply: the busy handler is OFF while the sequence runs (`busy_timeout` 0), so no
#: statement in a try waits at all and the loop's own pauses of `_OPEN_WAIT_S` are the only
#: waiting there is. Worst case: `BUSY_TIMEOUT_MS` plus one try's own work. Every open of a file
#: that already holds the board finds nothing to write and returns on its first try.
_OPEN_WAIT_S = 0.01

#: THE WRITE LOCK'S BOUND (#199): `BEGIN IMMEDIATE` is asked at most `_BEGIN_TRIES` times, each a
#: full `BUSY_TIMEOUT_MS` on SQLite's busy handler, with `_BEGIN_WAIT_S` between them — so a writer
#: waits at most 3 x 5 s + 2 x 10 ms, about 15 s, and is then refused with `BoardLocked`.
_BEGIN_TRIES, _BEGIN_WAIT_S = 3, 0.01

_SCHEMA = (
    # A card. `ref` is an INTEGER per project because the number sequence is per project (D5);
    # the PORT's two spellings (`#N` and bare `N`) are a rendering question and are resolved by
    # `canonical_ref` at the row, never stored twice.
    #
    # `position` IS WHERE THE CARD STANDS IN ITS COLUMN (#512) — the order the poller pulls the
    # queue in, and the one `LocalBoard.place_after` writes. A file made before the column existed
    # gains it through `_ADDED_COLUMNS`, and every card a writer puts in a column joins it at the
    # bottom through `_TRIGGERS`.
    """CREATE TABLE IF NOT EXISTS cards (
           project      TEXT NOT NULL,
           ref          INTEGER NOT NULL,
           title        TEXT NOT NULL DEFAULT '',
           body         TEXT NOT NULL DEFAULT '',
           state        TEXT NOT NULL DEFAULT 'open',
           closed_reason TEXT NOT NULL DEFAULT '',
           column_key   TEXT NOT NULL DEFAULT '',
           author       TEXT NOT NULL DEFAULT '',
           requester    TEXT NOT NULL DEFAULT '',
           created_at   TEXT NOT NULL,
           updated_at   TEXT NOT NULL,
           position     INTEGER NOT NULL DEFAULT 0,
           PRIMARY KEY (project, ref)
       )""",
    # Ordered by `seq` rather than by the timestamp: two comments written in the same second must
    # still come back oldest-first, and the ADR-0048 sweep reads the ORDER to decide whether an
    # answer is newer than the question it answers.
    """CREATE TABLE IF NOT EXISTS comments (
           project    TEXT NOT NULL,
           ref        INTEGER NOT NULL,
           seq        INTEGER NOT NULL,
           author     TEXT NOT NULL DEFAULT '',
           body       TEXT NOT NULL DEFAULT '',
           created_at TEXT NOT NULL,
           PRIMARY KEY (project, ref, seq)
       )""",
    """CREATE TABLE IF NOT EXISTS labels (
           project TEXT NOT NULL,
           ref     INTEGER NOT NULL,
           label   TEXT NOT NULL,
           PRIMARY KEY (project, ref, label)
       )""",
    # The board's own columns, in board order. A row per project, so two projects on one machine
    # may be renamed independently — which is what `columns:` in the registry already promises
    # every other board (C-14).
    """CREATE TABLE IF NOT EXISTS columns (
           project  TEXT NOT NULL,
           key      TEXT NOT NULL,
           name     TEXT NOT NULL,
           position INTEGER NOT NULL,
           PRIMARY KEY (project, key)
       )""",
    # One pull request. `patch_id` is `git patch-id --stable` over `merge-base(base,head)..head`,
    # recorded at open, at every re-push and immediately BEFORE the fast-forward — after it the
    # three-dot diff is empty by construction, so a patch id taken afterwards would say the pull
    # request changed nothing.
    #
    # `refused` HOLDS GIT'S OWN SENTENCE. When a fast-forward is refused the person needs the
    # words git used, not this platform's paraphrase of them: "your local changes would be
    # overwritten" names the file, and no rewriting of it is an improvement.
    #
    # `repo` IS THE REPOSITORY THE PULL REQUEST IS AGAINST, `''` for the project's own. Every git
    # command about the pull request runs THERE — see `LocalForge._where`. A file made before the
    # column existed gains it through `_ADDED_COLUMNS`, not here.
    """CREATE TABLE IF NOT EXISTS pull_requests (
           project    TEXT NOT NULL,
           number     INTEGER NOT NULL,
           repo       TEXT NOT NULL DEFAULT '',
           head       TEXT NOT NULL,
           base       TEXT NOT NULL,
           title      TEXT NOT NULL DEFAULT '',
           body       TEXT NOT NULL DEFAULT '',
           state      TEXT NOT NULL DEFAULT 'open',
           base_sha   TEXT NOT NULL DEFAULT '',
           patch_id   TEXT NOT NULL DEFAULT '',
           merge_sha  TEXT NOT NULL DEFAULT '',
           reviewers  TEXT NOT NULL DEFAULT '',
           events     TEXT NOT NULL DEFAULT '',
           refused    TEXT NOT NULL DEFAULT '',
           created_at TEXT NOT NULL,
           updated_at TEXT NOT NULL,
           PRIMARY KEY (project, number)
       )""",
    # Native parent→child linkage, the optional capability the splitter uses for idempotency.
    """CREATE TABLE IF NOT EXISTS links (
           project    TEXT NOT NULL,
           parent_ref INTEGER NOT NULL,
           child_ref  INTEGER NOT NULL,
           PRIMARY KEY (project, parent_ref, child_ref)
       )""",
    # A card somebody REMOVED before the factory took it up (#384) — the audit line, and the
    # reason its number is never handed out again. The card's own row is gone (that is what
    # removal means on this board), so this is what is left of it: who removed it, when, why, and
    # the title it had, which is how a person recognises what they are reading about. A NEW TABLE,
    # not a column, so `IF NOT EXISTS` is the whole migration (the module docstring's rule).
    """CREATE TABLE IF NOT EXISTS removed_cards (
           project    TEXT NOT NULL,
           ref        INTEGER NOT NULL,
           title      TEXT NOT NULL DEFAULT '',
           removed_by TEXT NOT NULL DEFAULT '',
           reason     TEXT NOT NULL DEFAULT '',
           removed_at TEXT NOT NULL,
           PRIMARY KEY (project, ref)
       )""",
)

#: Columns `_SCHEMA` gained after files holding that table were already out in the world, as
#: `(table, column, declaration)`. `connect` adds each one a file lacks — see `_add_columns`.
#:
#: APPEAR, NEVER CHANGE: every declaration here has to be one `ALTER TABLE … ADD COLUMN` accepts on
#: a table that already has rows, which for a `NOT NULL` column means a constant default.
_ADDED_COLUMNS = (
    # Which repository a pull request is against (#140). `''` is the project's own, which is the
    # truth for every ordinary ticket pull request written before the column existed. It is NOT
    # the truth for one opened against another repository before then — but that one was never
    # readable or mergeable either, so the default loses nothing it had: close it and propose
    # again, and the new one records where it is.
    ("pull_requests", "repo", "TEXT NOT NULL DEFAULT ''"),
    # Where a card stands in its column (#512). `0` for every card already on a running board,
    # which ties them, and a tie is served by number — the order that file was served in before
    # the column existed. Every card that ENTERS a column afterwards joins it below them
    # (`_TRIGGERS`), and a person's order rewrites the whole column (`LocalBoard.place_after`).
    ("cards", "position", "INTEGER NOT NULL DEFAULT 0"),
)

#: A CARD THAT ENTERS A COLUMN JOINS IT AT THE BOTTOM, whoever moved it there (#512).
#:
#: SIX WRITERS PUT A CARD IN A COLUMN on this board — the tracker's filing, its `set_state` and its
#: close and reopen, the board's `set_column` and `set_status` — and the queue is served in the
#: order a person set only if every one of them agrees on where a card lands. Written once per
#: writer, the seventh would put its card wherever `0` sorts — at the TOP of the queue, ahead of
#: work a person approved first. So the rule is the file's, and no writer can be added without it.
#:
#: ONLY WHEN THE COLUMN CHANGED (the `WHEN`): a move to where the card already is changes nothing,
#: and must not send a card a person placed first to the back of its own column. Created AFTER
#: `_add_columns`, because they write `position`, which a file made before #512 has only once it
#: was added.
_TRIGGERS = (
    """CREATE TRIGGER IF NOT EXISTS a_filed_card_joins_the_bottom_of_its_column
       AFTER INSERT ON cards
       BEGIN
           UPDATE cards SET position = (
               SELECT COALESCE(MAX(position), 0) + 1 FROM cards
               WHERE project = NEW.project AND column_key = NEW.column_key AND ref != NEW.ref)
           WHERE project = NEW.project AND ref = NEW.ref;
       END""",
    """CREATE TRIGGER IF NOT EXISTS a_moved_card_joins_the_bottom_of_its_column
       AFTER UPDATE OF column_key ON cards
       WHEN NEW.column_key IS NOT OLD.column_key
       BEGIN
           UPDATE cards SET position = (
               SELECT COALESCE(MAX(position), 0) + 1 FROM cards
               WHERE project = NEW.project AND column_key = NEW.column_key AND ref != NEW.ref)
           WHERE project = NEW.project AND ref = NEW.ref;
       END""",
)


class BoardLocked(sqlite3.OperationalError):
    """Another process held the board file past this module's stated bound — a wedged neighbour,
    not a busy one. An `OperationalError`, so every caller that already catches SQLite's errors
    handles it as it always did; the difference is the sentence, which names the file and what to
    do about it."""


def _refused(target: Path, waited: str) -> BoardLocked:
    return BoardLocked(
        f"The board file {target} stayed locked by another process for {waited}, so stop the "
        f"worker, panel or CLI command that is holding it and try again.")


def _locked(exc: sqlite3.OperationalError) -> bool:
    """SQLITE_BUSY, the one refusal a wait can cure; anything else is raised as it is."""
    return "database is locked" in str(exc)


def db_path(explicit: str | os.PathLike[str] | None = None) -> Path:
    """Where `board.db` is — the registry's own resolution, for the same reasons.

    An explicit path is never second-guessed (`namespace.operator_path` states the rule); then the
    deployment's variable; then the operator's own directory beside `registry.yaml`, which is where
    a host installation's `project init`, `act`, `run`, `poll` and `serve` all look."""
    if explicit:
        return Path(explicit)
    if named := os.environ.get(PATH_ENV, "").strip():
        return Path(named)
    from beeverforge import namespace

    return namespace.operator_path("board.db")


def now_iso() -> str:
    """`2026-09-09T12:34:56.789012+00:00` — the platform's timestamp, never SQLite's.

    NOT `CURRENT_TIMESTAMP`, and this is a correctness rule rather than a preference. SQLite writes
    `2026-09-09 12:34:56` — a SPACE, no offset — and the ADR-0048 sweep compares these as STRINGS
    (`knowledge/gather.py`) to decide whether a comment is newer than the question it answers.
    `'2026-09-09 12:35:00' <= '2026-09-09T12:30:00+00:00'` is true, because a space sorts below
    `T`, so an answer written five minutes AFTER the question would read as older than it and the
    person would be chased for an answer they had already given."""
    return datetime.now(UTC).isoformat()


@contextmanager
def connect(path: str | os.PathLike[str] | None = None,
            *, write: bool = False) -> Iterator[sqlite3.Connection]:
    """One connection, for one port call, with the discipline this file needs.

    ONE PER CALL rather than a pool or a module-level handle. A connection cached across calls is
    a connection held across a fork (the worker forks activities), across a request (the panel is
    async) and across a `docker compose exec` that has since exited — and SQLite's locking is
    per-connection, so a stale one is how the other two processes start seeing `database is
    locked` for a writer that went away.

    `write=True` opens the transaction with **BEGIN IMMEDIATE**, which is the whole reason this is
    a context manager. Two operations here READ A VALUE AND WRITE IT BACK — the next card number,
    and a column move that must not lose a concurrent one — and SQLite's default deferred
    transaction takes its write lock only at the first write, so two processes can both read `41`,
    both decide the next number is `42`, and the second one's INSERT fails or overwrites depending
    on the statement. `BEGIN IMMEDIATE` takes the lock at the top, so the second waits its
    `busy_timeout` and then reads `42`.

    The directory is created on demand: a host installation's `~/.beeverforge/` exists because the
    registry made it, but a deployment that names `BEEVERFORGE_BOARD_DB` somewhere else has no
    reason to have made it, and failing to open a database because its folder is missing is a
    remedy nobody can act on from the error sqlite3 gives."""
    target = Path(db_path(path))
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target, timeout=0, isolation_level=None)
    try:
        conn.row_factory = sqlite3.Row
        _open(conn, target)
        conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        if not write:
            yield conn
            return
        _begin(conn, target)
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")
    finally:
        conn.close()


def _open(conn: sqlite3.Connection, target: Path) -> None:
    """Put the file in WAL and give it the board's tables, asking again while another connection
    holds it — for `BUSY_TIMEOUT_MS` in all, then `BoardLocked`.

    THE WHOLE SEQUENCE, NOT THE CONVERSION ALONE (#166). Two connections opening a brand-new file
    race for it, and the WAL conversion was the step this module used to ask again, 40 times in
    0.4 s. Measured under load on 2026-11-02 (920 runs of the two-openers race on four CPUs beside
    the full suite, load average about 16), the one failure was NOT the conversion: it went
    through, and `CREATE TABLE IF NOT EXISTS cards` then lost the lock to the other opener after
    6.389 s. Every step here that finds something missing writes, so every step can lose, and the
    retry covers them all — conversion, schema, columns, triggers — under one bound.

    THE BUSY HANDLER IS OFF WHILE IT RUNS (`sqlite3.connect(timeout=0)` in `connect`). On a file
    still in the rollback journal SQLite sometimes refuses the conversion at once and sometimes
    waits out the WHOLE busy timeout for it (5.004 s measured) while this connection holds a
    shared lock the other opener needs to write its schema. Two openers each waiting for the
    other's lock is how one statement waited 6.389 s and still lost. With the handler off a
    refused statement holds nothing, the next pause is the loop's, and the total is the loop's
    deadline rather than the deadline times the statements in a try.

    MEASURED BEFORE, INCLUDING THE FIX THAT DOES NOT WORK: two threads opening a brand-new file
    failed 6/30 with an unconditional conversion and 6/40 with `busy_timeout` moved before it,
    and 0/60 once the conversion was asked again. Reordering is not a remedy. On an EXISTING
    file none of this arises — every step finds its table and writes nothing.

    RAISES WHEN THE BOUND RUNS OUT rather than degrading to a rollback journal or handing out a
    file without its tables: a file that is not in WAL would serialise the panel behind the
    worker, and the caller should hear that its database is wedged, in one sentence that names
    it."""
    # THE EXHAUSTION IS FALLING OUT OF THE LOOP, and a mutation is what taught that shape: written
    # as a give-up condition inside the `except`, the bound and the give-up are two expressions
    # that have to agree — cut one alone and the function returns NORMALLY over a file it never
    # prepared. Here the only way past the loop is the raise.
    deadline = time.monotonic() + BUSY_TIMEOUT_MS / 1000
    last: sqlite3.OperationalError | None = None
    while time.monotonic() < deadline:
        try:
            _prepare(conn)
            return
        except sqlite3.OperationalError as exc:
            if not _locked(exc):
                raise
            last = exc
        time.sleep(_OPEN_WAIT_S)
    log.warning("%s stayed locked through the whole opening wait (%d ms): %s",
                target, BUSY_TIMEOUT_MS, last)
    raise _refused(target, f"{BUSY_TIMEOUT_MS} ms while it was being opened") from last


def _prepare(conn: sqlite3.Connection) -> None:
    """One try of the opening sequence: WAL, then the schema, the columns and the triggers.

    Idempotent from any point it stopped at, which is what lets `_open` simply ask again: every
    statement is `IF NOT EXISTS`, the pragma is a no-op on a file in WAL, and `_add_columns` reads
    before it alters."""
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    for statement in _SCHEMA:
        conn.execute(statement)
    _add_columns(conn)
    for statement in _TRIGGERS:
        conn.execute(statement)


def _begin(conn: sqlite3.Connection, target: Path) -> None:
    """`BEGIN IMMEDIATE`, asked again when a full busy timeout went by without the lock (#199).

    A writer that loses one busy timeout under load has not met a wedged neighbour, only a slow
    one, and losing its card for it is the defect. So it asks `_BEGIN_TRIES` times in all, each a
    full `BUSY_TIMEOUT_MS`, and only then is refused — logged, and in one sentence. Nothing has
    been written when this runs, so asking again cannot write anything twice."""
    last: sqlite3.OperationalError | None = None
    for _ in range(_BEGIN_TRIES):
        try:
            conn.execute("BEGIN IMMEDIATE")
            return
        except sqlite3.OperationalError as exc:
            if not _locked(exc):
                raise
            last = exc
        time.sleep(_BEGIN_WAIT_S)
    log.warning("%s: no write lock after %d tries of %d ms each: %s",
                target, _BEGIN_TRIES, BUSY_TIMEOUT_MS, last)
    raise _refused(target, f"{_BEGIN_TRIES} tries of {BUSY_TIMEOUT_MS} ms") from last


def _add_columns(conn: sqlite3.Connection) -> None:
    """Give a file made before a column existed that column — once, and without losing a race.

    READ FIRST, ALTER ONLY WHAT IS MISSING. `PRAGMA table_info` is a read and costs nothing on
    the thousands of opens that find the column already there; an unconditional `ALTER` would
    take the write lock on every open just to be refused.

    A LOST RACE IS THE POST-CONDITION, NOT A FAILURE. Two processes opening the same old file —
    the worker and the panel right after an upgrade, which is the ordinary arrangement — both read
    the column as missing, both `ALTER`, and the second is told `duplicate column name`. What it
    wanted was the column, and the column is there, so it asks again instead of raising. Any other
    refusal leaves the column missing and raises: a file this module cannot write a pull request
    into must not be handed out as ready."""
    for table, column, declaration in _ADDED_COLUMNS:
        if column in _columns(conn, table):
            continue
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
        except sqlite3.OperationalError:
            if column not in _columns(conn, table):
                raise


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}

def next_pr(conn: sqlite3.Connection, project: str) -> int:
    """The next pull-request number for this project — the same rule and the same warning as
    `next_ref`: safe only inside the CALLER's `BEGIN IMMEDIATE` transaction.

    A SEPARATE SEQUENCE FROM THE CARDS'. On every hosted forge a pull request and an issue share
    a numbering space, and here they could have; they do not, because the two are addressed by
    different routes and a person reading `#3` on the board and `#3` on the pull-request page
    would be reading about two different things with no way to tell."""
    row = conn.execute("SELECT MAX(number) AS top FROM pull_requests WHERE project = ?",
                       (project,)).fetchone()
    return int(row["top"] or 0) + 1


def next_ref(conn: sqlite3.Connection, project: str) -> int:
    """The next card number for this project — read and written inside the CALLER's transaction.

    `MAX(ref) + 1` rather than an autoincrement column, because the number is per PROJECT and one
    file holds several. It is safe only under `BEGIN IMMEDIATE`, which is why this takes an open
    connection instead of opening its own: a helper that opened its own would take the lock, drop
    it, and hand the caller a number another process could already have used.

    A REMOVED CARD'S NUMBER COUNTS (#384). `MAX(ref)` over the cards alone handed the number of a
    card removed from the top of the board to the next card opened — and every comment, link or
    conversation that named `#7` would then point at somebody else's work. The audit table holds
    the numbers of the cards that are gone, so the highest of the two is where the sequence is."""
    row = conn.execute(
        "SELECT MAX(top) AS top FROM ("
        "  SELECT MAX(ref) AS top FROM cards WHERE project = ?"
        "  UNION ALL SELECT MAX(ref) AS top FROM removed_cards WHERE project = ?)",
        (project, project)).fetchone()
    return int(row["top"] or 0) + 1


def backup(to: str | os.PathLike[str], path: str | os.PathLike[str] | None = None) -> Path | None:
    """A consistent copy of the whole board at `to` through SQLite's online backup — or None when
    this machine holds no board file at all, which is nothing to copy rather than a failure. RAISES
    on anything else: a deletion stands on this copy (#453).

    THE BACKUP API, NOT A FILE COPY, for the reason `connect` is WAL: three processes write this
    file, the newest rows sit in `-wal` beside it, and a copy of the main file alone would miss
    exactly what was written last. And it never CREATES the file it was asked to copy — `connect`
    would, schema and all — so a deployment with no local board does not grow one by being backed
    up."""
    source = Path(db_path(path))
    if not source.is_file():
        return None
    target = Path(to)
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(source, timeout=BUSY_TIMEOUT_MS / 1000)
    try:
        copy = sqlite3.connect(target)
        try:
            conn.backup(copy)
        finally:
            copy.close()
    finally:
        conn.close()
    return target
