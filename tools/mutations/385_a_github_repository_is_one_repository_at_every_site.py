"""#385: a GitHub repository typed in another case is one repository at four more sites.

Every site gets three cuts, as plan 380 gave its own: the comparison put back to spelling; a fold
of one side only, aimed at a test where the registry holds the capitals (with the registry in
lowercase such a fold passes every other test); and the comparison dropped, so every repository
matches, aimed at the twin where the repository really is another.

The card checkout has two comparisons in its Azure DevOps branch, the name's leaf and its
qualifier, and each gets its own cuts. The product module labels its own mount on two lines, one
for a mounted source and one for a missing one, and each line gets the three cuts; their anchors
carry the text in front of `own=`, because the folded comparison is the same on both.
"""

TEST = "tests/test_a_github_repository_is_one_repository_at_every_site.py"
PAGE = "beeverforge/product/page.py"
CHECKOUT = "beeverforge/runtime/card_repo.py"
CATALOG = "beeverforge/actions/catalog.py"
MODULE = "beeverforge/product/module.py"

_PAGE = "    if repo.casefold() != mine.casefold():     # GitHub names ignore case (#385)\n"
_DEFAULT = "    if not repo or repo.casefold() == default.casefold():     # names ignore case (#385)\n"
_LEAF = '            and repo.rsplit("/", 1)[-1].casefold() == default.casefold():\n'
_QUALIFIER = '        qualifier = repo.rsplit("/", 1)[0].casefold()\n'
_MEMBERS = "        return qualifier in {q.casefold() for q in (tracker_repo, forge_project) if q}\n"
_BETWEEN = ('        tracker_repo = (project.tracker.repo or "") '
            'if getattr(project, "tracker", None) else ""\n'
            '        forge_project = ""\n'
            '        forge = getattr(project, "forge", None)\n'
            '        if forge is not None:\n'
            '            forge_project = str((getattr(forge, "options", None) or {})'
            '.get("project", ""))\n')
_AXIS = '                    and (want.repo or "").casefold() == (have.repo or "").casefold()\n'
_MOUNTED = ("path=os.path.relpath(path, root),\n"
            "                             own=repo.casefold() == own.casefold(),")
_MISSING = "why=why, own=repo.casefold() == own.casefold())"

