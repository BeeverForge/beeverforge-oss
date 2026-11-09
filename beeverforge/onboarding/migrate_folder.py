"""Propose the folder's rename, `.openfactory/` → `.beeverforge/`, as one pull request per
repository of a product, for a person to merge (GitHub issue #265).

The platform's folder in a product's repositories was formerly called `.openfactory/`;
BeeverForge keeps it as `.beeverforge/`. Those repositories belong to the people who run the
factory, so the platform never renames the folder on its own: `beeverforge migrate <project>`
PROPOSES it, through the forge, and a person merges it.

PER REPOSITORY, FROM A THROWAWAY CLONE OF ITS BASE BRANCH, one of four answers:

    only `.openfactory/`   one pull request on `beeverforge/migrate-folder`: the folder moved with
                           `git mv` (its files keep their history), and the text paths that spell
                           `.openfactory/` in the moved files rewritten — the files outside the
                           folder are left exactly as they were, and the body names every file a
                           path was rewritten in;
    only `.beeverforge/`   nothing to do — which is also what a run after the merge finds;
    or neither
    both                   no pull request: `.beeverforge/` is the one read, and which of the two
                           holds what the team means is not a question a tool can answer;
    a failure              one sentence with its cause and remedy, and the next repository runs.

SAFE TO RUN AGAIN. A pull request still open from the branch is named instead of a second one; a
branch pushed by an earlier run that never opened its pull request gets that pull request opened;
a branch the forge would not open one on is named, for a person to delete. Nothing is pushed
anywhere but the platform's own branch, and nothing is written outside the throwaway clone — a
project whose forge is this machine is refused before anything is cloned, because its repository
is somebody's checkout, and migrating it is a `git mv` they run themselves.
"""

from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from beeverforge import namespace

log = logging.getLogger("beeverforge.onboarding.migrate_folder")

#: The folder's former name, which this verb proposes to rename.
FORMER_DIR = ".openfactory"

#: Deterministic, so a second run finds the first run's pull request instead of opening another.
BRANCH = f"{namespace.BRANCH_PREFIX}/migrate-folder"

#: `.openfactory/` as a path segment of its own — never the tail of a longer name.
_FORMER_PATH = re.compile(r"(?<![\w.-])" + re.escape(FORMER_DIR) + r"/")

#: What the person is told to do when a repository carries both folders.
_RECONCILE = (f"carries both `{FORMER_DIR}/` and `{namespace.DIR}/`, and `{namespace.DIR}/` is the "
              f"one read — move what you still need out of `{FORMER_DIR}/` into it and remove "
              f"`{FORMER_DIR}/` yourself; no pull request was opened")


@dataclass
class Said:
    """What one repository came to, in the terms its line says."""

    repo: str
    #: False only for a failure: the clone, the forge or the push refused
    ok: bool = False
    #: the pull request's URL, when there is one
    url: str = ""
    #: the pull request was open already — named, not opened again
    existed: bool = False
    #: nothing to rename: the repository is on `.beeverforge/`, or has neither folder
    nothing: bool = False
    #: both folders: a person reconciles them, and nothing was proposed
    both: bool = False
    #: the files inside the moved folder whose text paths were rewritten
    rewritten: list[str] = field(default_factory=list)
    #: files OUTSIDE the folder that still spell the former path: named, never edited
    outside: list[str] = field(default_factory=list)
    detail: str = ""


def repositories(project, sources: list[str] | None = None) -> list[str]:
    """Every repository of `project` this verb looks at: its code repository (none for a product
    that started before its code), the other repositories named with `--source`, and its context
    repository — each once, the context repository last."""
    from beeverforge.adapters.forge.registry import repo_of
    from beeverforge.contracts.project import before_its_code
    from beeverforge.product.config import normalize_repo

    own = [] if before_its_code(project) else [repo_of(project)]
    docs = (getattr(getattr(project, "product", None), "docs_repo", "") or "").strip()
    seen: dict[str, str] = {}
    for repo in [*own, *(sources or []), docs]:
        key = normalize_repo(repo) or (repo or "").strip()
        if key and key not in seen:
            seen[key] = repo.strip()
    return list(seen.values())


def is_this_machine(project) -> bool:
    """Whether `project`'s forge is this machine — its repository somebody's checkout."""
    from beeverforge.adapters.forge.registry import forge_kind

    return forge_kind(project) == "local"


