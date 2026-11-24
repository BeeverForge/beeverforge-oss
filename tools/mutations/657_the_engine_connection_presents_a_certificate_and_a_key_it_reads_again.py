"""The engine connection presents a certificate AND a key, pins its server CA, and reads the key
again without reconnecting (#657).

Run:  .venv/bin/python tools/mutate.py tools/mutations/657_the_engine_connection_presents_a_certificate_and_a_key_it_reads_again.py

Rows 1-3 are the credentials together and the CA; rows 4-5 what the pool key covers; rows 6-11 the
key handed to the held client — on connect, by the refresher, kept for a bounded grace when a
re-read answers nothing, dropped at once when it is refused, and never overwritten by an older
read; the last rows a TLS file that cannot be read, said by name (review of CORE!664).
"""

TEST = "tests/test_the_engine_connection_presents_a_certificate_and_a_key_it_reads_again.py"
CONNECTION = "beeverforge/runtime/temporal/connection.py"
REGISTRY = "beeverforge/adapters/credential_store/registry.py"

MUTATIONS = [
    ("an API key replaces the client certificate again", CONNECTION,
     "    if cert and key:  # a client certificate: classic mTLS, or mTLS beside the key",
     "    if cert and key and not api_key.value:"),
    ("the engine's CA is never handed to the connection", CONNECTION,
     '        tls["server_root_ca_cert"] = _tls_file(',
     '        tls["unused"] = _tls_file('),
    ("a key alone no longer asks for TLS", CONNECTION,
     '        auth.setdefault("tls", True)',
     "        pass"),
    ("the pool key carries the key's value, so a rotation is a new client", CONNECTION,
     '        "api_key", "set" if api_key else "",',
     '        "api_key", api_key or "",'),
    ("the pool key ignores the engine's CA", CONNECTION,
     '        "server_ca", server_ca, _contents(server_ca),',
     '        "server_ca",'),
    ("a rotated key is not handed to the held client on connect", CONNECTION,
     "            if stored_key:\n                _settle(held, read, stored_key)",
     "            if False:\n                _settle(held, read, stored_key)"),
    ("the key is never actually set on the client", CONNECTION,
     "            client.api_key = value\n",
     "            pass\n"),
    # the review of the #657 branch: a bounded grace, the newest read wins, said once per state
    ("a re-read that answers nothing replaces the key with nothing at once", CONNECTION,
     '            phase = "kept" if holding and now - state.good_at < ttl else "dropped"',
     '            phase = "dropped"'),
    ("a key gone from its store is presented for ever", CONNECTION,
     "        if phase == \"dropped\" and holding:\n            client.api_key = None\n",
     "        if phase == \"dropped\" and holding:\n            pass\n"),
    ("a stale read overwrites a newer one", CONNECTION,
     "        if read < state.settled:\n            return False\n",
     "        if False:\n            return False\n"),
    ("a failure that persists is said at every read", CONNECTION,
     "        if state.said == (why, phase):\n            return False\n",
     "        if False:\n            return False\n"),
    ("a refusal is said as a key nobody holds", CONNECTION,
     '        what = {"refused": f"is refused by its store ({refused})",',
     '        what = {"refused": "is no longer held by its store (it answered nothing)",'),
    ("the grace is read, and an unreadable one said, at every read", CONNECTION,
     "            if state.grace is None:\n                state.grace = _stored_token_ttl()\n",
     "            if True:\n                state.grace = _stored_token_ttl()\n"),
    ("the grace never starts again after a good read", CONNECTION,
     "            state.good_at = now\n",
     "            pass\n"),
    # the review of CORE!664: a refusal is final at once, a store that fails is given the grace,
    # and a TLS file that cannot be read is said by name
    ("a refused re-read is given the grace again", CONNECTION,
     "        if refused and not failed:\n",
     "        if False:\n"),
    ("a store that failed is read as a refusal", CONNECTION,
     "        if refused and not failed:\n",
     "        if refused:\n"),
    ("the registry no longer tells a failed store from a refusal", REGISTRY,
     "                      failed=True)",
     "                      failed=False)"),
    ("a later silence claims to keep a key already let go of", CONNECTION,
     '            phase = "kept" if holding and now - state.good_at < ttl else "dropped"',
     '            phase = "kept" if now - state.good_at < ttl else "dropped"'),
    ("an unreadable TLS file raises the bare OSError again", CONNECTION,
     "    except OSError as exc:\n        raise EngineNotDeclared(",
     "    except ValueError as exc:\n        raise EngineNotDeclared("),
    ("the bare OSError is chained beneath the sentence", CONNECTION,
     '            f"process\'s user can read, or unset it") from None',
     '            f"process\'s user can read, or unset it") from exc'),
    ("the refresher ends at its first failed tick", CONNECTION,
     "            except Exception as exc:  # noqa: BLE001 — one failed read must not end the refresher\n",
     "            except Exception as exc:  # noqa: BLE001\n                raise\n"),
    ("no refresher is started for a held client with a key", CONNECTION,
     "        refresher.start()\n",
     "        pass\n"),
    ("a let-go client's refresher keeps running", CONNECTION,
     "    for old in ended:\n        old.stop()\n",
     "    for old in ended:\n        pass\n"),
]
