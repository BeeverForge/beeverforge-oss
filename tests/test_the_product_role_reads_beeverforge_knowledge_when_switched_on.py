"""The product role reads BeeverForge Knowledge, an optional separate service, only when a deployment
switches it on (ADR-0052 D15: any other source is an add-on axis; ADR-0041: facts are files).

THE AXIS IS `knowledge_source`, BORN WITH TWO: `none`, what a deployment that says nothing gets,
and `beeverforge-knowledge`, a client that asks the service over HTTP as the role the service's
administrator registered for the product. A stranger's row joins through the entry point, as on
every axis.

What these tests hold:

- OFF IS THE CORE AS IT WAS, BYTE FOR BYTE. The facts pack a turn writes with the axis unset, with
  it said `none`, and with the service's address and token in the environment but the row not
  named, is the pack the turn writes with the step taken out altogether — every file, every byte —
  and the service is never called.
- ON, THE PACK GAINS ONE FILE: `found/knowledge.md`, the message asked of the service, each
  sentence of its answer with the labels it cites, and each citation's title, address, document,
  version and classification. The README names it. An answer the service gave without its sources
  is written as an abstention, with its reason.
- A SERVICE THAT DOES NOT ANSWER NEVER FAILS THE TURN. Refused, rate-limited, without a model,
  erring, too slow, unreachable, or answering something that is not an answer: the pack is the off
  pack plus one line in its README naming what could not be asked, and why, in one sentence.
- THE TOKEN IS NEVER WRITTEN: not in a file of the pack, not in a log line, not in a refusal.
- A ROW SWITCHED ON WITHOUT ITS ADDRESS OR ITS TOKEN, or with an address a token may not be sent
  to in clear, is said by the variable's name, and nothing is sent.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import types
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from beeverforge import plugins
from beeverforge.product.module import ProductModule
from tests import index_bed as bed

TOKEN = "kn.service.0f0f0f0f.secret-token-never-written-anywhere"
KIND = "BEEVERFORGE_KNOWLEDGE_SOURCE"
ROW = "beeverforge-knowledge"
URL, TOKEN_ENV = "BEEVERFORGE_KNOWLEDGE_URL", "BEEVERFORGE_KNOWLEDGE_TOKEN"
PRODUCT, TIMEOUT = "BEEVERFORGE_KNOWLEDGE_PRODUCT", "BEEVERFORGE_KNOWLEDGE_TIMEOUT_SECONDS"
QUESTION = "What holds today about invoice numbering?"
FILE = "found/knowledge.md"

ANSWER = {
    "answered": True,
    "sentences": [
        {"text": "Invoice numbers restart every year with the year as a prefix.",
         "citations": ["E1"]},
        {"text": "The rule was confirmed by finance in March.", "citations": ["E1", "E2"]},
    ],
    "citations": [
        {"label": "E1", "document_id": "6b1f3c1e-6a43-4c55-9d0e-1a2b3c4d5e6f",
         "document_version": 3, "title": "Invoice numbering",
         "url": "https://wiki.example/pages/42", "classification": "internal",
         "excerpt": "numbers restart", "section_path": [], "deprecated": False,
         "acl_lag_seconds": None},
        {"label": "E2", "document_id": "0c2d4e6f-8a1b-4c3d-9e5f-7a8b9c0d1e2f",
         "document_version": 1, "title": "Finance minutes, March", "url": None,
         "classification": "confidential", "excerpt": "confirmed", "section_path": [],
         "deprecated": False, "acl_lag_seconds": None},
    ],
    "abstention": None,
    "read_as": {"role_id": "a3c1e5f7-0b2d-4f6a-8c1e-3b5d7f9a1c2e", "role": "Product Owner",
                "person_id": None},
    "classification": "confidential",
}
ABSTAINED = {
    "answered": False, "sentences": [], "citations": [],
    "abstention": {"reason": "no_readable_evidence", "detail": "nothing the role may read says"},
    "read_as": None,
}


# ── a fake BeeverForge Knowledge, over real HTTP on this machine ─────────────────────────────────

@dataclass
class Reply:
    status: int = 200
    body: object = field(default_factory=lambda: ANSWER)
    headers: dict[str, str] = field(default_factory=dict)
    delay: float = 0.0


class Knowledge:
    """A service on 127.0.0.1 that answers each request with the next scripted reply (the last
    one again once the script runs out), and records every request it was sent."""

    def __init__(self, *replies: Reply) -> None:
        self.replies = list(replies) or [Reply()]
        self.requests: list[dict] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802 — the standard library's name
                length = int(self.headers.get("Content-Length") or 0)
                outer.requests.append({"path": self.path, "headers": dict(self.headers),
                                       "body": self.rfile.read(length)})
                reply = outer.replies.pop(0) if len(outer.replies) > 1 else outer.replies[0]
                if reply.delay:
                    time.sleep(reply.delay)
                body = (reply.body if isinstance(reply.body, bytes)
                        else json.dumps(reply.body).encode())
                try:
                    self.send_response(reply.status)
                    for name, value in reply.headers.items():
                        self.send_header(name, value)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except OSError:
                    pass  # the client gave up waiting: that is the case under test

            def log_message(self, *_args):
                return None

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def knowledge():
    made: list[Knowledge] = []

    def _start(*replies: Reply) -> Knowledge:
        made.append(Knowledge(*replies))
        return made[-1]

    yield _start
    for each in made:
        each.close()


# ── a module answering a message, as `test_the_retrieval_step` builds one ───────────────────────

def _module(tmp_path, project, *, question: str = QUESTION, ws: str = "ws"):
    root = tmp_path / ws
    root.mkdir(exist_ok=True)
    ctx = SimpleNamespace(available=True, corpus=bed.corpus(tmp_path / "context"),
                          requirements_dir="requirements", domain=None)
    fake = SimpleNamespace(
        project=project, _combined=str(root), _turn_view=str(root), _workspace=lambda: None,
        _board_cards=lambda: bed.cards(), context=lambda: ctx, _facts_for="U1",
        _question=question, _said_before="", _conversation="person:U1",
        _documents_audience="internal", _product_model=None)
    fake._search_for_the_role = types.MethodType(ProductModule._search_for_the_role, fake)
    return fake


def _pack(tmp_path, project, **kw) -> dict[str, bytes]:
    """Every file of the pack a turn writes, by its path in the pack, its bytes with the pack's
    own random name stood in for — what "byte for byte" is measured over."""
    into = ProductModule._write_facts(_module(tmp_path, project, **kw))
    assert into is not None
    return {path.relative_to(into).as_posix():
            path.read_bytes().replace(into.name.encode(), b"<pack>")
            for path in sorted(into.rglob("*")) if path.is_file()}


def _readme(pack: dict[str, bytes]) -> str:
    return pack["README.md"].decode()


def _gaps_added(pack: dict[str, bytes], before: dict[str, bytes]) -> list[str]:
    """The lines of the manifest's list that this pack has and the pack before did not — the
    manifest's own framing of a gap section is not one of them."""
    had = set(_readme(before).splitlines())
    return [line for line in _readme(pack).splitlines()
            if line.startswith("- ") and line not in had]


