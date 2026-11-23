"""An agent run's turns and tokens are summed over its result events (#644).

Run:  .venv/bin/python tools/mutate.py \
      tools/mutations/644_a_run_is_counted_over_all_its_result_events.py
"""

TEST = "tests/test_a_run_is_counted_over_all_its_result_events.py"
AGENT = "beeverforge/adapters/agent/claude_code.py"

MUTATIONS = [
    ("the summing is cut: only the last result event's counts are read", AGENT,
     "    return sum(counts) if counts else None", "    return counts[-1] if counts else None"),
    ("the first result event is the run's outcome", AGENT,
     "            final = evt\n            results.append(evt)",
     "            final = final or evt\n            results.append(evt)"),
]
