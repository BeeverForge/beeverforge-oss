"""Nine more reads of a file a person writes name a file that is not UTF-8, never raise.

Each read below used `read_text(encoding="utf-8")`, so bytes saved as Latin-1 or UTF-16 with a
byte-order mark raised `UnicodeDecodeError` out of the command, and UTF-16 without a mark (valid
UTF-8, because NUL is a code point) was read as text full of NULs. A person who opens the file in
an editor sees nothing wrong, so every read now goes through `beeverforge/util/utf8.py::decode`
and its refusal names the file, the byte offset where it stops being UTF-8, and the remedy.

Each read keeps the shape its function already uses for its other failures: proposing a preview
returns an `Outcome` that wrote nothing; the requirement writers return a `WriteResult` and leave
the file as it was; superseding counts the number as failed; the facts pack leaves its README and
returns `False`; the refresh record's state names the file; a product's template is refused in
the decoder's words; and the upgrade from a 0.7 stack refuses before docker is asked anything.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests import the_git_bed
from tests.the_git_bed import a_served_tree

#: a repository from the bed, never one built here (see tests/the_git_bed.py)
git_bed = the_git_bed.git_bed

REMEDY = "save it as UTF-8"

#: one file per encoding family, as a person's editor might have saved it
FAMILIES = {
    "Latin-1": "café\n".encode("latin-1"),
    # the little-endian mark written explicitly, whatever the machine's byte order
    "UTF-16 with a byte-order mark": b"\xff\xfe" + "books\n".encode("utf-16-le"),
    "UTF-16-LE without a byte-order mark": "books\n".encode("utf-16-le"),
}


def _named(said: str, shown: str) -> None:
    """One sentence naming the file, the offset and the remedy — no exception's words."""
    assert f"`{shown}`" in said, said
    assert "offset" in said, said
    assert REMEDY in said, said
    assert "\n" not in said, said
    assert "Error" not in said, said


