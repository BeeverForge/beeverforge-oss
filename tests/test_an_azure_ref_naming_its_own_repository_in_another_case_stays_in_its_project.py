"""#399: an Azure DevOps repository typed in another case is still the adapter's own repository.

Azure DevOps reads repository and project names without case. `AzureReposForge.clone_url` obeys
a `project/repo` qualifier only when the ref names a DIFFERENT repository; it compared the names
by spelling, so `Docs/API` for an adapter of `api` in `Desk` cloned from `Docs`. The Boards
tracker's `_area_for` matched the `areas` map against the ref's leaf by spelling too, so a card of
`API` fell out of the area mapped to `api`. Both now compare without case and keep the spelling
they were given for anything they return.
"""

from beeverforge.adapters.forge.azure_devops import AzureReposForge
from beeverforge.adapters.tracker.azure_devops import AzureBoardsTracker


def _forge(repo: str) -> AzureReposForge:
    return AzureReposForge(repo, organization="acme", project="Desk", token="pat")


def _tracker(areas: dict[str, str]) -> AzureBoardsTracker:
    return AzureBoardsTracker(organization="acme", project="Desk", client=object(),
                              options={"areas": areas})


# ---- the forge's clone URL ---------------------------------------------------------------------

def test_a_ref_naming_the_own_repository_in_another_case_clones_from_the_own_project():
    assert (_forge("api").clone_url("Docs/API", token="pat")
            == "https://beeverforge:pat@dev.azure.com/acme/Desk/_git/API")


def test_an_adapter_whose_own_name_has_the_capitals_stays_in_its_project():
    assert (_forge("API").clone_url("Docs/api", token="pat")
            == "https://beeverforge:pat@dev.azure.com/acme/Desk/_git/api")


def test_a_ref_naming_another_repository_still_obeys_its_project():
    assert (_forge("api").clone_url("Docs/web", token="pat")
            == "https://beeverforge:pat@dev.azure.com/acme/Docs/_git/web")


# ---- the tracker's area -------------------------------------------------------------------------

def test_a_ref_in_another_case_is_filed_under_its_area():
    assert _tracker({"Portal": "acme/api"})._area_for("acme/API") == "Desk\\Portal"


def test_an_areas_map_with_the_capitals_files_a_lowercase_ref_under_its_area():
    assert _tracker({"Portal": "acme/API"})._area_for("acme/api") == "Desk\\Portal"


def test_another_repository_still_gets_its_own_area_or_the_default():
    tracker = _tracker({"Portal": "acme/api", "Site": "acme/web"})
    assert tracker._area_for("acme/web") == "Desk\\Site"
    assert tracker._area_for("acme/Docs") == "Desk\\Docs"