def _switched_on(monkeypatch, service: Knowledge | None, **overrides: str) -> None:
    settings = {KIND: ROW, URL: service.url if service else "", TOKEN_ENV: TOKEN,
                PRODUCT: "tidewater", TIMEOUT: "2"}
    settings.update(overrides)
    for name, value in settings.items():
        if value:
            monkeypatch.setenv(name, value)
        else:
            monkeypatch.delenv(name, raising=False)


@pytest.fixture
def built(tmp_path):
    project, _index = bed.build(tmp_path)
    return project


@pytest.fixture
def before(tmp_path, built, monkeypatch):
    """The pack the turn writes with the step taken out altogether: the core as it was."""
    with monkeypatch.context() as patched:
        patched.setattr("beeverforge.product.module._the_knowledge_answers",
                        lambda module: ({}, []))
        return _pack(tmp_path, built)


# ── the axis ─────────────────────────────────────────────────────────────────────────────────────

def test_the_axis_is_published_and_born_with_two():
    from beeverforge.adapters.knowledge_source.registry import (
        AXIS,
        DEFAULT_KIND,
        OFF,
        SOURCES,
    )

    assert AXIS == "knowledge_source" and AXIS in plugins.AXES
    assert set(SOURCES) == {OFF, ROW}
    assert DEFAULT_KIND == OFF == "none", "the add-on is off unless a deployment says otherwise"


def test_an_unknown_row_is_refused_by_name_and_never_a_fallback():
    from beeverforge.adapters.knowledge_source.registry import build_knowledge_source

    with pytest.raises(ValueError, match=r"unknown knowledge source 'acme' — known: .*none"):
        build_knowledge_source("acme")


# ── off: the core as it was ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("how", ["unset", "said none", "service configured, row not named"])
def test_off_the_facts_pack_is_byte_for_byte_the_pack_without_the_step(
        how, tmp_path, built, before, knowledge, monkeypatch):
    service = knowledge()
    if how == "said none":
        monkeypatch.setenv(KIND, "none")
    elif how == "service configured, row not named":
        _switched_on(monkeypatch, service)
        monkeypatch.delenv(KIND)

    assert _pack(tmp_path, built) == before
    assert service.requests == [], "the service was called while the add-on was off"