def rewrite_paths(folder: Path) -> list[str]:
    """Rewrite `.openfactory/` to `.beeverforge/` in the text of every file under `folder`, and
    return the ones it changed, relative to `folder`'s parent. A file that is not UTF-8 text, or
    is a link, is left as it is: a path inside it is not one this can read."""
    changed = []
    for path in sorted(folder.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        # READ AND WRITTEN AS BYTES (#470's review): `read_text` turns `\r\n` into `\n` and
        # `write_text` writes `\n`, so a file with Windows line endings came back with every line
        # changed, not only the path. Decoded only to find the paths, written back byte for byte
        # but those.
        try:
            raw = path.read_bytes()
            text = raw.decode("utf-8")
        except (UnicodeDecodeError, OSError):
            log.info("%s is not UTF-8 text; any path inside it is left as it is", path)
            continue
        new = _FORMER_PATH.sub(f"{namespace.DIR}/", text)
        if new != text:
            path.write_bytes(new.encode("utf-8"))
            changed.append(path.relative_to(folder.parent).as_posix())
    return changed


def outside_references(checkout: Path) -> list[str]:
    """The files OUTSIDE the folder that still spell `.openfactory/` (#470's review): a
    `.gitignore` line, a CI step, a document. This verb does not edit them, so it names them,
    for the person who merges to fix: once merged they point at a folder that is gone."""
    from beeverforge.onboarding.propose_manifest import _git

    rc, out = _git(["grep", "-l", "-I", "-F", f"{FORMER_DIR}/", "--", ".",
                    f":(exclude){namespace.DIR}"], cwd=checkout)
    return sorted(n for n in out.splitlines() if n.strip()) if rc == 0 else []


def pr_body(rewritten: list[str], *, project: str, outside: list[str] = ()) -> str:
    """What the repository's owner reads: what moved, why, and what else changed."""
    lines = [
        f"This platform's folder in your repository is now called `{namespace.DIR}/`; the former "
        f"`{FORMER_DIR}/` folder is still read until it is renamed. This pull request renames it "
        f"with `git mv`, so every file in it keeps its history, and edits nothing outside it.",
        "",
    ]
    if rewritten:
        lines.append(f"Inside the folder, these files spelled paths under `{FORMER_DIR}/`, and "
                     f"those paths now say `{namespace.DIR}/`:")
        lines.append("")
        lines.extend(f"- `{p}`" for p in rewritten)
    else:
        lines.append(f"No file in the folder spelled a path under `{FORMER_DIR}/`, so only the "
                     f"folder's name changed.")
    if outside:
        lines += ["", f"These files OUTSIDE the folder still mention `{FORMER_DIR}/` and are not "
                      f"changed here; once this is merged they point at a folder that is gone, so "
                      f"update them too:", ""]
        lines.extend(f"- `{p}`" for p in outside)
    lines += ["",
              "Read it and merge it when it suits you: until then the folder keeps its former "
              f"name. Running `beeverforge migrate {project}` again after the merge finds "
              f"`{namespace.DIR}/` and does nothing."]
    return "\n".join(lines)


def _existing(forge, repo: str) -> tuple[str, bool] | None:
    """`(the open pull request's URL, whether the branch is on the forge)` — `None` when the forge
    could not be asked, which is never read as "there is none"."""
    from beeverforge.onboarding.propose_manifest import already_proposed

    found = already_proposed(forge, repo, BRANCH)
    if found is None:
        return None
    if found:
        return found, True
    try:
        branches = {str(b) for b in (forge.list_branches(repo=repo) or ())}
    except Exception:  # noqa: BLE001 — unreadable is not "there is no branch"
        log.info("could not list %s's branches before proposing the folder's rename", repo,
                 exc_info=True)
        return None
    return "", BRANCH in branches


def migrate_repository(project, repo: str, *, forge, clone_url: str) -> Said:
    """One repository: clone its base branch, read which folders it carries, and propose the
    rename when only the former one is there."""
    from beeverforge.onboarding.propose_manifest import (
        _git,
        clone_for_proposal,
        default_branch,
        propose,
        scrub,
    )

    name = project.name
    checkout, why = clone_for_proposal(clone_url=clone_url)
    if checkout is None:
        said = " ".join(why.split())[-200:] or "git said nothing"
        return Said(repo=repo, detail=(
            f"could not clone `{repo}` ({said}) — check that this deployment's forge credential "
            f"can read it, then run `beeverforge migrate {name}` again; nothing was proposed "
            f"there."))
    try:
        former, current = (checkout / FORMER_DIR).is_dir(), (checkout / namespace.DIR).is_dir()
        if former and current:
            return Said(repo=repo, ok=True, both=True, detail=f"`{repo}` {_RECONCILE}.")
        if not former:
            kept = (f"keeps its folder as `{namespace.DIR}/`" if current else
                    f"carries neither `{FORMER_DIR}/` nor `{namespace.DIR}/`")
            return Said(repo=repo, ok=True, nothing=True,
                        detail=f"`{repo}` {kept} — nothing to rename.")
        base = default_branch(checkout)
        existing = _existing(forge, repo)
        if existing is None:
            return Said(repo=repo, detail=(
                f"could not ask the forge whether `{repo}` already has the rename proposed — "
                f"run `beeverforge migrate {name}` again in a moment; nothing was proposed, "
                f"which is safer than a second pull request."))
        url, branch_there = existing
        if url:
            return Said(repo=repo, ok=True, url=url, existed=True,
                        detail=f"the rename of `{repo}` is already proposed at {url}.")
        if branch_there:
            # A BRANCH WITH NO OPEN PULL REQUEST IS NEVER REOPENED (#470's review): it is an earlier
            # run that never opened one, or a proposal a person closed without merging, and the
            # two cannot be told apart from here. Reopening would bring a declined proposal back
            # on every run, on a branch whose content may predate the base.
            return Said(repo=repo, detail=(
                f"`{repo}` already has a branch `{BRANCH}` with no open pull request: an earlier "
                f"run was interrupted, or its proposal was closed — delete that branch on the "
                f"forge and run `beeverforge migrate {name}` again to propose the rename afresh."))
        rc, out = _git(["mv", FORMER_DIR, namespace.DIR], cwd=checkout)
        if rc != 0:
            return Said(repo=repo, detail=(
                f"git would not move `{FORMER_DIR}/` in `{repo}` "
                f"({' '.join(scrub(out).split())[-200:]}) — "
                f"rename it by hand; nothing was proposed."))
        rewritten = rewrite_paths(checkout / namespace.DIR)
        outside = outside_references(checkout)
        result = propose(
            checkout=checkout, manifest_path=namespace.DIR, repo=repo, clone_url=clone_url,
            base=base, forge=forge, project_name=name, branch=BRANCH,
            title=f"BeeverForge: rename {FORMER_DIR}/ to {namespace.DIR}/",
            body=pr_body(rewritten, project=name, outside=outside),
            message=(f"chore: rename {FORMER_DIR}/ to {namespace.DIR}/\n\n"
                     f"BeeverForge keeps its folder as {namespace.DIR}/; proposed by `beeverforge "
                     f"migrate {name}`, for a person to merge."))
        # ONE LINE: git's own words arrive with their newlines, and the outcome is one line
        detail = " ".join(result.detail.replace("the manifest", "the rename").split())
        if not result.ok:
            detail = (f"{detail} — check that this deployment's forge credential may push "
                      f"branches to `{repo}`, then run `beeverforge migrate {name}` again.")
        elif not result.url:
            detail = (f"{detail} — open it from `{BRANCH}` on the forge; a second run names "
                      f"the branch and does not open one on it.")
        return Said(repo=repo, ok=result.ok, url=result.url, existed=result.existed,
                    rewritten=rewritten, outside=outside, detail=detail)
    finally:
        shutil.rmtree(checkout, ignore_errors=True)


def migrate(project, *, sources: list[str] | None = None) -> list[Said]:
    """Every repository of `project`, one `Said` each, in `repositories`' order. A failure on
    one is said and the next one runs."""
    from beeverforge.adapters.forge.registry import build_forge, clone_url_for
    from beeverforge.credentials import deployment_forge_token, forge_token_for
    from beeverforge.onboarding.propose_manifest import scrub
    from beeverforge.product.onboard import context_clone_url, context_forge
    from beeverforge.runtime.card_repo import _runner_view

    docs = (getattr(getattr(project, "product", None), "docs_repo", "") or "").strip()
    said = []
    for repo in repositories(project, sources):
        try:
            if repo == docs:
                forge, url = context_forge(project), context_clone_url(project, repo)
            else:
                view, _ = _runner_view(project, f"{repo}#0")
                token = forge_token_for(view) or deployment_forge_token(view)
                forge, url = build_forge(view, token=token), clone_url_for(view, repo,
                                                                            token=token)
        except Exception as exc:  # noqa: BLE001 — the message is the finding
            log.warning("could not reach the forge of %s for its folder's rename: %s", repo,
                        scrub(str(exc))[:200])
            said.append(Said(repo=repo, detail=(
                f"could not reach the forge of `{repo}` ({scrub(str(exc))[:200]}) — check the "
                f"project's forge in the registry, then run `beeverforge migrate "
                f"{project.name}` again.")))
            continue
        said.append(migrate_repository(project, repo, forge=forge, clone_url=url))
    return said
