"""The people who may act on a product, as one list — `product_people_set` and `_list` (#528).

`product.admins` and `product.engineers` are two lists in the registry; a caller says them as ONE
list of `{person, role}` so that a person is never in both by a half-finished edit, and one left
out is removed. This module is the pure part: reading what was asked, and the digest that names a
state of the lists. It writes nothing.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Any

#: the roles whose lists the core reads today, each with the `product:` key that holds it. The
#: ADR-0057 roles map is its own work.
ROLES: dict[str, str] = {"admin": "admins", "engineer": "engineers"}

#: how many people one call may name — a list, not a directory
BOUND = 1000

#: the longest id one entry may carry; the identity provider's ids are far shorter
ID_BOUND = 256


def digest(admins: Sequence[str], engineers: Sequence[str]) -> str:
    """The sha256 of the two lists as a set of people, by role — the same for any order they were
    given in, and never a prefix of it. Carries ids, never a credential."""
    body = json.dumps({"admins": sorted(set(admins)), "engineers": sorted(set(engineers))},
                      sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(body.encode("ascii")).hexdigest()


def moved(held: Sequence[str], new: Sequence[str]) -> dict[str, list[str]]:
    """What a set changes in one role's list: who is added, removed and kept."""
    return {"added": [p for p in new if p not in held],
            "removed": [p for p in held if p not in new],
            "unchanged": [p for p in new if p in held]}


def _unfit(who: object) -> str:
    """Why an id cannot be a person's, or "" — an id is stored AS GIVEN, so what cannot be said
    plainly in a log line or a file (an empty one, a long one, a control character) is refused,
    and so is whitespace: an id is never trimmed, so a padded one is one authz never matches."""
    if not isinstance(who, str) or not who.strip():
        return "has no person"
    if len(who) > ID_BOUND:
        return f"has a person longer than {ID_BOUND} characters"
    if any(unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp") for c in who):
        return "has a person with a control character in it"
    if any(c.isspace() for c in who):
        return "has a person with whitespace in it; give the id exactly as the provider has it"
    return ""


def read(people: object) -> tuple[list[str], list[str], str]:
    """`(admins, engineers, "")` for a list that is well formed, or `([], [], why)` naming the
    entry that is not — the first one, by its place in the list."""
    if not isinstance(people, list):
        return [], [], "`people` is a list of {person, role} entries"
    if len(people) > BOUND:
        return [], [], f"`people` names {len(people)} people; at most {BOUND} in one call"
    lists: dict[str, list[str]] = {role: [] for role in ROLES}
    seen: dict[str, str] = {}
    for place, entry in enumerate(people, 1):
        if not isinstance(entry, dict) or set(entry) - {"person", "role"}:
            return [], [], f"entry {place} is not a {{person, role}} pair"
        who, role = entry.get("person"), entry.get("role")
        unfit = _unfit(who)
        if unfit:
            return [], [], f"entry {place} {unfit}"
        assert isinstance(who, str)
        if role not in ROLES:
            return [], [], (f"entry {place} ({who!r}) has the role {role!r}; "
                            f"one of {', '.join(ROLES)}")
        if who in seen:
            return [], [], (f"entry {place} ({who!r}) is a person already listed as "
                            f"{seen[who]!r} — a person has one role")
        seen[who] = role
        lists[role].append(who)
    return lists["admin"], lists["engineer"], ""


def loggable(people: object, changed: Mapping[str, Any] | None = None) -> str:
    """What the audit line says of a `people` parameter: how many, per role, the digest, and —
    once the set is done — the person ids it added and removed. A person id is not a credential;
    it is who was changed, which is what the record is for. A list that does not read is said as
    such; the refusal names why."""
    admins, engineers, why = read(people)
    if why:
        return "<a list that does not read>"
    line = (f"{len(admins)} admins, {len(engineers)} engineers, "
            f"digest {digest(admins, engineers)}")
    for role, said in (changed or {}).items():
        line += f"; {role} added {said['added']} removed {said['removed']}"
    return f"<{line}>"