def test_off_the_role_is_told_of_no_file_of_knowledge():
    from beeverforge.product.role import ProductRole

    role = ProductRole(agent=None, mounted={"facts": ".beeverforge-facts-0000"})
    section = "\n".join(role._facts_section(board_in_prompt=True))

    assert FILE not in section and "BeeverForge Knowledge" not in section


# ── on: one file of cited answers ────────────────────────────────────────────────────────────────

def test_switched_on_the_pack_gains_one_file_of_cited_answers(
        tmp_path, built, before, knowledge, monkeypatch):
    service = knowledge(Reply())
    _switched_on(monkeypatch, service)

    pack = _pack(tmp_path, built)

    assert set(pack) == set(before) | {FILE}
    assert {name: pack[name] for name in before if name != "README.md"} == {
        name: body for name, body in before.items() if name != "README.md"}
    written = pack[FILE].decode()
    for sentence in ANSWER["sentences"]:
        assert sentence["text"] in written
    assert "[E1]" in written and "[E1, E2]" in written
    for citation in ANSWER["citations"]:
        assert citation["title"] in written and citation["document_id"] in written
        assert f"version {citation['document_version']}" in written
        assert citation["classification"] in written
    assert "https://wiki.example/pages/42" in written
    assert "Product Owner" in written, "the file says which role the service read as"
    assert QUESTION in written
    assert f"`<pack>/{FILE}`" in _readme(pack)


def test_the_service_is_asked_as_its_role_with_the_message_and_the_product(
        tmp_path, built, knowledge, monkeypatch):
    service = knowledge(Reply())
    _switched_on(monkeypatch, service)

    _pack(tmp_path, built)

    (asked,) = service.requests
    headers = {name.lower(): value for name, value in asked["headers"].items()}
    assert asked["path"] == "/api/ask"
    assert headers["authorization"] == f"Bearer {TOKEN}"
    assert headers["accept"] == "application/json"
    assert headers["content-type"].startswith("application/json")
    assert "knowledge-person" not in headers, "the product role on a ticket names no person"
    assert json.loads(asked["body"]) == {"question": QUESTION, "product": "tidewater"}


def test_without_a_product_the_question_names_none(tmp_path, built, knowledge, monkeypatch):
    service = knowledge(Reply())
    _switched_on(monkeypatch, service, **{PRODUCT: ""})

    _pack(tmp_path, built)

    assert json.loads(service.requests[0]["body"]) == {"question": QUESTION}


def test_an_answer_without_its_sources_is_written_as_an_abstention_with_its_reason(
        tmp_path, built, knowledge, monkeypatch):
    _switched_on(monkeypatch, knowledge(Reply(body=ABSTAINED)))

    written = _pack(tmp_path, built)[FILE].decode()

    assert "did not answer" in written and "no_readable_evidence" in written
    assert "nothing the role may read says" in written


def test_switched_on_the_role_is_told_where_the_answers_are():
    from beeverforge.product.role import ProductRole

    role = ProductRole(agent=None, mounted={"facts": ".beeverforge-facts-0000"})
    with pytest.MonkeyPatch.context() as patched:
        patched.setenv(KIND, ROW)
        section = "\n".join(role._facts_section(board_in_prompt=True))

    assert f".beeverforge-facts-0000/{FILE}" in section


def test_a_message_with_no_words_asks_nothing(tmp_path, built, knowledge, monkeypatch):
    service = knowledge(Reply())
    _switched_on(monkeypatch, service)

    pack = _pack(tmp_path, built, question="   ")

    assert FILE not in pack and "BeeverForge Knowledge" not in _readme(pack)
    assert service.requests == []


# ── a service that does not answer never fails the turn ──────────────────────────────────────────

FAILURES = {
    "refused 401": ([Reply(status=401, body={"detail": "no identity"})], "refused"),
    "refused 403": ([Reply(status=403, body={"detail": "not yours"})], "refused"),
    "rate-limited, long": ([Reply(status=429, headers={"Retry-After": "120"})], "again later"),
    "rate-limited twice": ([Reply(status=429, headers={"Retry-After": "0"})], "again later"),
    "no model": ([Reply(status=503, body={"detail": "no model"})], "no model"),
    "erring": ([Reply(status=500, body={"detail": "boom"})], "HTTP 500"),
    "too slow": ([Reply(delay=4.0)], "within"),
    "not an answer": ([Reply(body=b"<html>a proxy page</html>")], "not an answer"),
    "an answer of the wrong shape": ([Reply(body={"sentences": "no"})], "not an answer"),
    # an answer in every other way, but larger than an answer is: read up to its bound and no more
    "too large": ([Reply(body={**ANSWER, "pad": "x" * 2_000_001})], "not an answer"),
    # a redirect is not followed: the token goes to the one address the deployment named
    "redirected": ([Reply(status=307, headers={"Location": "http://127.0.0.1:9/api/ask"})],
                   "HTTP 307"),
}


