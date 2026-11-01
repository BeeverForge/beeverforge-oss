"""The git bed: each shape of repository the suite needs, built ONCE per run (by whichever xdist
worker asks first, under a lock), and handed to every test as a fresh copy (#337).

WHY. Measured in the 2026-11-01 unit run (main b5f2742, 8 cores): 2,058 s of the 4,246 s summed
call time was in files that run git, and most of those build a fresh repository per test — an
`init -b main`, a commit, sometimes a clone and a second remote: 40 to 80 ms of fork, exec and disk
for the first commit, 200 to 500 ms for a repository with a remote, paid again for repositories
that are byte for byte the same. Measured here (#337, one process, a loaded 12-core box): building
the quayside context as `test_capabilities_and_checks.py` did took 146 ms; a copy of it (99 files,
`.git` included) took 10 ms, median of ten.

HOW A TEST GETS ONE. Register the fixture in the module (`git_bed = the_git_bed.git_bed`, an
assignment, so no unused import is left to silence), ask for `git_bed`, and copy a shape to where
the test wants it:

    repo = a_served_tree(git_bed, FIXTURE / "context", tmp_path / "context")
    repo = git_bed.copy("my-shape", tmp_path / "myapp", build)   # build(where, env) makes it

`build` is called the first time any worker of the run asks for the name, with a path that does
not exist yet and a `pytest.MonkeyPatch` that is undone right after; the whole of `os.environ` is
put back too, since a build that runs a CLI command may write it directly. So a shape that needs
its own `HOME` or identity sets it there, and `_the_environment_is_restored_after_every_test`
stays quiet. The copy is as disposable as a `tmp_path` repository: the test may commit, push and
delete in it.

A TEMPLATE IS NEVER HANDED OUT. Every `copy` is a new `copytree`, and the template's fingerprint
(every entry's relative path, size, mtime and mode, read without a subprocess) is compared before
each copy and again when the session ends: a template somebody changed in place is refused by
name, because every test copied after it would read that change in whatever order the suite ran.

A COPY NAMES ITS OWN PATH. A clone made in a template keeps the template's path as its
`remote.origin.url`, and a shape may write its root into a text file. At build, every file outside
`objects/` is read for the template's root; the text ones are rewritten to the copy's path at copy
time, and a binary one is refused, since a copy could not be told where it is.

The shapes the moved files need are below the class: a fixture tree made a repository that serves
partial clones (`a_served_tree`), and the card repositories of the worktree box's tests
(`a_card_repository`, `a_hosted_door`). A shape that only one file needs and that runs the
platform's own code (`test_a_product_can_start_before_its_code.py`'s `started`) is built there,
through `copy`.

THE COUNT. `count_git_inits` counts the bare `git init` calls left under `tests/` (the pattern is
its docstring), and `tests/test_a_test_gets_its_repository_from_the_bed.py` holds it at or below
its `BASELINE`: this module is the one place a repository is built for many tests.
"""

from __future__ import annotations

import ast
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from tests.the_tree_read_once import could_say, parsed, source_text

Build = Callable[[Path, pytest.MonkeyPatch], None]


class BedRefused(RuntimeError):
    """A template changed in place, or a shape a copy could not be told its path in."""


@dataclass
class _Template:
    root: Path
    print_: tuple
    texts: list[str] = field(default_factory=list)


def _fingerprint(root: Path) -> tuple:
    seen = []
    for top, dirs, files in os.walk(root):
        dirs.sort()
        for name in sorted(dirs + files):
            path = os.path.join(top, name)
            st = os.lstat(path)
            seen.append((os.path.relpath(path, root), st.st_size, st.st_mtime_ns, st.st_mode))
    return tuple(seen)


def _in_objects(rel: str) -> bool:
    parts = Path(rel).parts
    return any(part == "objects" and i and (parts[i - 1] == ".git" or parts[i - 1].endswith(".git"))
               for i, part in enumerate(parts))


