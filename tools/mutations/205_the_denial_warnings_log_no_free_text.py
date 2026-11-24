"""A refused message reaches no log line, proven by putting the words back.

Run:  .venv/bin/python tools/mutate.py tools/mutations/205_the_denial_warnings_log_no_free_text.py

`perform` prints `_loggable(key, params)` in its three denial warnings and in the INFO line. Each
row puts back one way the person's words reach a log.
"""

TEST = "tests/test_a_refused_message_reaches_no_log_line.py"
SOURCE = "beeverforge/actions/__init__.py"
GATE = TEST + "::test_a_refused_message_reaches_no_log_line_at_any_level"

MUTATIONS = [
    ("free text is printed as it was typed",
     SOURCE,
     '_words(v) if k in _FREE_TEXT and v else v)',
     'v)',
     GATE),
    ("the message is no longer free text",
     SOURCE,
     '{"message", "body",',
     '{"body",',
     GATE),
    ("the digest is dropped, the length alone is kept",
     SOURCE,
     'return {"chars": len(text), "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}',
     'return {"chars": len(text)}',
     GATE),
    ("a secret is printed",
     SOURCE,
     '("***" if k in _SECRET else _words',
     '(v if k in _SECRET else _words',
     TEST + "::test_a_secret_is_still_masked_beside_free_text"),
]
