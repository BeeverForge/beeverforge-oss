"""The requirement writers strip comments in time linear in a value's size (#322, after #76).

`authoring.py` checked, dropped and accepted a requirement with `re.sub(r"<!--.*?-->", "", value)`
on its Status, Asked by and Date values, which searched for a close from every `<!--` to the end of
the value: n unclosed openings cost n². Each row below puts one site back the way it was, and the
guard, which records the values each writer hands to the reader's helper, must go red.
"""

TEST = "tests/test_the_writers_strip_comments_in_time_linear_in_its_size.py"

_AUTHORING = "beeverforge/product/authoring.py"

MUTATIONS = [
    ("the dropped check strips the Status comment with `<!--.*?-->` again",
     _AUTHORING,
     '    value = _without_comments(m.group("value") if m else "").strip().lower()',
     '    value = re.sub(r"<!--.*?-->", "", m.group("value") if m else "").strip().lower()'),

    ("the drop strips the Status comment with `<!--.*?-->` again",
     _AUTHORING,
     '    value = _without_comments(raw).strip().lower()\n'
     '    word = value.split()[0] if value else ""\n'
     '    if word == DROPPED:',
     '    value = re.sub(r"<!--.*?-->", "", raw).strip().lower()\n'
     '    word = value.split()[0] if value else ""\n'
     '    if word == DROPPED:'),

    ("the accept strips the Status comment with `<!--.*?-->` again",
     _AUTHORING,
     '    value = _without_comments(raw).strip().lower()\n'
     '    word = value.split()[0] if value else ""\n'
     '    if word.startswith("accepted"):',
     '    value = re.sub(r"<!--.*?-->", "", raw).strip().lower()\n'
     '    word = value.split()[0] if value else ""\n'
     '    if word.startswith("accepted"):'),

    ("the accept strips an existing Asked by or Date comment with `<!--.*?-->` again",
     _AUTHORING,
     '        existing = _without_comments(pattern.match(lines[j]).group("value")).strip()',
     '        existing = re.sub(r"<!--.*?-->", "", pattern.match(lines[j]).group("value")).strip()'),
]
