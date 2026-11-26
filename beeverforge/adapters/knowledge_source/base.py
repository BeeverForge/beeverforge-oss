"""The knowledge-source port — a question in, a cited answer out (ADR-0052 D15, ADR-0041).

ONE METHOD, BECAUSE THE CORE CALLS ONE THING. The product role's facts pack asks the message being
answered and writes what comes back as a file (`product/knowledge_answers.py`). A source that can
do more — search, a graph, a stream — is asked for none of it here: a port that grows because a
provider has a feature is a leak with a Protocol on it (CONTRIBUTING.md).

AN ANSWER IS ITS CITATIONS. Every sentence names the labels of what it rests on, and every label is
one cited document: its title, where it is, its identity and version at the source, and how it is
classified there. An answer the source would not give from what it may read is an ABSTENTION with
its reason — a different fact from "it has nothing", and written as such.

NOT ASKED IS A SENTENCE, NEVER A CRASH. A source that refuses, is rate-limited, has no model,
errs, is too slow, cannot be reached, or answers something that is not an answer raises
`NotAsked` with one sentence saying which, and the turn goes on without it: the pack's manifest
names the gap (ADR-0041: what could not be read is not an absence). The sentence never carries a
credential or what the source sent back.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class NotAsked(RuntimeError):
    """The source could not be asked, or did not answer; `str(exc)` is the one sentence a person
    reads, naming why and never a secret."""


@dataclass(frozen=True)
class Cited:
    """One document an answer rests on, as the source names it."""

    label: str
    document_id: str
    version: int | None
    title: str
    url: str | None
    classification: str


@dataclass(frozen=True)
class Said:
    """One sentence of an answer, and the labels of the documents it rests on."""

    text: str
    citations: tuple[str, ...]


@dataclass(frozen=True)
class Answered:
    """What the source answered to `question`. `abstained` is the source's reason when it gave no
    answer from what it may read, and "" when it answered; `read_as` is whom it read as, when it
    says (a role its administrator registered), and "" when it does not."""

    question: str
    sentences: tuple[Said, ...] = ()
    citations: tuple[Cited, ...] = ()
    abstained: str = ""
    read_as: str = ""


@runtime_checkable
class KnowledgeSource(Protocol):
    """One row: `ask` answers one question, or raises `NotAsked` with why."""

    def ask(self, question: str) -> Answered: ...
