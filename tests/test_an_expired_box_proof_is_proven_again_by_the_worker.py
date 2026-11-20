"""#614 — an expired box proof held pickup until a person ran the proof; the worker proves it.

The gate (`scan_todo`) reads a hold. When the hold is an EXPIRY — a proof that passed against a
world that has since moved — the worker starts one `box_prove` row for it, once per hold reason,
only when the floor has a free slot, and the tick after the proof passes clears the hold and says
so. A hold that is not an expiry (never proven, a failed proof, an unmerged manifest) starts nothing.

Every case is driven with a FAKE proof (the `box_prove` row replaced by a recorder) and a fake floor:
no engine, no docker, no waiting on time.
"""

from __future__ import annotations

import asyncio

import pytest

import beeverforge.box_prove as bp
from beeverforge.contracts.project import Project

EXPIRED = bp.Expired("the image img changed (sha256:aaa… → sha256:bbb…) — "
                     "run `beeverforge box prove acme`")


@pytest.fixture
def proofs(monkeypatch, tmp_path):
    monkeypatch.setenv("BEEVERFORGE_PROOFS", str(tmp_path / "proofs"))
    monkeypatch.setenv("BEEVERFORGE_SANDBOX", "container")
    monkeypatch.delenv("BEEVERFORGE_BOX_REPROVE", raising=False)
    monkeypatch.setattr(bp, "PROOF_DIR", tmp_path / "proofs")
    return tmp_path / "proofs"


class _World:
    """The things a tick reads, as fakes: the gate's verdict, the floor, and the `box_prove` row."""

    def __init__(self, monkeypatch, proofs):
        import beeverforge.actions as actions
        import beeverforge.adapters.board as board_pkg
        import beeverforge.runtime.temporal.activities as acts

        self.acts = acts
        self.verdict: str | None = EXPIRED
        self.free = 1
        self.started: list[dict] = []
        self.spoken: list[str] = []
        self.refuse = False
        project = Project(name="acme", repo_path=str(proofs.parent))
        monkeypatch.setattr(acts.ProjectRegistry, "get", lambda self, name: project)

        class _Board:
            def items_in_status(self, status):
                return ["7"]

        class _Ticket:
            state = "open"

        class _Tracker:
            def get_ticket(self, ref):
                return _Ticket()

        monkeypatch.setattr(board_pkg, "build_board", lambda *a, **kw: _Board())
        monkeypatch.setattr(acts, "_tracker_for", lambda p: _Tracker())
        monkeypatch.setattr("beeverforge.credentials.tracker_token_for", lambda p: "tok")
        monkeypatch.setattr(bp, "gate_reason", lambda *a, **kw: self.verdict)
        # a proof of this key is not running unless the test says so
        self.running = False
        monkeypatch.setattr(bp, "proof_running", lambda key: self.running)

        async def _free():
            return self.free

        monkeypatch.setattr(acts, "_floor_free", _free)

        async def _perform(name, *, by, **params):
            from beeverforge.actions import done, refused
            from beeverforge.actions.base import FAILED

            self.started.append({"name": name, **params})
            if self.refuse:
                return refused(FAILED, "nope")
            return done("running", handle="h", joined=False)

        monkeypatch.setattr(actions, "perform", _perform)
        monkeypatch.setattr(bp, "_say_to_the_channel",
                            lambda project, registry_name, phrase, level, **f:
                            self.spoken.append(f"{phrase}:{f.get('reason', '')}"))

    def tick(self):
        from beeverforge.runtime.temporal.io import ScanInput

        return asyncio.run(self.acts.scan_todo(ScanInput(
            project="acme", board_owner="o", board_number="1", pickup_status="TO-DO")))


@pytest.fixture
def world(monkeypatch, proofs):
    return _World(monkeypatch, proofs)


def test_an_expired_proof_starts_one_box_proof_through_the_row(world):
    world.tick()

    assert world.started == [{"name": "box_prove", "project": "acme", "repo": ""}]


def test_it_starts_once_per_hold_reason(world):
    world.tick()
    world.tick()

    assert len(world.started) == 1, "the same hold started the proof on every tick"


def test_the_same_hold_with_other_detail_is_still_the_same_reason(world):
    world.tick()
    world.verdict = bp.Expired("the image img changed (sha256:ccc… → sha256:ddd…) — run `beeverforge box prove acme`")
    world.tick()

    assert len(world.started) == 1


def test_a_proof_still_running_starts_nothing(world):
    world.running = True

    world.tick()

    assert world.started == []


def test_no_free_slot_starts_nothing_and_the_next_tick_with_one_does(world):
    world.free = 0
    world.tick()
    assert world.started == []

    world.free = 1
    world.tick()
    assert len(world.started) == 1, "a tick without a slot spent the hold's one start"


def test_a_start_that_was_refused_is_tried_again_next_tick(world):
    world.refuse = True
    world.tick()
    world.refuse = False
    world.tick()

    assert len(world.started) == 2


def test_never_proven_starts_nothing(world):
    world.verdict = "the box has never been proven — run `beeverforge box prove acme`"

    world.tick()

    assert world.started == []


def test_a_failed_proof_hold_starts_nothing(world):
    world.verdict = "the last box proof FAILED — run `beeverforge box prove acme`"

    world.tick()

    assert world.started == []


