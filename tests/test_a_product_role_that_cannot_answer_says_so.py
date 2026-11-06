"""A product role whose model call fails says so, logs why, and files one impediment (#437).

WHAT WAS WRONG: when the role's harness failed (it refused the model, crashed, or was not logged
in), the person was told "I can't see the product's requirements at the moment… I've flagged it to
the team". The requirements had been read, and nothing was flagged: `engine.converse` dropped
`answer.error`, logged nothing and filed nothing. A failed DRAFT read as "there was nothing to
draft". And the false sentence stayed in the conversation the model read next, so its next answer
explained it with a reason that was also false.

WHAT IS HELD HERE, through the turn engine as a transport drives it:
  · a failed answer is said as a failure of the role, never as an unreadable product; its cause is
    logged; an impediment is filed once however many turns fail, and the sentence promises an alert
    only when one is open;
  · the next answered turn closes it;
  · a draft whose harness failed says so after the answer; a draft that came back and was refused
    is still "nothing to confirm";
  · the platform's own sentences are not handed back to the model as its earlier answers.
"""

from __future__ import annotations

import logging

import pytest

from beeverforge.ops import impediment
from beeverforge.product import voice
from beeverforge.product.role import ProductAnswer
from tests.test_the_conversation_is_pinned import (
    CLIENT,
    LANG,
    _Conversation,
    _Module,
    _project,
)
from tests.test_the_conversation_is_pinned import ledger as _ledger  # noqa: F401 — a fixture
from tests.test_the_conversation_is_pinned import table as _table  # noqa: F401 — a fixture

#: The suite's transcript and loop ledger, in memory, behind every turn below.
pytestmark = pytest.mark.usefixtures("_table", "_ledger")

REFUSED = ("the harness run failed: API Error: 400 Claude Code 2.1.219 does not support this "
           "model; version 2.1.280 or newer is required.")
FAILED = ProductAnswer(ok=False, error=REFUSED, harness_failed=True)
TITLE = impediment.title_on(_project(), impediment.PRODUCT_CANNOT_ANSWER)


class _Board:
    """The factory board an impediment is filed on: titles in, refs out."""

    def __init__(self) -> None:
        self.tickets: dict[str, str] = {}
        self.created: list[str] = []
        self.bodies: list[str] = []

    def find_ticket(self, *, title):
        return self.tickets.get(title)

    def create_ticket(self, *, title, body):
        ref = str(100 + len(self.created))
        self.created.append(title)
        self.bodies.append(body)
        self.tickets[title] = ref
        return ref

    def add_label(self, *_a, **_k):
        return None

    def set_assignees(self, *_a, **_k):
        return None


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.setattr(impediment, "_LAST", {})
    monkeypatch.setattr(impediment, "_FILED", {})
    monkeypatch.setattr(impediment, "_LOCKS", {})
    monkeypatch.setattr(impediment, "_born_in_the_queue", lambda project, trk: "")


@pytest.fixture
def board(monkeypatch) -> _Board:
    b = _Board()
    monkeypatch.setattr(impediment, "_tracker_for", lambda project, tracker: b)
    return b


@pytest.fixture
def closed(monkeypatch) -> list[str]:
    """Every cause `impediment.resolved` was asked to close."""
    seen: list[str] = []
    monkeypatch.setattr(impediment, "resolved",
                        lambda project, cause, evidence="", **_k: seen.append(cause) or False)
    return seen


def test_a_failed_answer_is_not_an_unreadable_product(board, caplog):
    talk = _Conversation(_project(), _Module(_project(), replies={"extrato": FAILED}))

    with caplog.at_level(logging.WARNING, logger="beeverforge.product.engine"):
        reply = talk.say("o extrato pode ser editado?", user=CLIENT)

    assert reply != voice.unavailable(language=LANG)
    assert reply == voice.cannot_answer(alerted=True, language=LANG)
    assert any("BEEVERFORGE_PRODUCT_CANNOT_ANSWER" in r.getMessage() and REFUSED in r.getMessage()
               for r in caplog.records), "the harness's cause was not logged"


