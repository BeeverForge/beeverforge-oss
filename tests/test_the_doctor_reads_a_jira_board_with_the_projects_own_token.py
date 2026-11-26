"""The doctor reads a Jira board with the token the project names, not only `JIRA_API_TOKEN` (#737).

`doctor` built its board, intake, stages and budget probes with a `token_provider` only, and the
Jira row reads a caller's `token=` or, failing that, the vendor's own default variable — never the
provider. So on a Jira project whose `tracker.options.token_env` names its credential, the probes
asked the site anonymously, and `board_columns` FAILED with "check that <TOKEN_ENV> is set" over a
variable that was set and valid. It passed wherever `JIRA_API_TOKEN` also happened to be in the
environment (a `.env` file), which is why it hid on most machines.

The poller and `cli.py` resolve the token first (`tracker_token_for(project)`) and hand it in as
`token=`; the doctor now does the same, so it reads the board with the credential the poller uses.

Deterministic on any machine: `JIRA_API_TOKEN` is removed and `PYTHON_DOTENV_DISABLED` is set, so
nothing but the project's own variable can reach the site.
"""

from __future__ import annotations

import base64
import io
import json
import urllib.error

import pytest

from beeverforge.contracts.project import Project, ProviderRef
from beeverforge.doctor import probes_for

TOKEN_ENV = "ACME_JIRA_TOKEN"
TOKEN = "jira-token-of-acme"
EMAIL = "alice@acme.ai"
STATUSES = ["A Fazer", "Em andamento", "Concluído"]


class _Answer:
    def __init__(self, payload) -> None:
        self._body = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> bool:
        return False

    def read(self) -> bytes:
        return self._body


def _site(req, timeout=0):  # noqa: ARG001 — urllib's own signature
    """A Jira Cloud site that answers only the account's own Basic pair, as a real one does: an
    anonymous or wrong-token request is a 401, never the project's statuses."""
    expected = "Basic " + base64.b64encode(f"{EMAIL}:{TOKEN}".encode()).decode()
    if req.get_header("Authorization") != expected:
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", hdrs=None,
                                     fp=io.BytesIO(b'{"errorMessages": ["unauthorized"]}'))
    path = req.full_url.split("/rest/api/3/", 1)[1].split("?")[0]
    if path == "project/DAR/statuses":
        return _Answer([{"name": "Task", "statuses": [{"name": n} for n in STATUSES]}])
    raise AssertionError(f"the doctor called {req.full_url}, a route this test does not serve")


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A Jira project whose credential is named by `token_env`, stored under that name, and NO
    `JIRA_API_TOKEN` anywhere — the shape the issue reported."""
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    monkeypatch.setenv(TOKEN_ENV, TOKEN)
    monkeypatch.setattr("urllib.request.urlopen", _site)
    return Project(name="acme", repo_path=str(tmp_path), tracker=ProviderRef(
        kind="jira", repo="DAR", options={
            "site": "https://acme-team.atlassian.net", "project_key": "DAR", "email": EMAIL,
            "token_env": TOKEN_ENV,
            "status_map": json.dumps({"todo": "A Fazer", "in_progress": "Em andamento",
                                      "done": "Concluído"}),
        }))


def test_THE_REPORT_board_columns_reads_the_board_with_the_token_env_credential(project):
    """The probe the issue quoted: it FAILED as unreadable, with the variable set and valid."""
    assert probes_for(project).board_columns() == STATUSES


@pytest.mark.parametrize("probe", [
    "board_columns", "pickup_column", "board_intake", "board_stages", "api_budget"])
def test_every_board_and_tracker_probe_hands_the_tracker_the_projects_own_token(
        project, monkeypatch, probe):
    """Each probe builds its own board or tracker, so each is asked on its own: the token every
    Jira tracker the probe builds carries is the one `token_env` names, never None."""
    from beeverforge.adapters.tracker.jira import JiraTracker

    carried: list[str | None] = []
    real = JiraTracker.__init__

    def _spy(self, *a, **kw):
        carried.append(kw.get("token"))
        real(self, *a, **kw)

    monkeypatch.setattr(JiraTracker, "__init__", _spy)
    try:
        getattr(probes_for(project), probe)()
    except Exception:  # noqa: BLE001 — what the probe concluded is not the question here
        pass

    assert carried, f"{probe} built no Jira tracker, so it asked nothing of this project's board"
    assert set(carried) == {TOKEN}, f"{probe} reached the tracker with {carried!r}"
