"""A knowledge-bundle manifest that exists but cannot be read is never written over.

WHAT WAS MEASURED. `read_manifest` folds every failure — a missing file, an empty one, one that is
not UTF-8, not YAML, not a mapping, not a valid manifest, an `OSError` — into `None`, and three
writers did `read_manifest(...) or OkfManifest(...)` then `write_okf`. So a manifest a person had
saved as Latin-1, or broken by one stray bracket, was replaced by a fresh one on the next round:
the answered questions it held were gone, and the same questions were asked again.

THE REMEDY. A strict reader, `load_manifest`, tells "there is none" (`None`) from "there is one and
it cannot be read" (`ManifestUnreadable`, one sentence naming the file, the reason and the remedy).
The renewal, the recording of requested gaps and the covering read through it and write nothing
when it refuses; the refresh activity names the refusal and leaves the requests pending.

Every run-added name is imported INSIDE the test that uses it, so on the base each test fails at
that import alone rather than taking the whole module down with it.
"""

from __future__ import annotations

import logging
from pathlib import Path

from beeverforge.knowledge import requests as asked
from beeverforge.knowledge.contracts import ANSWERED, Concept, ConceptSource, Gap, OkfManifest
from beeverforge.knowledge.gaps import record_in_bundle
from beeverforge.knowledge.inventory import take_inventory, write_inventory
from beeverforge.knowledge.okf import (
    OKF_INDEX_FILE,
    OKF_MANIFEST_FILE,
    read_manifest,
    render_manifest,
    write_okf,
)
from beeverforge.onboarding import cover as _cover
from beeverforge.onboarding.concepts import Authored
from beeverforge.onboarding.cover import cover_paths
from beeverforge.onboarding.renew import renew_concepts
from tests.test_the_merge_re_authors_what_it_invalidated import (
    _PROJECT,
    _REWRITE,
    _harness,
    _published,
)

QUESTION = "Is the late fee décided anywhere, or only in the environment?"
ANSWER = "2%, décidé by finance: a product decision, not a setting."
REMEDY = "it holds the answered questions"


def _answered() -> Gap:
    return Gap(kind="open-question", path="billing", detail=QUESTION).model_copy(update={
        "status": ANSWERED, "answer": ANSWER, "answered_by": "someone",
        "answered_at": "2026-09-06T10:00:00Z"})


def _manifest_text() -> str:
    """A manifest holding one answered question, as the platform writes it."""
    return render_manifest(OkfManifest(source_commit="c1", gaps=[_answered()]))


def _latin1(path: Path) -> int:
    """Plant the manifest as whole-file Latin-1; the offset of its first byte that is not UTF-8."""
    raw = _manifest_text().encode("latin-1")
    path.write_bytes(raw)
    return raw.index(b"\xe9")


def _utf16(path: Path) -> None:
    path.write_bytes(_manifest_text().encode("utf-16"))


def _not_yaml(path: Path) -> None:
    path.write_text(_manifest_text().replace("gaps:", "gaps: [", 1), encoding="utf-8")


def _bytes_of(bundle: Path) -> dict[str, bytes]:
    """Every file in the bundle, by relative path — the manifest, the index, the inventory and the
    concepts — so "writes nothing" is checked on all of them at once."""
    return {str(p.relative_to(bundle)): p.read_bytes()
            for p in sorted(bundle.rglob("*")) if p.is_file()}


def _says_file_reason_remedy(sentence: str, path: Path, reason: str) -> None:
    assert str(path) in sentence, f"the sentence must name the file: {sentence!r}"
    assert reason in sentence, f"the sentence must give the reason {reason!r}: {sentence!r}"
    assert REMEDY in sentence and "restore" in sentence, (
        f"the sentence must give the remedy: {sentence!r}")
    assert "\n" not in sentence, f"the sentence must be one line: {sentence!r}"


# ── the strict reader ───────────────────────────────────────────────────────────────────────────

def test_a_missing_or_empty_manifest_is_no_manifest(tmp_path):
    from beeverforge.knowledge.okf import load_manifest

    assert load_manifest(tmp_path / "nothing-here") is None
    for empty in ("", "  \n", "~\n", "{}\n"):
        (tmp_path / OKF_MANIFEST_FILE).write_text(empty, encoding="utf-8")
        assert load_manifest(tmp_path) is None, f"{empty!r} is no manifest, as today"
    (tmp_path / OKF_MANIFEST_FILE).write_text(_manifest_text(), encoding="utf-8")
    assert load_manifest(tmp_path).gaps == [_answered()]


