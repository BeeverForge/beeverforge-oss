"""#265, criterion 3: `beeverforge migrate <project>` proposes the folder's rename as one pull
request per repository, through the forge, for a person to merge — and it is safe to run again.

The claims, and what each cut breaks: the FOUR ANSWERS per repository (only the former folder is
proposed; only the current one, or neither, is nothing; both is said and never proposed), WHAT the
pull request carries (the moved folder, its paths rewritten as path segments only, nothing outside
it, and a body naming the files), RUNNING AGAIN (an open pull request is named, a pushed branch
gets its pull request, an unaskable forge proposes nothing), ONE REPOSITORY'S FAILURE (said with
its remedy, and the next one runs), the CONTEXT REPOSITORY counted among the product's, and the
two refusals that keep it off anybody's checkout (`--yes`, and a forge that is this machine).
"""

TEST = "tests/test_beeverforge_migrate_proposes_the_folder_rename.py"
MF = "beeverforge/onboarding/migrate_folder.py"
CLI = "beeverforge/cli.py"

MUTATIONS = [
    ("a repository carrying both folders is proposed like one carrying only the former", MF,
     "        if former and current:\n",
     "        if False:\n"),

    ("a repository on `.beeverforge/`, or with neither, is not left alone — and a merged "
     "proposal is not the end of it", MF,
     "        if not former:\n",
     "        if False:\n"),

    ("the paths written inside the moved folder keep saying `.openfactory/`", MF,
     "        rewritten = rewrite_paths(checkout / namespace.DIR)\n",
     "        rewritten = []\n"),

    ("the rewrite reaches outside the folder, into files the rename has no business touching", MF,
     "        rewritten = rewrite_paths(checkout / namespace.DIR)\n",
     "        rewritten = rewrite_paths(checkout)\n"),

    ("`.openfactory/` is rewritten wherever it appears, even as the tail of another name", MF,
     '_FORMER_PATH = re.compile(r"(?<![\\w.-])" + re.escape(FORMER_DIR) + r"/")\n',
     '_FORMER_PATH = re.compile(re.escape(FORMER_DIR) + r"/")\n'),

    ("the pull request's body stops naming the files a path was rewritten in", MF,
     '        lines.extend(f"- `{p}`" for p in rewritten)\n',
     "        pass\n"),

    ("the sentence for both folders stops saying which one is read", MF,
     '_RECONCILE = (f"carries both `{FORMER_DIR}/` and `{namespace.DIR}/`, and `{namespace.DIR}/` '
     'is the "\n'
     '              f"one read — ',
     '_RECONCILE = (f"carries both `{FORMER_DIR}/` and `{namespace.DIR}/`, and `{namespace.DIR}/` '
     'is the "\n'
     '              f"newer — '),

    ("a second run does not see the open pull request and opens another", MF,
     "        if url:\n",
     "        if False:\n"),

    ("a branch an earlier run pushed is not finished — the manifest's wedge arm opens it with "
     "the manifest's words", MF,
     "        if branch_there:\n",
     "        if False:\n"),

    ("a forge that could not be asked reads as one with nothing proposed", MF,
     "    if found is None:\n        return None\n",
     '    if found is None:\n        found = ""\n'),

    ("a refused push stops saying what to do about it", MF,
     '            detail = (f"{detail} — check that this deployment\'s forge credential may push "\n'
     '                      f"branches to `{repo}`, then run `beeverforge migrate {name}` again.")\n',
     "            pass\n"),

    # RE-PINNED 2026-11-09 (#470's review): a second run no longer opens it, so the sentence says
    # to open it from the branch, and that a second run will not
    ("a pushed branch whose pull request did not open stops saying how to open it", MF,
     '            detail = (f"{detail} — open it from `{BRANCH}` on the forge; a second run names "\n'
     '                      f"the branch and does not open one on it.")\n',
     "            pass\n"),

    ("a refused clone stops naming the credential and the second run", MF,
     '            f"could not clone `{repo}` ({said}) — check that this deployment\'s forge '
     'credential "\n'
     '            f"can read it, then run `beeverforge migrate {name}` again; nothing was proposed "\n'
     '            f"there."))\n',
     '            f"could not clone `{repo}`."))\n'),

    ("one repository's failure stops the ones after it", MF,
     "        said.append(migrate_repository(project, repo, forge=forge, clone_url=url))\n",
     "        said.append(migrate_repository(project, repo, forge=forge, clone_url=url))\n"
     "        if not said[-1].ok:\n            break\n"),

    ("the context repository is not one of the product's repositories", MF,
     "    for repo in [*own, *(sources or []), docs]:\n",
     "    for repo in [*own, *(sources or [])]:\n"),

    ("a failure on a repository leaves the command exiting 0", CLI,
     "            typer.echo(f\"✗ {said.repo}: {said.detail}\")\n",
     "            failed = False\n            typer.echo(f\"✗ {said.repo}: {said.detail}\")\n"),

    ("without `--yes` the verb clones and proposes anyway", CLI,
     '        typer.echo(f"This may open a pull request on: {\', \'.join(repos)} — re-run with '
     '--yes.")\n'
     "        raise typer.Exit(2)\n",
     "        pass\n"),

    ("a project whose forge is this machine is cloned and pushed to — somebody's checkout", CLI,
     "    if is_this_machine(project):\n",
     "    if False:\n"),

    # #470's review
    ("a rewritten file loses its Windows line endings: read as text, `\\r\\n` becomes `\\n`", MF,
     '            text = raw.decode("utf-8")\n',
     '            text = path.read_text(encoding="utf-8")\n'),

    ("the files outside the folder that still spell the former path are not named", MF,
     "        outside = outside_references(checkout)\n",
     "        outside = []\n"),

    ("a branch left with no open pull request is proposed again", MF,
     "        if branch_there:\n",
     "        if False:\n"),
]
