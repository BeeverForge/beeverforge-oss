"""Git that reads or writes inside a repository another user owns runs as that user when the
platform is root, proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/688_git_runs_as_the_repositorys_owner.py

The claims, each with its rows:

  1. who git runs as: root only, the repository's owner, two owners refused;
  2. a directory the owner cannot enter is refused, by its bits and then one attempt as the user;
  3. the short environment, the empty `HOME`, and the process arguments;
  4. the command git starts for the other side, quoted, and only for a path on this machine;
  5. the local forge's git, its scratch tree and what its callers say of a refusal;
  6. the box's clone and fetches; 7. the push and the keep; 8. the repository cache;
  9. the proof's `box` line, and what a cut message keeps.

What only real ownership shows (nothing in the repository is root's, the owner's own acts, the
uid a hook runs as) is in `tests/test_git_run_as_root_leaves_the_repository_to_its_owner.py`,
which needs root, and is not proven here.
"""

TEST = "tests/test_git_runs_as_the_repositorys_owner.py"
OWNER = "beeverforge/gitowner.py"
FORGE = "beeverforge/adapters/forge/local.py"
BOX = "beeverforge/adapters/sandbox/container.py"
PUSH = "beeverforge/adapters/sandbox/host_push.py"
CACHE = "beeverforge/runtime/repo_cache.py"
PROVE = "beeverforge/box_prove.py"

