"""`beeverforge bot-token` says a failed mint in one sentence, never a traceback (#217).

Claims:
  - a key `jwt.encode` cannot sign with (a public-key PEM through `--key-path`, a whitespace key
    through `BEEVERFORGE_GH_APP_KEY` or `_CONTENT`) is one sentence naming the key's source, and
    nothing is sent to GitHub;
  - GitHub's refusal (`HTTPStatusError`) and an unreachable API (`TransportError`) are each one
    sentence naming the installation, with the check-the-ids remedy;
  - the signing translation wraps the signing step only, and is keyed off no exception's text.
"""

TEST = "tests/test_a_failed_mint_is_refused_in_words.py"
GA = "beeverforge/adapters/github_app.py"
CLI = "beeverforge/cli.py"

CANNOT_SIGN = (TEST + "::test_a_key_that_cannot_sign_is_refused_naming_its_source_and_nothing_"
               "is_sent")
ANY_TEXT = TEST + "::test_any_signing_failure_is_app_key_does_not_sign_whatever_its_text"
AFTER = TEST + "::test_a_failure_after_signing_is_not_called_a_key_that_cannot_sign"
REFUSED = (TEST + "::test_github_refusing_the_mint_is_one_sentence_naming_status_message_and_"
           "installation")
UNREACHABLE = TEST + "::test_github_unreachable_is_one_sentence_naming_the_installation"

MUTATIONS = [
    ("the signing translation removed: whatever the signer raises leaves the mint as itself", GA,
     "    try:\n        app_jwt = _app_jwt(app_id, private_key)\n"
     "    except Exception as exc:  # every failure to sign is one answer: "
     "this key does not sign\n"
     "        raise AppKeyDoesNotSign(type(exc).__name__) from exc\n",
     "    app_jwt = _app_jwt(app_id, private_key)\n", TEST),

    ("the signing translation keyed off one exception type, not every failure to sign", GA,
     "    except Exception as exc:  # every failure to sign is one answer: "
     "this key does not sign\n",
     "    except AttributeError as exc:\n", ANY_TEXT),

    ("the signing translation widened past signing: a failure after the JWT is called a key "
     "that does not sign", GA,
     "        raise AppKeyDoesNotSign(type(exc).__name__) from exc\n    r = httpx.post(\n"
     "        f\"https://api.github.com/app/installations/{installation_id}/access_tokens\",\n"
     "        headers={\"Authorization\": f\"Bearer {app_jwt}\", "
     "\"Accept\": \"application/vnd.github+json\"},\n"
     "        timeout=30,\n    )\n    r.raise_for_status()\n",
     "        raise AppKeyDoesNotSign(type(exc).__name__) from exc\n    try:\n"
     "        r = httpx.post(\n"
     "            f\"https://api.github.com/app/installations/{installation_id}/access_tokens\",\n"
     "            headers={\"Authorization\": f\"Bearer {app_jwt}\", "
     "\"Accept\": \"application/vnd.github+json\"},\n"
     "            timeout=30,\n        )\n        r.raise_for_status()\n"
     "    except Exception as exc:\n"
     "        raise AppKeyDoesNotSign(type(exc).__name__) from exc\n", AFTER),

    ("the CLI's translation of a key that cannot sign removed: the typed error is a traceback",
     CLI, "    except AppKeyDoesNotSign as exc:\n", "    except ArithmeticError as exc:\n",
     CANNOT_SIGN),

    ("the refusal names a fixed --key-path instead of where the key came from", CLI,
     "        typer.echo(f\"✗ the App key from {source} does not sign",
     "        typer.echo(f\"✗ the App key from --key-path does not sign", CANNOT_SIGN),

    ("the CLI's translation of GitHub's refusal removed: a 404 is a traceback", CLI,
     "    except httpx.HTTPStatusError as exc:\n", "    except ArithmeticError as exc:\n",
     REFUSED),

    ("GitHub's message dropped from its refusal: only the bare status is said", CLI,
     "{message or exc.response.reason_phrase}", "", REFUSED),

    ("GitHub's message read, then dropped for the 404's reason phrase (#372's review)",
     CLI, "{message or exc.response.reason_phrase}", "{exc.response.reason_phrase}", REFUSED),

    ("the CLI's translation of an unreachable API removed: a ConnectError is a traceback", CLI,
     "    except httpx.TransportError as exc:\n", "    except ArithmeticError as exc:\n",
     UNREACHABLE),
]
