"""`beeverforge migrate <project>` proposes the folder's rename — `.openfactory/` to `.beeverforge/`
— as one pull request per repository, through the forge, for a person to merge; and it is safe to
run again (GitHub issue #265, its third criterion).

Driven through the command line against real repositories from the git bed standing for the
forge's remotes, and a forge double that records the pull requests it is asked to open and answers
what is open — the git side (clone, `git mv`, commit, push) is production code. What is held:

- ONLY `.openfactory/`: one pull request on `beeverforge/migrate-folder` that moves the folder,
  rewrites the `.openfactory/` paths written inside it, touches nothing outside it, and names in
  its body the files a path was rewritten in;
- ONLY `.beeverforge/`, or NEITHER: nothing, said in one line;
- BOTH: no pull request, and one sentence saying `.beeverforge/` is read and a person reconciles;
- AGAIN: the open pull request is named, never a second; a branch an earlier run pushed gets its
  pull request; after the merge, nothing;
- ONE REPOSITORY FAILING — the clone refused, the push refused, the forge unreachable — is one
  sentence with its cause and remedy, and the next repository still runs;
- THE CONTEXT REPOSITORY is one of the product's repositories;
- NOTHING IS WRITTEN INTO A CHECKOUT: a project whose forge is this machine is refused before
  anything is cloned, and no `--yes` means nothing is cloned or opened.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests import the_git_bed
from tests.the_git_bed import a_served_tree

git_bed = the_git_bed.git_bed

#: The platform's own branch for the proposal — spelled here, so the name is held and a test of a
#: tree without the verb fails on the verb rather than on an import.
BRANCH = "beeverforge/migrate-folder"

#: A code repository still on OpenFactory's folder: a manifest naming a path inside it, a file
#: naming no path, and a README OUTSIDE the folder that also spells the former path.
FORMER = {
    ".openfactory/project.yaml": ("version: 1\n"
                                  "preview:\n"
                                  "  compose: .openfactory/preview.compose.yml\n"
                                  "notes: my.openfactory/ and xopenfactory/ are not ours\n"),
    ".openfactory/preview.compose.yml": "services:\n  app:\n    image: app\n",
    "README.md": "Our manifest is at .openfactory/project.yaml.\n",
}
CURRENT = {".beeverforge/project.yaml": "version: 1\n", "README.md": "hello\n"}


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout


def _served(bed, root: Path, slug: str, files: dict[str, str]) -> Path:
    """A repository holding `files` on `main`, from the git bed — what the forge serves for
    `slug`. Pushes land on the platform's branch, never on the checked-out `main`."""
    name = slug.replace("/", "--")
    src = root / f"{name}-src"
    for rel, text in files.items():
        (src / rel).parent.mkdir(parents=True, exist_ok=True)
        (src / rel).write_text(text, encoding="utf-8")
    return a_served_tree(bed, src, root / f"{name}.git")


class _Forge:
    """The forge port at the methods a proposal uses, answering from what it was asked to open —
    so a second run sees the first run's pull request the way a real forge would."""

    def __init__(self, remotes: dict[str, Path]):
        self.remotes = remotes
        self.opened: list[dict] = []
        self.state: dict[tuple[str, str], str] = {}
        self.unreachable: set[str] = set()
        self.refuses_to_open: set[str] = set()

    def pr_for_head(self, head, *, repo=""):
        if repo in self.unreachable:
            raise RuntimeError("the forge could not be reached")
        return next((o["url"] for o in reversed(self.opened)
                     if o["repo"] == repo and o["head"] == head), "")

    def pr_status(self, *, pr, repo=""):
        return next(s for (r, url), s in self.state.items() if url == pr)

    def list_branches(self, repo="", *, prefix=""):
        out = _git(self.remotes[repo], "branch", "--list", "--format=%(refname:short)")
        return out.split()

    def open_pr(self, *, head, base, title, body, repo=""):
        if repo in self.refuses_to_open:
            raise RuntimeError("the forge refused to open the pull request")
        url = f"https://forge.example/{repo}/pull/{len(self.opened) + 1}"
        self.opened.append({"head": head, "base": base, "title": title, "body": body,
                            "repo": repo, "url": url})
        self.state[(repo, url)] = "open"
        return url

    def merge(self, repo: str) -> None:
        """A person merged the proposal: `main` is the branch, and the pull request is merged."""
        remote = self.remotes[repo]
        _git(remote, "update-ref", "refs/heads/main", f"refs/heads/{BRANCH}")
        for key in self.state:
            if key[0] == repo:
                self.state[key] = "merged"


def _cli():
    from beeverforge.cli import app

    return app


