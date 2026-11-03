"""#386, proven by breaking it — the host's push never reads git configuration a pass can write.

Run:  .venv/bin/python tools/mutate.py tools/mutations/386_the_hosts_push_never_reads_the_passs_config.py

THE CLAIMS, each held by a row:
  1. **Each box pushes from a repository the host makes for it**, never with the pass's repository
     (the worktree, or the container's bind-mounted host clone) as its git directory.
  2. **The pass's commits come in as objects**: a fetch into the host's own repository, which the
     push then sends, never the pass's repository pushing for itself.
  3. **With no forge URL, the worktree box pushes to the origin it read before the pass ran**, a
     relative one resolved against the repository it belongs to, and refuses with a cause and a
     remedy when there is none.
  4. **The host's repository goes when the push is done**, and a failed fetch says which step
     failed and what to do.

The guard is real git: scratch bare repositories, a pass-written `insteadOf`, `pushInsteadOf`,
`core.sshCommand` and `core.fsmonitor` whose stand-ins only create a sentinel file.
"""

TEST = "tests/test_a_pass_written_git_config_never_steers_the_hosts_push.py"

BOX = "beeverforge/adapters/sandbox/worktree.py"
CONTAINER = "beeverforge/adapters/sandbox/container.py"
PUSH = "beeverforge/adapters/sandbox/host_push.py"

MUTATIONS = [
    # ── 1. the push runs from the host's own repository ────────────────────────────────────────
    ("the worktree box pushes from the job's worktree again, reading the pass's config", BOX,
     "        push_from_the_hosts_own_repository(source=Path(workspace.path), "
     "branch=workspace.branch,\n"
     "                                           target=target, run=_run, redact=_redact)\n",
     "        rc, out = _run(gitpin.argv([\"-C\", str(workspace.path), \"push\", \"--force\", "
     "\"--\", target,\n"
     "                                    workspace.branch]))\n"
     "        if rc != 0:\n"
     "            raise RuntimeError(f\"push failed: {_redact(out)}\")\n"),

    ("the container box pushes from the bind-mounted host clone again, reading the job's config",
     CONTAINER,
     "        push_from_the_hosts_own_repository(source=self._host_clone, "
     "branch=workspace.branch,\n"
     "                                           target=target, run=_host, redact=_redact)\n",
     "        rc, out = _host(gitpin.argv([\"-C\", str(self._host_clone), \"push\", \"--force\", "
     "\"--\",\n"
     "                                     target, workspace.branch]))\n"
     "        if rc != 0:\n"
     "            raise RuntimeError(f\"push failed: {_redact(out)}\")\n"),

    ("the helper pushes with the pass's repository as its git directory", PUSH,
     '"-C", str(own), "push",', '"-C", str(source), "push",'),

    # ── 2. the commits come in as objects ──────────────────────────────────────────────────────
    ("the host's repository never fetches the pass's commits, so it has nothing to push", PUSH,
     '"-C", str(own), "fetch",\n                                   "--no-tags", "--", str(source), '
     'f"+{ref}:{ref}"]),',
     '"-C", str(own), "ls-remote",\n                                   "--", str(source)]),'),

    # ── 3. the ambient origin ──────────────────────────────────────────────────────────────────
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

    # ── 4. nothing left behind, and the step named ─────────────────────────────────────────────
    ("the host's repository is left in the temporary directory after every push", PUSH,
     "        shutil.rmtree(own, ignore_errors=True)\n", "        pass\n"),

    ("a failed fetch reads as git's sentence alone, with no step and no remedy", PUSH,
     "            raise RuntimeError(\n"
     "                f\"push failed: could not bring {branch!r}'s commits out of the job's "
     "repository \"\n",
     "            raise RuntimeError(f\"push failed: {redact(out)}\")\n"
     "            raise RuntimeError(\n"
     "                f\"push failed: could not bring {branch!r}'s commits out of the job's "
     "repository \"\n"),
]
