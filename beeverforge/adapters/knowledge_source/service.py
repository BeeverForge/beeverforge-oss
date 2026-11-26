"""The `beeverforge-knowledge` row: BeeverForge Knowledge, an optional separate service, asked over
HTTP as the role its administrator registered (ADR-0052 D15).

WHAT IT SENDS. `POST <BEEVERFORGE_KNOWLEDGE_URL>/api/ask` with the message being answered as the
question, and the product to ask within when `BEEVERFORGE_KNOWLEDGE_PRODUCT` names one. It
authenticates with the bearer token of a service principal the service's administrator registered
— the role reads what that registration lets it read, and nothing else — and names no person: the
product role answers on a ticket, and who may talk to the role is the deployment's to decide.

THE TOKEN IS A CREDENTIAL, AND IS TREATED AS ONE. It is read through the credential store when
the row is asked (`BEEVERFORGE_KNOWLEDGE_TOKEN`, `adapters/credential_store/registry.py`), so a
store that rotates it is read again and a mounted secret file works as a variable does. It is
held nowhere between asks, sent to the one address the deployment configured and to no address a
redirect names (redirects are not followed), sent in clear to no host but this machine's
loopback, and never written: not in a log line, not in a refusal, not in the pack. The worktree
box strips it from what a workload can read (`sandbox/worktree.py::_PANEL_SECRET_VARS`).

WHAT IT READS BACK. The answer's sentences with the labels each cites, and each citation's title,
address, document and version at the source, and classification; an abstention with its reason;
and whom the service read as, when it says. An answer larger than `MAX_ANSWER_BYTES`, or of any
other shape, is not an answer. A 429 whose `Retry-After` is at most `SHORT_WAIT_SECONDS` is waited
for and asked again ONCE — never in a loop: the pack waits for this, and a rate-limited service
asked again and again is the load that limited it.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import math
import os
import time
from urllib.parse import urlsplit

import httpx

from beeverforge.adapters.credential_store import registry as credential_store
from beeverforge.adapters.knowledge_source.base import Answered, Cited, NotAsked, Said

log = logging.getLogger("beeverforge.knowledge_source")

URL_ENV = "BEEVERFORGE_KNOWLEDGE_URL"
TOKEN_ENV = "BEEVERFORGE_KNOWLEDGE_TOKEN"
PRODUCT_ENV = "BEEVERFORGE_KNOWLEDGE_PRODUCT"
TIMEOUT_ENV = "BEEVERFORGE_KNOWLEDGE_TIMEOUT_SECONDS"

#: The service's question door.
ASK_PATH = "/api/ask"
#: How long one ask may take, unless the deployment says: an answer is written by a model and
#: checked sentence by sentence, which takes seconds, and the pack waits for it before the role is
#: asked. At most `MOST_TIMEOUT_SECONDS`.
DEFAULT_TIMEOUT_SECONDS = 30.0
MOST_TIMEOUT_SECONDS = 300.0
#: An answer is a few kilobytes of sentences and citations; anything larger is not one.
MAX_ANSWER_BYTES = 2_000_000
#: A `Retry-After` at most this long is waited for, once.
SHORT_WAIT_SECONDS = 5.0
#: Hosts a token may be sent to over plain http: this machine's own.
_LOOPBACK_NAMES = frozenset({"localhost"})

NAME = "BeeverForge Knowledge"


def _loopback(host: str) -> bool:
    if host.lower() in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _address(said: str) -> str:
    """The service's base address, or `NotAsked` naming the variable: https, or http to this
    machine's loopback alone — a bearer token sent in clear across a network is a token handed to
    whoever is on it. No userinfo, query or fragment: the address names a place, not a secret."""
    if not said:
        raise NotAsked(f"{URL_ENV} is not set: it names where {NAME} is")
    parts = urlsplit(said)
    host = parts.hostname or ""
    if parts.scheme not in ("https", "http") or not host:
        raise NotAsked(f"{URL_ENV} is not an http(s) address")
    if parts.username is not None or parts.password is not None or parts.query or parts.fragment:
        raise NotAsked(f"{URL_ENV} carries more than a place (userinfo, a query or a fragment)")
    if parts.scheme == "http" and not _loopback(host):
        raise NotAsked(f"{URL_ENV} is plain http to another machine, and the token would cross the "
                       f"network in clear: give its https address")
    return said.rstrip("/")


def _timeout(said: str) -> float:
    if not said:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        seconds = float(said)
    except ValueError:
        seconds = math.nan
    if not math.isfinite(seconds) or not 0 < seconds <= MOST_TIMEOUT_SECONDS:
        raise NotAsked(f"{TIMEOUT_ENV} is not a number of seconds above 0 and at most "
                       f"{MOST_TIMEOUT_SECONDS:g}")
    return seconds


def _the_token() -> str:
    """The token, read through the store now; `NotAsked` naming the variable when nothing holds it
    or the store refuses it — never the value, never in a log line."""
    found = credential_store.lookup(TOKEN_ENV)
    if found.refused:
        raise NotAsked(f"the credential store refused {TOKEN_ENV}: {found.refused}")
    if not found.value or not found.value.strip():
        raise NotAsked(f"{TOKEN_ENV} is not set: it is the token of the role {NAME}'s "
                       f"administrator registered for this deployment")
    return found.value.strip()


class KnowledgeService:
    """The row. Holds where the service is, the product and the timeout; never the token."""

    display_name = NAME

    def __init__(self, *, url: str, product: str = "", timeout: float = DEFAULT_TIMEOUT_SECONDS,
                 transport: httpx.BaseTransport | None = None) -> None:
        self.url = url
        self.product = product
        self.timeout = timeout
        self._transport = transport

    def __repr__(self) -> str:
        return f"KnowledgeService(url={self.url!r}, product={self.product!r})"

    @classmethod
    def configured(cls) -> KnowledgeService:
        """The row as the deployment configured it, or `NotAsked` naming what is missing. The token
        is not read here: it is read at each ask, before anything is sent (`_post`)."""
        url = _address((os.environ.get(URL_ENV) or "").strip())
        timeout = _timeout((os.environ.get(TIMEOUT_ENV) or "").strip())
        return cls(url=url, product=(os.environ.get(PRODUCT_ENV) or "").strip(), timeout=timeout)

    def ask(self, question: str) -> Answered:
        body: dict[str, str] = {"question": question}
        if self.product:
            body["product"] = self.product
        response = self._post(body)
        if response.status_code == 429:
            wait = _retry_after(response.headers.get("retry-after"))
            if wait is None or wait > SHORT_WAIT_SECONDS:
                raise NotAsked("it asked to be asked again later (HTTP 429)")
            time.sleep(wait)
            response = self._post(body)
            if response.status_code == 429:
                raise NotAsked("it asked to be asked again later (HTTP 429), twice")
        return _answered(question, response)

    def _post(self, body: dict[str, str]) -> _Read:
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=False,
                              transport=self._transport) as client:
                with client.stream(
                        "POST", f"{self.url}{ASK_PATH}", content=json.dumps(body),
                        headers={"Authorization": f"Bearer {_the_token()}",
                                 "Content-Type": "application/json",
                                 "Accept": "application/json"}) as response:
                    return _Read(response.status_code, response.headers, _bounded(response))
        except httpx.TimeoutException:
            raise NotAsked(f"it did not answer within {self.timeout:g} seconds") from None
        except httpx.HTTPError as exc:
            # THE CLASS, NEVER THE MESSAGE: an error's words can carry the request it failed on
            log.warning("BEEVERFORGE_KNOWLEDGE_SOURCE_UNREACHABLE %s", type(exc).__name__)
            raise NotAsked(f"it could not be reached at its address "
                           f"({type(exc).__name__})") from None


class _Read:
    """A response read whole, within its bound: its status, its headers and its bytes."""

    def __init__(self, status_code: int, headers: httpx.Headers, content: bytes | None) -> None:
        self.status_code, self.headers, self.content = status_code, headers, content


def _bounded(response: httpx.Response) -> bytes | None:
    """The body, or None when it is larger than an answer is."""
    read = bytearray()
    for chunk in response.iter_bytes():
        read += chunk
        if len(read) > MAX_ANSWER_BYTES:
            return None
    return bytes(read)


def _retry_after(said: str | None) -> float | None:
    """Seconds to wait, from a `Retry-After` of seconds; None for a date or anything else, which is
    read as "later" and not waited for."""
    try:
        seconds = float(said or "")
    except ValueError:
        return None
    return seconds if math.isfinite(seconds) and seconds >= 0 else None


#: What each refusal is said as. Anything else that is not 200 is "answered HTTP <n>".
_REFUSALS = {
    401: "refused the token this deployment holds (HTTP 401)",
    403: "refused the token this deployment holds (HTTP 403)",
    503: "has no model to answer with (HTTP 503)",
}


def _answered(question: str, response: _Read) -> Answered:
    if response.status_code != 200:
        said = _REFUSALS.get(response.status_code, f"answered HTTP {response.status_code}")
        raise NotAsked(f"it {said}")
    if response.content is None:
        raise NotAsked(f"it sent back something that is not an answer (larger than "
                       f"{MAX_ANSWER_BYTES} bytes)")
    try:
        return _read(question, json.loads(response.content))
    except (ValueError, TypeError, KeyError, AttributeError):
        raise NotAsked("it sent back something that is not an answer") from None


def _read(question: str, body: dict) -> Answered:
    """The answer the service's JSON says, or a `TypeError`/`KeyError`/`ValueError` for a body that
    is not one. Unknown fields are ignored: the service may say more than the pack writes."""
    if not isinstance(body, dict) or not isinstance(body["sentences"], list):
        raise TypeError("not an answer")
    sentences = tuple(Said(text=_text(each["text"]),
                           citations=tuple(_text(label) for label in each.get("citations") or ()))
                      for each in body["sentences"])
    citations = tuple(
        Cited(label=_text(each["label"]), document_id=_text(each["document_id"]),
              version=_number(each.get("document_version")), title=_text(each.get("title") or ""),
              url=each.get("url") if isinstance(each.get("url"), str) else None,
              classification=_text(each.get("classification") or ""))
        for each in body.get("citations") or ())
    return Answered(question=question, sentences=sentences, citations=citations,
                    abstained=_abstention(body), read_as=_read_as(body.get("read_as")))


def _text(value) -> str:
    if not isinstance(value, str):
        raise TypeError("not text")
    return value


def _number(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _abstention(body: dict) -> str:
    """The reason the service gave no answer, "" when it answered: its reason, and what it says of
    it, as text."""
    said = body.get("abstention")
    if said is None:
        return "" if body.get("answered", True) is not False else "it gave no reason"
    if isinstance(said, str):
        return said or "it gave no reason"
    if isinstance(said, dict):
        parts = [str(said.get(key)) for key in ("reason", "detail") if said.get(key)]
        return " — ".join(parts) or "it gave no reason"
    raise TypeError("not an abstention")


def _read_as(said) -> str:
    if isinstance(said, dict) and isinstance(said.get("role"), str):
        return said["role"]
    return ""
