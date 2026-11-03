"""#386, proven by breaking it — the host's push never reads git configuration a pass can write.

Run:  .venv/bin/python tools/mutate.py tools/mutations/386_the_hosts_push_never_reads_the_passs_config.py

THE CLAIMS, each held by a row:
  1. **Each box pushes from a repository the host makes for it**, never with the pass's repository
     (the worktree, or the container's bind-mounted host clone) as its git directory.
  2. **No git command starts in the pass's repository** (review of #403): the host's repository
     borrows the pass's objects through `objects/info/alternates` and takes the branch's commit
     from the ref read as data — a plain object name, from the loose ref or `packed-refs`, never
     through a symbolic ref, a symlink or a reftable, and from the git directory the box settled
     before the pass ran. An objects directory that borrows from another one (`info/alternates`,
     `info/http-alternates`, a symlinked `objects` or `objects/info`) is refused.
  3. **The forge door reads no user-level, system or ssh configuration** (review of #403): on the
     worktree box the pass runs as the worker's user and can write them.
  4. **The ambient door keeps the person's own configuration, in the workload's own environment**,
     with hooks off in the host's repository.
  5. **With no forge URL, the worktree box pushes to the origin it read before the pass ran**, a
     relative one resolved against the repository it belongs to, and refuses with a cause and a
     remedy when there is none.
  6. **The host's repository goes when the push is done**, and a failed step says which step
     failed and what to do.

The guard is real git: scratch bare repositories, a pass-written `insteadOf`, `pushInsteadOf`,
`core.sshCommand`, `core.fsmonitor` and `core.hooksPath` whose stand-ins only create a sentinel
file, `example.invalid` hosts, and git's own trace of the processes a push starts.
"""

TEST = "tests/test_a_pass_written_git_config_never_steers_the_hosts_push.py"

BOX = "beeverforge/adapters/sandbox/worktree.py"
CONTAINER = "beeverforge/adapters/sandbox/container.py"
PUSH = "beeverforge/adapters/sandbox/host_push.py"

