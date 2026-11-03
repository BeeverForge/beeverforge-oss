"""#399: an Azure DevOps repository typed in another case is the adapter's own repository.

It follows #380 / PR #388. Two sites compared a ref's repository by spelling: the forge's
`clone_url` (is this the adapter's own repository, so its project qualifier is ignored?) and the
Boards tracker's `_area_for` (which area does the `areas` map give this repository?).

For each site: one cut puts the comparison back to spelling; two fold only one side, each aimed
at the test where the OTHER side has the capitals (a one-sided fold passes whenever the unfolded
side is already lowercase); two drop the comparison, one each way: every ref treated as the own
repository (or matched to the first area), and none of them.
"""

TEST = "tests/test_an_azure_ref_naming_its_own_repository_in_another_case_stays_in_its_project.py"
FORGE = "beeverforge/adapters/forge/azure_devops.py"
TRACKER = "beeverforge/adapters/tracker/azure_devops.py"

_OWN = "        own = name.casefold() == self.repo.casefold()\n"
_AREA = '                     if r.rsplit("/", 1)[-1].casefold() == leaf.casefold()), leaf)\n'

MUTATIONS = [
    ("the forge compares by spelling, so `Docs/API` for `api` clones from `Docs`", FORGE,
     _OWN, "        own = name == self.repo\n",
     f"{TEST}::test_a_ref_naming_the_own_repository_in_another_case_clones_from_the_own_project"),

    ("the forge folds the ref only, so an adapter of `API` asked for `Docs/api` clones from `Docs`",
     FORGE, _OWN, "        own = name.casefold() == self.repo\n",
     f"{TEST}::test_an_adapter_whose_own_name_has_the_capitals_stays_in_its_project"),

    ("the forge folds its own name only, so `Docs/API` for `api` clones from `Docs`", FORGE,
     _OWN, "        own = name == self.repo.casefold()\n",
     f"{TEST}::test_a_ref_naming_the_own_repository_in_another_case_clones_from_the_own_project"),

    ("the forge obeys every qualifier, so its own repository is cloned from `Docs`", FORGE,
     _OWN, "        own = False\n",
     f"{TEST}::test_a_ref_naming_the_own_repository_in_another_case_clones_from_the_own_project"),

    ("the forge ignores every qualifier, so `Docs/web` is cloned from `Desk`", FORGE,
     _OWN, "        own = True\n",
     f"{TEST}::test_a_ref_naming_another_repository_still_obeys_its_project"),

    ("the tracker compares by spelling, so `acme/API` falls out of the area mapped to `acme/api`",
     TRACKER, _AREA, '                     if r.rsplit("/", 1)[-1] == leaf), leaf)\n',
     f"{TEST}::test_a_ref_in_another_case_is_filed_under_its_area"),

    ("the tracker folds the ref only, so a map naming `acme/API` misses `acme/api`", TRACKER,
     _AREA, '                     if r.rsplit("/", 1)[-1] == leaf.casefold()), leaf)\n',
     f"{TEST}::test_an_areas_map_with_the_capitals_files_a_lowercase_ref_under_its_area"),

    ("the tracker folds the map only, so `acme/API` misses the area mapped to `acme/api`", TRACKER,
     _AREA, '                     if r.rsplit("/", 1)[-1].casefold() == leaf), leaf)\n',
     f"{TEST}::test_a_ref_in_another_case_is_filed_under_its_area"),

    ("the tracker matches every repository, so `acme/web` is filed under the first area", TRACKER,
     _AREA, "                     if True), leaf)\n",
     f"{TEST}::test_another_repository_still_gets_its_own_area_or_the_default"),

    ("the tracker matches no repository, so every card goes under its leaf name", TRACKER,
     _AREA, "                     if False), leaf)\n",
     f"{TEST}::test_a_ref_in_another_case_is_filed_under_its_area"),
]
