"""#410: an Azure DevOps ref qualified with the wrong project reads its API where it clones.

Run:  .venv/bin/python tools/mutate.py tools/mutations/410_an_azure_ref_qualified_with_the_wrong_project_reads_where_it_clones.py

`clone_url` and `_client_for` both pick a ref's project through `_project_for`, which ignores the
qualifier when the ref names the adapter's own repository (compared without case, #399). Row 1 is
the defect as it shipped: `_client_for` obeys every qualifier again, so `Owner/api` is read in
`Owner`. Row 2 puts the shared rule back to spelling. Rows 3 and 4 drop it, one each way: every
qualifier obeyed, and none.

Found in the same sweep: `disabled_ci_paths` matched a pipeline's repository by spelling. Row 5
puts it back to spelling; rows 6 and 7 fold one side only, each aimed at the test where the OTHER
side has the capitals; rows 8 and 9 drop the comparison, one each way.
"""

TEST = "tests/test_an_azure_ref_qualified_with_the_wrong_project_reads_where_it_clones.py"
FORGE = "beeverforge/adapters/forge/azure_devops.py"

_CLIENT = "        where = self._project_for(repo)\n"
_OWN = "        own = name.casefold() == self.repo.casefold()\n"
_PIPELINE = ("            if path and (not named or str(named).casefold() == target.casefold()):"
             "\n")

MUTATIONS = [
    ("TODAY'S DEFECT: `_client_for` obeys the qualifier, so `Owner/api` is read in `Owner`", FORGE,
     _CLIENT,
     '        where = (repo or "").strip().strip("/").rpartition("/")[0].strip() or self.project\n',
     f"{TEST}::test_a_misconfigured_owner_ref_clones_and_reads_in_the_own_project"),

    ("the shared rule compares by spelling, so `Docs/API` for `api` is read in `Docs`", FORGE,
     _OWN, "        own = name == self.repo\n",
     f"{TEST}::test_a_ref_naming_the_own_repository_in_another_case_reads_and_clones_in_the_own_project"),

    ("the shared rule is dropped so every qualifier is obeyed: `Owner/api` is read in `Owner`",
     FORGE, _OWN, "        own = False\n",
     f"{TEST}::test_a_misconfigured_owner_ref_clones_and_reads_in_the_own_project"),

    ("the shared rule is dropped so no qualifier is obeyed: `Docs/web` is read in `Desk`", FORGE,
     _OWN, "        own = True\n",
     f"{TEST}::test_a_ref_naming_another_repository_reads_and_clones_in_the_project_it_names"),

    ("the pipelines compare by spelling, so a pipeline of `API` is not `api`'s", FORGE,
     _PIPELINE, "            if path and (not named or str(named) == target):\n",
     f"{TEST}::test_a_pipeline_of_the_own_repository_in_another_case_is_its_own"),

    ("the pipelines fold the asked-for repository only, so a pipeline of `API` is not `api`'s",
     FORGE, _PIPELINE,
     "            if path and (not named or str(named) == target.casefold()):\n",
     f"{TEST}::test_a_pipeline_of_the_own_repository_in_another_case_is_its_own"),

    ("the pipelines fold the pipeline's repository only, so `api`'s is not `API`'s", FORGE,
     _PIPELINE,
     "            if path and (not named or str(named).casefold() == target):\n",
     f"{TEST}::test_a_pipeline_of_the_own_repository_asked_for_in_another_case_is_its_own"),

    ("the pipelines match every repository, so another repository's pipeline is its own", FORGE,
     _PIPELINE, "            if path:\n",
     f"{TEST}::test_a_pipeline_of_another_repository_is_still_not_its_own"),

    ("the pipelines match no named repository, so its own pipeline is dropped", FORGE,
     _PIPELINE, "            if path and not named:\n",
     f"{TEST}::test_a_pipeline_of_the_own_repository_in_another_case_is_its_own"),
]
