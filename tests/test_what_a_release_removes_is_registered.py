"""What a release removes is registered, and the release cannot carry it (#264, review of #499).

`beeverforge/deprecations.py` is the register: each compatibility path promised "until X" in a
release note is one entry. This file fails once the package's own version reaches an entry's
`removed_in`, naming the entry — so the release that is meant to drop it is cut without it.
"""

from __future__ import annotations

import beeverforge
from beeverforge import deprecations, former_names


def test_no_entry_is_due_at_this_version():
    due = deprecations.due(beeverforge.__version__)

    assert due == [], "\n".join(
        f"{e.what} is registered as removed in {e.removed_in}, and this is "
        f"{beeverforge.__version__}: remove it, then its entry in beeverforge/deprecations.py"
        for e in due)


def test_an_entry_is_due_from_its_release_on_and_not_before(monkeypatch):
    """The positive twin: the comparison the guard above relies on, at its edges."""
    entry = deprecations.Removal("someone-path", "1.1", "someone's old path")
    monkeypatch.setattr(deprecations, "REMOVALS", (entry,))

    assert deprecations.due("1.1.0") == [entry]
    assert deprecations.due("1.1") == [entry]
    assert deprecations.due("1.1.0.dev0") == [entry], "a pre-release of 1.1 is 1.1's code"
    assert deprecations.due("1.2.3") == [entry]
    assert deprecations.due("1.0.9") == []
    assert deprecations.due("0.2.0.dev0") == []

    spelled_long = deprecations.Removal("someone-path", "1.1.0", "someone's old path")
    monkeypatch.setattr(deprecations, "REMOVALS", (spelled_long,))
    assert deprecations.due("1.1") == [spelled_long], "`1.1` and `1.1.0` are one release"


def test_the_openfactory_environment_names_are_registered_and_read_from_the_register():
    assert deprecations.removed_in("openfactory-environment") == "1.1"
    assert former_names.LAST_READ_BEFORE == deprecations.removed_in("openfactory-environment")
