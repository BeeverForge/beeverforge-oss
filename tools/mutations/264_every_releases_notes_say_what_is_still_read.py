"""#264: every release's notes say what is still read under an OpenFactory 0.7 name, and until when.

The removal register stopped the release that drops a name from being cut with it still in, but
the notes said a name was kept only once. `scripts/release_notes.py` now closes every version's
"Upgrade notes" with an item made from the register (each entry's `said` and `removed_in`), read
with `ast`; a register it cannot read fails the preview and the assembly and warns on a page.
"""

TEST = "tests/test_every_releases_notes_say_what_is_still_read_under_an_old_name.py"
SCRIPT = "scripts/release_notes.py"
REGISTER = "beeverforge/deprecations.py"

MUTATIONS = [
    ("the item is never added", SCRIPT,
     '''        if name == "upgrade" and still:''',
     '''        if False:'''),

    ("the item opens no group of its own", SCRIPT,
     '''        if name == "upgrade" and still:''',
     '''        if name == "upgrade" and still and items:'''),

    ("the item comes first in its group", SCRIPT,
     '''            items.append(_still_read_item(still))''',
     '''            items.insert(0, _still_read_item(still))'''),

    ("the row drops its release", SCRIPT,
     '''    rows = "\\n".join(f"  - {said}: until {until}" for said, until in entries)''',
     '''    rows = "\\n".join(f"  - {said}" for said, until in entries)'''),

    ("the assembly leaves it out", SCRIPT,
     '''    notes = render(fragments, still)''',
     '''    notes = render(fragments)'''),

    ("a candidate's page leaves it out", SCRIPT,
     '''    print(render(fragments, still), end="")''',
     '''    print(render(fragments), end="")'''),

    ("an unreadable register fails no preview", SCRIPT,
     '''    if problem:
        print(problem, file=sys.stderr)
        return None''',
     '''    if problem:
        return []'''),

    ("an unreadable register is no warning on a page", SCRIPT,
     '''    for problem in [*problems, *([unreadable] if unreadable else [])]:''',
     '''    for problem in problems:'''),

    ("an entry that says nothing is read as one", SCRIPT,
     '''            if not (isinstance(said, str) and said.strip() and isinstance(until, str)):''',
     '''            if not isinstance(until, str):'''),

    ("a keyword that is no field is read", SCRIPT,
     '''                if keyword.arg not in _REMOVAL_FIELDS:''',
     '''                if False:'''),

    ("the register is imported, not read", SCRIPT,
     '''        module = ast.parse(register.read_text(encoding="utf-8"))''',
     '''        exec(compile(register.read_text(encoding="utf-8"), str(register), "exec"), {})
        module = ast.parse(register.read_text(encoding="utf-8"))'''),

    ("an entry says nothing to a reader", REGISTER,
     '''            said="the `openfactory` command, an alias of `beeverforge`"),''',
     '''            said=""),'''),
]