@pytest.fixture
def product(tmp_path, monkeypatch, git_bed):
    """`acme-api`, registered by URL, with a context repository; `_make` seeds each repository
    the forge serves, and the forge and the clone URLs are doubled through the registry."""
    monkeypatch.setenv("BEEVERFORGE_REGISTRY", str(tmp_path / "registry.yaml"))
    from beeverforge.adapters.forge import registry as forge_registry

    def _make(repos: dict[str, dict[str, str]], *, docs: str = "") -> _Forge:
        remotes = {slug: _served(git_bed, tmp_path / "forge", slug, files)
                   for slug, files in repos.items()}
        forge = _Forge(remotes)
        monkeypatch.setattr(forge_registry, "build_forge", lambda *a, **kw: forge)
        monkeypatch.setattr(
            forge_registry, "clone_url_for",
            lambda project, repo="", **kw: str(remotes.get(repo, tmp_path / "nowhere.git")))
        out = CliRunner().invoke(_cli(), ["project", "add", "acme-api",
                                          "https://github.com/acme/api.git"])
        assert out.exit_code == 0, out.output
        if docs:
            from beeverforge.registry import ProjectRegistry

            ProjectRegistry().set_docs_repo("acme-api", docs)
        return forge

    return _make


def _migrate(*extra: str):
    return CliRunner().invoke(_cli(), ["migrate", "acme-api", *extra, "--yes"])


def _branches(remote: Path) -> list[str]:
    return _git(remote, "branch", "--list", "--format=%(refname:short)").split()


# ── only `.openfactory/`: one pull request that moves it ───────────────────────────────────────

def test_a_repository_on_the_former_folder_gets_one_pull_request_that_moves_it(product):
    forge = product({"acme/api": FORMER})
    remote = forge.remotes["acme/api"]

    out = _migrate()

    assert out.exit_code == 0, out.output
    opened, = forge.opened
    assert (opened["repo"], opened["head"], opened["base"]) == ("acme/api", BRANCH, "main")
    from beeverforge.onboarding import migrate_folder

    assert migrate_folder.BRANCH == BRANCH
    tree = _git(remote, "ls-tree", "-r", "--name-only", BRANCH).split()
    assert sorted(tree) == [".beeverforge/preview.compose.yml", ".beeverforge/project.yaml",
                            "README.md"]
    assert _git(remote, "show", f"{BRANCH}:.beeverforge/project.yaml") == (
        "version: 1\n"
        "preview:\n"
        "  compose: .beeverforge/preview.compose.yml\n"
        "notes: my.openfactory/ and xopenfactory/ are not ours\n")
    # nothing outside the folder changed, and the file nothing named moved byte for byte
    assert _git(remote, "show", f"{BRANCH}:README.md") == FORMER["README.md"]
    changes = _git(remote, "diff", "--name-status", "-M", "main", BRANCH).splitlines()
    assert sorted(line.split("\t", 1)[1] for line in changes) == [
        ".openfactory/preview.compose.yml\t.beeverforge/preview.compose.yml",
        ".openfactory/project.yaml\t.beeverforge/project.yaml"]
    assert any(line.startswith("R100\t.openfactory/preview.compose.yml") for line in changes)
    # the body says what and why, and names the one file a path was rewritten in
    body = opened["body"]
    assert ".openfactory/" in body and ".beeverforge/" in body and "git mv" in body
    assert "- `.beeverforge/project.yaml`" in body
    assert "preview.compose.yml`" not in body
    # the README OUTSIDE the folder still spells the former path: not edited, but named, in the
    # body and in the line, for the person who merges (#470's review)
    assert "OUTSIDE the folder still mention `.openfactory/`" in body and "- `README.md`" in body
    assert "outside the folder, README.md still mention `.openfactory/`" in out.output
    assert "OpenFactory" not in body
    assert "✓ acme/api: the rename is proposed at https://forge.example/acme/api/pull/1" in (
        out.output)
    assert ".beeverforge/project.yaml" in out.output
    # the base branch is untouched until a person merges
    assert _git(remote, "ls-tree", "-r", "--name-only", "main").split() == sorted(FORMER)


def test_only_a_path_segment_named_after_the_former_folder_is_rewritten(tmp_path):
    from beeverforge.onboarding import migrate_folder

    folder = tmp_path / ".beeverforge"
    folder.mkdir()
    (folder / "a.yaml").write_text("x: .openfactory/a\ny: ./.openfactory/b\nz: my.openfactory/c\n"
                                   "w: .openfactoryx/d\n")
    (folder / "b.bin").write_bytes(b"\xff\xfe.openfactory/")
    (folder / "c.txt").write_text("nothing here\n")

    assert migrate_folder.rewrite_paths(folder) == [".beeverforge/a.yaml"]
    assert (folder / "a.yaml").read_text() == (
        "x: .beeverforge/a\ny: ./.beeverforge/b\nz: my.openfactory/c\nw: .openfactoryx/d\n")
    assert (folder / "b.bin").read_bytes() == b"\xff\xfe.openfactory/"