MUTATIONS = [
    # ── 1. the push runs from the host's own repository ────────────────────────────────────────
    ("the worktree box pushes from the job's worktree again, reading the pass's config", BOX,
     "        push_from_the_hosts_own_repository(\n"
     "            git_dir=self._git_dir, branch=workspace.branch, target=target, run=_run,\n"
     "            redact=_redact, ambient_env=None if remote_url else "
     "_scrubbed_env(self.extra_env))\n",
     "        rc, out = _run(gitpin.argv([\"-C\", str(workspace.path), \"push\", \"--force\", "
     "\"--\", target,\n"
     "                                    workspace.branch]))\n"
     "        if rc != 0:\n"
     "            raise RuntimeError(f\"push failed: {_redact(out)}\")\n"),

    ("the container box pushes from the bind-mounted host clone again, reading the job's config",
     CONTAINER,
     "        push_from_the_hosts_own_repository(\n"
     "            git_dir=git_dir, branch=workspace.branch, target=target, run=_host, "
     "redact=_redact,\n"
     "            ambient_env=None if remote_url else dict(os.environ))\n",
     "        rc, out = _host(gitpin.argv([\"-C\", str(self._host_clone), \"push\", \"--force\", "
     "\"--\",\n"
     "                                     target, workspace.branch]))\n"
     "        if rc != 0:\n"
     "            raise RuntimeError(f\"push failed: {_redact(out)}\")\n"),

    ("the helper pushes with the pass's git directory as its own", PUSH,
     '[*_HOOKLESS, "-C", str(own), "push",', '[*_HOOKLESS, "-C", str(git_dir), "push",'),

    # ── 2. no git command in the pass's repository ─────────────────────────────────────────────
    ("the host's repository fetches the branch out of the pass's again, running its serving side "
     "there", PUSH,
     '[*_HOOKLESS, "-C", str(own), "update-ref", ref, commit]',
     '[*_HOOKLESS, "-C", str(own), "fetch", "--no-tags", "--", str(git_dir), f"+{ref}:{ref}"]'),

    ("the host's repository never borrows the pass's objects, so it holds no commit to push",
     PUSH,
     "        (own / \"objects\" / \"info\" / \"alternates\").write_text(f\"{git_dir / "
     "'objects'}\\n\")\n",
     "        pass\n"),

    ("a job-written alternates chain is followed, so the push sends another repository's objects",
     PUSH, "    _borrows_nothing(git_dir)\n", ""),

    ("a symlinked `objects` or `objects/info` is followed to wherever it points", PUSH,
     "        if path.is_symlink():\n", "        if False:\n"),

    ("whatever the ref file holds is taken as the commit, a symbolic ref or a word included",
     PUSH,
     "    if _OBJECT_NAME.fullmatch(name):\n        return name\n",
     "    return name\n"),

    ("a ref that is a symlink is followed to wherever it points", PUSH,
     "os.O_RDONLY | os.O_NOFOLLOW", "os.O_RDONLY"),

    ("a repository keeping its refs in a reftable is read as if they were loose files", PUSH,
     '    if (git_dir / "reftable").exists():\n',
     "    if False:\n"),

    ("a branch held only in packed-refs is never found", PUSH,
     '    packed = _read_as_data(git_dir / "packed-refs", ref="packed-refs", git_dir=git_dir) '
     'or ""\n',
     '    packed = ""\n'),

    ("a SHA-256 repository fails in git's words, with no cause named and no remedy", PUSH,
     "    if _OBJECT_NAME.fullmatch(name) and len(name) == 64:\n",
     "    if False:\n"),

    ("a branch naming an object the pass's repository lacks fails with no step and no remedy",
     PUSH,
     "            raise RuntimeError(\n"
     "                f\"push failed: could not bring {branch!r}'s commits out of the job's "
     "repository \"\n"
     "                f\"{git_dir}: its branch names",
     "            raise RuntimeError(f\"push failed: {redact(out)}\")\n"
     "            raise RuntimeError(\n"
     "                f\"push failed: could not bring {branch!r}'s commits out of the job's "
     "repository \"\n"
     "                f\"{git_dir}: its branch names"),

    ("the worktree box asks the worktree for its git directory at push time, after the pass "
     "could repoint it", BOX,
     "git_dir=self._git_dir, branch=workspace.branch,",
     "git_dir=_common_dir(workspace.path), branch=workspace.branch,"),

    ("a worktree box whose git directory could not be read at prepare pushes with none", BOX,
     "        if self._git_dir is None:\n", "        if False:\n"),

    ("the container box reads whatever the clone's `.git` now names", CONTAINER,
     "        if git_dir.is_symlink() or not git_dir.is_dir():\n",
     "        if False:\n"),

    # ── 3. the forge door reads no configuration the pass can write ────────────────────────────
    ("the forge door runs in the host's whole environment, reading every config again", PUSH,
     "else _own_configuration_only(scratch)", "else None"),

    ("the forge door reads the user-level git config again", PUSH,
     '        "GIT_CONFIG_GLOBAL": os.devnull,\n'
     '        "HOME": str(home),\n'
     '        "XDG_CONFIG_HOME": str(home / ".config"),\n',
     ""),

    ("the forge door reads the system git config again", PUSH,
     '        "GIT_CONFIG_NOSYSTEM": "1",\n', ""),

    ("the forge door's ssh reads the user's ssh config again", PUSH,
     '"GIT_SSH_COMMAND": "ssh -F /dev/null"', '"GIT_SSH_COMMAND": "ssh"'),

    # ── 4. the ambient door ────────────────────────────────────────────────────────────────────
    ("the worktree box's ambient door runs in the worker's whole environment", BOX,
     "else _scrubbed_env(self.extra_env))", "else dict(os.environ))"),

    ("the ambient door drops the person's own configuration, where their credential lives", BOX,
     "ambient_env=None if remote_url else _scrubbed_env(self.extra_env))",
     "ambient_env=None)"),

    ("hooks are on in the host's repository, so a hooks path the user config names runs", PUSH,
     '_HOOKLESS = ("-c", "core.hooksPath=/dev/null")', "_HOOKLESS = ()"),

    # ── 5. the ambient origin ──────────────────────────────────────────────────────────────────
    ("the ambient door reads `origin` from the workspace at push time, after the pass wrote it",
     BOX,
     "        target = remote_url or self._origin\n",
     "        target = remote_url or _origin_of(workspace.path)\n"),

    ("a relative origin is pushed to as written, from a directory it is not relative to", BOX,
     "    return os.path.normpath(os.path.join(str(repo_path), url))\n",
     "    return url\n"),

    ("a repository with no origin and no forge URL fails in git's words, with no remedy", BOX,
     "        target = remote_url or self._origin\n        if not target:\n",
     "        target = remote_url or self._origin or \"origin\"\n        if not target:\n"),

    # ── 6. nothing left behind, and the step named ─────────────────────────────────────────────
    ("the host's repository is left in the temporary directory after every push", PUSH,
     "        shutil.rmtree(scratch, ignore_errors=True)\n", "        pass\n"),

    ("a branch the pass's repository no longer has reads with no step and no remedy", PUSH,
     "    raise RuntimeError(\n"
     "        f\"push failed: could not bring {branch!r}'s commits out of the job's repository \"\n"
     "        f\"{git_dir}: it has no such branch",
     "    raise RuntimeError(\"push failed\")\n"
     "    raise RuntimeError(\n"
     "        f\"push failed: could not bring {branch!r}'s commits out of the job's repository \"\n"
     "        f\"{git_dir}: it has no such branch"),
]
