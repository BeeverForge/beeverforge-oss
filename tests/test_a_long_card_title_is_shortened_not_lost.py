"""A breakdown's card whose title the redrafts left too long is shortened, not lost (#476).

THE DEFECT. A requirement's only front came back with a title of 84 characters. The floor refused
it ("the title has 84 characters; the limit is 80"), the redraft did not shorten it, and the card was
not filed — so the whole breakdown ended with no card, though nothing else about the card was wrong.

Now, when the title's length is the ONLY thing the floor still finds after the redrafts, the title
is shortened in whole words (the trailing clause first) and the card goes through the floor and the
judge once more, with no redraft. Anything else they find still refuses it, and a title within the
limit is never touched. The doubles are the judge and the redraft; the check is the shipped
`cards.vet_issue`.
"""

from __future__ import annotations

import pytest

from beeverforge.product import cards
from beeverforge.product.cards import TITLE_LIMIT, shortened_title
from tests.test_a_card_is_drafted_and_judged_before_the_yes import ISSUE, _judge_says, _vet

LONG = ("Metamodel v0.1 is published once by the delivery pipeline, with the system recorded as "
        "its author")


def test_a_title_within_the_limit_is_left_alone():
    assert shortened_title("Short title") == "Short title"


def test_the_trailing_clause_goes_first():
    assert shortened_title(LONG) == "Metamodel v0.1 is published once by the delivery pipeline"


@pytest.mark.parametrize("title", [
    LONG,
    "'My requests' lists only the signed-in user's own requests, updates live without a reload "
    "and never shows another person's draft",
    "A" * 120,
    "word " * 40,
    "short head, " + "then a very long tail of words that goes on and on past the limit of a title",
])
def test_the_result_is_within_the_limit_and_never_cuts_a_word(title):
    short = shortened_title(title)

    whole = " ".join(title.split())
    assert 0 < len(short) <= TITLE_LIMIT
    if " " in whole:
        assert whole.startswith(short) and whole[len(short):len(short) + 1] in (" ", ",", ";")


def test_a_clause_that_would_leave_too_little_is_not_the_cut():
    # dropping everything after "short head" would leave 10 characters of an 80 limit
    title = "short head, " + "then a very long tail of words that goes on and on and on well past the limit"
    assert len(title) > TITLE_LIMIT and len(shortened_title(title)) > TITLE_LIMIT // 2


def test_a_card_the_redraft_left_too_long_is_filed_shortened_and_judged_on_it():
    judged = []
    kept, why = _vet({**ISSUE, "title": LONG}, lambda p: judged.append(p) or _judge_says(5),
                     lambda p: {"title": LONG})  # the redraft keeps the long title

    assert why == "" and kept["title"] == shortened_title(LONG)
    assert kept["objective"] == ISSUE["objective"]
    [prompt] = judged
    assert f"# {shortened_title(LONG)}\n" in prompt  # the judge read the shortened card


def test_with_no_redraft_the_long_title_is_shortened_too():
    kept, why = _vet({**ISSUE, "title": LONG}, lambda p: _judge_says(5))

    assert why == "" and len(kept["title"]) <= TITLE_LIMIT


def test_a_long_title_with_another_problem_is_still_refused():
    kept, why = _vet({**ISSUE, "title": LONG, "acceptance_criteria": []}, lambda p: _judge_says(5),
                     lambda p: {"title": LONG})

    assert kept is None and why


def test_the_judge_still_decides_on_the_shortened_card():
    kept, why = _vet({**ISSUE, "title": LONG}, lambda p: _judge_says(2, findings=["vague"]))

    assert kept is None and why


def test_the_shortening_is_said_in_the_log(caplog):
    caplog.set_level("INFO", logger=cards.log.name)

    _vet({**ISSUE, "title": LONG}, lambda p: _judge_says(5))

    assert "BEEVERFORGE_CARD_TITLE_SHORTENED" in caplog.text


def test_a_shortened_card_is_not_redrafted_back_into_a_long_one():
    # the judge blocks every draft and the redraft always answers the long title: the shortened
    # card is judged once, with no redraft, and refused — not shortened and lengthened for ever
    judged = []
    kept, why = _vet({**ISSUE, "title": LONG},
                     lambda p: judged.append(p) or _judge_says(2, findings=["vague"]),
                     lambda p: {"title": LONG})

    assert kept is None and why and len(judged) == 1
