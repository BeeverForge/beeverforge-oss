"""A hook planted in the shared repo cache never runs on the host (#182, first half), proven by
breaking it.

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/182_a_hook_in_the_shared_cache_never_runs_on_the_host.py

The claims, each a row:

  1. the worktree box's push carries `--no-verify` and the hooks override;
  2. every other host-side git call of the box carries the override, through its one runner
     `_run`, and the job mark's rev-parse names it itself;
  3. the repository cache's two runners carry it;
  3a. the knowledge refresh's calls in the cache carry it, the bundle build's `status` too;
  4. the guards see a call that bypasses the runner, and check every call, not only the push.
"""

TEST = "tests/test_a_hook_in_the_shared_cache_never_runs_on_the_host.py"
PIN = "beeverforge/gitpin.py"
WORKTREE = "beeverforge/adapters/sandbox/worktree.py"
MARKS = "beeverforge/adapters/gitworktrees.py"
CACHE = "beeverforge/runtime/repo_cache.py"

ACTIVITIES = "beeverforge/runtime/temporal/activities.py"
CACHE_GUARD = f"{TEST}::test_every_literal_git_call_in_a_cache_caller_turns_hooks_off"

MUTATIONS = [
    ("the knowledge refresh's checkout and clean run with the shared cache's hooks (#384's review)",
     ACTIVITIES,
     '            subprocess.run(["git", *gitpin.HOOKLESS, "-C", str(repo_path), *args],',
     '            subprocess.run(["git", "-C", str(repo_path), *args],', CACHE_GUARD),

    ("the knowledge build's `status` runs with the shared cache's hooks (#384's second review)",
     "beeverforge/knowledge/generator.py",
     '            ["git", *gitpin.HOOKLESS, "-C", str(repo), "status", "--porcelain", "--ignored",',
     '            ["git", "-C", str(repo), "status", "--porcelain", "--ignored",',
     TEST + "::test_the_knowledge_build_runs_no_hook_of_the_cache"),

    ("`_head_of` runs with the shared cache's hooks", ACTIVITIES,
     "def _head_of(repo_path: Path) -> str:\n"
     "    # hooks off: `repo_path` is the shared repo cache, whose hooks a pass can write (#182)\n"
     '    head = subprocess.run(["git", *gitpin.HOOKLESS, "-C", str(repo_path), "rev-parse",',
     "def _head_of(repo_path: Path) -> str:\n"
     '    head = subprocess.run(["git", "-C", str(repo_path), "rev-parse",', CACHE_GUARD),

    # 1. the push
    ("the push runs a pre-push hook again: `--no-verify` is gone", WORKTREE,
     '"push", "--force", "--no-verify", "--", target,',
     '"push", "--force", "--", target,'),
    ("the push, and only the push, runs with the shared cache's hooks", WORKTREE,
     '    if cmd[:1] == ["git"]:\n',
     '    if cmd[:1] == ["git"] and "push" not in cmd:\n'),

    # 2. the box's runner and the mark
    ("the box's runner runs each git argv as given, hooks on", WORKTREE,
     '        cmd = ["git", *gitpin.HOOKLESS, *cmd[1:]]\n',
     '        pass\n'),
    ("the override is empty, so no call anywhere turns hooks off", PIN,
     'HOOKLESS: tuple[str, ...] = ("-c", "core.hooksPath=/dev/null")',
     'HOOKLESS: tuple[str, ...] = ()'),
    ("the override names no path git reads as empty, and the planted hooks directory wins", PIN,
     '"core.hooksPath=/dev/null")', '"core.hooksPath=")'),
    ("the job mark's rev-parse runs with the shared cache's hooks", MARKS,
     '["git", *gitpin.HOOKLESS, "-C", str(worktree),', '["git", "-C", str(worktree),'),

    # 3. the repository cache
    ("the cache's `_git` runs with the cache's hooks", CACHE,
     '    p = subprocess.run(["git", *gitpin.HOOKLESS, *args], cwd=cwd,',
     '    p = subprocess.run(["git", *args], cwd=cwd,'),
    ("the cache's `_git_out` runs with the cache's hooks", CACHE,
     '    return subprocess.run(["git", *gitpin.HOOKLESS, *args], cwd=cwd,',
     '    return subprocess.run(["git", *args], cwd=cwd,',
     TEST + "::test_the_cache_runners_put_the_override_first"),

    # 4. the guards
    ("the source guard lets any spawn through", TEST,
     '                    allowed = (fn == "_run" or',
     '                    allowed = (True or fn == "_run" or'),
    ("the recording guard checks the push alone", TEST,
     '    return [str(gitpin.subcommand(argv)) for argv in argvs if not _hookless(argv)]',
     '    return [str(gitpin.subcommand(argv)) for argv in argvs\n'
     '            if gitpin.subcommand(argv) == "push" and not _hookless(argv)]'),
    ("an override after the subcommand counts as one", TEST,
     '    head = argv[:argv.index(sub)] if sub in argv else argv\n',
     '    head = argv\n'),
]