MUTATIONS = [
    # 1. who
    ("a process that is not root is switched too", OWNER,
     "    if os.geteuid() != 0 or not path:", "    if not path:"),
    ("an empty path is the current directory", OWNER,
     "    if os.geteuid() != 0 or not path:", "    if os.geteuid() != 0:"),
    ("root's own repository is switched", OWNER,
     "    if of_git.uid == 0:\n        return None\n", ""),
    ("two owners are guessed at", OWNER,
     "    if of_tree.uid != of_git.uid:", "    if False:"),
    ("the group is the work tree's", OWNER,
     "    return of_git\n", "    return of_tree\n"),
    ("a `.git` file is not followed", OWNER,
     "    if dot.is_file():", "    if False:"),
    ("a relative `gitdir:` is read from wherever the process stands", OWNER,
     "os.path.realpath(tree / named)", "os.path.realpath(named)"),
    ("a `.git` that names nothing is followed all the same", OWNER,
     ' if named else None', ""),
    ("a bare repository is nobody's", OWNER,
     '    if (tree / "HEAD").is_file() and (tree / "objects").is_dir():', "    if False:"),
    ("any directory is a repository", OWNER,
     '    if (tree / "HEAD").is_file() and (tree / "objects").is_dir():', "    if True:"),
    ("ownership that cannot be read escapes", OWNER,
     "    except OSError:\n        return None\n    if of_tree", "    except KeyError:\n"
     "        return None\n    if of_tree"),
    ("a symlinked path is read as it is spelled", OWNER,
     "    tree = Path(os.path.realpath(path))", "    tree = Path(path)"),
    ("the remedy gives the repository to root", OWNER,
     "(of_tree, git_dir) if of_tree.uid else (of_git, tree)", "(of_git, tree)"),
    ("the remedy changes the path that already has that owner", OWNER,
     "(of_tree, git_dir) if of_tree.uid else (of_git, tree)", "(of_tree, git_dir)"),
    ("a refusal loses its parts when pickled", OWNER,
     "        return (Refused, (self.reason, self.remedy, self.detail))",
     "        return (Refused, (str(self),))"),

    # 2. entering
    ("nobody asks whether the owner can get there", OWNER,
     "    _refuse_where_shut(of_git, tree, git_dir)\n", ""),
    ("the git directory is not looked at", OWNER,
     "    _refuse_where_shut(of_git, tree, git_dir)\n", "    _refuse_where_shut(of_git, tree)\n"),
    ("the parents are not looked at", OWNER,
     "for d in (*reversed(end.parents), end))", "for d in (end,))"),
    ("the bits alone decide, so an access list is refused", OWNER,
     "    return _bits_let_in(owner, directory) or _tried_and_entered(owner, directory)",
     "    return _bits_let_in(owner, directory)"),
    ("the attempt is made wherever the bits already allow", OWNER,
     "    return _bits_let_in(owner, directory) or _tried_and_entered(owner, directory)",
     "    return _tried_and_entered(owner, directory)"),
    ("the owner's own bits are not its", OWNER,
     "stat.S_IXUSR", "stat.S_IXOTH"),
    ("the group's bits are not its", OWNER,
     "stat.S_IXGRP", "stat.S_IXOTH"),
    ("a stranger is read by the owner's bits", OWNER,
     "    return bool(st.st_mode & stat.S_IXOTH)", "    return bool(st.st_mode & stat.S_IXUSR)"),
    ("an attempt that could not be made is a denial", OWNER,
     "    except (OSError, subprocess.TimeoutExpired):\n        return True\n",
     "    except (OSError, subprocess.TimeoutExpired):\n        return False\n"),
    ("an attempt that never ends escapes", OWNER,
     "    except (OSError, subprocess.TimeoutExpired):\n", "    except OSError:\n",
     TEST + "::test_an_attempt_that_could_not_be_made_refuses_nothing"),
    ("the attempt is made in the worker's environment", OWNER,
     "**_as(owner, _kept_from_the_worker()))", "**_as(owner, dict(os.environ)))"),

    # 3. the environment
    ("a switched git is given the worker's environment", OWNER,
     '    return {**_kept_from_the_worker(), "HOME": home,',
     '    return {**os.environ, "HOME": home,'),
    ("root's HOME is read", OWNER,
     '    return {**_kept_from_the_worker(), "HOME": home,',
     '    return {**_kept_from_the_worker(), "HOME": os.environ.get("HOME", ""),'),
    ("the locale is dropped", OWNER,
     'if name in ("LANG", "LANGUAGE") or name.startswith("LC_")}', "if False}"),
    ("the process keeps root's supplementary groups", OWNER,
     '"extra_groups": [], ', ""),
    ("the group is not switched", OWNER,
     '"group": owner.gid, ', ""),
    ("git starts in the worker's own directory", OWNER,
     ' "cwd": "/",', ""),
    ("`-C` is the path as it was named", OWNER,
     "        yield os.path.realpath(path), _as(owner, _environment(home))",
     "        yield path, _as(owner, _environment(home))"),
    ("the HOME of a call is left behind", OWNER,
     "    finally:\n        shutil.rmtree(home, ignore_errors=True)", "    finally:\n        pass"),
    ("the HOME stays root's", OWNER,
     "            _chown(home, *owner)\n        yield home", "            pass\n        yield home"),
    ("a git that cannot be started as the owner is a traceback", OWNER,
     "    with _an_empty_home(owner) as home, _said_as_a_refusal(owner):",
     "    with _an_empty_home(owner) as home:"),

    # 4. the served side
    ("the served side keeps the environment of the git that starts it", OWNER,
     'shlex.join(["env", "-i", *(', 'shlex.join(["env", *('),
    ("the words are joined unquoted", OWNER,
     "command = shlex.join(", 'command = " ".join('),
    ("the supplementary groups are kept", OWNER,
     '                              "--clear-groups", f"git-{side}"])',
     '                              f"git-{side}"])'),
    ("the group is the user's number", OWNER,
     '"--regid", str(owner.gid)', '"--regid", str(owner.uid)'),
    ("the protocol is dropped with the rest", OWNER,
     ', GIT_PROTOCOL="version=2")', ")"),
    ("a missing setpriv is found out by git", OWNER,
     "    if not _setpriv():", "    if False:"),
    ("a remote's name is read as a path", OWNER,
     '    return text if text.startswith("/") else ""', "    return text"),
    ("a `file://` URL is not a path on this machine", OWNER,
     '    if text.startswith("file://"):', "    if False:"),

    # 5. the local forge
    ("the local forge's git runs as root", FORGE,
     "        with gitowner.running_as_owner(repository) as (where, how):\n",
     "        with gitowner.running_as_owner('') as (_, how):\n            where = repository\n"),
    ("a refusal escapes the forge's git", FORGE,
     "    except gitowner.Refused as exc:\n        log.warning(\"git was not run",
     "    except KeyError as exc:\n        log.warning(\"git was not run"),
    ("a refusal is not logged", FORGE,
     '        log.warning("git was not run in %s: %s", repository, exc)\n', ""),
    ("a pull request is opened with empty shas", FORGE,
     "        gitowner.owner_of(where)  # refused here, before a row that would hold empty shas\n",
     ""),
    ("the scratch tree stays root's", FORGE,
     "        gitowner.hand_to_the_owner_of(where, scratch)\n", ""),
    ("a directory that cannot be handed over escapes", OWNER,
     "    except (Refused, OSError):\n        return\n", "    except KeyError:\n        return\n"),
    ("a repository nobody could read is a branch that is gone", FORGE,
     "        if not gitowner.is_switched(where):\n", "        if True:\n"),
    ("a branch that is gone is said in git's empty words", FORGE,
     "        if asked.returncode == 0:\n            return gone\n", ""),
    ("the merge does not record why", FORGE,
     "        said = self._sentence(asked)\n        self._refuse(pr, said)\n",
     "        said = self._sentence(asked)\n"),
    ("a refused repository is not switched", OWNER,
     "    except Refused:\n        return True\n", "    except Refused:\n        return False\n"),

    # 6. the box
    ("the box's clone is served as root", BOX,
     "    with gitowner.upload_pack(repo_path) as served:\n        _must(",
     "    with gitowner.upload_pack('') as served:\n        _must("),
    ("the existing branch is served as root", BOX,
     "    return gitowner.upload_pack(remote_url or repo_path)",
     "    return gitowner.upload_pack('')"),
    ("a fetch of `origin` asks about its name", BOX,
     "    return gitowner.upload_pack(remote_url or repo_path)",
     "    return gitowner.upload_pack(remote_url or 'origin')"),
    ("the forge's base is served as root", BOX,
     "    with gitowner.upload_pack(remote_url) as served:",
     "    with gitowner.upload_pack('') as served:"),
    ("the rebase before a merge is served as root", BOX,
     "        with gitowner.upload_pack(target) as served:",
     "        with gitowner.upload_pack('') as served:"),
    ("a progress line comes before git's reason", BOX,
     '    return ["--quiet", *served] if served else []', "    return list(served)"),
    ("every clone is quiet", BOX,
     '    return ["--quiet", *served] if served else []', '    return ["--quiet", *served]'),
    ("git's own refusal is cut and prefixed", BOX,
     "    if served:\n        return gitowner.Refused(words, detail=what)\n", ""),
    ("git's own refusal shows a credential", BOX,
     "    words = _redact(out).strip()", "    words = out.strip()"),
    ("what was being done is dropped", BOX,
     "gitowner.Refused(words, detail=what)", "gitowner.Refused(words)"),
    ("a switched read that said nothing has no reason at all", BOX,
     "    if served and not words:\n", "    if False:\n",
     TEST + "::test_a_switched_read_that_said_nothing_says_what_failed"),
    ("an unswitched failure is not cut", BOX,
     '{words[:300]}")', '{words}")'),
    ("the rebase's unswitched failure is worded anew", BOX,
     '                          f"fetch failed: {_redact(out)}")', '                          "")'),

    # 7. the push and the keep
    ("the push is received as root", PUSH,
     "        with gitowner.receive_pack(target) as option:",
     "        with gitowner.receive_pack('') as option:"),
    ("a refused push does not say it failed", PUSH,
     '        raise RuntimeError(f"push failed: {exc}") from exc', "        raise"),
    ("the keep's fetch is served as root", PUSH,
     "gitowner.upload_pack(target) as read", "gitowner.upload_pack('') as read"),
    ("the keep's push is received as root", PUSH,
     "gitowner.receive_pack(target) as received:\n        theirs",
     "gitowner.receive_pack('') as received:\n        theirs"),

    # 8. the cache
    ("the cache's probe is served as root", CACHE,
     "        with gitowner.upload_pack(clone_url) as served:\n            rc, out",
     "        with gitowner.upload_pack('') as served:\n            rc, out"),
    ("the probe raises a refusal", CACHE,
     "    except gitowner.Refused as exc:\n        return 128, str(exc)",
     "    except KeyError as exc:\n        return 128, str(exc)"),
    ("the cache's refresh is served as root", CACHE,
     "        with gitowner.upload_pack(clone_url) as served:\n            fetch",
     "        with gitowner.upload_pack('') as served:\n            fetch"),
    ("the cache's clone is served as root", CACHE,
     "            with gitowner.upload_pack(clone_url) as read:",
     "            with gitowner.upload_pack('') as read:"),
    ("the master goes before the clone is refused", CACHE,
     "            with gitowner.upload_pack(clone_url) as read:\n"
     "                shutil.rmtree(master, ignore_errors=True)\n",
     "            shutil.rmtree(master, ignore_errors=True)\n"
     "            with gitowner.upload_pack(clone_url) as read:\n"),
    ("a refusal's remedy is cut off the log", CACHE,
     "    return said if isinstance(exc, gitowner.Refused) else said[:160]",
     "    return said[:160]"),
    ("every failure is logged whole", CACHE,
     "    return said if isinstance(exc, gitowner.Refused) else said[:160]",
     "    return said"),

    # 9. the proof, and what a cut keeps
    ("a refused repository is reported as a leftover container", PROVE,
     "    if isinstance(refused, gitowner.Refused):", "    if False:"),
    ("git's own words are given no remedy at all", PROVE,
     ' or "git\'s own words above are the whole reason")', ")"),
    ("the refusal never reaches the proof", PROVE,
     "            box_start_exception=lambda: start_exception,\n", ""),
    ("the reason comes after the remedy, so a cut loses it", OWNER,
     "for part in (reason, remedy, detail) if part))",
     "for part in (remedy, reason, detail) if part))"),
    ("the uids come after the paths", OWNER,
     '        f"the repository has two owners: work tree uid',
     '        f"{tree} and {git_dir} have two owners: work tree uid'),
]
