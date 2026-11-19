"""#118: no form of the Jira credential reaches a refusal or a log line (2026-11-19).

The tracker sends `Authorization: Basic base64(email:token)`. That value carries the token without
containing it as text, so a test that looked only for the plaintext token stayed green over a
leak of the header. The claims these cuts hold:

  - the mismatch refusal never carries the token, the base64 `email:token` pair or the
    `Basic …` header value, in its text, its args or any log line;
  - a probe of `GET myself` that could not be made logs why, never the request's credential.

Each cut keeps its form of the leak and nothing else: the refusal keeps its code and sentence, and
the log line keeps its `%s` arity, so the red comes from the leak check, not from a format error.
"""

TEST = ("tests/test_on_jira_an_email_and_a_token_of_different_accounts_are_named_not_read_as_"
        "missing.py")
JIRA = "beeverforge/adapters/tracker/jira.py"

MUTATIONS = [
    ("the Authorization header the tracker sends is written into the mismatch refusal", JIRA,
     "                                                   refused=self.refused),",
     "                                                   refused=self.refused) "
     "+ str(self._headers()),"),

    ("a probe that could not be made writes the request's headers, credential included, into "
     "the log", JIRA,
     "\"404, since nothing says the credential was not accepted\", str(exc)[:200])",
     "\"404, since nothing says the credential was not accepted\" + str(req.headers), "
     "str(exc)[:200])"),
]
