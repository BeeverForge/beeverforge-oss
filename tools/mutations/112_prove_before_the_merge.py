"""#112: a manifest on a branch can be measured, and measuring it never authorises anything.

The dangerous reverse is the first cut. A branch proof written where the poller looks satisfies
the gate that holds pickup on the BASE branch — work would then run against a manifest nobody
merged, and the deployment would look correct while doing it. The other reverses: the base
branch's own proof must keep recording, and the base branch's checkout must not be replaced by
whatever branch was last measured.
"""

TEST = "tests/test_a_manifest_can_be_proven_before_it_is_merged.py"
CLI = "beeverforge/cli.py"
PROVE = "beeverforge/box_prove.py"
FACTORY = "beeverforge/factory.py"

MUTATIONS = [
    # RE-PINNED 2026-11-13 (#237): the command's body is the `box_prove` row's
    # (`box_prove.prove_the_box`), so the rows that cut the proving and the recording cut it there;
    # what stays in the command is how a terminal says the verdict, and the recorder it hands the
    # row (`_record`), which asks the ref again — cut on its own below.
    # The command's recorder asks the ref again, so through the command this cut cannot be seen;
    # the row's own test hands the bare `save`, as the worker does.
    ("a branch proof is recorded where the poller looks, unlocking an unmerged manifest", PROVE,
     "    where = None if ref else record(proof)",
     "    where = record(proof)",
     "tests/test_box_prove_is_a_catalogue_row.py::test_a_ref_proof_is_measured_and_never_recorded"),

    ("…and the reverse: the base branch's proof stops being recorded at all", PROVE,
     "    where = None if ref else record(proof)",
     "    where = None if not ref else record(proof)"),

    ("the command's own recorder stops recording the base branch's proof", CLI,
     "        return None if ref else save(proof)",
     "        return None"),

    ("the ref shares the base branch's checkout key and replaces its tree", PROVE,
     '            ref_root = resolve_repo_path(view, cache_key=f"{key}@{safe}", ref=ref)',
     "            ref_root = resolve_repo_path(view, cache_key=key, ref=ref)"),

    ("the ref is never handed down, so a branch proof silently measures the base branch", PROVE,
     '            ref_root = resolve_repo_path(view, cache_key=f"{key}@{safe}", ref=ref)',
     '            ref_root = resolve_repo_path(view, cache_key=f"{key}@{safe}")'),

    ("a ref's slash reaches the directory name", PROVE,
     '        safe = _re.sub(r"[^A-Za-z0-9._-]", "-", ref)',
     "        safe = ref"),

    ("the measurement is announced in the word the recorded verdict uses", CLI,
     '        typer.echo(f"{\'WOULD PROVE\' if proven else \'WOULD NOT PROVE\'} — measured on {ref!r}, "',
     '        typer.echo(f"{\'PROVEN\' if proven else \'NOT PROVEN\'} — measured on {ref!r}, "'),

    ("a failing branch exits 0, so a script proposing a manifest reads it as fine", CLI,
     "        raise typer.Exit(0 if proven else 1)",
     "        raise typer.Exit(0)"),

    ("an unreadable ref raises instead of refusing by name", PROVE,
     "            _let_go(held)\n            return Run(key=key, ref=ref,\n",
     "            _let_go(held)\n            raise\n            return Run(key=key, ref=ref,\n"),

    # ── the local-path half (review of #119) ────────────────────────────────────────────────────
    ("a locally-registered project ignores the ref and measures the working tree", FACTORY,
     "        return _worktree_at(local, ref, cache_key or project.name) if ref else local",
     "        return local"),

    ("…and the reverse: a project with NO ref gets a worktree instead of its own tree", FACTORY,
     "        return _worktree_at(local, ref, cache_key or project.name) if ref else local",
     "        return _worktree_at(local, ref, cache_key or project.name)"),

    ("the second checkout claims the branch, so measuring the branch you are on fails", FACTORY,
     '    rc, out = _git(["-C", str(repo), "worktree", "add", "--detach", str(dest), ref])',
     '    rc, out = _git(["-C", str(repo), "worktree", "add", str(dest), ref])'),

    ("a stale worktree is left registered, so measuring one ref twice fails the second time",
     FACTORY,
     '        _git(["-C", str(repo), "worktree", "remove", "--force", str(dest)])\n'
     "        if dest.exists():\n"
     "            shutil.rmtree(dest, ignore_errors=True)",
     "        pass"),

    ("a path that is not a repository reaches git instead of a sentence", FACTORY,
     '    if not (repo / ".git").exists():', "    if False:"),

    ("a ref nobody fetched reaches git instead of a sentence naming `git fetch`", FACTORY,
     '    if _git(["-C", str(repo), "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"])[0] != 0:',
     "    if False:"),

    ("the seam ignores the ref and syncs the base branch whatever the caller asked for", FACTORY,
     '                                ref or load_manifest_base_branch(project, default=""))',
     '                                load_manifest_base_branch(project, default=""))'),
]