def test_a_manifest_not_in_utf8_is_named_with_the_decoders_sentence(tmp_path):
    from beeverforge.knowledge.okf import ManifestUnreadable, load_manifest

    path = tmp_path / OKF_MANIFEST_FILE
    at = _latin1(path)
    before = path.read_bytes()
    try:
        load_manifest(tmp_path)
    except ManifestUnreadable as exc:
        assert isinstance(exc, ValueError)
        assert exc.path == path
        _says_file_reason_remedy(str(exc), path,
                                 f"the byte at offset {at} (0xe9) cannot be read")
    else:
        raise AssertionError("a Latin-1 manifest was read as no manifest")
    assert path.read_bytes() == before

    _utf16(path)
    try:
        load_manifest(tmp_path)
    except ManifestUnreadable as exc:
        _says_file_reason_remedy(str(exc), path,
                                 "the byte at offset 0 (0xff) cannot be read (it looks like UTF-16)")
    else:
        raise AssertionError("a UTF-16 manifest was read as no manifest")


def test_a_manifest_not_yaml_or_not_a_manifest_is_named_on_one_line(tmp_path):
    from beeverforge.knowledge.okf import ManifestUnreadable, load_manifest

    path = tmp_path / OKF_MANIFEST_FILE
    cases = [
        (_manifest_text().replace("gaps:", "gaps: [", 1), "expected the node content"),
        ("- not: a mapping\n", "not a mapping"),
        ("gaps: nope\n", "Input should be a valid list"),
    ]
    for text, reason in cases:
        path.write_text(text, encoding="utf-8")
        try:
            load_manifest(tmp_path)
        except ManifestUnreadable as exc:
            _says_file_reason_remedy(str(exc), path, reason)
        else:
            raise AssertionError(f"{text!r} was read as no manifest")


def test_a_manifest_the_system_cannot_read_is_named(tmp_path):
    from beeverforge.knowledge.okf import ManifestUnreadable, load_manifest

    path = tmp_path / OKF_MANIFEST_FILE
    path.mkdir()
    try:
        load_manifest(tmp_path)
    except ManifestUnreadable as exc:
        _says_file_reason_remedy(str(exc), path, "Is a directory")
    else:
        raise AssertionError("a manifest the system cannot read was read as no manifest")


def test_read_manifest_still_reads_an_unreadable_manifest_as_none(tmp_path):
    """The read-only callers keep today's answer: no manifest to read from."""
    path = tmp_path / OKF_MANIFEST_FILE
    for plant in (_latin1, _utf16, _not_yaml):
        plant(path)
        assert read_manifest(tmp_path) is None
    path.write_text("- not: a mapping\n", encoding="utf-8")
    assert read_manifest(tmp_path) is None
    path.unlink()
    path.mkdir()
    assert read_manifest(tmp_path) is None


# ── the renewal ─────────────────────────────────────────────────────────────────────────────────

def _renewal_says(got, caplog, path: Path, reason: str) -> None:
    assert got.mode == "manifest-unreadable" and not got.wrote
    _says_file_reason_remedy(got.summary(), path, reason)
    [line] = [r.getMessage() for r in caplog.records
              if "BEEVERFORGE_OKF_MANIFEST_UNREADABLE" in r.getMessage()]
    _says_file_reason_remedy(line, path, reason)


def test_a_fresh_round_leaves_an_unreadable_manifest_and_the_bundle_as_they_were(
        tmp_path, monkeypatch, caplog):
    """The tree changed (a file added), so the round would re-take the inventory and republish
    the manifest — the fresh path. Its manifest is Latin-1, holding an answered question."""
    repo, bundle, _ = _published(tmp_path)
    at = _latin1(bundle / OKF_MANIFEST_FILE)
    (repo / "billing" / "new.py").write_text("X = 1\n", encoding="utf-8")
    asked_ = _harness(monkeypatch, _REWRITE)
    before = _bytes_of(bundle)
    caplog.set_level(logging.INFO)

    got = renew_concepts(_PROJECT, bundle, repo, commit="c2", generated_at="t")

    _renewal_says(got, caplog, bundle / OKF_MANIFEST_FILE,
                  f"the byte at offset {at} (0xe9) cannot be read")
    assert asked_ == []
    assert _bytes_of(bundle) == before, "an unreadable manifest's round wrote into the bundle"


def test_a_broken_round_leaves_an_unreadable_manifest_and_the_bundle_as_they_were(
        tmp_path, monkeypatch, caplog):
    """A concept made stale by its source changing — the broken path, which would ask the harness
    and rewrite the manifest. Its manifest is not YAML, holding an answered question."""
    repo, bundle, _ = _published(tmp_path)
    _not_yaml(bundle / OKF_MANIFEST_FILE)
    (repo / "billing" / "rules.py").write_text("def charge():\n    return 2\n", encoding="utf-8")
    asked_ = _harness(monkeypatch, _REWRITE)
    before = _bytes_of(bundle)
    caplog.set_level(logging.INFO)

    got = renew_concepts(_PROJECT, bundle, repo, commit="c2", generated_at="t")

    _renewal_says(got, caplog, bundle / OKF_MANIFEST_FILE, "expected the node content")
    assert asked_ == [], "nothing that cannot be written is worth a model call"
    assert _bytes_of(bundle) == before, "an unreadable manifest's round wrote into the bundle"


