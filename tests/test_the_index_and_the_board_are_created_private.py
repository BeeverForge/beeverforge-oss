"""#308: the product index and the board are created owner-only, like the metrics store (#228).

The product index (`<product_state_dir>/index/memory.sqlite`) holds client conversation text; the
board (`board.db`) holds cards, comments and registered accounts. Both were created by
`sqlite3.connect` under the process's umask — `0644` under the usual `022`, readable by every user
on the machine — and so were their `-wal`/`-shm` files and the board backup `project forget` takes.

Every test sets its umask and restores it in `finally`, opens the store through its real code path,
and reads the mode on disk. The last connection to close removes `-wal` and `-shm`, so a second
connection is held open while they are read.
"""

from __future__ import annotations

import os
import sqlite3
import stat
from pathlib import Path

import pytest

from beeverforge.adapters import board_db
from beeverforge.product.index.store import Index
from beeverforge.util.private_file import SIDECARS, LinkedPath, NotRegularFile, create_private

UMASKS = pytest.mark.parametrize("umask", [0o000, 0o022, 0o277], ids=["000", "022", "277"])

KEY = "someone-product"


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _modes_with_sidecars(db: Path) -> dict[str, int]:
    """The mode of `db` and of its `-wal` and `-shm`, each of which must exist."""
    found = {}
    for path in (db, db.with_name(db.name + "-wal"), db.with_name(db.name + "-shm")):
        assert path.exists(), path.name
        found[path.name] = _mode(path)
    return found


def _private(db: Path) -> dict[str, int]:
    return {db.name: 0o600, db.name + "-wal": 0o600, db.name + "-shm": 0o600}


# ── the product index ────────────────────────────────────────────────────────────────────────


@UMASKS
def test_a_new_index_and_its_sidecars_are_private_whatever_the_umask(tmp_path, umask):
    db = tmp_path / "index" / "memory.sqlite"
    db.parent.mkdir()   # before the umask: a directory made under 0o277 cannot be written
    index = Index(KEY, path=db)
    old = os.umask(umask)
    try:
        with index.open():
            pass
        held = sqlite3.connect(db)
        try:
            held.execute("SELECT count(*) FROM meta").fetchone()
            with index.open() as con, con:
                Index.set_meta(con, "someone", "was here")
            assert _modes_with_sidecars(db) == _private(db)
        finally:
            held.close()
    finally:
        os.umask(old)
    with index.open() as con:   # still readable and writable, even under umask 0o277
        assert Index.meta(con, "someone") == "was here"


def test_an_existing_0644_index_is_tightened_when_opened(tmp_path):
    db = tmp_path / "index" / "memory.sqlite"
    db.parent.mkdir()
    old = os.umask(0o022)
    try:
        sqlite3.connect(db).close()
        db.chmod(0o644)
        with Index(KEY, path=db).open() as con:
            assert Index.meta(con, "product") == KEY
    finally:
        os.umask(old)
    assert _mode(db) == 0o600


def test_an_index_rebuilt_from_a_corrupt_file_is_private(tmp_path):
    db = tmp_path / "index" / "memory.sqlite"
    db.parent.mkdir()
    old = os.umask(0o022)
    try:
        db.write_bytes(b"this is not a database")
        db.chmod(0o644)
        with Index(KEY, path=db).open() as con:
            assert Index.meta(con, "product") == KEY
    finally:
        os.umask(old)
    assert _mode(db) == 0o600


def test_a_link_at_the_index_s_path_is_refused_by_name_and_nothing_is_made(tmp_path):
    db, elsewhere = tmp_path / "index" / "memory.sqlite", tmp_path / "elsewhere.sqlite"
    db.parent.mkdir()
    db.symlink_to(elsewhere)
    with pytest.raises(LinkedPath) as refused, Index(KEY, path=db).open():
        pass
    assert f"{db} is a symbolic link" in str(refused.value)
    assert not elsewhere.exists(), "the link was followed"