@pytest.mark.parametrize("case", sorted(FAILURES))
def test_a_service_that_does_not_answer_leaves_the_pack_and_says_so_in_one_line(
        case, tmp_path, built, before, knowledge, monkeypatch, caplog):
    replies, said = FAILURES[case]
    service = knowledge(*replies)
    _switched_on(monkeypatch, service, **({TIMEOUT: "0.5"} if case == "too slow" else {}))

    with caplog.at_level(logging.DEBUG):
        pack = _pack(tmp_path, built)

    assert set(pack) == set(before), "a file was written for an answer that never came"
    (line,) = _gaps_added(pack, before)
    assert "BeeverForge Knowledge" in line and said in line, line
    assert "unknown, not absent" in line
    assert TOKEN not in caplog.text and TOKEN not in line


def test_the_service_is_asked_once_a_turn_however_often_the_pack_is_written(
        tmp_path, built, knowledge, monkeypatch):
    service = knowledge(Reply())
    _switched_on(monkeypatch, service)
    fake = _module(tmp_path, built)

    for _ in range(3):
        assert ProductModule._write_facts(fake) is not None

    assert len(service.requests) == 1


def test_a_redirect_is_not_followed_and_the_token_goes_nowhere_else(
        tmp_path, built, knowledge, monkeypatch):
    elsewhere = knowledge(Reply())
    service = knowledge(Reply(status=307, headers={"Location": f"{elsewhere.url}/api/ask"}))
    _switched_on(monkeypatch, service)

    pack = _pack(tmp_path, built)

    assert FILE not in pack and elsewhere.requests == []


def test_a_short_retry_after_is_waited_for_once_and_never_in_a_loop(
        tmp_path, built, knowledge, monkeypatch):
    service = knowledge(Reply(status=429, headers={"Retry-After": "0"}), Reply())
    _switched_on(monkeypatch, service)

    pack = _pack(tmp_path, built)

    assert len(service.requests) == 2 and FILE in pack
    flooded = knowledge(Reply(status=429, headers={"Retry-After": "0"}))
    _switched_on(monkeypatch, flooded)
    _pack(tmp_path, built)
    assert len(flooded.requests) == 2, "a rate-limited service was asked more than twice"


def test_an_unreachable_service_is_said_and_the_turn_goes_on(
        tmp_path, built, before, knowledge, monkeypatch):
    gone = knowledge()
    address = gone.url
    gone.close()
    _switched_on(monkeypatch, None, **{URL: address})

    pack = _pack(tmp_path, built)

    (line,) = _gaps_added(pack, before)
    assert "could not be reached" in line, line


# ── switched on without what it needs ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("missing, said", [
    (URL, URL), (TOKEN_ENV, TOKEN_ENV),
    ("clear", URL), ("timeout", TIMEOUT),
])
def test_a_row_switched_on_without_what_it_needs_is_said_by_name_and_sends_nothing(
        missing, said, tmp_path, built, before, knowledge, monkeypatch):
    service = knowledge(Reply())
    if missing == "clear":
        _switched_on(monkeypatch, service, **{URL: "http://knowledge.example:8000"})
    elif missing == "timeout":
        _switched_on(monkeypatch, service, **{TIMEOUT: "soon"})
    else:
        _switched_on(monkeypatch, service, **{missing: ""})

    pack = _pack(tmp_path, built)

    (line,) = _gaps_added(pack, before)
    assert said in line, line
    assert service.requests == []


# ── the token is never written ───────────────────────────────────────────────────────────────────

def test_the_token_is_in_no_file_no_log_line_and_no_refusal(
        tmp_path, built, knowledge, monkeypatch, caplog):
    from beeverforge.adapters.knowledge_source.registry import build_knowledge_source

    cases = [Reply(), Reply(body=ABSTAINED), *(r for replies, _ in FAILURES.values()
                                               for r in replies if not r.delay)]
    seen: list[str] = []
    with caplog.at_level(logging.DEBUG):
        for n, reply in enumerate(cases):
            _switched_on(monkeypatch, knowledge(reply))
            pack = _pack(tmp_path, built, ws=f"ws-{n}")
            seen += [body.decode(errors="replace") for body in pack.values()]
        row = build_knowledge_source(ROW)
        seen += [repr(row), str(vars(row))]
    for text in [*seen, caplog.text]:
        assert TOKEN not in text
