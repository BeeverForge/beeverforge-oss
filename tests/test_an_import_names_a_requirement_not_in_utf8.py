"""An import that would change a requirement file that is not UTF-8 names it, and lands nothing.

The plan reads the product's requirements with `errors="replace"`, so a requirement saved as
Latin-1 or UTF-16 still plans as one whose register the folder's rows join (a `SAME` row with
rows), or as one a revision replaces. Writing that plan read the file with
`read_text(encoding="utf-8")`, and a `UnicodeDecodeError` escaped `land` part-way through. Now the
read goes through `beeverforge/util/utf8.py::decode`: `land` fails as `not_utf8`, keeps the
decoder's sentence (the file, the byte offset, the remedy) in `Landed.unread`, writes nothing over
the file, and `land_import` commits nothing, as for the import's other failures.
"""

from __future__ import annotations

import subprocess

import pytest

from beeverforge.product import importing
from beeverforge.product.corpus import ACCEPTED
from tests import the_git_bed
from tests.test_nine_more_reads_name_a_file_that_is_not_utf8 import (
    FAMILIES,
    _named,
    _offset,
    _saved,
)
from tests.test_requirements_are_imported_under_the_corpus_rules import (
    _file,
    _Forge,
    _requirement,
    _tree,
)
from tests.the_git_bed import a_served_tree

#: a repository from the bed, never one built here (see tests/the_git_bed.py)
git_bed = the_git_bed.git_bed

DAY = "2026-10-21"
TWIN = _file(4, "Monthly close")
WHY = "close the month at the café"
JOINED = ("2026-09-01", "export in CSV", "someone")
NEW_ROW = ("2026-09-02", "totals per branch", "someone")


def _plain(text: str) -> str:
    """The product's text with its dashes as hyphens, which every family can encode: an editor
    saving Latin-1 would not keep an em dash, and the reader takes either in the title."""
    return text.replace("—", "-")


def _joining(tmp_path):
    """A product whose REQ-0004 holds one decision, and a folder bringing the same text with one
    more: the plan joins that row into REQ-0004's register."""
    twin = _plain(_requirement(4, "Monthly close", status=ACCEPTED, why=WHY, rows=[JOINED]))
    folder = _tree(tmp_path / "folder", {_file(1, "Monthly close"): _requirement(
        1, "Monthly close", why=WHY, rows=[JOINED, NEW_ROW])})
    return twin, importing.read(folder)


def _plan(brought, root):
    return importing.plan(brought, root=root, requirements_dir="requirements",
                          first=importing.first_number(root, "requirements", []),
                          ident=importing.import_id(brought, DAY), origin="round two")


def _land(the_plan, brought, root):
    return importing.land(the_plan, brought, root=root, requirements_dir="requirements",
                          by="someone", at=DAY)


@pytest.mark.parametrize("family", FAMILIES)
def test_joining_decisions_into_a_requirement_not_in_utf8_lands_nothing(tmp_path, family):
    """The register's rows are not joined, the file keeps its bytes, nothing new is written, and
    the person's sentence names the file, the offset and the remedy."""
    twin, brought = _joining(tmp_path)
    root = _tree(tmp_path / "product", {TWIN: twin})
    the_plan = _plan(brought, root)
    row = the_plan.requirements[0]
    assert (row.kind, row.number, row.rows) == (importing.SAME, 4, 1), the_plan.as_dict()
    raw = _saved(twin, family)
    (root / TWIN).write_bytes(raw)
    before = {p.name for p in (root / "requirements").iterdir()}

    done = _land(the_plan, brought, root)

    assert done.failed == "not_utf8", (done.failed, done.broken)
    assert done.record == {}
    _named(done.unread, TWIN, _offset(twin, family))
    said = importing._land_failed(done, language="en")
    assert done.unread in said and "nothing landed" in said, said
    assert (root / TWIN).read_bytes() == raw, "the requirement that is not UTF-8 was written"
    assert {p.name for p in (root / "requirements").iterdir()} == before


@pytest.mark.parametrize("family", FAMILIES)
def test_a_revision_over_a_requirement_not_in_utf8_says_why(tmp_path, family):
    """A new text of REQ-0004 replaces it; REQ-0004 is not UTF-8, so it cannot be marked replaced,
    and the person is told which file, where, and what to do, not only that it failed."""
    old = _plain(_requirement(4, "Monthly close", why=WHY))
    root = _tree(tmp_path / "product", {TWIN: old})
    brought = importing.read(_tree(tmp_path / "folder", {_file(1, "Monthly close"): _requirement(
        1, "Monthly close", why="close it every week")}))
    the_plan = _plan(brought, root)
    row = the_plan.requirements[0]
    assert (row.kind, tuple(row.replaces)) == (importing.REVISION, (4,)), the_plan.as_dict()
    raw = _saved(old, family)
    (root / TWIN).write_bytes(raw)

    done = _land(the_plan, brought, root)

    assert done.failed == "not_utf8", (done.failed, done.broken)
    assert done.record == {}
    _named(done.unread, TWIN, _offset(old, family))
    said = importing._land_failed(done, language="en")
    assert done.unread in said and "nothing landed" in said, said
    assert (root / TWIN).read_bytes() == raw, "the requirement that is not UTF-8 was written"


def _origin(origin, *args: str) -> str:
    return subprocess.run(["git", "-C", str(origin), *args], capture_output=True, text=True,
                          check=True).stdout


@pytest.mark.parametrize("family", FAMILIES)
def test_an_import_into_a_requirement_not_in_utf8_commits_nothing(tmp_path, git_bed, monkeypatch,
                                                                  family):
    """Through `land_import`: the base moves past the plan's read to a REQ-0004 that is not UTF-8,
    and the import ends as a named failure with nothing committed to the context repository."""
    twin, brought = _joining(tmp_path)
    tree = _tree(tmp_path / "tree", {".beeverforge/product.yaml":
                                     "product: lark\nsources: [lark/lark]\n", TWIN: twin})
    origin = a_served_tree(git_bed, tree, tmp_path / "origin")
    # a push to `main` lands, so a commit the import made would show on the base
    _origin(origin, "config", "receive.denyCurrentBranch", "ignore")
    head = _origin(origin, "rev-parse", "main")
    raw = _saved(twin, family)
    real = importing.plan

    def plan_then_resave(*args, **kw):
        made = real(*args, **kw)
        (kw["root"] / TWIN).write_bytes(raw)
        return made

    monkeypatch.setattr(importing, "plan", plan_then_resave)

    said = importing.land_import(docs_repo="someone/docs", clone_url=str(origin),
                                 brought=brought, forge=_Forge(), by="someone", today=DAY,
                                 language="en")

    assert said.ok is False, said
    assert said.refusal == importing.NOT_REFUSED, said
    assert said.plan.requirements[0].kind == importing.SAME, said.plan.as_dict()
    _named(said.detail, TWIN, _offset(twin, family))
    assert "nothing landed" in said.detail, said.detail
    assert _origin(origin, "rev-parse", "main") == head, "the import committed to the base"
    assert _origin(origin, "show", f"main:{TWIN}") == twin
