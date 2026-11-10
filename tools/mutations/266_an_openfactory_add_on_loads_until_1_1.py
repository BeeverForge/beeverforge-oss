"""#266: an OpenFactory 0.7 add-on, declared under `openfactory.adapters`, still loads until 1.1.

The defect was the rename's: only `beeverforge.adapters` was scanned, so every 0.7 add-on vanished
on an upgrade in place. Each row below undoes one part of reading the old group: not reading it,
letting it override the new group, losing it from the list a supervisor reads, leaving it out of
the doctor's list, or saying nothing, or saying it on every load.
"""

PLUGINS = "beeverforge/plugins.py"

TEST = "tests/test_an_openfactory_add_on_loads_until_1_1.py"
LOADED = TEST + "::test_a_row_declared_only_under_the_0_7_group_is_built_and_listed"
BOTH = TEST + "::test_a_name_both_groups_declare_is_the_new_groups_row"
ONCE = TEST + "::test_the_distribution_on_the_old_group_is_named_once_per_process"
QUIET = TEST + "::test_nothing_is_said_when_no_add_on_is_on_the_old_group"

MUTATIONS = [
    ("THE FINDING: the 0.7 group is not scanned", PLUGINS,
     "    former = [p for p in entry_points(group=FORMER_GROUP) if p.name not in taken]",
     "    former = []", LOADED),

    ("the 0.7 group's row overrides the new group's for the same name", PLUGINS,
     "    return [(p, GROUP) for p in current] + [(p, FORMER_GROUP) for p in former]",
     "    former = list(entry_points(group=FORMER_GROUP))\n"
     "    return [(p, GROUP) for p in current] + [(p, FORMER_GROUP) for p in former]", BOTH),

    ("a name both groups declare is listed twice", PLUGINS,
     "    taken = {p.name for p in current}",
     "    taken = set()", BOTH),

    ("the doctor's list leaves the old group's rows out", PLUGINS,
     "                   for p, g in points if g == FORMER_GROUP),",
     "                   for p, g in points if g == GROUP),", LOADED),

    ("nothing is said about a package still on the old group", PLUGINS,
     "    _warn_former(points)\n", "", ONCE),

    ("it is said on every load, not once per process", PLUGINS,
     "    _REPORTED_FORMER.update(names)\n", "", ONCE),

    ("a package on the new group is named as if it were on the old one", PLUGINS,
     "    names = sorted({_distribution(p) or p.name for p, g in points if g == FORMER_GROUP}",
     "    names = sorted({_distribution(p) or p.name for p, g in points}", QUIET),
]
