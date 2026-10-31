"""#172: a git refusal in the box is named, not swallowed.

Two places used to drop git's answer on the floor. `ContainerSandbox.prepare` ran
`git config --global --add safe.directory /workspace` and discarded its exit code, so a client
image whose HOME cannot hold a global config left a box in which every later git call is refused
with "detected dubious ownership" (exit 128). `JobRunner._commit` then ran
`git add -A && git commit … || true`, so that refusal read as "nothing to commit" and the job
silently committed nothing.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from beeverforge.adapters.sandbox import container
from beeverforge.adapters.sandbox.base import Workspace
from beeverforge.adapters.sandbox.container import ContainerSandbox

IMAGE = "client/app:1"
LOCK = "error: could not lock config file /nonexistent/.gitconfig: No such file or directory"
DUBIOUS = ("fatal: detected dubious ownership in repository at '/workspace'\n"
           "To add an exception for this directory, call:\n\n"
           "\tgit config --global --add safe.directory /workspace\n")


# ── 1. prepare: the safe.directory write ────────────────────────────────────────────────────────

def _a_daemon(monkeypatch, tmp_path, *, write: tuple[int, str], home: tuple[int, str]):
    calls: list[list[str]] = []

    def host(cmd, *_, **__):
        calls.append(list(cmd))
        if cmd[:2] == ["docker", "inspect"]:
            return 1, ""
        if cmd[:2] == ["docker", "exec"] and "safe.directory" in cmd:
            return write
        if cmd[:2] == ["docker", "exec"] and "sh" in cmd:
            return home
        return 0, ""

    monkeypatch.setattr(container, "_host", host)
    monkeypatch.setattr(container, "_materialize_workspace", lambda **_: "a" * 40)
    monkeypatch.setenv("BEEVERFORGE_WORK_DIR", str(tmp_path / "work"))
    return calls


def _prepare(box: ContainerSandbox, tmp_path: Path) -> Workspace:
    return box.prepare(repo_path=tmp_path / "cache", base_branch="main", branch="beeverforge/7")


def test_a_failed_safe_directory_write_refuses_naming_the_image_its_home_and_the_remedy(
        monkeypatch, tmp_path):
    calls = _a_daemon(monkeypatch, tmp_path, write=(255, LOCK), home=(0, "OFHOME:/nonexistent\n"))
    box = ContainerSandbox(image=IMAGE)

    with pytest.raises(RuntimeError) as err:
        _prepare(box, tmp_path)

    msg = str(err.value)
    assert repr(IMAGE) in msg, msg
    assert "'/nonexistent'" in msg, f"the refusal does not name the box's HOME: {msg}"
    assert "exited 255" in msg, msg
    assert "could not lock config file" in msg, f"git's own words are missing: {msg}"
    assert "writable HOME" in msg, f"the refusal names no remedy: {msg}"
    assert "\n" not in msg and msg.endswith(".") and ". " not in msg, f"not one sentence: {msg}"

    started = next(c for c in calls if c[:3] == ["docker", "run", "-d"])
    cname = started[started.index("--name") + 1]
    assert ["docker", "rm", "-f", cname] in calls, "the refused box was left running"
    assert box._container is None, "the sandbox holds a handle to a box that refused"
    assert not list((tmp_path / "work").glob("beeverforge-*")), "the host clone was left behind"


def test_a_failed_safe_directory_write_with_an_unreadable_home_says_so(monkeypatch, tmp_path):
    _a_daemon(monkeypatch, tmp_path, write=(255, LOCK), home=(1, "sh: not found"))

    with pytest.raises(RuntimeError) as err:
        _prepare(ContainerSandbox(image=IMAGE), tmp_path)

    msg = str(err.value)
    assert "an unreadable HOME" in msg and "''" not in msg, msg


def test_a_safe_directory_write_that_succeeds_prepares_the_box(monkeypatch, tmp_path):
    calls = _a_daemon(monkeypatch, tmp_path, write=(0, ""), home=(0, "OFHOME:/root\n"))
    box = ContainerSandbox(image=IMAGE)

    ws = _prepare(box, tmp_path)

    assert ws.base_commit == "a" * 40
    started = next(c for c in calls if c[:3] == ["docker", "run", "-d"])
    assert box._container == started[started.index("--name") + 1]
    assert not any(c[:2] == ["docker", "rm"] for c in calls), "a good box was removed"


# ── 2. _commit: nothing to commit vs a refusal ──────────────────────────────────────────────────

class _Sink:
    def __init__(self) -> None:
        self.events: list = []

    def emit(self, event) -> None:
        self.events.append(event)


class _Bot:
    name, email = "beeverforge[bot]", "bot@example.com"


def _runner(sandbox):
    from beeverforge.contracts import Manifest
    from beeverforge.orchestrator import JobRunner

    r = JobRunner.__new__(JobRunner)
    r.sandbox, r.events, r.manifest, r.bot = sandbox, _Sink(), Manifest(), _Bot()
    return r


def _ticket():
    from beeverforge.contracts import Ticket

    return Ticket(id="#172", title="the job", objective="o", repo="o/r")


def _git(repo: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t", "HOME": str(repo)}
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True, env=env).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "app.py").write_text("x = 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    return repo


class _RealSandbox:
    def __init__(self, repo: Path, prefix: str = "") -> None:
        self.repo, self.prefix = repo, prefix

    def run(self, *, command: str, **_):
        out = subprocess.run(self.prefix + command, shell=True, cwd=self.repo,
                             capture_output=True, text=True, check=False,
                             env={**os.environ, "HOME": str(self.repo)})
        return out.returncode, out.stdout + out.stderr


class _Answers:
    """A box whose git answers what it is told: the commit and the status read."""

    def __init__(self, commit: tuple[int, str], status: tuple[int, str]) -> None:
        self.commit, self.status = commit, status

    def run(self, *, command: str, **_):
        if "git commit" in command:
            return self.commit
        if "status --porcelain" in command and "workflows" not in command:
            return self.status
        return 0, ""


def _ws(repo: Path) -> Workspace:
    return Workspace(path=repo, host_path=repo, branch="b", base_branch="main")


def test_nothing_to_commit_on_a_clean_tree_is_quiet(repo):
    head = _git(repo, "rev-parse", "HEAD")
    r = _runner(_RealSandbox(repo))

    r._commit(_ws(repo), _ticket())

    assert _git(repo, "rev-parse", "HEAD") == head
    assert r.events.events == []


def test_a_change_is_committed(repo):
    head = _git(repo, "rev-parse", "HEAD")
    (repo / "new.py").write_text("N = 1\n")

    _runner(_RealSandbox(repo))._commit(_ws(repo), _ticket())

    assert _git(repo, "rev-parse", "HEAD") != head
    assert "new.py" in _git(repo, "show", "--name-only", "--pretty=format:", "HEAD").split()


def _assert_names_the_refusal(msg: str, rc: int, words: str) -> None:
    assert f"exit {rc}" in msg, f"the failure does not carry git's exit: {msg}"
    assert msg.count(words) == 1, f"git's words are not in the failure exactly once: {msg}"
    assert "make git usable on this workspace in the box" in msg, f"no remedy: {msg}"
    assert "\n" not in msg and msg.endswith("."), f"not one sentence: {msg}"


def test_a_git_refusal_fails_the_commit_with_gits_exit_and_words(repo):
    probe = subprocess.run(["git", "rev-parse", "--git-dir"], cwd=repo, capture_output=True,
                           env={**os.environ, "GIT_TEST_ASSUME_DIFFERENT_OWNER": "1"})
    if probe.returncode == 0:
        pytest.skip("this machine's git has no ownership check to refuse with (git 2.35.2 added "
                    "it; GIT_TEST_ASSUME_DIFFERENT_OWNER is how a test reaches it)")
    (repo / "new.py").write_text("N = 1\n")
    head = _git(repo, "rev-parse", "HEAD")
    r = _runner(_RealSandbox(repo, prefix="export GIT_TEST_ASSUME_DIFFERENT_OWNER=1; "))

    with pytest.raises(RuntimeError) as err:
        r._commit(_ws(repo), _ticket())

    _assert_names_the_refusal(str(err.value), 128, "detected dubious ownership")
    assert _git(repo, "rev-parse", "HEAD") == head


def test_a_git_refusal_answered_by_a_double_fails_the_commit(repo):
    r = _runner(_Answers(commit=(128, DUBIOUS), status=(128, DUBIOUS)))

    with pytest.raises(RuntimeError) as err:
        r._commit(_ws(repo), _ticket())

    _assert_names_the_refusal(str(err.value), 128, "detected dubious ownership")


def test_exit_1_with_a_dirty_tree_is_a_failure(repo):
    r = _runner(_Answers(commit=(1, "hook said no"), status=(0, " M app.py\n")))

    with pytest.raises(RuntimeError) as err:
        r._commit(_ws(repo), _ticket())

    _assert_names_the_refusal(str(err.value), 1, "hook said no")


def test_exit_1_whose_status_read_fails_is_a_failure(repo):
    r = _runner(_Answers(commit=(1, "nothing to commit"), status=(128, DUBIOUS)))

    with pytest.raises(RuntimeError) as err:
        r._commit(_ws(repo), _ticket())

    assert "exit 1" in str(err.value), str(err.value)
