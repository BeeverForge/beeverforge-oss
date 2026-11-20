"""A git call the repo cache or the worktree box makes never asks for a password at the terminal.

A fetch, clone or `ls-remote` with no credential, or a rejected one, makes git ask
`Username for 'https://github.com':`. An attended command then sits on that prompt and the
worker waits until the timeout. Both host-side runners switch the prompt off for every git
call, and the box's runner leaves a non-git command's environment as it was given.
"""

import subprocess

from beeverforge.adapters.sandbox import worktree
from beeverforge.runtime import repo_cache

_OFF = {"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
_TURNED_ON = {"GIT_TERMINAL_PROMPT": "1", "GCM_INTERACTIVE": "always"}


def _record(monkeypatch, module) -> list:
    seen: list = []

    def run(argv, **kwargs):
        seen.append(kwargs.get("env"))
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(module.subprocess, "run", run)
    return seen


def _turn_the_prompt_on_in_the_process(monkeypatch) -> None:
    for name, value in _TURNED_ON.items():
        monkeypatch.setenv(name, value)


def _prompt_entries(env) -> dict:
    assert isinstance(env, dict), (
        f"git ran with env={env!r}, which inherits whatever the process has and leaves the "
        "credential prompt on; pass an explicit env that sets the prompt entries")
    return {name: env.get(name) for name in _OFF}


def test_the_cache_turns_the_prompt_off_when_the_caller_passes_no_env(monkeypatch):
    seen = _record(monkeypatch, repo_cache)
    monkeypatch.setenv("SOMEONE_PROCESS_MARKER", "here")
    repo_cache._git(["status"])
    assert _prompt_entries(seen[0]) == _OFF, (
        "the cache ran git with its credential prompt on, so a call with no credential waits "
        "at the terminal; set GIT_TERMINAL_PROMPT=0 and GCM_INTERACTIVE=never last in `_git`")
    assert seen[0].get("SOMEONE_PROCESS_MARKER") == "here", (
        "the cache dropped the process environment from git's; build the env over os.environ")


def test_the_cache_keeps_a_callers_env_with_the_prompt_still_off(monkeypatch):
    seen = _record(monkeypatch, repo_cache)
    repo_cache._git(["status"], env={"SOMEONE_MARKER": "kept", **_TURNED_ON})
    assert seen[0].get("SOMEONE_MARKER") == "kept", (
        "the cache dropped an entry its caller passed; merge the caller's env, do not replace it")
    assert _prompt_entries(seen[0]) == _OFF, (
        "a caller's env turned git's credential prompt back on; merge the prompt entries after "
        "the caller's in `_git`")


def test_the_cache_keeps_the_prompt_off_when_the_process_turns_it_on(monkeypatch):
    seen = _record(monkeypatch, repo_cache)
    _turn_the_prompt_on_in_the_process(monkeypatch)
    repo_cache._git(["status"])
    repo_cache._git(["status"], env={"SOMEONE_MARKER": "kept"})
    for env in seen:
        assert _prompt_entries(env) == _OFF, (
            "the process environment turned git's credential prompt back on; merge the prompt "
            "entries after os.environ in `_git`")


def test_the_box_turns_the_prompt_off_for_git_with_no_env(monkeypatch):
    seen = _record(monkeypatch, worktree)
    _turn_the_prompt_on_in_the_process(monkeypatch)
    monkeypatch.setenv("SOMEONE_PROCESS_MARKER", "here")
    worktree._run(["git", "status"])
    assert _prompt_entries(seen[0]) == _OFF, (
        "the box ran git with its credential prompt on, so a call with no credential waits at "
        "the terminal; set GIT_TERMINAL_PROMPT=0 and GCM_INTERACTIVE=never last in `_run`")
    assert seen[0].get("SOMEONE_PROCESS_MARKER") == "here", (
        "the box dropped the process environment for a git call given no env; build it over "
        "os.environ")


def test_the_box_turns_the_prompt_off_for_git_without_widening_a_callers_env(monkeypatch):
    seen = _record(monkeypatch, worktree)
    monkeypatch.setenv("SOMEONE_PROCESS_ONLY", "leaked")
    worktree._run(["git", "status"], env={"SOMEONE_MARKER": "kept", **_TURNED_ON})
    assert _prompt_entries(seen[0]) == _OFF, (
        "a caller's env turned git's credential prompt back on in the box; merge the prompt "
        "entries after the caller's env in `_run`")
    assert seen[0].get("SOMEONE_MARKER") == "kept", (
        "the box dropped an entry its caller passed; use the caller's env as the base")
    assert "SOMEONE_PROCESS_ONLY" not in seen[0], (
        "a caller's full env was merged with the process env, which restores scrubbed "
        "credentials; use the caller's env as the whole environment")


def test_the_box_leaves_a_non_git_commands_env_as_given(monkeypatch):
    seen = _record(monkeypatch, worktree)
    mapping = {"SOMEONE_MARKER": "kept"}
    worktree._run(["true"])
    worktree._run(["true"], env=mapping)
    assert seen[0] is None, (
        "the box changed a non-git command's environment; add the prompt entries for git only")
    assert seen[1] is mapping and seen[1] == {"SOMEONE_MARKER": "kept"}, (
        "the box changed the env a non-git command was given; pass it through as given")