class Bed:
    """The templates under `root`: built once by whichever process asks first, under a lock per
    shape, and read by every process that shares the root."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._shapes: dict[str, _Template] = {}

    def copy(self, name: str, dest: Path, build: Build) -> Path:
        """A fresh copy of shape `name` at `dest` (made, or filled when it is an empty or existing
        directory), the shape built through `build` the first time anybody sharing the root asks
        for it."""
        template = self._shapes.get(name)
        if template is None:
            template = self._template(name, build)
        self._verify(name, template)
        dest = Path(dest)
        shutil.copytree(template.root, dest, symlinks=True, dirs_exist_ok=True)
        old, new = str(template.root).encode(), str(dest).encode()
        for rel in template.texts:
            path = dest / rel
            path.write_bytes(path.read_bytes().replace(old, new))
        return dest

    def verify_all(self) -> None:
        """Every template this process copied from as it was built, or a refusal naming the first
        that is not."""
        for name, template in self._shapes.items():
            self._verify(name, template)

    def _template(self, name: str, build: Build) -> _Template:
        """The template of `name`: read from its manifest when another process built it, else
        built here. The lock is held across the build, so a second process waits for it rather
        than building the same shape beside it."""
        slug = hashlib.blake2b(name.encode(), digest_size=8).hexdigest()
        home = self.root / slug
        where, manifest = home / "template", home / "manifest.json"
        self.root.mkdir(parents=True, exist_ok=True)
        with open(self.root / f"{slug}.lock", "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if manifest.is_file():
                made = json.loads(manifest.read_text(encoding="utf-8"))
                template = _Template(root=where, print_=tuple(tuple(e) for e in made["print"]),
                                     texts=made["texts"])
            else:
                template = self._build(name, build, home, where)
                manifest.write_text(json.dumps({"name": name, "print": template.print_,
                                                "texts": template.texts}), encoding="utf-8")
        self._shapes[name] = template
        return template

    def _build(self, name: str, build: Build, home: Path, where: Path) -> _Template:
        shutil.rmtree(home, ignore_errors=True)
        home.mkdir()
        # THE WHOLE ENVIRONMENT IS PUT BACK, not only what `env` set: a build that runs the
        # platform's own code (a CLI command) may write `os.environ` itself, and the test that
        # happened to build the shape would run on with what the next one never sees.
        saved = dict(os.environ)
        try:
            try:
                with pytest.MonkeyPatch.context() as env:
                    build(where, env)
            finally:
                os.environ.clear()
                os.environ.update(saved)
            where.mkdir(exist_ok=True)
            texts = self._texts_naming(name, where)
        except BaseException:
            shutil.rmtree(home, ignore_errors=True)
            raise
        return _Template(root=where, print_=_fingerprint(where), texts=texts)

    @staticmethod
    def _texts_naming(name: str, where: Path) -> list[str]:
        needle = str(where).encode()
        texts = []
        for top, _dirs, files in os.walk(where):
            for file in files:
                path = Path(top) / file
                rel = os.path.relpath(path, where)
                if path.is_symlink() or _in_objects(rel):
                    continue
                data = path.read_bytes()
                if needle not in data:
                    continue
                try:
                    data.decode("utf-8")
                except UnicodeDecodeError:
                    raise BedRefused(
                        f"the bed's shape {name!r} leaves its own path inside the binary file "
                        f"{rel}, which a copy cannot be rewritten in, so build that state from the "
                        f"copy instead.") from None
                texts.append(rel)
        return sorted(texts)

    @staticmethod
    def _verify(name: str, template: _Template) -> None:
        now = _fingerprint(template.root)
        if now == template.print_:
            return
        was = {entry[0]: entry for entry in template.print_}
        is_ = {entry[0]: entry for entry in now}
        what = sorted(set(was) ^ set(is_)) or sorted(r for r in was if was[r] != is_.get(r))
        raise BedRefused(
            f"the bed's template {name!r} was changed in place ({', '.join(what[:3])}), which every "
            f"test copied after it would read, so change the copy `git_bed.copy` handed out, never "
            f"the template it was copied from.")


_STASH = pytest.StashKey[Bed]()


@pytest.fixture(scope="session")
def git_bed(request, tmp_path_factory, _git_asks_this_suite_who_it_is) -> Bed:
    """The session's bed: ONE per process whichever test module registered this fixture, on ONE
    root for every xdist worker of the run (the parent of the workers' own base directories), so a
    shape is built once per run. Measured (#337, 12 cores): with a bed per worker,
    `test_capabilities_and_checks.py` alone under `-n auto` summed 3.13 s of setup against 3.24 s
    on b5f2742, since each of 12 workers ran about four of its tests and built all five shapes for
    them. The templates are only read across workers; each
    test's copy is its own, so `_repo_cache_is_not_shared_between_workers` is untouched.

    The templates this process copied from are verified when the session ends."""
    bed = request.config.stash.get(_STASH, None)
    if bed is None:
        base = tmp_path_factory.getbasetemp()
        shared = base.parent if hasattr(request.config, "workerinput") else base
        bed = Bed(shared / "git-bed")
        request.config.stash[_STASH] = bed
    yield bed
    bed.verify_all()


# ── the shapes ──────────────────────────────────────────────────────────────────────────────────

def _git(repo: Path, *args: str, env: dict | None = None) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True, env=env)
    return done.stdout


def _served_tree(src: Path) -> Build:
    def build(where: Path, _env: pytest.MonkeyPatch) -> None:
        lazy = {**os.environ, "GIT_NO_LAZY_FETCH": "1"}
        shutil.copytree(src, where)
        _git(where, "init", "-q", "-b", "main", env=lazy)
        _git(where, "config", "user.name", "fixture", env=lazy)
        _git(where, "config", "user.email", "fixture@example.invalid", env=lazy)
        _git(where, "config", "commit.gpgsign", "false", env=lazy)
        _git(where, "config", "uploadpack.allowFilter", "true", env=lazy)
        _git(where, "config", "uploadpack.allowAnySHA1InWant", "true", env=lazy)
        _git(where, "add", "-A", env=lazy)
        _git(where, "commit", "-qm", "the fixture", env=lazy)
    return build


def a_served_tree(bed: Bed, src: Path, dest: Path) -> Path:
    """`src` as a git repository at `dest`: one commit on `main` by `fixture`, serving partial
    clones (`uploadpack.allowFilter`, `uploadpack.allowAnySHA1InWant`)."""
    return bed.copy(f"served-tree:{Path(src).resolve()}", dest, _served_tree(Path(src)))


#: The card's branch the worktree box's tests prepare.
CARD_BRANCH = "beeverforge/28"
WORK = "WORK = True\n"


def _card_commit(repo: Path, name: str, text: str, message: str) -> None:
    (repo / name).write_text(text)
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgSign=false",
         "commit", "-q", "-m", message)


def _card_repository(where: Path, work: str) -> Path:
    subprocess.run(["git", "init", "-q", "-b", "main", str(where)], capture_output=True, check=True)
    _card_commit(where, "README.md", "# app\n", "base")
    _git(where, "switch", "-q", "-c", CARD_BRANCH)
    _card_commit(where, "work.py", work, "the job's work")
    _git(where, "switch", "-q", "main")
    return where


def a_card_repository(bed: Bed, dest: Path, work: str = WORK) -> Path:
    """`main`, and the card's branch `beeverforge/28` carrying the job's committed `work.py`."""
    return bed.copy(f"card-repository:{work!r}", dest,
                    lambda where, _env: _card_repository(where, work))


def _hosted_door(where: Path, _env: pytest.MonkeyPatch) -> None:
    where.mkdir()
    origin = where / "forge.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)],
                   capture_output=True, check=True)
    seed = _card_repository(where / "seed", WORK)
    _git(seed, "push", "-q", str(origin), "main", CARD_BRANCH)
    subprocess.run(["git", "clone", "-q", str(origin), str(where / "myapp")], capture_output=True,
                   check=True)
    _git(seed, "switch", "-q", CARD_BRANCH)
    _card_commit(seed, "work.py", "WORK = 2\n", "the factory's second pass")
    _git(seed, "push", "-q", str(origin), CARD_BRANCH)


def a_hosted_door(bed: Bed, dest: Path) -> Path:
    """A hosted forge under `dest`: a bare `forge.git` holding `main` and the card's branch, the
    `seed` that pushed them, and `myapp`, a clone of it whose tracking ref is one push behind."""
    return bed.copy("hosted-door", dest, _hosted_door)


# ── the count ───────────────────────────────────────────────────────────────────────────────────

_GIT_INIT = re.compile(r"\bgit\s+init\b")
#: What a file's text must hold for its tree to hold one of the three forms: a `"init"` constant
#: as written, or the words of a command line. Necessary, so a file without it is never parsed.
_COULD_BE_ONE = re.compile(r"""['"]init['"]|\bgit\s+init\b""")
#: Files the count does not read: the bed, the one place a repository is built for many tests,
#: and the guard, whose planted sources spell every form on purpose.
NOT_COUNTED = ("the_git_bed.py", "test_a_test_gets_its_repository_from_the_bed.py")


def _subcommand(items: list[ast.expr]) -> str:
    """git's subcommand among `items`: the first string constant that is not an option."""
    for item in items:
        if isinstance(item, ast.Constant) and isinstance(item.value, str):
            if not item.value.startswith("-"):
                return item.value
    return ""


def _is_git_init_list(node: ast.AST) -> bool:
    if not isinstance(node, (ast.List, ast.Tuple)) or not node.elts:
        return False
    head = node.elts[0]
    return (isinstance(head, ast.Constant) and head.value == "git"
            and _subcommand(node.elts[1:]) == "init")


def _is_git_helper_init(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(
        func, ast.Attribute) else ""
    if "git" not in name.lower():
        return False
    first = node.args[0] if node.args else None
    if isinstance(first, (ast.List, ast.Tuple)) and _subcommand(first.elts) == "init":
        return True
    return _subcommand(node.args) == "init"


def _git_inits(tree: ast.Module) -> int:
    """The bare `git init` calls in one parsed file, each counted once, in any of three forms:

      · a list or tuple literal whose first element is `"git"` and whose subcommand is `"init"` —
        `subprocess.run(["git", "init", ...])`, `["git", "-C", d, "init"]`;
      · a call of a function whose name holds `git` (any case) whose subcommand is `"init"`, given
        positionally or as the list it is handed first — `_git(d, "init", ...)`,
        `om.git(repo, "init")`, `_git(["init", "-q"], repo)`;
      · a string constant matching `\\bgit\\s+init\\b` that is not a docstring or a bare string
        statement — a command line handed to a shell, `f"git init {d}"`.

    The SUBCOMMAND is the first string constant that is not an option (`-C`, `-q`), so a commit
    whose message is "init" (`_git(repo, "commit", "-m", "init")`) is not one.

    Not counted: comments (not in the tree), docstrings, `"init"` handed to a call that is not
    git's (`om.cli("project", "init", ...)`), and a list that does not start with `"git"`.

    NOT SEEN, AND SO A FLOOR RATHER THAN A CENSUS: a helper whose name does not say git
    (`_ok(where, "init")`) and a loop over argument lists (`for args in (["init"], ...)`), both
    on b5f2742. The count holds the line all the same: a new file written in the seen forms raises
    it, and moving one of the unseen ones onto the bed lowers nothing it holds."""
    prose = {id(stmt.value) for stmt in ast.walk(tree)
             if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)}
    count = 0
    for node in ast.walk(tree):
        if _is_git_init_list(node) or _is_git_helper_init(node):
            count += 1
        elif (isinstance(node, ast.Constant) and isinstance(node.value, str)
              and id(node) not in prose and _GIT_INIT.search(node.value)):
            count += 1
    return count


def count_git_inits(root: Path) -> int:
    """The bare `git init` calls in every `*.py` under `root` but `NOT_COUNTED` (`_git_inits`)."""
    total = 0
    for path in sorted(Path(root).rglob("*.py")):
        if path.name in NOT_COUNTED:
            continue
        if not could_say(source_text(path), _COULD_BE_ONE):
            continue
        total += _git_inits(parsed(path))
    return total


def over_the_line(count: int, baseline: int) -> str:
    """The refusal when `count` is over `baseline`, else nothing."""
    return refusal(count, baseline) if count > baseline else ""


def refusal(count: int, baseline: int) -> str:
    """The sentence a test that built one repository too many by hand reads."""
    return (f"tests/ builds {count} repositories with a bare `git init`, over the {baseline} the "
            f"bed left, so get a repository from `git_bed` in tests/the_git_bed.py instead (see "
            f"CONTRIBUTING.md).")