def test_a_rewritten_file_keeps_its_line_endings(tmp_path):
    """#470's review: `read_text`/`write_text` turned every `\\r\\n` into `\\n`, so the pull
    request changed every line of a file with Windows line endings, not only its path."""
    from beeverforge.onboarding import migrate_folder

    folder = tmp_path / ".beeverforge"
    folder.mkdir()
    (folder / "a.yaml").write_bytes(b"a: .openfactory/x\r\nb: 1\r\n")

    assert migrate_folder.rewrite_paths(folder) == [".beeverforge/a.yaml"]
    assert (folder / "a.yaml").read_bytes() == b"a: .beeverforge/x\r\nb: 1\r\n"


# ── only `.beeverforge/`, or neither: nothing ───────────────────────────────────────────────────

@pytest.mark.parametrize("files,said", [
    (CURRENT, "keeps its folder as `.beeverforge/` — nothing to rename"),
    ({"README.md": "hello\n"}, "carries neither `.openfactory/` nor `.beeverforge/` — nothing "
                               "to rename"),
])
def test_a_repository_with_nothing_to_rename_is_left_alone_in_one_line(product, files, said):
    forge = product({"acme/api": files})

    out = _migrate()

    assert out.exit_code == 0, out.output
    assert out.output.strip() == f"· acme/api: `acme/api` {said}."
    assert forge.opened == [] and _branches(forge.remotes["acme/api"]) == ["main"]


# ── both: a person reconciles ───────────────────────────────────────────────────────────────────

def test_a_repository_with_both_folders_is_said_and_never_proposed(product):
    forge = product({"acme/api": {**FORMER, **CURRENT}})

    out = _migrate()

    assert out.exit_code == 0, out.output
    line, = out.output.strip().splitlines()
    assert line.startswith("! acme/api: `acme/api` carries both `.openfactory/` and "
                           "`.beeverforge/`"), line
    assert "`.beeverforge/` is the one read" in line and "remove `.openfactory/`" in line
    assert forge.opened == [] and _branches(forge.remotes["acme/api"]) == ["main"]


# ── safe to run again ───────────────────────────────────────────────────────────────────────────

def test_a_second_run_names_the_open_pull_request_and_opens_none(product):
    forge = product({"acme/api": FORMER})
    assert _migrate().exit_code == 0
    head = _git(forge.remotes["acme/api"], "rev-parse", BRANCH)

    again = _migrate()

    assert again.exit_code == 0, again.output
    assert len(forge.opened) == 1
    assert ("· acme/api: the rename of `acme/api` is already proposed at "
            "https://forge.example/acme/api/pull/1.") in again.output
    assert _git(forge.remotes["acme/api"], "rev-parse", BRANCH) == head


def test_a_branch_left_with_no_open_pull_request_is_named_and_never_reopened(product):
    """#470's review: a branch with no open pull request is an earlier run that never opened one,
    or a proposal a person closed, and the two cannot be told apart. Reopening it would bring a
    declined proposal back on every run, so it is named, for a person to delete, even when the
    forge would open one now."""
    forge = product({"acme/api": FORMER})
    forge.refuses_to_open.add("acme/api")
    first = _migrate()
    assert forge.opened == [] and BRANCH in _branches(forge.remotes["acme/api"]), first.output
    assert ("open it from `beeverforge/migrate-folder` on the forge; a second run names the "
            "branch and does not open one on it") in " ".join(first.output.split()), first.output
    head = _git(forge.remotes["acme/api"], "rev-parse", BRANCH)
    forge.refuses_to_open.clear()

    again = _migrate()

    assert again.exit_code == 1, again.output
    assert forge.opened == [], "a branch left with no pull request was proposed again"
    assert ("already has a branch `beeverforge/migrate-folder` with no open pull request" in
            again.output and "delete that branch" in again.output), again.output
    assert _git(forge.remotes["acme/api"], "rev-parse", BRANCH) == head


def test_a_leftover_branch_no_pull_request_opens_on_is_named_for_a_person(product):
    forge = product({"acme/api": FORMER})
    forge.refuses_to_open.add("acme/api")
    _migrate()

    again = _migrate()

    assert again.exit_code == 1
    assert ("already has a branch `beeverforge/migrate-folder` with no open pull request" in
            again.output and "delete that branch" in again.output), again.output
    assert forge.opened == []