# ── the recording of what a reader asked for ────────────────────────────────────────────────────

def _bundle(tmp_path: Path) -> Path:
    """A published bundle without git: one concept on `billing/rules.py`, its inventory, an index."""
    repo = tmp_path / "src"
    (repo / "billing").mkdir(parents=True)
    (repo / "billing" / "rules.py").write_text("def charge():\n    return 1\n", encoding="utf-8")
    taken = take_inventory(repo, commit="c1")
    bundle = tmp_path / "bundle"
    concept = Concept(type="policy", title="Billing rules", description="d", what_it_does="w",
                      sources=[ConceptSource(repo="r", path="billing/rules.py", commit="c1",
                                             fingerprint=taken.files[0].fingerprint)])
    write_okf(bundle, manifest=OkfManifest(source_commit="c1", gaps=[_answered()]),
              concepts=[concept])
    write_inventory(bundle, taken)
    (bundle / OKF_INDEX_FILE).write_text("# old\n", encoding="utf-8")
    return bundle


def test_recording_into_an_unreadable_manifest_raises_and_writes_nothing(tmp_path):
    from beeverforge.knowledge.okf import ManifestUnreadable

    bundle = _bundle(tmp_path)
    _utf16(bundle / OKF_MANIFEST_FILE)
    before = _bytes_of(bundle)

    try:
        record_in_bundle(bundle, [asked.gap_for("billing/other.py")])
    except ManifestUnreadable as exc:
        _says_file_reason_remedy(str(exc), bundle / OKF_MANIFEST_FILE,
                                 "the byte at offset 0 (0xff) cannot be read")
    else:
        raise AssertionError("the request was recorded over an unreadable manifest")
    assert _bytes_of(bundle) == before


def test_a_missing_manifest_still_gets_a_fresh_one(tmp_path):
    bundle = _bundle(tmp_path)
    (bundle / OKF_MANIFEST_FILE).unlink()
    gap = asked.gap_for("billing/other.py")

    assert record_in_bundle(bundle, [gap]) == [gap]
    manifest = read_manifest(bundle)
    assert manifest is not None and [g.path for g in manifest.gaps] == ["billing/other.py"]


# ── the refresh activity ────────────────────────────────────────────────────────────────────────

def _queued(tmp_path, monkeypatch):
    """The setup of the request test in `test_capabilities_and_checks.py`: a published, seeded
    bundle the refresh calls "unchanged", and one request about its repository queued. Returns
    the activity module, its input, the inbox and the context repository."""
    from beeverforge.runtime.temporal.io import KnowledgeRefreshInput
    from tests.test_knowledge_pipeline import _client_repo, _context_repo, _patch_activity
    from tests.test_the_merge_re_authors_what_it_invalidated import _seed_concepts

    monkeypatch.setenv("BEEVERFORGE_LOG_DIR", str(tmp_path / "logs"))
    remote, work = _client_repo(tmp_path)
    context = _context_repo(tmp_path, with_docs=True)
    acts = _patch_activity(monkeypatch, tmp_path, remote, context)
    inp = KnowledgeRefreshInput(project="p", issue="1")
    assert acts._do_refresh_knowledge(inp) == "published"
    _seed_concepts(context, work, tmp_path)
    acts._do_refresh_knowledge(inp)
    assert acts._do_refresh_knowledge(inp) == "unchanged"
    inbox = asked.inbox_for(acts.ProjectRegistry().get("p"))
    assert asked.request(inbox, repo="owner/repo", path="core/__init__.py", at="2026-09-24T10")
    return acts, inp, inbox, context


def _refreshed_with_a_request(tmp_path, monkeypatch):
    """`_queued`, with the recording refusing for a planted reason."""
    from beeverforge.knowledge.okf import ManifestUnreadable

    acts, inp, inbox, _ = _queued(tmp_path, monkeypatch)

    def unreadable(bundle_dir, requested):
        raise ManifestUnreadable(Path(bundle_dir) / OKF_MANIFEST_FILE, "planted")

    monkeypatch.setattr("beeverforge.knowledge.gaps.record_in_bundle", unreadable)
    return acts, inp, inbox


def _named_and_pending(caplog, inbox) -> None:
    [line] = [r.getMessage() for r in caplog.records
              if "BEEVERFORGE_KNOWLEDGE_REQUESTS_NOT_RECORDED" in r.getMessage()]
    assert "cannot be read (planted)" in line and REMEDY in line and "owner/repo" in line
    assert [g.path for g in asked.pending(inbox, "owner/repo")] == ["core/__init__.py"], (
        "a request the manifest could not take was marked taken")


