"""#308, proven by breaking it — the product index and the board are created `0600`, like #228's
metrics store, and an existing `0644` one is narrowed when it is opened.

The index holds client conversation text; the board holds cards, comments and registered accounts.
Left to `sqlite3.connect`, both took the process's umask (`0644` under `022`), and so did their
`-wal`/`-shm` and the board backup `project forget` takes.

THE CLAIMS:

  1. **A new index, a new board and a board backup are `0600` whatever the umask**, and so are
     their `-wal` and `-shm`.
  2. **An existing `0644` index or board, and an existing `0644` `-wal`, `-shm` or `-journal`
     (the board backup's copy is written under `journal_mode=DELETE`), become `0600`** when the
     store is opened.
  3. **An index rebuilt from a corrupt file is `0600` too.**
  4. **A symbolic link at any of the three paths is refused by name**, never followed.
  5. **A symbolic link at a sidecar's path is refused by name too** (review of #432), and its
     target keeps its mode and its content.
  6. **A file that is not regular — a FIFO — at the store's path or a sidecar's is refused by
     name**, opened without blocking (review of #432).

Not a row: dropping `O_NONBLOCK`. The cut is real, but its only witness is a test that blocks
forever, and a row that hangs the runner proves nothing; it was shown red by hand, under the shell
`timeout`, against the code before the fix.

The guard is `tests/test_the_index_and_the_board_are_created_private.py`; #228's own plan still
guards the metrics store through the same helper.
"""

TEST = "tests/test_the_index_and_the_board_are_created_private.py"

HELPER = "beeverforge/util/private_file.py"

STORE = "beeverforge/product/index/store.py"

BOARD = "beeverforge/adapters/board_db.py"

MUTATIONS = [
    ("THE DEFECT ITSELF for the index: it is created by sqlite under the umask", STORE,
     '        create_private(self.path, what="product index", remedy=_LINK_REMEDY, tighten=True)\n',
     ""),

    ("THE DEFECT ITSELF for the board: it is created by sqlite under the umask", BOARD,
     '    create_private(target, what="board", remedy=_LINK_REMEDY, tighten=True)\n',
     ""),

    ("the board backup is created by sqlite under the umask", BOARD,
     '    create_private(target, what="board backup",\n'
     '                   remedy="remove the link, or back up to another path", tighten=True)\n',
     ""),

    ("an existing 0644 index is left as it is", STORE,
     'remedy=_LINK_REMEDY, tighten=True)\n        con = sqlite3.connect',
     'remedy=_LINK_REMEDY, tighten=False)\n        con = sqlite3.connect',
     TEST + "::test_an_existing_0644_index_is_tightened_when_opened"),

    ("an existing 0644 board is left as it is", BOARD,
     'create_private(target, what="board", remedy=_LINK_REMEDY, tighten=True)',
     'create_private(target, what="board", remedy=_LINK_REMEDY, tighten=False)',
     TEST + "::test_an_existing_0644_board_and_its_wal_and_shm_are_tightened_when_opened"),

    ("the narrowing finds a wide mode and does not change it", HELPER,
     "                os.fchmod(fd, mode & ~0o077)\n",
     "                pass\n"),

    ("the sidecars are not narrowed, only the main file", HELPER,
     '    for name in ("", *SIDECARS):\n',
     '    for name in ("",):\n',
     TEST + "::test_an_existing_0644_board_and_its_wal_and_shm_are_tightened_when_opened"),

    ("no fchmod on creation: the umask still narrows the mode it is created with", HELPER,
     "        os.fchmod(fd, 0o600)\n",
     "        pass\n"),

    ("the existing file is never looked at: `tighten` is ignored", HELPER,
     "        if tighten:\n            _tighten(path, what, remedy)\n",
     ""),

    # RETIRED 2026-11-04: "a symbolic link at the path is followed, not refused" (cutting
    # `if path.is_symlink():`). Since the review of #432, `_narrow` opens the main path with
    # `O_NOFOLLOW` too, so for the three stores this plan covers — all `tighten=True` — a link at
    # the main path is refused by two lines, and cutting either alone still raises `LinkedPath`
    # naming the path (the row ran 22 passed). The `is_symlink` line is still proved where it is
    # the only one: #228's identical row, against the metrics store, which does not tighten. The
    # `ELOOP` line is proved by the "a link at a sidecar is logged" row below.

    ("the `-shm` is not narrowed: it is left out of the sidecars", HELPER,
     'SIDECARS = ("-wal", "-shm", "-journal")',
     'SIDECARS = ("-wal", "-journal")',
     TEST + "::test_an_existing_0644_board_and_its_wal_and_shm_are_tightened_when_opened"),

    ("the `-journal` is not narrowed: it is left out of the sidecars", HELPER,
     'SIDECARS = ("-wal", "-shm", "-journal")',
     'SIDECARS = ("-wal", "-shm")',
     TEST + "::test_an_existing_0644_journal_beside_a_board_backup_is_tightened"),

    ("the narrowing opens with no O_NOFOLLOW: a link at a sidecar is chmodded through", HELPER,
     '    flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)\n',
     "    flags = os.O_RDONLY | os.O_NONBLOCK\n",
     TEST + "::test_a_link_at_a_sidecar_s_path_is_refused_by_name_and_its_target_is_untouched"),

    ("a link at a sidecar is logged and the open goes on, as before the review", HELPER,
     "        if exc.errno == errno.ELOOP:",
     "        if False:",
     TEST + "::test_a_link_at_a_sidecar_s_path_is_refused_by_name_and_its_target_is_untouched"),

    ("a file that is not regular is narrowed and opened like a regular one", HELPER,
     "        if not stat.S_ISREG(found):\n",
     "        if False:\n",
     TEST + "::test_a_fifo_at_the_board_or_its_journal_is_refused_by_name"),
]