def test_many_failed_turns_file_one_impediment(board):
    talk = _Conversation(_project(), _Module(_project(), replies={"extrato": FAILED}))

    for n in range(3):
        reply = talk.say(f"o extrato pode ser editado? ({n})", user=CLIENT)
        assert reply == voice.cannot_answer(alerted=True, language=LANG)

    assert board.created == [TITLE]


def test_two_turns_failing_at_once_file_one_impediment(board, monkeypatch):
    """Two people, or a thread and its retry, failing at the same moment (#463's review): the
    board's check and create run under one lock per cause, so the second waits for the first's
    create instead of filing its own. The first create is held open until the second turn has
    reached the lock (or, without one, the board), so the race is forced, not hoped for.

    THE BOARD'S SEARCH LAGS HERE, as a forge's search index does behind a create: the waiting turn
    cannot find the ticket filed a moment ago, so what stops the second create is the lock and
    the memory of the occurrence that held it first, not a lookup."""
    import threading

    from beeverforge.product import engine

    first_in, second_here, go = threading.Event(), threading.Event(), threading.Event()
    create = board.create_ticket

    def held_create(*, title, body):
        if threading.current_thread().name == "second":
            second_here.set()
        else:
            first_in.set()
            go.wait()
        return create(title=title, body=body)

    board.create_ticket = held_create
    board.find_ticket = lambda *, title: None               # the search has not caught up yet
    real_lock = impediment._lock_for

    class _Watched:
        def __init__(self, lock):
            self.lock = lock

        def __enter__(self):
            if threading.current_thread().name == "second":
                second_here.set()
            return self.lock.__enter__()

        def __exit__(self, *exc):
            return self.lock.__exit__(*exc)

    monkeypatch.setattr(impediment, "_lock_for", lambda key: _Watched(real_lock(key)))
    said: dict[str, str] = {}

    def fail(name):
        said[name] = engine._could_not(_project(), REFUSED, step="answer", language=LANG)

    first = threading.Thread(target=fail, args=("first",), name="first")
    second = threading.Thread(target=fail, args=("second",), name="second")
    first.start()
    assert first_in.wait(30), "the first turn never reached the board"   # a hang guard only
    second.start()
    assert second_here.wait(30), "the second turn never reached the lock"
    go.set()
    first.join()
    second.join()

    assert board.created == [TITLE], "two turns failing at once filed two tickets"
    assert said == {name: voice.cannot_answer(alerted=True, language=LANG)
                    for name in ("first", "second")}


def test_a_ticket_a_person_closed_is_filed_again(board):
    """This process remembers it filed the impediment; a person may have closed it since (#463's
    review). The person is about to be told the team knows, so the board is asked again."""
    talk = _Conversation(_project(), _Module(_project(), replies={"extrato": FAILED}))
    talk.say("o extrato pode ser editado?", user=CLIENT)
    board.tickets.clear()                                   # closed on the board by a person

    reply = talk.say("o extrato pode ser editado? de novo", user=CLIENT)

    assert board.created == [TITLE, TITLE], "a closed ticket was taken as still open"
    assert reply == voice.cannot_answer(alerted=True, language=LANG)


#: A credential-shaped string in the harness's own text: the shape, not a credential.
SHAPED = "ghp_" + "Aa0" * 12


def test_the_cause_is_scrubbed_before_the_log_and_the_ticket(board, caplog):
    leaky = ProductAnswer(ok=False, harness_failed=True,
                          error=f"the harness run failed: auth header token {SHAPED} refused")
    talk = _Conversation(_project(), _Module(_project(), replies={"extrato": leaky}))

    with caplog.at_level(logging.DEBUG):
        talk.say("o extrato pode ser editado?", user=CLIENT)

    assert board.created == [TITLE]
    assert SHAPED not in board.bodies[0], "the ticket carries the credential-shaped string"
    assert not [r for r in caplog.records if SHAPED in r.getMessage()], (
        "a log line carries the credential-shaped string")
    assert any("the harness run failed: auth header token" in r.getMessage()
               for r in caplog.records), "the scrubbed cause was not logged at all"


def test_with_no_board_it_promises_no_alert():
    talk = _Conversation(_project(), _Module(_project(), replies={"extrato": FAILED}))

    reply = talk.say("o extrato pode ser editado?", user=CLIENT)

    assert reply == voice.cannot_answer(alerted=False, language=LANG)


