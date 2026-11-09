"""#410: an Azure DevOps ref qualified with the wrong project reads its API where it clones.

`AzureReposForge.clone_url` ignores a `project/repo` qualifier when the ref names the adapter's
own repository (compared without case since #399): a registry row that filled the generic
`owner/name` field on an Azure axis would otherwise have its owner read as a project.
`_client_for` obeyed every qualifier, so `Owner/api` cloned from `Desk` but listed its branches,
looked up and opened its pull requests and read its branch policies in `Owner`, a project that
does not exist. Both now ask one rule, so they cannot drift again. A ref naming ANOTHER
repository (the context repository in a shared documentation project) still obeys its qualifier
for both.

Found in the same sweep: `disabled_ci_paths` matched a pipeline's repository against the one asked
for by spelling, so a pipeline of `API` was not this adapter's `api`. It compares without case now.

Found in #414's review: `delete_branch` and `_pr` (behind `pr_status`, `merge_pr`, `pr_body`,
`set_pr_body`, `pr_diff`) named the repository through `_repo_or_self` and then used the adapter's
own client, so `Docs/web` was deleted from and read in `Desk`. They read through `_client_for` now.
"""

from __future__ import annotations

import pytest

from beeverforge.adapters.forge import azure_devops as mod
from beeverforge.adapters.forge.azure_devops import AzureReposForge

URL = "https://beeverforge:pat@dev.azure.com/acme"


def _forge(repo: str = "api") -> AzureReposForge:
    return AzureReposForge(repo, organization="acme", project="Desk", token="pat")


# ---- the clone URL and the client agree ---------------------------------------------------------

def test_a_misconfigured_owner_ref_clones_and_reads_in_the_own_project():
    f = _forge()

    assert f.clone_url("Owner/api", token="pat") == f"{URL}/Desk/_git/api"
    assert f._client_for("Owner/api").project == "Desk"


def test_a_ref_naming_another_repository_reads_and_clones_in_the_project_it_names():
    f = _forge()

    assert f.clone_url("Docs/web", token="pat") == f"{URL}/Docs/_git/web"
    assert f._client_for("Docs/web").project == "Docs"


def test_a_ref_naming_the_own_repository_in_another_case_reads_and_clones_in_the_own_project():
    f = _forge()

    assert f.clone_url("Docs/API", token="pat") == f"{URL}/Desk/_git/API"
    assert f._client_for("Docs/API").project == "Desk"


def test_an_empty_ref_is_the_own_repository_in_the_own_project():
    f = _forge()

    assert f.clone_url("", token="pat") == f"{URL}/Desk/_git/api"
    assert f._client_for("").project == "Desk"


# ---- real read paths through `_client_for` ------------------------------------------------------

class _ProjectAwareClient:
    """Records `(project, method, path)` for every request and answers "nothing there"."""

    def __init__(self, asked: list, project: str):
        self.asked, self.project = asked, project

    def values(self, path, **kw):
        self.asked.append((self.project, "GET", path))
        return []

    def call(self, method, path, *, body=None, params=None, **kw):
        self.asked.append((self.project, method, path))
        if method == "GET":
            return {"value": []}
        return {"pullRequestId": 12, "repository": {"name": "api", "project": {"name": "Desk"}}}


@pytest.fixture
def asked(monkeypatch) -> list:
    calls: list = []
    monkeypatch.setattr(mod, "AzureDevOpsClient",
                        lambda **kw: _ProjectAwareClient(calls, kw.get("project")))
    return calls


@pytest.mark.parametrize("ref,project,repo", [
    ("Owner/api", "Desk", "api"),
    ("Docs/API", "Desk", "API"),
    ("Docs/web", "Docs", "web"),
])
def test_the_branches_of_a_ref_are_read_where_it_clones(asked, ref, project, repo):
    assert _forge().list_branches(ref) == []

    assert asked == [(project, "GET", f"git/repositories/{repo}/refs")]
    assert f"/{project}/_git/" in _forge().clone_url(ref, token="pat")


@pytest.mark.parametrize("ref,project", [("Owner/api", "Desk"), ("Docs/web", "Docs")])
def test_a_pull_request_of_a_ref_is_looked_up_and_opened_where_it_clones(asked, ref, project):
    _forge().open_pr(head="beeverforge/x", base="main", title="t", body="b", repo=ref)

    assert asked, "no call was made"
    assert {p for p, _m, _path in asked} == {project}, f"a call went to another project: {asked}"
    assert any(m == "POST" for _p, m, _path in asked), f"nothing was opened: {asked}"


# ---- the pipelines of a repository in another case (same sweep) --------------------------------

class _Pipelines:
    """One disabled YAML pipeline, its repository named as the server spells it."""

    def __init__(self, named: str):
        self.named = named

    def values(self, path, **kw):
        return [{"id": 7, "name": "ci", "queueStatus": "disabled"}]

    def call(self, method, path, **kw):
        return {"configuration": {"path": "/azure-pipelines.yml"},
                "repository": {"name": self.named}}


