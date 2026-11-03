"""#150: a GitHub organisation is one organisation however the registry spells it.

The claims, each held by one named test and broken here by one cut:
- `owners_by_project` groups owners by their casefold, so `Acme/api` and `acme/web` do not span
  (`spanning_installations`), `ProjectRegistry.list` logs no spanning warning, `project add`
  accepts the second project, and doctor's `installation_scope` line does not fail the registry;
- the organisation is named by the first spelling the registry holds, in an order that does not
  depend on hash order, and a project spelling it two ways is listed once;
- `_warn_foreign_pointers` compares a pointer's owner with the project's own without case.

Every row names the one test it must turn red, so a cut that some OTHER test happens to catch
does not pass for the guard that claims it.
"""

REGISTRY = "beeverforge/registry.py"

TEST = "tests/test_a_github_organisation_is_one_organisation_in_any_case.py"

_NO_CASEFOLD = ("            key = spelling.setdefault(owner.casefold(), owner)",
                "            key = spelling.setdefault(owner, owner)")

MUTATIONS = [
    # ── the grouping (registry.owners_by_project) ───────────────────────────────────────────────
    ("owners are grouped by spelling, so two spellings of one organisation span", REGISTRY,
     *_NO_CASEFOLD,
     f"{TEST}::test_two_spellings_of_one_organisation_do_not_span"),

    ("owners are grouped by spelling, so `list` logs a false spanning warning", REGISTRY,
     *_NO_CASEFOLD,
     f"{TEST}::test_list_logs_no_spanning_warning_for_two_spellings"),

    ("owners are grouped by spelling, so `project add` refuses the second project", REGISTRY,
     *_NO_CASEFOLD,
     f"{TEST}::test_project_add_accepts_the_same_organisation_spelled_differently"),

    ("owners are grouped by spelling, so doctor's installation_scope line fails", REGISTRY,
     *_NO_CASEFOLD,
     f"{TEST}::test_doctor_installation_scope_does_not_fail_two_spellings"),

    ("the last spelling met replaces the first one as the organisation's name", REGISTRY,
     "            key = spelling.setdefault(owner.casefold(), owner)",
     "            key = spelling[owner.casefold()] = owner",
     f"{TEST}::test_the_sentence_names_the_organisation_by_its_first_spelling"),

    ("a project's owners are walked in the other order, so its first spelling changes", REGISTRY,
     "        for owner in sorted(github_owners(project)):",
     "        for owner in sorted(github_owners(project), reverse=True):",
     f"{TEST}::test_one_project_spelling_its_organisation_two_ways_is_listed_once"),

    ("a project spelling its organisation two ways is listed twice", REGISTRY,
     "            if project.name not in names:",
     "            if True:",
     f"{TEST}::test_one_project_spelling_its_organisation_two_ways_is_listed_once"),

    # ── the foreign pointers (ProjectRegistry._warn_foreign_pointers) ──────────────────────────
    ("a factory board in the same organisation, spelled differently, is warned as foreign",
     REGISTRY,
     "            if owner and owner.casefold() not in same:",
     "            if owner and owner not in mine:",
     f"{TEST}::test_a_factory_board_in_the_same_organisation_spelled_differently_is_not_foreign"),

    ("the project's own owners are compared by spelling", REGISTRY,
     "        same = {owner.casefold() for owner in mine}",
     "        same = set(mine)",
     f"{TEST}::test_a_factory_board_in_the_same_organisation_spelled_differently_is_not_foreign"),
]
