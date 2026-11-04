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
from beeverforge.util.private_file import LinkedPath

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


def test_an_existing_0644_board_and_its_wal_are_tightened_when_opened(tmp_path):
    db = tmp_path / "board.db"
    wal = db.with_name("board.db-wal")
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
            assert wal.stat().st_size > 0
            db.chmod(0o644)
            wal.chmod(0o644)
            with board_db.connect(db) as conn:
                conn.execute("SELECT count(*) FROM cards").fetchone()
            assert _mode(db) == 0o600
            assert _mode(wal) == 0o600
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