def test_a_run_after_the_merge_does_nothing(product):
    forge = product({"acme/api": FORMER})
    assert _migrate().exit_code == 0
    forge.merge("acme/api")

    after = _migrate()

    assert after.exit_code == 0, after.output
    assert "keeps its folder as `.beeverforge/` — nothing to rename" in after.output
    assert len(forge.opened) == 1


# ── one repository failing does not stop the next ───────────────────────────────────────────────

def test_a_clone_refused_is_one_sentence_and_the_next_repository_runs(product):
    forge = product({"acme/web": FORMER})  # acme/api is served by nobody

    out = _migrate("--source", "acme/web")

    assert out.exit_code == 1
    failed, = [ln for ln in out.output.splitlines() if ln.startswith("✗ acme/api:")]
    assert "could not clone `acme/api`" in failed and "credential can read it" in failed
    assert "run `beeverforge migrate acme-api` again" in failed
    assert [o["repo"] for o in forge.opened] == ["acme/web"]
    assert "✓ acme/web: the rename is proposed at" in out.output


def test_a_push_refused_is_one_sentence_and_the_next_repository_runs(product):
    forge = product({"acme/api": FORMER, "acme/web": FORMER})
    hook = forge.remotes["acme/api"] / ".git" / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho 'pushes are closed here' >&2\nexit 1\n")
    hook.chmod(0o755)

    out = _migrate("--source", "acme/web")

    assert out.exit_code == 1
    failed, = [ln for ln in out.output.splitlines() if ln.startswith("✗ acme/api:")]
    assert "could not push beeverforge/migrate-folder" in failed
    assert "may push branches to `acme/api`" in failed
    assert [o["repo"] for o in forge.opened] == ["acme/web"]


def test_a_forge_that_cannot_be_asked_proposes_nothing_there_and_the_next_runs(product):
    forge = product({"acme/api": FORMER, "acme/web": FORMER})
    forge.unreachable.add("acme/api")

    out = _migrate("--source", "acme/web")

    assert out.exit_code == 1
    assert "✗ acme/api: could not ask the forge whether `acme/api` already has the rename" in (
        out.output)
    assert _branches(forge.remotes["acme/api"]) == ["main"]
    assert [o["repo"] for o in forge.opened] == ["acme/web"]


# ── the context repository is one of them ───────────────────────────────────────────────────────

def test_the_context_repository_is_proposed_too(product):
    forge = product({"acme/api": CURRENT,
                     "acme/api-context": {".openfactory/product.yaml": "product: acme\n"}},
                    docs="acme/api-context")

    out = _migrate()

    assert out.exit_code == 0, out.output
    lines = out.output.strip().splitlines()
    assert lines[0].startswith("· acme/api:") and lines[1].startswith("✓ acme/api-context:")
    opened, = forge.opened
    assert opened["repo"] == "acme/api-context"
    assert _git(forge.remotes["acme/api-context"], "ls-tree", "-r", "--name-only",
                BRANCH).split() == [".beeverforge/product.yaml"]


# ── nothing is written into a checkout ──────────────────────────────────────────────────────────

def test_without_yes_nothing_is_cloned_or_opened(product, monkeypatch):
    from beeverforge.onboarding import migrate_folder

    forge = product({"acme/api": FORMER})
    monkeypatch.setattr(migrate_folder, "migrate",
                        lambda *a, **kw: pytest.fail("migrate ran without --yes"))

    out = CliRunner().invoke(_cli(), ["migrate", "acme-api"])

    assert out.exit_code == 2 and "re-run with --yes" in out.output and "acme/api" in out.output
    assert forge.opened == [] and _branches(forge.remotes["acme/api"]) == ["main"]


def test_a_project_whose_forge_is_this_machine_is_refused_and_its_checkout_untouched(
        tmp_path, monkeypatch, git_bed):
    monkeypatch.setenv("BEEVERFORGE_REGISTRY", str(tmp_path / "registry.yaml"))
    checkout = _served(git_bed, tmp_path, "someone/app", FORMER)
    before = _git(checkout, "for-each-ref")
    assert CliRunner().invoke(_cli(), ["project", "add", "acme-api", str(checkout)]).exit_code == 0

    out = _migrate()

    assert out.exit_code == 2
    assert "checkout on this machine" in out.output and "git mv .openfactory .beeverforge" in (
        out.output)
    assert _git(checkout, "for-each-ref") == before
    assert (checkout / ".openfactory" / "project.yaml").is_file()
    assert _git(checkout, "status", "--porcelain") == ""
    assert not (checkout / ".beeverforge").exists()
