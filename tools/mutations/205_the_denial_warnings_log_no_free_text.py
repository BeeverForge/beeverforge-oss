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
     'v if k in _SAFE or not _says(v) else _words(v))',
     'v)',
     GATE),
    ("a parameter that takes words is put back in the safe list",
     SOURCE,
     '"project", "promote",',
     '"project", "promote", "restated",',
     TEST + "::test_a_parameter_that_takes_words_is_digested_not_printed"),
    ("a catalogue parameter is neither safe nor digested",
     SOURCE,
     'if k in _SAFE or not _says(v)',
     'if k in _SAFE or not _says(v) or k == "decision"',
     TEST + "::test_every_string_parameter_in_the_catalogue_is_safe_or_digested"),
    ("the digest is dropped, the length alone is kept",
     SOURCE,
     'return {"chars": len(text), "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}',
     'return {"chars": len(text)}',
     GATE),
    ("a secret is printed",
     SOURCE,
     '("***" if k in _SECRET else v',
     '(v if k in _SECRET else v',
     TEST + "::test_a_secret_is_still_masked_beside_free_text"),
]
