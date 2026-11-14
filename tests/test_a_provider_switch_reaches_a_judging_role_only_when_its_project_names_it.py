"""A provider switch reaches a judging role only when its project's `box.env` names it (#472).

THE DEFECT. On a deployment where one project reaches its model through Bedrock and another
through a different provider, `CLAUDE_CODE_USE_BEDROCK` is set in the worker's environment for
the first. The judging roles (product, tech lead, sizer) run in a worktree box with the worker's
environment, and `_scrubbed_env` removed the AWS credentials of a project that does not name them
but left the switch. The second project's harness chose Bedrock, found no credentials and failed
("Could not load AWS credentials"), and its product role answered that it could not see the
product's requirements.

The container box passes only the names `box.env` declares, and `routes.declared_route` reads a
project's route from there, so a project that uses Bedrock already names the switch. The worktree
now withholds the switches the routes read unless the project names them, as it does the
credentials, and leaves every other variable as it was.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from beeverforge.adapters.sandbox.base import Workspace
from beeverforge.adapters.sandbox.registry import judging_worktree
from beeverforge.adapters.sandbox.worktree import _PROVIDER_SWITCH_VARS, _scrubbed_env
from beeverforge.contracts.project import Project
from tests.the_tree_read_once import parsed

ROOT = Path(__file__).resolve().parent.parent
ROUTES = ROOT / "beeverforge" / "adapters" / "agent" / "routes.py"

BEDROCK, VERTEX, FOUNDRY = ("CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX",
                            "CLAUDE_CODE_USE_FOUNDRY")


@pytest.fixture
def switches(monkeypatch):
    """The worker's environment on such a deployment: the switches set deployment-wide.
    `tests/conftest.py` strips them before every test, so they are set here."""
    for var in (BEDROCK, VERTEX, FOUNDRY):
        monkeypatch.setenv(var, "1")


def _project(name: str, env: list[str]) -> Project:
    return Project(name=name, repo_path="/tmp/p", box={"image": "python:3.12", "env": env})


def test_a_provider_switch_the_project_does_not_name_is_withheld(switches):
    for keep in ((), ("AWS_REGION",)):
        env = _scrubbed_env(keep)

        assert BEDROCK not in env and VERTEX not in env, keep


def test_a_provider_switch_the_project_names_is_kept(switches):
    env = _scrubbed_env((BEDROCK, "AWS_REGION"))

    assert env[BEDROCK] == "1"
    assert VERTEX not in env  # named alone, the one switch passes, not its sibling

    assert _scrubbed_env((VERTEX,))[VERTEX] == "1"


def test_a_switch_the_routes_do_not_read_is_left_as_it_is(switches):
    assert _scrubbed_env()[FOUNDRY] == "1"
    assert _scrubbed_env((BEDROCK,))[FOUNDRY] == "1"


def test_every_provider_switch_the_routes_read_is_one_the_worktree_withholds():
    """Parsed, not grepped: the string constants `routes.py` reads, never its comments."""
    read = {node.value for node in ast.walk(parsed(ROUTES))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and node.value.startswith("CLAUDE_CODE_USE_")}

    assert read, "routes.py reads no CLAUDE_CODE_USE_* switch — this measures nothing"
    assert set(_PROVIDER_SWITCH_VARS) == read


def _seen_by_the_harness(project: Project, tmp_path: Path) -> str:
    """What a judging role's harness process reads, run through the project's own judging box."""
    box = judging_worktree(project, root=tmp_path / "boxes")
    code, out = box.run(workspace=Workspace(path=tmp_path, branch="b", base_branch="main"),
                        command=f'printf "%s" "${{{BEDROCK}:-absent}}"', timeout=30)
    assert code == 0, out
    return out.strip()


def test_on_one_deployment_only_the_project_that_names_bedrock_reaches_it(switches, tmp_path):
    on_bedrock = _project("product-a", [BEDROCK, "AWS_REGION"])
    elsewhere = _project("product-b", [])

    assert _seen_by_the_harness(on_bedrock, tmp_path) == "1"
    assert _seen_by_the_harness(elsewhere, tmp_path) == "absent"