def test_the_next_answered_turn_closes_it(closed):
    talk = _Conversation(_project(), _Module(_project(), replies={"extrato": FAILED}))
    talk.say("o extrato pode ser editado?", user=CLIENT)
    assert impediment.PRODUCT_CANNOT_ANSWER not in closed

    talk.say("e o pró-labore?", user=CLIENT)

    assert impediment.PRODUCT_CANNOT_ANSWER in closed


ASKED = ProductAnswer(ok=True, text="Entendi: você quer exportar o extrato.", is_request=True)


def test_a_draft_whose_harness_failed_says_so_after_the_answer(board):
    module = _Module(_project(), replies={"exportar": ASKED}, drafted=FAILED)
    talk = _Conversation(_project(), module)

    reply = talk.say("quero exportar o extrato", user=CLIENT)

    assert reply == f"{ASKED.text}\n\n" + voice.cannot_draft(alerted=True, language=LANG)
    assert board.created == [TITLE]


def test_a_draft_that_came_back_refused_is_still_nothing_to_confirm(board):
    refused = ProductAnswer(ok=False, error="the draft states no testable outcome")
    module = _Module(_project(), replies={"exportar": ASKED}, drafted=refused)
    talk = _Conversation(_project(), module)

    reply = talk.say("quero exportar o extrato", user=CLIENT)

    assert reply == ASKED.text
    assert board.created == []


def test_the_platform_sentence_is_not_read_back_as_the_roles_answer(board):
    module = _Module(_project(), replies={"extrato": FAILED})
    talk = _Conversation(_project(), module)
    talk.say("o extrato pode ser editado?", user=CLIENT)

    talk.say("e o pró-labore?", user=CLIENT)

    read = module.asked("answer")[-1]["conversation"]
    assert "o extrato pode ser editado?" in read, "the unanswered question left the conversation"
    for sentence in (voice.cannot_answer(alerted=True, language=LANG),
                     voice.unavailable(language=LANG)):
        assert sentence not in read, "the platform's sentence was read back as the role's answer"


def test_an_earlier_unavailable_is_not_read_back_either():
    """The same for the other platform sentences (#457 marked them; the live conversation now drops
    them too): the turn that could not read the product, then a turn that can, in one thread."""
    _Conversation(_project(), _Module(_project(), available=False)).say(
        "o extrato pode ser editado?", user=CLIENT)
    module = _Module(_project())

    _Conversation(_project(), module).say("e o pró-labore?", user=CLIENT)

    read = module.asked("answer")[-1]["conversation"]
    assert "o extrato pode ser editado?" in read
    assert voice.unavailable(language=LANG) not in read


# ── the role says which failure it was ──────────────────────────────────────────────────────────

class _Harness:
    """A harness that answers with `result` whatever it is asked."""

    name = "stand-in"

    def __init__(self, result) -> None:
        self.result = result

    def ask(self, *, sandbox, workspace, prompt, phase="ask"):
        return self.result


def _role_says(result, verb: str):
    from types import SimpleNamespace

    from beeverforge.adapters.sandbox.base import Workspace
    from beeverforge.product.role import ProductRole

    ws = Workspace(path="/tmp", branch="main", base_branch="main")
    box = SimpleNamespace(run=lambda **k: (0, ""))
    role = ProductRole(_Harness(result))
    if verb == "draft":
        return role.draft(sandbox=box, workspace=ws, request="quero exportar o extrato")
    return role.answer(sandbox=box, workspace=ws, question="o extrato pode ser editado?")


@pytest.mark.parametrize("verb", ["answer", "draft"])
def test_a_harness_that_failed_is_marked_as_one(verb):
    from beeverforge.contracts import AgentRunResult

    said = _role_says(AgentRunResult(ok=False, summary=REFUSED, error=REFUSED), verb)

    assert said.ok is False and said.harness_failed is True, said


def test_a_draft_that_came_back_untestable_is_not_a_harness_failure():
    from beeverforge.contracts import AgentRunResult

    said = _role_says(AgentRunResult(ok=True, summary='{"title": "", "must_be_true": []}'),
                      "draft")

    assert said.ok is False and said.harness_failed is False, said