MUTATIONS = [
    # ── the product page ─────────────────────────────────────────────────────────────────────────
    ("the page compares by spelling, so the project's own card typed `Acme/api#42` is refused",
     PAGE, _PAGE, "    if repo != mine:\n",
     f"{TEST}::test_a_card_of_the_projects_repository_typed_otherwise_is_its_own"),
    ("the page folds the typed card only, so a registry in capitals refuses its own card",
     PAGE, _PAGE, "    if repo.casefold() != mine:\n",
     f"{TEST}::test_a_registry_in_capitals_takes_its_own_card_typed_in_lowercase"),
    ("the page stops comparing repositories, so another repository's card is read as its own",
     PAGE, _PAGE, "    if False:\n",
     f"{TEST}::test_a_card_of_another_repository_is_still_refused"),

    # ── the card checkout: the default repository ────────────────────────────────────────────────
    ("the checkout compares by spelling, so its own repository typed otherwise is foreign",
     CHECKOUT, _DEFAULT, "    if not repo or repo == default:\n",
     f"{TEST}::test_a_card_of_the_default_repository_typed_otherwise_checks_out_under_the_projects_key"),
    ("the checkout folds the ref only, so a registry in capitals files its own card as foreign",
     CHECKOUT, _DEFAULT, "    if not repo or repo.casefold() == default:\n",
     f"{TEST}::test_a_registry_in_capitals_checks_out_its_own_card_typed_in_lowercase"),
    ("the checkout takes every repository for the default, so a foreign one shares its key",
     CHECKOUT, _DEFAULT, "    if not repo or True:\n",
     f"{TEST}::test_a_card_of_another_repository_is_still_foreign_in_any_case"),

    # ── the card checkout: the Azure DevOps leaf ─────────────────────────────────────────────────
    ("the Azure leaf compares by spelling, so `DeskLine/FX-ADO` is not the bare `fx-ado`",
     CHECKOUT, _LEAF, '            and repo.rsplit("/", 1)[-1] == default:\n',
     f"{TEST}::test_an_ado_qualified_default_typed_otherwise_keys_to_the_project_name"),
    ("the Azure leaf folds the ref only, so a registry `FX-Ado` is not its own `fx-ado`",
     CHECKOUT, _LEAF, '            and repo.rsplit("/", 1)[-1].casefold() == default:\n',
     f"{TEST}::test_an_ado_registry_in_capitals_keys_its_own_lowercase_ref_to_the_project_name"),
    ("the Azure leaf stops comparing, so `Deskline/other-repo` is the default repository",
     CHECKOUT, _LEAF, "            and True:\n",
     f"{TEST}::test_an_ado_repository_of_another_project_or_name_is_still_foreign"),

    # ── the card checkout: the Azure DevOps qualifier ────────────────────────────────────────────
    ("the Azure qualifier compares by spelling, so `DeskLine` is not the project `Deskline`",
     CHECKOUT, _QUALIFIER + _BETWEEN + _MEMBERS,
     '        qualifier = repo.rsplit("/", 1)[0]\n' + _BETWEEN
     + "        return qualifier in {q for q in (tracker_repo, forge_project) if q}\n",
     f"{TEST}::test_an_ado_qualified_default_typed_otherwise_keys_to_the_project_name"),
    ("the Azure qualifier folds the ref only, so a registry `DeskLine` is not its own `deskline`",
     CHECKOUT, _MEMBERS,
     "        return qualifier in {q for q in (tracker_repo, forge_project) if q}\n",
     f"{TEST}::test_an_ado_registry_in_capitals_keys_its_own_lowercase_ref_to_the_project_name"),
    ("the Azure qualifier folds the registry only, so a ref `DeskLine/…` is not its project's",
     CHECKOUT, _QUALIFIER, '        qualifier = repo.rsplit("/", 1)[0]\n',
     f"{TEST}::test_an_ado_qualified_default_typed_otherwise_keys_to_the_project_name"),
    ("the Azure qualifier stops comparing, so `OtherProject/fx-ado` is the default repository",
     CHECKOUT, _MEMBERS, "        return True\n",
     f"{TEST}::test_an_ado_repository_of_another_project_or_name_is_still_foreign"),

    # ── project add, again ───────────────────────────────────────────────────────────────────────
    ("project add compares by spelling, so `Acme/api` over `acme/api` is a conflict",
     CATALOG, _AXIS, "                    and want.repo == have.repo\n",
     f"{TEST}::test_adding_again_with_the_repository_typed_otherwise_changes_nothing"),
    ("project add folds what was asked only, so a registry `Acme/API` conflicts with `acme/api`",
     CATALOG, _AXIS, '                    and (want.repo or "").casefold() == have.repo\n',
     f"{TEST}::test_a_registry_in_capitals_is_not_different_from_its_lowercase_address"),
    ("project add stops comparing repositories, so another repository is registered as asked",
     CATALOG, _AXIS, "                    and True\n",
     f"{TEST}::test_adding_again_with_another_repository_is_still_refused"),

    # ── the product module: a mounted source ─────────────────────────────────────────────────────
    ("a mounted source is compared by spelling, so `Acme/API` is not the project's own mount",
     MODULE, _MOUNTED,
     "path=os.path.relpath(path, root),\n                             own=repo == own,",
     f"{TEST}::test_a_source_spelling_the_projects_own_repository_otherwise_is_its_own_mount"),
    ("a mounted source folds its own side only, so a registry in capitals loses its own mount",
     MODULE, _MOUNTED,
     "path=os.path.relpath(path, root),\n                             own=repo.casefold() == own,",
     f"{TEST}::test_a_registry_in_capitals_labels_its_lowercase_mounted_source_its_own"),
    ("every mounted source is the project's own",
     MODULE, _MOUNTED,
     "path=os.path.relpath(path, root),\n                             own=True,",
     f"{TEST}::test_a_source_spelling_the_projects_own_repository_otherwise_is_its_own_mount"),

    # ── the product module: a missing source ─────────────────────────────────────────────────────
    ("a missing source is compared by spelling, so `acme/api` is not a registry `Acme/API`'s own",
     MODULE, _MISSING, "why=why, own=repo == own)",
     f"{TEST}::test_a_registry_in_capitals_labels_its_lowercase_missing_source_its_own"),
    ("a missing source folds its own side only, so a registry in capitals loses its own mount",
     MODULE, _MISSING, "why=why, own=repo.casefold() == own)",
     f"{TEST}::test_a_registry_in_capitals_labels_its_lowercase_missing_source_its_own"),
    ("every missing source is the project's own",
     MODULE, _MISSING, "why=why, own=True)",
     f"{TEST}::test_a_source_spelling_the_projects_own_repository_otherwise_is_its_own_mount"),
]
