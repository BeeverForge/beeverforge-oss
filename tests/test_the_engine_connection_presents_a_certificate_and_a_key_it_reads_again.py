"""The engine connection presents a client certificate AND an API key, pins its own server CA, and
reads a stored API key again without reconnecting (#657).

THE GAPS. A worker connecting to a self-hosted Temporal server with mutual TLS and JWT
authorization both on could not authenticate:

  1. `_auth()` returned `{"api_key": key, "tls": True}` as soon as `TEMPORAL_API_KEY` answered and
     never added `TEMPORAL_TLS_CERT` / `TEMPORAL_TLS_KEY`, so a server that requires a client
     certificate refused the connection at the handshake;
  2. neither TLS path set `server_root_ca_cert`, so the engine connection trusted the process's
     whole trust store and a deployment could not pin the engine's CA without changing what every
     other TLS connection of the process trusts;
  3. the key was read once, at connect: a short-lived token made the worker fail when it expired.
     And the pool key digested the key's VALUE, so a rotated key was a new client — which the
     worker, holding the client it was born with, never asked for.

WHAT IS HELD HERE, through `_auth()`, `fingerprint()` and the real `connection.connect` with
`Client.connect` replaced by a recorder (the seam `tests/conftest.py` already holds):

  · both credentials together; either alone exactly as before; neither, nothing;
  · `TEMPORAL_TLS_SERVER_CA_CERT` as the connection's `server_root_ca_cert` and nowhere else, in
    every mode; unset, nothing changes;
  · the pool key changes with the CA's contents and with whether a key is set, never with the
    key's value, and carries neither;
  · a key that changed where it is stored is handed to the client the process already holds — on
    the next `connect()`, and by the refresher every `TEMPORAL_AUTH_REFRESH_SECONDS` for a
    holder that never asks again (the worker) — through the client's `api_key` setter, without a
    second `Client.connect`;
  · a re-read that is refused or answers nothing keeps the key the client has, said once by name;
  · no key value reaches a log line.

No test here waits on real time: the refresher's wait is handed in. The same properties against a
real server: `tests/test_a_worker_holds_its_engine_under_mutual_tls_and_a_token.py`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading

import pytest
from temporalio.client import Client
from temporalio.service import TLSConfig

from beeverforge.adapters.credential_store.file import DIR_VAR
from beeverforge.adapters.credential_store.registry import STORE_VAR
from beeverforge.runtime.temporal import connection

FIRST = "fictitious-657-first-key"
SECOND = "fictitious-657-second-key"


class _Client:
    """A client that is not a client: it records what its `api_key` setter was handed, which is
    the one way temporalio lets a held client present a new key without reconnecting."""

    def __init__(self, n: int, api_key: str | None) -> None:
        self.n = n
        self._key = api_key
        self.set_to: list[str | None] = []

    @property
    def api_key(self) -> str | None:
        return self._key

    @api_key.setter
    def api_key(self, value: str | None) -> None:
        self.set_to.append(value)
        self._key = value

    def __repr__(self) -> str:
        return f"<fake client {self.n}>"


@pytest.fixture
def engine(monkeypatch):
    """A declared engine, every TLS and key setting unset, and `Client.connect` recording what it
    was handed and answering a `_Client`."""
    monkeypatch.setenv("TEMPORAL_ADDRESS", "engine.example:7233")
    for name in ("TEMPORAL_ENDPOINT", "TEMPORAL_API_KEY", "TEMPORAL_TLS_CERT", "TEMPORAL_TLS_KEY",
                 "TEMPORAL_TLS_SERVER_CA_CERT", "TEMPORAL_AUTH_REFRESH_SECONDS",
                 "BEEVERFORGE_LOG_FORMAT", STORE_VAR, DIR_VAR):
        monkeypatch.delenv(name, raising=False)
    made: list[dict] = []

    async def record(*_args, **kwargs):
        await asyncio.sleep(0)
        made.append(kwargs)
        return _Client(len(made), kwargs.get("api_key"))

    monkeypatch.setattr(Client, "connect", record)
    connection.forget()
    yield made
    connection.forget()


def _files(tmp_path, **contents: bytes) -> dict[str, str]:
    paths = {}
    for name, data in contents.items():
        path = tmp_path / name
        path.write_bytes(data)
        paths[name] = str(path)
    return paths


def _mtls(monkeypatch, tmp_path) -> None:
    files = _files(tmp_path, cert=b"CLIENT-CERT", key=b"CLIENT-KEY")
    monkeypatch.setenv("TEMPORAL_TLS_CERT", files["cert"])
    monkeypatch.setenv("TEMPORAL_TLS_KEY", files["key"])


def _stored_key(monkeypatch, tmp_path, value: str):
    """`TEMPORAL_API_KEY` as a file in the `file` store — the shape a mounted, rotated secret has."""
    secrets = tmp_path / "secrets"
    secrets.mkdir(mode=0o700)
    held = secrets / "TEMPORAL_API_KEY"
    held.write_text(value)
    held.chmod(0o600)
    monkeypatch.setenv(STORE_VAR, "file")
    monkeypatch.setenv(DIR_VAR, str(secrets))
    return held


# ── 1. a certificate AND a key ──────────────────────────────────────────────────────────────────

def test_a_key_and_a_certificate_together_present_BOTH(engine, monkeypatch, tmp_path):
    monkeypatch.setenv("TEMPORAL_API_KEY", FIRST)
    _mtls(monkeypatch, tmp_path)

    auth = connection._auth()

    assert auth.get("api_key") == FIRST, "the API key was dropped beside the client certificate"
    tls = auth.get("tls")
    assert isinstance(tls, TLSConfig), (
        f"tls is {tls!r}: the client certificate was dropped because an API key answered — a "
        f"server that requires client certificates refuses that connection at the handshake")
    assert (tls.client_cert, tls.client_private_key) == (b"CLIENT-CERT", b"CLIENT-KEY")
    assert tls.server_root_ca_cert is None


def test_a_key_ALONE_is_as_it_was(engine, monkeypatch):
    monkeypatch.setenv("TEMPORAL_API_KEY", FIRST)

    assert connection._auth() == {"api_key": FIRST, "tls": True}


def test_a_certificate_ALONE_is_as_it_was(engine, monkeypatch, tmp_path):
    _mtls(monkeypatch, tmp_path)

    auth = connection._auth()

    assert set(auth) == {"tls"}, auth
    assert auth["tls"] == TLSConfig(client_cert=b"CLIENT-CERT", client_private_key=b"CLIENT-KEY")


def test_NOTHING_is_still_a_plain_dev_server(engine):
    assert connection._auth() == {}


def test_a_refused_certificate_key_beside_an_answered_api_key_is_still_final(
        engine, monkeypatch, tmp_path):
    """A refusal opens no door (#822), with a key beside it as without: the connection is not
    made with the API key alone in place of the certificate the deployment asked for."""
    monkeypatch.setenv("TEMPORAL_API_KEY", FIRST)
    files = _files(tmp_path, cert=b"CLIENT-CERT")
    monkeypatch.setenv("TEMPORAL_TLS_CERT", files["cert"])
    secrets = tmp_path / "secrets"
    secrets.mkdir(mode=0o700)
    loose = secrets / "TEMPORAL_TLS_KEY"
    loose.write_text(str(tmp_path / "client.key"))
    loose.chmod(0o666)  # group- and world-writable: the file store refuses it
    monkeypatch.setenv(STORE_VAR, "file")
    monkeypatch.setenv(DIR_VAR, str(secrets))

    with pytest.raises(RuntimeError, match="TEMPORAL_TLS_KEY") as refused:
        connection._auth()
    assert FIRST not in str(refused.value)


# ── 2. the engine's own CA, for the engine connection alone ────────────────────────────────────

@pytest.mark.parametrize("mode", ["key", "certificate", "both", "neither"])
def test_the_server_CA_is_the_connections_root_in_every_mode(engine, monkeypatch, tmp_path, mode):
    ca = _files(tmp_path, ca=b"ENGINE-CA")["ca"]
    monkeypatch.setenv("TEMPORAL_TLS_SERVER_CA_CERT", ca)
    if mode in ("key", "both"):
        monkeypatch.setenv("TEMPORAL_API_KEY", FIRST)
    if mode in ("certificate", "both"):
        _mtls(monkeypatch, tmp_path)
    before = dict(os.environ)

    auth = connection._auth()

    tls = auth.get("tls")
    assert isinstance(tls, TLSConfig), f"{mode}: tls is {tls!r}, the engine's CA was not used"
    assert tls.server_root_ca_cert == b"ENGINE-CA", (
        f"{mode}: the connection's root is {tls.server_root_ca_cert!r}, not the engine's CA")
    assert (tls.client_cert is not None) == (mode in ("certificate", "both")), mode
    assert (auth.get("api_key") == FIRST) == (mode in ("key", "both")), mode
    assert dict(os.environ) == before, (
        "reading the engine's CA changed the process environment — the CA is for the engine "
        "connection alone, never the trust store every other TLS connection of the process uses")


def test_an_UNSET_server_CA_leaves_the_trust_store_as_it_was(engine, monkeypatch, tmp_path):
    _mtls(monkeypatch, tmp_path)

    assert connection._auth()["tls"].server_root_ca_cert is None


# ── 3. what the pool key covers, and what it never carries ─────────────────────────────────────

def test_the_key_changes_with_the_CA_and_never_carries_it(engine, monkeypatch, tmp_path):
    ca = tmp_path / "engine-ca.pem"
    ca.write_bytes(b"CA-BEFORE")
    unset = connection.fingerprint()
    monkeypatch.setenv("TEMPORAL_TLS_SERVER_CA_CERT", str(ca))
    before = connection.fingerprint()
    ca.write_bytes(b"CA-ROTATED-IN-PLACE")
    after = connection.fingerprint()

    assert len({unset, before, after}) == 3, (
        f"the pool key did not follow the engine's CA: {unset} / {before} / {after}")
    for key in (before, after):
        assert "CA-" not in repr(key) and str(ca) not in repr(key), key


def test_the_key_follows_WHETHER_a_key_is_set_and_never_its_value(engine, monkeypatch):
    without = connection.fingerprint()
    monkeypatch.setenv("TEMPORAL_API_KEY", FIRST)
    first = connection.fingerprint()
    monkeypatch.setenv("TEMPORAL_API_KEY", SECOND)
    second = connection.fingerprint()

    assert without != first, "a key that appeared did not change the pool key"
    assert first == second, (
        "the pool key changed with the key's VALUE, so a rotated key makes a new client — and the "
        "worker, which holds the client it was born with, never asks for one")
    assert FIRST not in repr(first) and SECOND not in repr(second)


# ── 4. a rotated key reaches the client the process holds, without a reconnect ─────────────────

async def test_a_rotated_key_is_handed_to_the_HELD_client_on_the_next_connect(
        engine, monkeypatch, tmp_path):
    _mtls(monkeypatch, tmp_path)
    held = _stored_key(monkeypatch, tmp_path, FIRST)

    client = await connection.connect()
    held.write_text(SECOND)
    again = await connection.connect()

    assert again is client, f"a rotated key made a new client: {client!r} then {again!r}"
    assert len(engine) == 1, f"a rotated key reconnected: {len(engine)} Client.connect calls"
    assert client.set_to == [SECOND], (
        f"the held client was handed {client.set_to!r}, not the key now stored")
    assert engine[0]["api_key"] == FIRST and isinstance(engine[0]["tls"], TLSConfig)


async def test_an_UNCHANGED_key_is_not_handed_again(engine, monkeypatch):
    monkeypatch.setenv("TEMPORAL_API_KEY", FIRST)

    client = await connection.connect()
    await connection.connect()

    assert client.set_to == [], client.set_to


def test_the_refresher_hands_a_rotated_key_to_a_holder_that_never_asks_again(
        engine, monkeypatch, tmp_path):
    """The worker is born with its client and never calls `connect()` again, so the refresher is
    what reads the store for it. Driven with the wait handed in: each `False` is one interval."""
    held = _stored_key(monkeypatch, tmp_path, FIRST)
    client = _Client(1, FIRST)
    waited: list[float] = []
    ticks = iter([False, False, False, True])

    def wait(seconds: float) -> bool:
        waited.append(seconds)
        if len(waited) == 2:
            held.write_text(SECOND)   # rotated between the first and the second re-read
        return next(ticks)

    connection._KeyRefresh(client, every=7.0, wait=wait).run()

    assert waited == [7.0] * 4, waited
    assert client.set_to == [SECOND], (
        f"three re-reads across one rotation handed the client {client.set_to!r}")
    assert client.api_key == SECOND


@pytest.mark.parametrize("how", ["refused", "gone"])
def test_a_reread_that_fails_KEEPS_the_key_and_says_so_by_name(
        engine, monkeypatch, tmp_path, caplog, how):
    held = _stored_key(monkeypatch, tmp_path, FIRST)
    client = _Client(1, FIRST)
    if how == "refused":
        held.chmod(0o666)   # anyone may write it: the file store refuses it
    else:
        held.unlink()

    with caplog.at_level(logging.DEBUG):
        presented = connection.refresh_api_key(client)

    assert presented is False
    assert client.set_to == [] and client.api_key == FIRST, (
        "a re-read that failed replaced the key the client holds — a refusal is not a new key")
    said = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(said) == 1 and "TEMPORAL_API_KEY" in said[0], said
    assert FIRST not in caplog.text


async def test_a_held_client_with_a_key_has_ONE_refresher_and_it_ends_with_the_client(
        engine, monkeypatch, tmp_path):
    monkeypatch.setenv("TEMPORAL_API_KEY", FIRST)
    monkeypatch.setenv("TEMPORAL_AUTH_REFRESH_SECONDS", "3600")

    client = await connection.connect()
    await connection.connect()

    refreshers = list(connection._REFRESHING.values())
    assert len(refreshers) == 1, f"{len(refreshers)} refreshers for one held client"
    refresher = refreshers[0]
    assert refresher.client is client and refresher.every == 3600.0
    assert refresher.thread.is_alive() and refresher.thread.daemon

    monkeypatch.delenv("TEMPORAL_API_KEY")      # the target changes: the old client is let go
    await connection.connect()
    refresher.thread.join(timeout=5)
    assert not refresher.thread.is_alive(), "the let-go client's refresher kept running"
    assert connection._REFRESHING == {}, "a client without a key was given a refresher"


async def test_forget_stops_the_refresher(engine, monkeypatch):
    monkeypatch.setenv("TEMPORAL_API_KEY", FIRST)
    await connection.connect()
    (refresher,) = connection._REFRESHING.values()

    connection.forget()

    refresher.thread.join(timeout=5)
    assert not refresher.thread.is_alive()
    assert connection._REFRESHING == {}


@pytest.mark.parametrize(("declared", "every"), [
    (None, 60.0), ("", 60.0), ("15", 15.0), ("2.5", 2.5),
    ("0", 60.0), ("-3", 60.0), ("soon", 60.0), ("nan", 60.0), ("inf", 60.0),
])
def test_the_refresh_interval_is_a_setting(monkeypatch, declared, every):
    if declared is None:
        monkeypatch.delenv(connection.AUTH_REFRESH_VAR, raising=False)
    else:
        monkeypatch.setenv(connection.AUTH_REFRESH_VAR, declared)

    assert connection.AUTH_REFRESH_VAR == "TEMPORAL_AUTH_REFRESH_SECONDS"
    assert connection.api_key_refresh_every() == every


def test_a_presented_key_is_said_by_name_never_by_value(engine, monkeypatch, tmp_path, caplog):
    held = _stored_key(monkeypatch, tmp_path, FIRST)
    client = _Client(1, FIRST)
    held.write_text(SECOND)

    with caplog.at_level(logging.DEBUG):
        assert connection.refresh_api_key(client) is True

    assert client.api_key == SECOND
    assert "TEMPORAL_API_KEY" in caplog.text
    assert FIRST not in caplog.text and SECOND not in caplog.text


def test_a_refresher_that_raises_keeps_running(engine, monkeypatch, caplog):
    """One failed tick is one warning, not a dead refresher: the next interval reads again."""
    calls = []

    def boom(client):
        calls.append(client)
        if len(calls) == 1:
            raise RuntimeError("the store's own failure")
        return False

    monkeypatch.setattr(connection, "refresh_api_key", boom)
    ticks = iter([False, False, True])
    with caplog.at_level(logging.WARNING):
        connection._KeyRefresh(_Client(1, FIRST), every=1.0, wait=lambda _s: next(ticks)).run()

    assert len(calls) == 2, calls
    assert any("TEMPORAL_API_KEY" in r.getMessage() for r in caplog.records), caplog.text


def test_the_refresher_thread_is_named_for_what_it_does(engine):
    refresher = connection._KeyRefresh(_Client(1, FIRST), every=1.0,
                                       wait=threading.Event().wait)
    assert "engine-api-key" in refresher.thread.name


# ── 5. a key that stays gone is let go of, after a bounded grace (review of the #657 branch) ───

class _Clock:
    """`connection._now`, moved by the test."""

    def __init__(self) -> None:
        self.at = 1000.0

    def __call__(self) -> float:
        return self.at


@pytest.fixture
def clock(monkeypatch):
    moved = _Clock()
    monkeypatch.setattr(connection, "_now", moved)
    monkeypatch.setenv("BEEVERFORGE_STORED_TOKEN_TTL", "100")
    return moved


def _warnings(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]


def test_a_key_GONE_from_its_store_is_kept_for_the_grace_then_dropped(
        engine, monkeypatch, tmp_path, caplog, clock):
    """A static key never expires on the server, so keeping a removed key for ever is keeping a
    revoked credential for ever. It is kept for `BEEVERFORGE_STORED_TOKEN_TTL` after its last good
    read, then the client presents NO key — it fails closed — and says so by name."""
    held = _stored_key(monkeypatch, tmp_path, FIRST)
    client = _Client(1, FIRST)
    with caplog.at_level(logging.DEBUG):
        connection.refresh_api_key(client)          # the last good read, at 1000
        held.unlink()
        for at in (1050.0, 1070.0, 1099.0):         # inside the grace
            clock.at = at
            connection.refresh_api_key(client)
        inside = _warnings(caplog)
        assert client.api_key == FIRST and client.set_to == [], client.set_to
        for at in (1101.0, 1200.0, 1300.0):         # past it
            clock.at = at
            connection.refresh_api_key(client)

    assert client.set_to == [None], (
        f"past the grace the client was handed {client.set_to!r}: a key nobody stores any more "
        f"was still presented")
    assert len(inside) == 1, f"one state, {len(inside)} warnings: {inside}"
    assert "no longer held" in inside[0] and "BEEVERFORGE_STORED_TOKEN_TTL" in inside[0], inside
    said = _warnings(caplog)
    assert len(said) == 2, f"two states, {len(said)} warnings: {said}"
    assert "TEMPORAL_API_KEY" in said[1] and "no key" in said[1], said[1]
    assert FIRST not in caplog.text


def test_a_REFUSED_reread_is_said_as_a_refusal_not_as_a_key_nobody_holds(
        engine, monkeypatch, tmp_path, caplog, clock):
    held = _stored_key(monkeypatch, tmp_path, FIRST)
    client = _Client(1, FIRST)
    connection.refresh_api_key(client)
    held.chmod(0o666)

    with caplog.at_level(logging.DEBUG):
        for at in (1010.0, 1020.0, 1030.0, 1040.0):
            clock.at = at
            connection.refresh_api_key(client)

    said = _warnings(caplog)
    assert len(said) == 1, f"a refusal that persists was said {len(said)} times: {said}"
    assert "refused" in said[0] and "no longer held" not in said[0], said[0]
    assert client.api_key == FIRST


def test_a_key_that_COMES_BACK_is_presented_and_the_grace_starts_again(
        engine, monkeypatch, tmp_path, caplog, clock):
    held = _stored_key(monkeypatch, tmp_path, FIRST)
    client = _Client(1, FIRST)
    connection.refresh_api_key(client)
    held.unlink()
    clock.at = 1200.0
    connection.refresh_api_key(client)                  # past the grace: dropped
    held.write_text(SECOND)
    held.chmod(0o600)
    clock.at = 1210.0

    assert connection.refresh_api_key(client) is True
    assert client.api_key == SECOND and client.set_to == [None, SECOND], client.set_to

    held.unlink()
    clock.at = 1300.0                                   # 90 s after the good read: kept
    connection.refresh_api_key(client)
    assert client.api_key == SECOND, "the grace did not start again from the last good read"


# ── 6. connect() and the refresher never set a stale key over a newer one ──────────────────────

async def test_a_STALE_reread_does_not_overwrite_a_key_connect_handed_over_since(
        engine, monkeypatch):
    """The refresher reads the old key, connect() reads and hands over the new one, then the
    refresher's read lands. The read that STARTED later wins, whatever order they end in."""
    from beeverforge.adapters.credential_store import registry
    from beeverforge.adapters.credential_store.registry import Answer

    monkeypatch.setenv("TEMPORAL_API_KEY", FIRST)
    client = await connection.connect()
    entered, release = threading.Event(), threading.Event()

    def stale(name, *, quiet=False):
        entered.set()
        assert release.wait(5), "the test never released the stale read"
        return Answer(reference=f"env:{name}", value=FIRST)

    monkeypatch.setattr(registry, "lookup", stale)
    reader = threading.Thread(target=connection.refresh_api_key, args=(client,))
    reader.start()
    assert entered.wait(5)
    monkeypatch.setenv("TEMPORAL_API_KEY", SECOND)
    assert await connection.connect() is client
    assert client.api_key == SECOND
    release.set()
    reader.join(timeout=5)

    assert not reader.is_alive()
    assert client.api_key == SECOND, (
        f"the refresher's stale read overwrote the newer key: the client was handed "
        f"{client.set_to!r}")


def test_an_INVALID_grace_is_said_once_per_lapse_not_at_every_read(
        engine, monkeypatch, tmp_path, caplog, clock):
    """The grace is read once when a lapse begins and kept for it: an unreadable
    `BEEVERFORGE_STORED_TOKEN_TTL` is said once, not at every interval (re-review of #657)."""
    monkeypatch.setenv("BEEVERFORGE_STORED_TOKEN_TTL", "soon")
    held = _stored_key(monkeypatch, tmp_path, FIRST)
    client = _Client(1, FIRST)
    connection.refresh_api_key(client)
    held.unlink()

    with caplog.at_level(logging.DEBUG):
        for at in (1010.0, 1020.0, 1030.0, 5000.0, 5010.0):   # inside the hour, then past it
            clock.at = at
            connection.refresh_api_key(client)

    about_the_grace = [m for m in _warnings(caplog) if "is not a number of seconds" in m]
    assert len(about_the_grace) == 1, (
        f"the unreadable grace was said {len(about_the_grace)} times in one lapse")
    assert client.set_to == [None], "the hour the unreadable setting falls back to was not used"