# ── the board ────────────────────────────────────────────────────────────────────────────────


@UMASKS
def test_a_new_board_and_its_sidecars_are_private_whatever_the_umask(tmp_path, umask):
    db = tmp_path / "board.db"
    old = os.umask(umask)
    try:
        with board_db.connect(db, write=True):
            pass
        held = sqlite3.connect(db)
        try:
            held.execute("SELECT count(*) FROM cards").fetchone()
            with board_db.connect(db, write=True) as conn:
                conn.execute("SELECT count(*) FROM cards").fetchone()
            assert _modes_with_sidecars(db) == _private(db)
        finally:
            held.close()
    finally:
        os.umask(old)
    with board_db.connect(db) as conn:   # still readable, even under umask 0o277
        assert conn.execute("SELECT count(*) FROM cards").fetchone()[0] == 0


def test_an_existing_0644_board_and_its_wal_and_shm_are_tightened_when_opened(tmp_path):
    db = tmp_path / "board.db"
    wal, shm = db.with_name("board.db-wal"), db.with_name("board.db-shm")
    old = os.umask(0o022)
    try:
        with board_db.connect(db, write=True):
            pass
        held = sqlite3.connect(db)
        try:
            # Frames in the `-wal`, so it is not empty: SQLite re-modes an EMPTY sidecar it opens
            # by itself, and only a `-wal` with content shows whether the open narrows it.
            held.execute("CREATE TABLE someone (x)")
            held.commit()
            # The `-shm` holds the wal-index of those frames, so it is not empty either.
            assert wal.stat().st_size > 0 and shm.stat().st_size > 0
            for path in (db, wal, shm):
                path.chmod(0o644)
            with board_db.connect(db) as conn:
                conn.execute("SELECT count(*) FROM cards").fetchone()
            assert {p.name: _mode(p) for p in (db, wal, shm)} == _private(db)
        finally:
            held.close()
    finally:
        os.umask(old)


def test_an_existing_0644_journal_beside_a_board_backup_is_tightened(tmp_path):
    """The board backup's copy is written under SQLite's default `journal_mode=DELETE` — a fresh
    file's — so the sidecar beside it while it is written is a `-journal`, and a copy cut short
    leaves one. The finished copy carries the board's WAL header, so the test puts it back in
    DELETE; a connection held inside a write transaction keeps the journal on disk with the
    original page in it. The helper is called as `board_db.backup` calls it, because the backup
    itself would wait on that held lock."""
    db, copy = tmp_path / "board.db", tmp_path / "copy.db"
    journal = copy.with_name("copy.db-journal")
    with board_db.connect(db, write=True):
        pass
    old = os.umask(0o022)
    try:
        assert board_db.backup(copy, db) == copy
        held = sqlite3.connect(copy, isolation_level=None)
        try:
            assert held.execute("PRAGMA journal_mode=DELETE").fetchone()[0] == "delete"
            held.execute("BEGIN IMMEDIATE")
            held.execute("CREATE TABLE someone (x)")
            assert journal.stat().st_size > 0
            copy.chmod(0o644)
            journal.chmod(0o644)
            create_private(copy, what="board backup",
                           remedy="remove the link, or back up to another path", tighten=True)
            assert {p.name: _mode(p) for p in (copy, journal)} == {
                "copy.db": 0o600, "copy.db-journal": 0o600}
            held.execute("ROLLBACK")
        finally:
            held.close()
    finally:
        os.umask(old)


@UMASKS
def test_the_board_backup_and_its_sidecars_are_private(tmp_path, umask):
    db, copy = tmp_path / "board.db", tmp_path / "copy.db"
    with board_db.connect(db, write=True):
        pass
    old = os.umask(umask)
    try:
        assert board_db.backup(copy, db) == copy
        assert _mode(copy) == 0o600
        held = sqlite3.connect(copy)
        try:
            held.execute("SELECT count(*) FROM cards").fetchone()
            with board_db.connect(copy, write=True) as conn:
                conn.execute("SELECT count(*) FROM cards").fetchone()
            assert _modes_with_sidecars(copy) == _private(copy)
        finally:
            held.close()
    finally:
        os.umask(old)