def test_turned_off_starts_nothing(world, monkeypatch):
    monkeypatch.setenv("BEEVERFORGE_BOX_REPROVE", "off")

    world.tick()

    assert world.started == []


@pytest.mark.parametrize("value,on", [("", True), ("on", True), ("off", False), ("0", False),
                                      ("false", False), ("NO", False), ("anything", True)])
def test_the_setting_reads_off_words_only(monkeypatch, value, on):
    monkeypatch.setenv("BEEVERFORGE_BOX_REPROVE", value)

    assert bp.reprove_enabled() is on


def test_when_the_proof_passes_the_next_tick_picks_up_and_the_channel_hears_once(world):
    assert world.tick() == []
    world.verdict = None  # the proof passed: the gate opens

    assert world.tick() == ["7"]
    world.tick()

    told = [s for s in world.spoken if s.startswith("gate.box-reproven")]
    assert len(told) == 1, world.spoken
    assert "image img changed" in told[0], "the channel was not told why it was proven again"


def test_a_hold_that_was_never_reproven_does_not_announce_a_reproof(world):
    world.verdict = None

    world.tick()

    assert not [s for s in world.spoken if "reproven" in s]


def test_when_the_proof_fails_the_hold_becomes_the_proofs_own_sentence_and_nothing_restarts(world):
    world.tick()
    world.verdict = ("the last box proof FAILED — test: `pytest` exited 1 — fix the test, "
                     "then run `beeverforge box prove acme`")

    assert world.tick() == []
    assert world.tick() == []

    assert len(world.started) == 1, "a failed proof started again: a loop of failing proofs"
    assert not [s for s in world.spoken if "reproven" in s]


def test_a_foreign_repository_is_proven_under_its_own_key_once(world, monkeypatch):
    seen = []
    monkeypatch.setattr(bp, "proof_running", lambda key: seen.append(key) or False)
    monkeypatch.setattr(world.acts, "_ref_repo", lambda p, ref: ("acme/web", "9"))
    monkeypatch.setattr(world.acts, "_is_default_repo_for_test", None, raising=False)
    monkeypatch.setattr("beeverforge.runtime.card_repo._is_default_repo", lambda p, r: False)
    monkeypatch.setattr(bp, "gate_reason",
                        lambda p, *, sandbox, repo="": None if not repo else EXPIRED)
    monkeypatch.setattr(bp, "foreign_proofs_recorded", lambda p: True)
    monkeypatch.setattr(world.acts, "_taken_out_for_its_repository", lambda *a: False)

    world.tick()
    world.tick()

    assert [s["repo"] for s in world.started] == ["acme/web"]
    assert any("--" in k for k in seen), seen


# ── the box_prove side: the sentence, the classes, the lock, the marker ───────────────────────────

def test_a_failed_proof_is_held_with_its_own_finding_and_remedy(proofs, monkeypatch):
    bp.save(bp.Proof(project="acme", image="img", ok=False, at="t", findings=[
        bp.Finding("validate", False, "test: `pytest` exited 1\nline two\nline three",
                   "fix the failing test on main")]))
    monkeypatch.setattr("beeverforge.adapters.sandbox.registry.box_traits",
                        lambda kind: type("T", (), {"honours_image": True})())

    reason = bp.gate_reason(Project(name="acme", repo_path="x"), sandbox="container")

    assert reason.startswith("the last box proof FAILED — ")
    assert "validate" in reason and "exited 1" in reason and "fix the failing test" in reason
    assert "line two" not in reason, "the finding's output tail reached the hold's sentence"
    assert not isinstance(reason, bp.Expired)


def test_the_expiry_is_a_class_of_hold_and_the_other_holds_are_not(proofs):
    proof = bp.Proof(project="acme", image="img", ok=True, digest="d1", toolbox="t",
                     commands_hash="c", findings=[])

    why = bp._freshness_reason(proof, digest="d2", variant="t", commands="c",
                               run_it="run it", machine="")

    assert isinstance(why, bp.Expired)


def test_a_proof_running_on_this_machine_is_seen_by_its_lock(proofs):
    assert bp.proof_running("acme") is False
    lock = bp._hold_the_proof_of("acme")
    try:
        # the lock is re-entrant for the thread that holds it, so ask from another
        import threading

        seen: list[bool] = []
        t = threading.Thread(target=lambda: seen.append(bp.proof_running("acme")))
        t.start()
        t.join()
    finally:
        bp._let_go(lock)

    assert seen == [True]
    assert bp.proof_running("acme") is False


def test_a_scan_admits_no_more_cards_than_the_floor_has_free_after_the_gate(world):
    """A scan of another project may have started a proof since the poller counted its slots."""
    world.verdict = None
    world.free = 0

    assert world.tick() == []


def test_the_floor_counts_a_running_box_proof_as_a_job(monkeypatch):
    import beeverforge.runtime.temporal.activities as acts

    asked: list[str] = []

    class _Client:
        async def list_workflows(self, query):
            asked.append(query)
            for _ in range(2):
                yield object()

    monkeypatch.setenv("BEEVERFORGE_MAX_CONCURRENT_JOBS", "3")

    assert asyncio.run(acts._free_slots(_Client())) == 1
    assert "BoxProveWorkflow" in asked[0] and "JobWorkflow" in asked[0]
