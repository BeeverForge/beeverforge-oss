"""#121: the installer's guards can be run on the machine a maintainer is sitting at.

Two independent portability defects lived in one file and the first hid the second. The rows below
restore each, and the reverses check that the guards measure BEHAVIOUR rather than the spelling
that happens to fix it today.
"""

TEST = "tests/test_the_suite_runs_where_a_maintainer_sits.py"
SRC = "tests/test_the_installer_builds_the_commands_it_says_it_does.py"
#: #336: the "no test errors" run and the "no directory left" run became ONE child run of SRC, so
#: the rows those two guards turned red are aimed at the one node that now asks both.
RUN = f"{TEST}::test_the_file_runs_without_an_error_and_leaves_no_directory_behind"

MUTATIONS = [
    # RETIRED 2026-09-14: THE CUT WAS AIMED WRONG, the second of the three meanings a survivor
    # can have. Plain `tempfile.mkdtemp()` measures 72 bytes on macOS and BINDS FINE — the
    # problem was never TMPDIR, it was the `pytest-of-<user>/pytest-<N>/<test name>/` segments
    # pytest appends on top of it. So that cut is a legitimate alternative fix rather than a
    # regression, and a guard going red on it would be enforcing a spelling. `dir="/tmp"` is
    # kept because it is short by definition, where TMPDIR is only short by habit.

    # RE-PINNED (#423): the helper's parent became `SOCKET_ROOT_ENV` or `/tmp`, so the leak guard
    # can count in a directory no parallel worker shares. The cut is the same: a 90-byte prefix.
    ("…and the reverse: a long directory is accepted as long as it is not pytest's", SRC,
     '    return pathlib.Path(tempfile.mkdtemp(prefix="ofsock", '
     'dir=os.environ.get(SOCKET_ROOT_ENV,',
     '    return pathlib.Path(tempfile.mkdtemp(prefix="a" * 90, '
     'dir=os.environ.get(SOCKET_ROOT_ENV,', RUN),

    ("the module fixture binds under tmp_path again", SRC,
     '    socket_home = _socket_dir()\n    socket_path = socket_home / "docker.sock"'
     '\n    import socket as socketlib',
     '    socket_home = _socket_dir()\n    socket_path = home / "docker.sock"'
     '\n    import socket as socketlib', RUN),

    ("the fixture stops releasing its directory, as it never did until #128's review", SRC,
     "\n    shutil.rmtree(socket_home, ignore_errors=True)\n",
     "\n", RUN),

    # #336: THE OTHER CALLERS release theirs too, and the merged run has to see each one. This is
    # the helper most of the file's tests reach through, and it is not a fixture, so it is the
    # cut the module fixture's row cannot stand in for.
    ("the installer helper stops releasing its directory", SRC,
     "        shutil.rmtree(socket_home, ignore_errors=True)\n    return done, house",
     "        pass\n    return done, house", RUN),

    # #336: AND THE PARENT HAS TO REACH THE CHILD. Under a `BEEVERFORGE_*` name the child's
    # conftest stripped it, the sockets went to `/tmp`, and the row above survived on main.
    ("the private parent goes back under a name the child's conftest strips", SRC,
     'SOCKET_ROOT_ENV = "TEST_SOCKET_ROOT"',
     'SOCKET_ROOT_ENV = "BEEVERFORGE_TEST_SOCKET_ROOT"', RUN),

    ("the curl stub rewrites the checksums with GNU's spelling of sed", SRC,
     "    && sed 's| \\\\./| |' SHA256SUMS > SHA256SUMS.rewritten && mv SHA256SUMS.rewritten SHA256SUMS ) ;;",
     "    && sed -i 's| \\\\./| |' SHA256SUMS ) ;;"),

    ("…and the reverse: the rewrite stops happening at all, so the names keep their `./`", SRC,
     "    && sed 's| \\\\./| |' SHA256SUMS > SHA256SUMS.rewritten && mv SHA256SUMS.rewritten SHA256SUMS ) ;;",
     "    ) ;;"),
]
