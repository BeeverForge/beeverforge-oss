"""The people who may act on a product, as one list — `product_people_set` and `_list` (#528).

`product.admins` and `product.engineers` are two lists in the registry; a caller says them as ONE
list of `{id, role}` so that a person is never in both by a half-finished edit, and a person left
out is removed. This module is the pure part: reading what was asked, and the digest that names a
state of the lists. It writes nothing.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence

#: the roles whose lists the core reads today, each with the `product:` key that holds it. The
#: ADR-0057 roles map is its own work.
ROLES: dict[str, str] = {"admin": "admins", "engineer": "engineers"}

#: how many people one call may name — a list, not a directory
BOUND = 200


def digest(admins: Sequence[str], engineers: Sequence[str]) -> str:
    """The sha256 of the two lists as a set of people, by role — the same for any order they were
    given in, and never a prefix of it. Carries ids, never a credential."""
    body = json.dumps({"admins": sorted(set(admins)), "engineers": sorted(set(engineers))},
                      sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(body.encode("ascii")).hexdigest()


def read(people: object) -> tuple[list[str], list[str], str]:
    """`(admins, engineers, "")` for a list that is well formed, or `([], [], why)` naming the
    entry that is not — the first one, by its place in the list."""
    if not isinstance(people, list):
        return [], [], "`people` is a list of {id, role} entries"
    if len(people) > BOUND:
        return [], [], f"`people` names {len(people)} people; at most {BOUND} in one call"
    lists: dict[str, list[str]] = {role: [] for role in ROLES}
    seen: dict[str, str] = {}
    for place, entry in enumerate(people, 1):
        if not isinstance(entry, dict) or set(entry) - {"id", "role"}:
            return [], [], f"entry {place} is not an {{id, role}} pair"
        who, role = entry.get("id"), entry.get("role")
        if not isinstance(who, str) or not who.strip():
            return [], [], f"entry {place} has no id"
        who = who.strip()
        if role not in ROLES:
            return [], [], (f"entry {place} ({who!r}) has the role {role!r}; "
                            f"one of {', '.join(ROLES)}")
        if who in seen:
            return [], [], (f"entry {place} ({who!r}) is a person already listed as "
                            f"{seen[who]!r} — a person has one role")
        seen[who] = role
        lists[role].append(who)
    return lists["admin"], lists["engineer"], ""


def loggable(people: object) -> str:
    """What the audit line says of a `people` parameter: how many, per role, and the digest —
    never the ids. A list that does not read is said as such; the refusal names why."""
    admins, engineers, why = read(people)
    if why:
        return "<a list that does not read>"
    return (f"<{len(admins)} admins, {len(engineers)} engineers, "
            f"digest {digest(admins, engineers)}>")
