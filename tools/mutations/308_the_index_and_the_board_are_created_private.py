"""#308, proven by breaking it — the product index and the board are created `0600`, like #228's
metrics store, and an existing `0644` one is narrowed when it is opened.

The index holds client conversation text; the board holds cards, comments and registered accounts.
Left to `sqlite3.connect`, both took the process's umask (`0644` under `022`), and so did their
`-wal`/`-shm` and the board backup `project forget` takes.

THE CLAIMS:

  1. **A new index, a new board and a board backup are `0600` whatever the umask**, and so are
     their `-wal` and `-shm`.
  2. **An existing `0644` index or board, and an existing `0644` `-wal`, become `0600`** when the
     store is opened.
  3. **An index rebuilt from a corrupt file is `0600` too.**
  4. **A symbolic link at any of the three paths is refused by name**, never followed.

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
     TEST + "::test_an_existing_0644_board_and_its_wal_are_tightened_when_opened"),

    ("the narrowing finds a wide mode and does not change it", HELPER,
     "                os.fchmod(fd, mode & ~0o077)\n",
     "                pass\n"),

    ("the sidecars are not narrowed, only the main file", HELPER,
     '    for name in ("", *SIDECARS):\n',
     '    for name in ("",):\n',
     TEST + "::test_an_existing_0644_board_and_its_wal_are_tightened_when_opened"),

    ("no fchmod on creation: the umask still narrows the mode it is created with", HELPER,
     "        os.fchmod(fd, 0o600)\n",
     "        pass\n"),

    ("the existing file is never looked at: `tighten` is ignored", HELPER,
     "        if tighten:\n            _tighten(path, what)\n",
     ""),

    ("a symbolic link at the path is followed, not refused", HELPER,
     "        if path.is_symlink():\n",
     "        if False:\n"),
]