def test_the_refresh_names_an_unreadable_manifest_and_leaves_the_requests_pending(
        tmp_path, monkeypatch, caplog):
    acts, inp, inbox = _refreshed_with_a_request(tmp_path, monkeypatch)
    caplog.set_level(logging.INFO)

    assert acts._do_refresh_knowledge(inp) == "unchanged"

    _named_and_pending(caplog, inbox)


def test_a_publish_for_other_reasons_still_leaves_the_requests_pending(
        tmp_path, monkeypatch, caplog):
    from beeverforge.onboarding.renew import Renewal

    acts, inp, inbox = _refreshed_with_a_request(tmp_path, monkeypatch)

    def renewed(project, bundle_dir, source, *, commit, generated_at):
        """A renewal that re-authored one concept: a file the publish has to carry."""
        extra = Path(bundle_dir) / "concepts" / "policy" / "renewed.md"
        extra.parent.mkdir(parents=True, exist_ok=True)
        extra.write_text("---\ntitle: Renewed\n---\n", encoding="utf-8")
        return Renewal(1, 1, 1, 0, "fake")

    monkeypatch.setattr("beeverforge.onboarding.renew.renew_concepts", renewed)
    caplog.set_level(logging.INFO)

    assert acts._do_refresh_knowledge(inp) == "published+concepts:1"

    _named_and_pending(caplog, inbox)


def test_a_real_unreadable_manifest_stops_the_renewal_and_the_recording_in_one_round(
        tmp_path, monkeypatch, caplog):
    """End to end, no fake on the recording: the published manifest itself is Latin-1. The renewal
    and the recording both refuse in the same round, both name the file, the request stays
    pending and nothing is published over the context repository."""
    from tests.test_knowledge_pipeline import _SUBPATH, _git

    acts, inp, inbox, context = _queued(tmp_path, monkeypatch)
    clone = tmp_path / "ctx-plant"
    _git(tmp_path, "clone", "-q", str(context), str(clone))
    _latin1(clone / _SUBPATH / OKF_MANIFEST_FILE)
    _git(clone, "commit", "-qam", "a manifest saved as Latin-1")
    _git(clone, "push", "-q", "origin", "HEAD")
    head = _git(context, "rev-parse", "main")
    caplog.set_level(logging.INFO)

    assert acts._do_refresh_knowledge(inp) == "unchanged"

    messages = [r.getMessage() for r in caplog.records]
    for key in ("BEEVERFORGE_OKF_MANIFEST_UNREADABLE",
                "BEEVERFORGE_KNOWLEDGE_REQUESTS_NOT_RECORDED"):
        [line] = [m for m in messages if key in m]
        assert OKF_MANIFEST_FILE in line and "(0xe9) cannot be read" in line and REMEDY in line
    assert [g.path for g in asked.pending(inbox, "owner/repo")] == ["core/__init__.py"]
    assert _git(context, "rev-parse", "main") == head, "a round over an unreadable manifest published"


# ── the covering ────────────────────────────────────────────────────────────────────────────────

def test_covering_over_an_unreadable_manifest_writes_nothing_and_says_why(
        tmp_path, monkeypatch, caplog):
    bundle = _bundle(tmp_path)
    _not_yaml(bundle / OKF_MANIFEST_FILE)
    before = _bytes_of(bundle)
    called: list[list[str]] = []

    def fake_author(project, source, paths, *, commit, generated_at, answered=None):
        called.append(list(paths))
        concept = Concept(type="policy", title="Tax", what_it_does="w",
                          sources=[ConceptSource(repo="r", path="billing/tax.py", commit="c2")])
        return Authored([concept], [], "fake")

    monkeypatch.setattr(_cover, "author_for_paths", fake_author)
    caplog.set_level(logging.INFO)

    got = cover_paths(_PROJECT, bundle, tmp_path / "src", ["billing/tax.py", "billing/x.py"],
                      commit="c2", generated_at="t2")

    path = bundle / OKF_MANIFEST_FILE
    assert (got.authored, got.covered, got.left) == (0, (), ("billing/tax.py", "billing/x.py"))
    _says_file_reason_remedy(got.mode, path, "expected the node content")
    assert got.mode in got.summary()
    assert called == [], "nothing that cannot be written is worth a model call"
    assert _bytes_of(bundle) == before
    [line] = [r.getMessage() for r in caplog.records
              if "BEEVERFORGE_KNOWLEDGE_COVER_MANIFEST_UNREADABLE" in r.getMessage()]
    _says_file_reason_remedy(line, path, "expected the node content")