def test_a_backup_of_no_board_creates_nothing(tmp_path):
    copy = tmp_path / "copy.db"
    assert board_db.backup(copy, tmp_path / "board.db") is None
    assert not copy.exists()
    assert not (tmp_path / "board.db").exists()


def test_a_link_at_the_board_s_path_is_refused_by_name_and_nothing_is_made(tmp_path):
    db, elsewhere = tmp_path / "board.db", tmp_path / "elsewhere.db"
    db.symlink_to(elsewhere)
    with pytest.raises(LinkedPath) as refused, board_db.connect(db, write=True):
        pass
    said = str(refused.value)
    assert f"{db} is a symbolic link" in said and "BEEVERFORGE_BOARD_DB" in said, said
    assert not elsewhere.exists(), "the link was followed"


def test_a_link_at_the_board_backup_s_path_is_refused_by_name(tmp_path):
    db, copy, elsewhere = tmp_path / "board.db", tmp_path / "copy.db", tmp_path / "elsewhere.db"
    with board_db.connect(db, write=True):
        pass
    copy.symlink_to(elsewhere)
    with pytest.raises(LinkedPath) as refused:
        board_db.backup(copy, db)
    assert f"{copy} is a symbolic link" in str(refused.value)
    assert not elsewhere.exists(), "the link was followed"


@pytest.mark.parametrize("sidecar", SIDECARS)
def test_a_link_at_a_sidecar_s_path_is_refused_by_name_and_its_target_is_untouched(tmp_path,
                                                                                    sidecar):
    db, elsewhere = tmp_path / "board.db", tmp_path / "elsewhere"
    with board_db.connect(db, write=True):
        pass
    old = os.umask(0o022)
    try:
        elsewhere.write_bytes(b"someone's file")
        elsewhere.chmod(0o644)
        link = Path(f"{db}{sidecar}")
        link.symlink_to(elsewhere)
        with pytest.raises(LinkedPath) as refused, board_db.connect(db):
            pass
    finally:
        os.umask(old)
    said = str(refused.value)
    assert f"{link} is a symbolic link" in said and "BEEVERFORGE_BOARD_DB" in said, said
    assert link.is_symlink(), "the link was replaced"
    assert _mode(elsewhere) == 0o644, "the link was followed and its target chmodded"
    assert elsewhere.read_bytes() == b"someone's file", "the link was followed and written"


@pytest.mark.parametrize("name", ["", "-journal"], ids=["main", "journal"])
def test_a_fifo_at_the_board_or_its_journal_is_refused_by_name(tmp_path, name):
    """A FIFO, like any file that is not a regular one, is refused before SQLite opens the store.

    The test holds the FIFO open for reading and writing itself, so no other open of it waits for
    a partner — not the check's, and not SQLite's when the check is cut away — and the test fails
    rather than blocks whatever code it runs against. That the check opens it without blocking
    even with nobody holding it is the `O_NONBLOCK` in `_narrow`."""
    db = tmp_path / "board.db"
    if name:
        with board_db.connect(db, write=True):
            pass
    special = Path(f"{db}{name}")
    old = os.umask(0o022)
    try:
        os.mkfifo(special)
        both_ends = os.open(special, os.O_RDWR | os.O_NONBLOCK)
        try:
            with pytest.raises(NotRegularFile) as refused, board_db.connect(db):
                pass
        finally:
            os.close(both_ends)
    finally:
        os.umask(old)
    assert f"{special} is not a regular file" in str(refused.value), str(refused.value)
    assert stat.S_ISFIFO(special.lstat().st_mode), "the FIFO was replaced"
