"""A product proposal's actual confirmation validates, and its required typed sentence is held."""

TEST = ("tests/test_the_event_models_describe_every_frame_the_streams_send.py"
        "::test_a_proposal_reply_carries_the_confirmation_the_product_role_produces")

MUTATIONS = [
    ("the reply schema describes a list instead of the actual confirmation object",
     "beeverforge/api/events.py",
     "    options: ConfirmationOptions | None\n", "    options: list[Any] | None\n"),
    ("the confirmation no longer requires the typed-answer sentence",
     "beeverforge/api/events.py",
     "    typed: str\n", '    typed: str = ""\n'),
]
