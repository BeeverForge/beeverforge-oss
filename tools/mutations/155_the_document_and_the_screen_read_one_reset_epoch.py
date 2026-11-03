"""The document and the screen read ONE `reset_epoch`, so a minute boundary between the two
renders cannot make them disagree (#155).

Run:  .venv/bin/python tools/mutate.py tools/mutations/155_the_document_and_the_screen_read_one_reset_epoch.py

The claim, a row below that must go RED: the pinned API budget refills at one fixed moment, never
at the wall clock read again by each render. With the clock stubbed so the screen renders at
HH:MM:59.9 and the document a moment later, the two "refills at HH:MM" agree only while the epoch
is pinned. Closes #155.
"""

TEST = "tests/test_doctor_json_is_a_versioned_contract.py"

HELPER = "tests/pinned_probes.py"

MUTATIONS = [
    # The shape the flake had: each `diagnose` reads the clock for itself. `__import__` keeps the
    # cut valid in a module that no longer imports `time`, and it reads the stubbed `time.time`.
    ("reset_epoch is read from the clock at each render again", HELPER,
     "reset_epoch=RESET_EPOCH",
     'reset_epoch=int(__import__("time").time()) + 3600'),
]
