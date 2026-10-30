"""#228, proven by breaking it — the metrics store and its backup are created `0600`.

The store holds clients' messages and the audit trail. Left to `sqlite3.connect`, it took the
process's umask (`0644` under `022`), and so did every copy `forget` took of it.

THE CLAIMS:

  1. **A new store is `0600` whatever the umask**, made by a write or by the first read.
  2. **An existing store keeps its mode** — that is the operator's.
  3. **The copy `backup()` makes is `0600` too**, directly and through `project forget`.
  4. **A symbolic link at either path is refused by name**, never followed.

The guards are `tests/test_sqlite_metrics.py` and, for the forget path,
`tests/test_a_project_is_forgotten_in_one_command.py`.
"""

TEST = "tests/test_sqlite_metrics.py"

SINK = "beeverforge/observability/sqlite_metrics.py"

FORGET = "tests/test_a_project_is_forgotten_in_one_command.py"

MUTATIONS = [
    ("THE DEFECT ITSELF on a write: the store is created by sqlite under the umask", SINK,
     "        if write:\n            self.path.parent.mkdir(parents=True, exist_ok=True)\n"
     "            _create_private(self.path)\n",
     "        if write:\n            self.path.parent.mkdir(parents=True, exist_ok=True)\n"),

    ("a store first created by a read follows the umask", SINK,
     "                self.path.parent.mkdir(parents=True, exist_ok=True)\n"
     "                _create_private(self.path)\n",
     "                self.path.parent.mkdir(parents=True, exist_ok=True)\n"),

    ("no fchmod: the umask still narrows the mode it is created with", SINK,
     "        os.fchmod(fd, 0o600)\n",
     "        pass\n"),

    ("no O_EXCL skip: an existing store is opened and chmodded to 0600", SINK,
     "os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr",
     "os.O_WRONLY | os.O_CREAT | getattr"),

    ("THE GAP OF THE REVIEW: a backup is created by sqlite under the umask", SINK,
     '        _create_private(target, what="metrics backup",\n'
     '                        remedy="remove the link, or back up to another path")\n',
     ""),

    ("the backup forget takes is created by sqlite under the umask", SINK,
     '        _create_private(target, what="metrics backup",\n'
     '                        remedy="remove the link, or back up to another path")\n',
     "",
     FORGET + "::test_the_metrics_backup_forget_takes_is_private_whatever_the_umask"),

    ("a symbolic link at the path is followed, not refused", SINK,
     "        if path.is_symlink():\n",
     "        if False:\n"),
]
