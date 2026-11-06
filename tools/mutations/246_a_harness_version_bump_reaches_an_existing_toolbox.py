"""A harness version bump reaches a deployment that already has a toolbox (#246).

Run:  .venv/bin/python tools/mutate.py \
        tools/mutations/246_a_harness_version_bump_reaches_an_existing_toolbox.py

Row 1 is the defect as it shipped: a populated stamp of the right variant is taken as current
whatever the versions. Row 2 is the boot not handing its source over, so the check never compares.
Row 3 stops recording the versions. Row 4 takes a stamp written before versions were recorded as
current. Row 5 stops reading scoped packages, which is where `claude` lives. Rows 6-7 break the
proof's line: no versions printed, and no word when none were recorded.
"""

TEST = "tests/test_a_harness_version_bump_reaches_an_existing_toolbox.py"

TB = "beeverforge/runtime/toolbox.py"
PROVE = "beeverforge/box_prove.py"

MUTATIONS = [
    ("TODAY'S DEFECT: a populated toolbox of the right variant is current whatever its versions", TB,
     '        return stamp.get("packages") == packages(source)\n',
     "        return True\n"),

    ("the boot checks the live stamp without the baked source", TB,
     "    if not force and is_populated(dst, source=src):\n",
     "    if not force and is_populated(dst):\n"),

    ("the stamp records no versions", TB,
     '    stamp = {"variant": variant(), "harnesses": harnesses, "packages": packages(src)}\n',
     '    stamp = {"variant": variant(), "harnesses": harnesses, "packages": {}}\n'),

    ("a stamp written before versions were recorded is taken as current", TB,
     '        return stamp.get("packages") == packages(source)\n',
     '        return stamp.get("packages", packages(source)) == packages(source)\n'),

    ("scoped packages are not read", TB,
     '        dirs = sorted(entry.iterdir()) if entry.name.startswith("@") and entry.is_dir() else [entry]\n',
     "        dirs = [entry]\n"),

    ("the proof prints no versions", PROVE,
     '                                          f"{variant} — {harnesses} ({recorded})"))',
     '                                          f"{variant} — {harnesses}"))'),

    ("the proof says nothing when no version was recorded", PROVE,
     '            recorded = versions(stamp) or "versions not recorded"\n',
     '            recorded = versions(stamp)\n'),
]
