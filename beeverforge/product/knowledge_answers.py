"""What a knowledge source answered to the message, as one file of the product role's facts pack
(ADR-0052 D15, ADR-0041: facts are files).

ONLY WHEN A DEPLOYMENT SWITCHED ONE ON. With `BEEVERFORGE_KNOWLEDGE_SOURCE` unset or `none`,
`answers` is `({}, [])` before anything else is read: no request, no file, no line in the
manifest — the pack is the one the core wrote before this axis existed, byte for byte
(`tests/test_the_product_role_reads_beeverforge_knowledge_when_switched_on.py`).

ON, ONE FILE: `found/knowledge.md` — the message as it was asked, whom the source read as when it
says, each sentence of its answer with the labels it cites, and each citation's title, address,
document and version, and classification. The source chose what it may read; the role answers
from what it was given, and says the label. An abstention is written as one, with the source's
reason: "it would not answer from what it may read" is not "there is nothing".

A SOURCE THAT DID NOT ANSWER IS A GAP, in one sentence, in the manifest — ADR-0041's rule that what
could not be read is not an absence — and the turn goes on. The sentence says why in the row's
own words (`base.NotAsked`), which never carry a credential.

THE FILE LEAVES THROUGH THE PACK'S WITHHOLDINGS like every other file of it (`facts.gather`): it
is one of the files under `found/`, and those are finished with the rest.
"""

from __future__ import annotations

import logging

from beeverforge.adapters.knowledge_source import registry
from beeverforge.adapters.knowledge_source.base import Answered, NotAsked

log = logging.getLogger("beeverforge.product")

#: The pack's name for the file, under `facts.FOUND_DIR`.
FILE = "found/knowledge.md"


def answers(question: str, *, project=None) -> tuple[dict[str, str], list[str]]:
    """`(files, gaps)` for one message: `({}, [])` when no source is switched on or there is no
    question, `({FILE: text}, [])` when the source answered, `({}, [gap])` when it did not."""
    if not registry.switched_on() or not question.strip():
        return {}, []
    name = registry.display_name()
    source, why = registry.for_the_turn(project)
    if source is None:
        return {}, [_gap(name, why)]
    try:
        answered = source.ask(question.strip())
    except NotAsked as exc:
        log.warning("BEEVERFORGE_KNOWLEDGE_SOURCE_NOT_ASKED %s", exc)
        return {}, [_gap(name, str(exc))]
    except Exception:  # noqa: BLE001 — an add-on's row that raised is a gap, never a crash
        # ITS WORDS GO TO THE LOG, never into the manifest the role reads and answers from
        log.warning("BEEVERFORGE_KNOWLEDGE_SOURCE_NOT_ASKED the %s row raised", registry.kind(),
                    exc_info=True)
        return {}, [_gap(name, "it raised an error (the reason is in the platform's log)")]
    return {FILE: render(answered, name=name)}, []


def _gap(name: str, why: str) -> str:
    return (f"{name} could not be asked about this message: {' '.join(why.split())} — what it "
            f"holds about this is unknown, not absent: say you could not ask it, never that it "
            f"has nothing")


def render(answered: Answered, *, name: str) -> str:
    """The file: the question, whom it read as, the answer with its labels, the citations."""
    lines = [f"# What {name} answered", "",
             f"Asked, as this message asked it: {' '.join(answered.question.split())}", ""]
    if answered.read_as:
        lines += [f"It read as the role `{answered.read_as}`: what that role may read, and "
                  f"nothing else.", ""]
    if answered.abstained:
        lines += [f"It did not answer from what it may read: {answered.abstained}. Do not answer "
                  f"this from it; say it had nothing it could cite.", ""]
        return "\n".join(lines)
    lines += ["## The answer", "",
              "Each sentence ends with the labels of the documents it rests on. Say the label "
              "when you use a sentence; a sentence of yours that rests on none of them is not "
              "from here.", ""]
    for said in answered.sentences:
        labels = f" [{', '.join(said.citations)}]" if said.citations else ""
        lines.append(f"- {' '.join(said.text.split())}{labels}")
    lines += ["", "## What it cites", ""]
    for cited in answered.citations:
        where = cited.url or "no address given"
        version = f", version {cited.version}" if cited.version is not None else ""
        lines.append(f"- [{cited.label}] {' '.join(cited.title.split()) or '(untitled)'} — "
                     f"{where} · document {cited.document_id}{version} · "
                     f"{cited.classification or 'unclassified'}")
    if not answered.citations:
        lines.append("Nothing: an answer that cites nothing is not one to repeat.")
    return "\n".join(lines) + "\n"