def _put(path: Path, raw: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return path


def _files(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


# ── proposing a preview: the manifest the `preview:` block is drafted into ──────────────────────

@pytest.mark.parametrize("family", FAMILIES)
def test_proposing_a_preview_refuses_a_manifest_not_in_utf8(tmp_path, family):
    from beeverforge.onboarding.preview_propose import Outcome, _draft_into

    rel = ".beeverforge/project.yaml"
    raw = b"name: podbeam\n" + FAMILIES[family]
    manifest = _put(tmp_path / rel, raw)
    project = SimpleNamespace(name="podbeam", manifest_path=rel)

    out = _draft_into(tmp_path, project, repo="someone/podbeam", accept=False, answers=None)

    assert isinstance(out, Outcome), out
    assert not out.ok
    _named(out.detail, rel)
    assert out.detail.endswith("Nothing was written."), out.detail
    assert manifest.read_bytes() == raw
    assert _files(tmp_path) == {rel}


# ── superseding: a retired requirement's file ───────────────────────────────────────────────────

@pytest.mark.parametrize("family", FAMILIES)
def test_superseding_counts_a_requirement_not_in_utf8_as_failed(tmp_path, caplog, family):
    from beeverforge.product.authoring import _mark_superseded

    raw = b"# REQ-0003\n\n- **Status:** accepted\n" + FAMILIES[family]
    file = _put(tmp_path / "requirements" / "0003-x.md", raw)

    with caplog.at_level(logging.WARNING):
        changed, failed = _mark_superseded(tmp_path, "requirements", [3], by=7)

    assert changed == []
    assert failed == [3]
    said = [r.getMessage() for r in caplog.records
            if "BEEVERFORGE_PRODUCT_SUPERSEDE_NOT_UTF8" in r.getMessage()]
    assert len(said) == 1, [r.getMessage() for r in caplog.records]
    _named(said[0].split("BEEVERFORGE_PRODUCT_SUPERSEDE_NOT_UTF8 ", 1)[1],
           "requirements/0003-x.md")
    assert file.read_bytes() == raw


# ── the three requirement writers: decision, acceptance, drop ───────────────────────────────────

REQ = "requirements/0002-pacote-de-fecho.md"


def _git(*args, cwd) -> bytes:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True).stdout


@pytest.fixture
def git_identity(monkeypatch):
    for key, value in (("GIT_AUTHOR_NAME", "t"), ("GIT_AUTHOR_EMAIL", "t@t"),
                       ("GIT_COMMITTER_NAME", "t"), ("GIT_COMMITTER_EMAIL", "t@t")):
        monkeypatch.setenv(key, value)


def _origin(bed, tmp_path: Path, raw: bytes) -> Path:
    """The docs repository holding the requirement's bytes on `main`, one commit, from the bed;
    a push to its checked-out `main` would be taken, so a writer that wrote would show."""
    _put(tmp_path / "docs-tree" / REQ, raw)
    origin = a_served_tree(bed, tmp_path / "docs-tree", tmp_path / "docs-origin")
    _git("config", "receive.denyCurrentBranch", "ignore", cwd=origin)
    return origin


def _a_requirement(family: str) -> bytes:
    return ("# REQ-0002 — Pacote de fecho\n\n- **Status:** proposed\n\n## Decisões\n\n"
            "| Data | Decisão | Quem | Onde |\n|---|---|---|---|\n").encode() + FAMILIES[family]


def _writers():
    from beeverforge.product.authoring import (
        accept_requirement,
        drop_requirement,
        record_decision,
    )

    return {
        "record_decision": lambda url: record_decision(
            docs_repo="someone/docs", clone_url=url, path=REQ, number=2,
            decision="the close runs monthly", decided_by="<@someone>", today="2026-07-31"),
        "accept_requirement": lambda url: accept_requirement(
            docs_repo="someone/docs", clone_url=url, path=REQ, number=2,
            accepted_by="<@someone>", today="2026-07-31"),
        "drop_requirement": lambda url: drop_requirement(
            docs_repo="someone/docs", clone_url=url, path=REQ, number=2,
            dropped_by="<@someone>", reason="out of scope", today="2026-07-31"),
    }


def _refused_and_left(bed, tmp_path: Path, writer: str, family: str) -> None:
    from beeverforge.product.authoring import NOT_REFUSED

    raw = _a_requirement(family)
    origin = _origin(bed, tmp_path, raw)
    before = _git("rev-parse", "main", cwd=origin)

    res = _writers()[writer](str(origin))

    assert res.ok is False, res
    assert res.refusal == NOT_REFUSED, res
    assert res.ref == REQ, res
    _named(res.detail, REQ)
    assert _git("rev-parse", "main", cwd=origin) == before
    assert _git("show", f"main:{REQ}", cwd=origin) == raw


@pytest.mark.parametrize("family", FAMILIES)
def test_recording_a_decision_refuses_a_requirement_not_in_utf8(git_bed, tmp_path, git_identity,
                                                                family):
    _refused_and_left(git_bed, tmp_path, "record_decision", family)


@pytest.mark.parametrize("family", FAMILIES)
def test_accepting_refuses_a_requirement_not_in_utf8(git_bed, tmp_path, git_identity, family):
    _refused_and_left(git_bed, tmp_path, "accept_requirement", family)


@pytest.mark.parametrize("family", FAMILIES)
def test_dropping_refuses_a_requirement_not_in_utf8(git_bed, tmp_path, git_identity, family):
    _refused_and_left(git_bed, tmp_path, "drop_requirement", family)


# ── the facts pack's README, which names every file the pack holds ──────────────────────────────

def _add_file(into: Path) -> bool:
    from beeverforge.product.facts import add_file

    return add_file(into, "found/x.md", "a search the role ran\n")


def _add_image(into: Path) -> bool:
    from beeverforge.product.facts import add_image

    return add_image(into, "found/attached-1.png", b"\x89PNG\r\n\x1a\n")


ADDERS = {"add_file": _add_file, "add_image": _add_image}


@pytest.mark.parametrize("adder", ADDERS)
@pytest.mark.parametrize("family", FAMILIES)
def test_a_facts_readme_not_in_utf8_is_said_and_left(tmp_path, caplog, adder, family):
    into = tmp_path / "facts"
    raw = b"# Product facts\n\n" + FAMILIES[family]
    readme = _put(into / "README.md", raw)

    with caplog.at_level(logging.WARNING):
        added = ADDERS[adder](into)

    assert added is False
    said = [r.getMessage() for r in caplog.records if REMEDY in r.getMessage()]
    assert len(said) == 1, [r.getMessage() for r in caplog.records]
    _named(said[0], "facts/README.md")
    assert readme.read_bytes() == raw


# ── the refresh record of a product's knowledge ─────────────────────────────────────────────────

@pytest.fixture
def record(tmp_path, monkeypatch):
    from beeverforge.product import refresh

    path = tmp_path / "state" / "refresh.json"
    monkeypatch.setattr(refresh, "record_path", lambda project: path)
    return path


@pytest.mark.parametrize("family", FAMILIES)
def test_a_refresh_record_not_in_utf8_is_named_in_its_state(record, family):
    from beeverforge.product import refresh

    _put(record, b'{"by": "' + FAMILIES[family] + b'"}')

    seen = refresh.state(SimpleNamespace(name="podbeam"))

    assert seen["outcome"] is None and seen["refreshed_at"] is None
    assert len(seen["degraded"]) == 1, seen
    _named(seen["degraded"][0], str(record))


@pytest.mark.parametrize("family", FAMILIES)
def test_a_refresh_record_not_in_utf8_is_named_in_the_log(record, caplog, family):
    import json

    from beeverforge.product import refresh

    _put(record, b'{"by": "' + FAMILIES[family] + b'"}')

    with caplog.at_level(logging.WARNING):
        refresh._update(SimpleNamespace(name="podbeam"), lambda held: held.update(seen=True))

    said = [r.getMessage() for r in caplog.records if REMEDY in r.getMessage()]
    assert len(said) == 1, [r.getMessage() for r in caplog.records]
    assert f"`{record}`" in said[0] and "offset" in said[0], said[0]
    assert json.loads(record.read_text(encoding="utf-8")) == {"seen": True}


# ── a product's requirement template ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("family", FAMILIES)
def test_a_template_not_in_utf8_is_refused_in_the_decoders_words(tmp_path, family):
    from beeverforge.product.template import TEMPLATE_FILE, load_template

    _put(tmp_path / TEMPLATE_FILE, b"fields: []\n# " + FAMILIES[family])

    found, why = load_template(tmp_path)

    assert found is None
    _named(why, TEMPLATE_FILE)


@pytest.mark.parametrize("family", FAMILIES)
def test_a_template_not_in_utf8_is_a_template_refused_finding_in_the_corpus(tmp_path, family):
    from beeverforge.product.corpus import load_corpus
    from beeverforge.product.template import TEMPLATE_FILE

    _put(tmp_path / TEMPLATE_FILE, b"fields: []\n# " + FAMILIES[family])
    (tmp_path / "0001-x.md").write_text("# REQ-0001 — x\n\n- **Status:** proposed\n",
                                        encoding="utf-8")

    corpus = load_corpus(tmp_path)

    assert corpus.template is None
    refused = [f for f in corpus.findings if f.code == "template-refused"]
    assert len(refused) == 1, corpus.findings
    assert refused[0].path == TEMPLATE_FILE
    _named(refused[0].message, TEMPLATE_FILE)


# ── the upgrade from an OpenFactory 0.7 stack ───────────────────────────────────────────────────

def _env_0_7(tmp_path: Path, family: str) -> tuple[Path, bytes]:
    raw = b"OPENFACTORY_BOT_TOKEN=x\n# " + FAMILIES[family]
    return _put(tmp_path / ".env.compose", raw), raw


@pytest.mark.parametrize("family", FAMILIES)
def test_carrying_refuses_a_0_7_file_not_in_utf8_before_docker_is_asked(tmp_path, family):
    from beeverforge.onboarding import upgrade_from_openfactory as up

    env, raw = _env_0_7(tmp_path, family)
    asked: list[list[str]] = []

    def docker(args: list[str]) -> tuple[int, str]:
        asked.append(args)
        return 0, ""

    with pytest.raises(up.Refused) as refused:
        up.carry(env, docker=docker, image="img")

    said = str(refused.value)
    _named(said, str(env))
    assert "nothing was stopped, copied or emptied" in said, said
    assert asked == []
    assert env.read_bytes() == raw


@pytest.mark.parametrize("image", [("--image", "img"), ()], ids=["with an image", "without one"])
@pytest.mark.parametrize("family", FAMILIES)
def test_the_upgrade_command_refuses_a_0_7_file_not_in_utf8(tmp_path, monkeypatch, family, image):
    from typer.testing import CliRunner

    from beeverforge.cli import app

    env, raw = _env_0_7(tmp_path, family)
    monkeypatch.delenv("BEEVERFORGE_VERSION", raising=False)
    monkeypatch.setattr("subprocess.run", lambda *a, **k: pytest.fail("docker was called"))

    result = CliRunner().invoke(app, ["upgrade-from-openfactory", "--env-file", str(env),
                                      *image], env={})

    assert result.exit_code == 1, result.output
    lines = [line for line in result.output.splitlines() if line.startswith("✗ ")]
    assert len(lines) == 1, result.output
    _named(lines[0], str(env))
    assert env.read_bytes() == raw
