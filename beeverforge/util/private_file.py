"""A SQLite file created readable by its owner only, whatever the umask (#228, #308).

THREE STORES HOLD WHAT OTHER USERS ON THE MACHINE MUST NOT READ: the metrics store (clients'
messages and the audit trail), the product index (client conversation text) and the board (cards,
comments and registered accounts). Left to `sqlite3.connect`, each took the process's umask —
`0644` under the usual `022` — and so did every backup copy of them. #228 fixed the metrics store;
this is its helper, moved here so the index and the board use the same lines (#308).

SQLITE GIVES `-wal`, `-shm` AND `-journal` THE MAIN FILE'S MODE, so a main file that is `0600`
before the first connect is enough for the files SQLite makes beside it.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

#: The files SQLite keeps beside a database, which take its mode when it makes them.
SIDECARS = ("-wal", "-shm", "-journal")


class LinkedPath(Exception):
    """A symbolic link where a private store or its backup is to be created (#228) — refused, not
    followed. Not an `OSError`, so a read's "could not create it" logging does not swallow it."""


def create_private(path: Path, *, what: str, remedy: str, tighten: bool = False) -> None:
    """Create `path`, mode `0600`, if it is missing (#228); with `tighten`, narrow an existing one.

    It is created here first, exclusively, and `fchmod`ed so no umask can widen or narrow it;
    SQLite then opens a private file, and gives its `-wal` and `-shm` files the same mode. At no
    moment does the file exist with a wider mode: `os.open` makes it with `0600` masked by the
    umask, which can only narrow it.

    `O_EXCL` is what leaves an existing file alone when `tighten` is off: the metrics store's mode
    is the operator's, not ours. With `tighten` (the index and the board, #308), an existing file
    and each sidecar beside it lose their group and other bits — a `0644` left by an older release
    becomes `0600`. A file this process may not chmod (another user's) is logged, not raised: the
    open goes on, as it did before.

    A SYMBOLIC LINK AT THE PATH IS REFUSED, dangling or not, with `LinkedPath`. `O_EXCL` fails on
    a link without following it, but `sqlite3.connect` would then follow it — to a file made under
    the umask, wherever the link points. What this does not close: a link planted between this
    check and SQLite's own open, by somebody who can already write the store's directory."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError:
        if path.is_symlink():
            raise LinkedPath(f"the {what} at {path} is a symbolic link, which is refused rather "
                             f"than followed — {remedy}") from None
        if tighten:
            _tighten(path, what)
        return
    try:
        os.fchmod(fd, 0o600)
    finally:
        os.close(fd)


def _tighten(path: Path, what: str) -> None:
    """Clear the group and other bits of `path` and of each sidecar beside it that exists.

    Opened without `O_CREAT` and read-only, so a file in a read-only directory, or one this
    process may only read, is still checked; and with `O_NOFOLLOW`, so a link is never chmodded
    through."""
    for name in ("", *SIDECARS):
        _narrow(Path(f"{path}{name}"), what)


def _narrow(path: Path, what: str) -> None:
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return
    except OSError as exc:
        log.warning("the %s file %s could not be opened to make it private — %s", what, path, exc)
        return
    try:
        mode = os.fstat(fd).st_mode & 0o7777
        if mode & 0o077:
            try:
                os.fchmod(fd, mode & ~0o077)
            except PermissionError as exc:
                log.warning("the %s file %s stays mode %o: it could not be made private — %s",
                            what, path, mode, exc)
    finally:
        os.close(fd)
