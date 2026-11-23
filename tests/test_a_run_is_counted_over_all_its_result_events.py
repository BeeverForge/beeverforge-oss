"""An agent run's turns and tokens are those of the whole run, not of its last result event (#644).

A run that is resumed inside one invocation prints one `result` event per leg, each counting only
its own turns and tokens, while `total_cost_usd` is cumulative. Reading the last event alone
reported the last leg as the run. Turns and tokens are summed; the cost is the last cumulative
figure; and `ok`, the summary, the pause and the model rejection still read the last event.
"""

from __future__ import annotations

import json

from beeverforge.adapters.agent.claude_code import _parse_stream


def _result(*, turns, tokens, cost, is_error=False, result="done"):
    return {"type": "result", "is_error": is_error, "result": result, "num_turns": turns,
            "total_cost_usd": cost,
            "usage": {"input_tokens": tokens[0], "output_tokens": tokens[1]}}


def _stream(*events) -> str:
    return "\n".join(json.dumps(e) for e in events)


def test_two_result_events_are_summed_and_the_cost_is_the_last_cumulative():
    out = _stream(_result(turns=20, tokens=(100, 6000), cost=1.5, result="first"),
                  _result(turns=8, tokens=(40, 3697), cost=2.25, result="second"))
    r = _parse_stream(0, out)
    assert (r.num_turns, r.input_tokens, r.output_tokens) == (28, 140, 9697)
    assert r.cost_usd == 2.25
    assert r.summary == "second"


def test_a_one_result_stream_answers_as_it_did():
    r = _parse_stream(0, _stream(_result(turns=5, tokens=(7, 11), cost=0.3)))
    assert (r.num_turns, r.input_tokens, r.output_tokens, r.cost_usd) == (5, 7, 11, 0.3)


def test_a_result_without_usage_is_unknown_not_zero():
    out = _stream({"type": "result", "is_error": False, "result": "x"})
    r = _parse_stream(0, out)
    assert (r.num_turns, r.input_tokens, r.output_tokens) == (None, None, None)


def test_ok_reads_the_last_result_event():
    bad = _result(turns=1, tokens=(1, 1), cost=0.1, is_error=True, result="boom")
    good = _result(turns=1, tokens=(1, 1), cost=0.2)
    assert _parse_stream(0, _stream(bad, good)).ok is True
    assert _parse_stream(0, _stream(good, bad)).ok is False