def _disabled(own: str, named: str, asked_for: str = "") -> list[str] | None:
    f = _forge(own)
    f._client = lambda: _Pipelines(named)
    return f.disabled_ci_paths(asked_for)


def test_a_pipeline_of_the_own_repository_in_another_case_is_its_own():
    assert _disabled("api", "API") == ["azure-pipelines.yml"]


def test_a_pipeline_of_the_own_repository_asked_for_in_another_case_is_its_own():
    assert _disabled("api", "api", asked_for="API") == ["azure-pipelines.yml"]


def test_a_pipeline_of_another_repository_is_still_not_its_own():
    assert _disabled("api", "web") == []


# ---- the delete and the pull-request reads go where the ref is cloned (#414's review) ----------

class _PullRequestClient:
    """Records `(project, method, path)` for every repository route and answers a PR of `repo`.

    `connectionData` is organisation-scoped (`project_scoped=False`), so it is not recorded: the
    project its client carries is not where the request goes."""

    def __init__(self, asked: list, project: str, repo: str):
        self.asked, self.project, self.repo = asked, project, repo

    def values(self, path, **kw):
        self.asked.append((self.project, "GET", path))
        return []

    def call(self, method, path, *, body=None, params=None, **kw):
        if path == "connectionData":
            return {"authenticatedUser": {"id": "me"}}
        self.asked.append((self.project, method, path))
        if path.endswith("/refs"):
            return {"value": [{"success": True, "updateStatus": "succeeded"}]}
        if path.endswith("/diffs/commits"):
            return {"changes": [{"changeType": "edit", "item": {"path": "/README.md"}}]}
        return {"pullRequestId": 5, "status": "active", "description": "d",
                "lastMergeSourceCommit": {"commitId": "b" * 40},
                "lastMergeTargetCommit": {"commitId": "a" * 40},
                "repository": {"name": self.repo, "project": {"name": self.project}}}


_REFS = [("Docs/web", "Docs", "web"), ("Owner/api", "Desk", "api")]


@pytest.fixture
def pr_asked(monkeypatch, request) -> list:
    calls: list = []
    repo = request.node.callspec.params["repo"]
    monkeypatch.setattr(mod, "AzureDevOpsClient",
                        lambda **kw: _PullRequestClient(calls, kw.get("project"), repo))
    return calls


@pytest.mark.parametrize("ref,project,repo", _REFS)
def test_a_branch_of_a_ref_is_deleted_where_it_clones(pr_asked, ref, project, repo):
    assert _forge().delete_branch("req/1", repo=ref) is True

    assert pr_asked == [(project, "POST", f"git/repositories/{repo}/refs")]
    assert f"/{project}/_git/{repo}" in _forge().clone_url(ref, token="pat")


@pytest.mark.parametrize("ref,project,repo", _REFS)
def test_a_pull_request_of_a_ref_is_read_where_it_clones(pr_asked, ref, project, repo):
    assert _forge().pr_status(pr="5", repo=ref) == "open"

    assert pr_asked == [(project, "GET", "git/pullrequests/5")]


@pytest.mark.parametrize("ref,project,repo", _REFS)
def test_a_pull_request_of_a_ref_is_merged_where_it_clones(pr_asked, ref, project, repo):
    _forge().merge_pr(pr="5", repo=ref)

    assert (project, "PATCH", f"git/repositories/{repo}/pullrequests/5") in pr_asked
    assert {p for p, _m, _path in pr_asked} == {project}, f"a call went elsewhere: {pr_asked}"


@pytest.mark.parametrize("ref,project,repo", _REFS)
def test_a_pull_request_description_of_a_ref_is_written_where_it_clones(pr_asked, ref, project,
                                                                         repo):
    assert _forge().set_pr_body(pr="5", body="new", repo=ref) is True

    assert (project, "PATCH", f"git/repositories/{repo}/pullrequests/5") in pr_asked
    assert {p for p, _m, _path in pr_asked} == {project}, f"a call went elsewhere: {pr_asked}"


@pytest.mark.parametrize("ref,project,repo", _REFS)
def test_a_pull_request_diff_of_a_ref_is_read_where_it_clones(pr_asked, ref, project, repo):
    assert "README.md" in (_forge().pr_diff(pr="5", repo=ref) or "")

    assert (project, "GET", f"git/repositories/{repo}/diffs/commits") in pr_asked
    assert {p for p, _m, _path in pr_asked} == {project}, f"a call went elsewhere: {pr_asked}"


def test_a_qualifier_padded_with_spaces_names_the_project_without_them():
    f = _forge()

    assert f._client_for("Docs /web").project == "Docs"
    assert f.clone_url("Docs /web", token="pat") == f"{URL}/Docs/_git/web"
