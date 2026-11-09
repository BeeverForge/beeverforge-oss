"""A mint that fails is a sentence from `beeverforge bot-token`, never a traceback (#217).

THE DEFECT, measured on the former name with a fictitious key from `openssl genrsa 2048`:

  - GitHub refusing the mint (`404 Not Found` for an installation the App does not have) ended in
    a Rich traceback out of `r.raise_for_status()`: `HTTPStatusError`, rc=1;
  - `--key-path` naming the PUBLIC half of a key ended in a traceback through `_app_jwt` and
    `jwt.encode`: `AttributeError: 'RSAPublicKey' object has no attribute 'sign'`, with nothing
    sent;
  - a key of whitespace only through the environment reached `jwt.encode` as truthy text and
    raised `InvalidKeyError` as a traceback.

THE TRANSLATION IS BY TYPE, never by an exception's text: `mint_installation_token` wraps the
signing step, and only that step, into `AppKeyDoesNotSign`; the CLI catches that and httpx's own
`HTTPStatusError` / `TransportError`.

The only stub is `httpx.post` inside `beeverforge.adapters.github_app`, with the exact keyword
signature the mint calls it with. The keys are real RSA keys made once per module.
"""

from __future__ import annotations

import functools

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from typer.testing import CliRunner

from beeverforge.adapters import github_app as ga
from beeverforge.cli import app

APP_VARS = ("BEEVERFORGE_GH_APP_ID", "BEEVERFORGE_GH_APP_INSTALLATION_ID",
            "BEEVERFORGE_GH_APP_KEY", "BEEVERFORGE_GH_APP_KEY_CONTENT")

TOKENS_URL = "https://api.github.com/app/installations/{}/access_tokens"


@functools.cache
def _key() -> rsa.RSAPrivateKey:
    """A fictitious App key, made once for the module (2048-bit RSA, as GitHub issues)."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _private_pem() -> str:
    return _key().private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode()


def _public_pem() -> str:
    return _key().public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()


@pytest.fixture
def posts(monkeypatch):
    """Every call to GitHub's token endpoint, recorded; the answer is set per test."""
    calls: list[str] = []
    for var in APP_VARS:
        monkeypatch.delenv(var, raising=False)
    return calls


def _answer(monkeypatch, calls, respond):
    def post(url, *, headers, timeout):
        calls.append(url)
        return respond(url)

    monkeypatch.setattr(ga.httpx, "post", post)


def _never(url):
    raise AssertionError(f"nothing may be sent to GitHub for a key that cannot sign: {url}")


def _refused_in_one_sentence(result) -> str:
    assert result.exit_code == 1, result.output
    assert isinstance(result.exception, SystemExit), (
        f"the refusal must be a sentence, not an exception: {result.exception!r}")
    assert result.stdout == "", f"stdout carries the token alone: {result.stdout!r}"
    assert "Traceback" not in result.output
    stderr = result.stderr.strip()
    assert stderr.startswith("✗ "), stderr
    assert "\n" not in stderr, f"one sentence, one line: {stderr!r}"
    return stderr


@pytest.mark.parametrize("delivery", ["key-path-public-pem", "key-variable-blank-file",
                                      "content-variable-blank"])
def test_a_key_that_cannot_sign_is_refused_naming_its_source_and_nothing_is_sent(
        delivery, posts, monkeypatch, tmp_path):
    """Criterion: a key `jwt.encode` cannot sign with is refused in one sentence naming its source
    and the remedy, exit 1, stdout empty, no traceback, and `httpx.post` never called.

    `BEEVERFORGE_GH_APP_KEY` is a PATH variable today, so "holding whitespace only" is the key it
    delivers: a file of whitespace (a whitespace path does not exist, and the "need the App id"
    sentence answers before the signer). The content form is the same key handed directly."""
    _answer(monkeypatch, posts, _never)
    argv = ["bot-token"]
    if delivery == "key-path-public-pem":
        public = tmp_path / "public.pem"
        public.write_text(_public_pem())
        argv += ["--app-id", "1", "--installation-id", "1", "--key-path", str(public)]
        source = f"--key-path {public}"
    else:
        monkeypatch.setenv("BEEVERFORGE_GH_APP_ID", "1")
        monkeypatch.setenv("BEEVERFORGE_GH_APP_INSTALLATION_ID", "1")
        if delivery == "key-variable-blank-file":
            blank = tmp_path / "blank.pem"
            blank.write_text("\n  \n")
            monkeypatch.setenv("BEEVERFORGE_GH_APP_KEY", str(blank))
            source = "BEEVERFORGE_GH_APP_KEY"
        else:
            monkeypatch.setenv("BEEVERFORGE_GH_APP_KEY_CONTENT", "\n  \n")
            source = "BEEVERFORGE_GH_APP_KEY_CONTENT"

    result = CliRunner().invoke(app, argv)

    stderr = _refused_in_one_sentence(result)
    assert posts == [], "nothing may be sent to GitHub for a key that cannot sign"
    assert source in stderr, f"the refusal must name the key's source {source!r}: {stderr!r}"
    assert "-----BEGIN RSA PRIVATE KEY-----" in stderr, stderr
    assert "-----BEGIN PRIVATE KEY-----" in stderr, stderr
    assert "settings page" in stderr, stderr


def _not_found(url):
    # GITHUB'S OWN MESSAGE IS NOT THE REASON PHRASE (#372's review): with `"Not Found"` here the
    # guard could not tell the message from the 404's phrase, and dropping it went unseen.
    return httpx.Response(404, json={"message": "Integration not found"},
                          request=httpx.Request("POST", url))


def test_github_refusing_the_mint_is_one_sentence_naming_status_message_and_installation(
        posts, monkeypatch, tmp_path):
    """Criterion: GitHub's refusal (`HTTPStatusError`) is one sentence naming the status, GitHub's
    message and the installation, with the check-the-ids remedy. The 404 is a real
    `httpx.Response`, so the mint's own `raise_for_status` raises."""
    _answer(monkeypatch, posts, _not_found)
    key = tmp_path / "app.pem"
    key.write_text(_private_pem())

    result = CliRunner().invoke(app, ["bot-token", "--app-id", "1", "--installation-id", "7",
                                      "--key-path", str(key)])

    stderr = _refused_in_one_sentence(result)
    assert posts == [TOKENS_URL.format(7)]
    for word in ("404", "Integration not found", "installation 7", "--app-id",
                 "--installation-id"):
        assert word in stderr, (word, stderr)


def test_github_unreachable_is_one_sentence_naming_the_installation(posts, monkeypatch, tmp_path):
    """Criterion: a transport failure (`httpx.TransportError`) is one sentence naming the
    installation and the same remedy."""
    def unreachable(url):
        raise httpx.ConnectError("unreachable", request=httpx.Request("POST", url))

    _answer(monkeypatch, posts, unreachable)
    key = tmp_path / "app.pem"
    key.write_text(_private_pem())

    result = CliRunner().invoke(app, ["bot-token", "--app-id", "1", "--installation-id", "7",
                                      "--key-path", str(key)])

    stderr = _refused_in_one_sentence(result)
    for word in ("ConnectError", "installation 7", "--app-id", "--installation-id"):
        assert word in stderr, (word, stderr)


@pytest.mark.parametrize("raised", [ValueError("zz"), AttributeError("qq")],
                         ids=["ValueError", "AttributeError"])
def test_any_signing_failure_is_app_key_does_not_sign_whatever_its_text(
        raised, posts, monkeypatch):
    """Criterion: the signing refusal is never keyed off an exception's English text. Any
    failure of the signer, of any type and any words, is `AppKeyDoesNotSign`, chained."""
    _answer(monkeypatch, posts, _never)

    def encode(*_args, **_kwargs):
        raise raised

    monkeypatch.setattr(ga.jwt, "encode", encode)

    with pytest.raises(ga.AppKeyDoesNotSign) as caught:
        ga.mint_installation_token(app_id="1", private_key=_private_pem(), installation_id="1")

    assert caught.value.__cause__ is raised
    assert posts == []


@pytest.mark.parametrize("respond", ["RuntimeError", "404"])
def test_a_failure_after_signing_is_not_called_a_key_that_cannot_sign(respond, posts, monkeypatch):
    """Criterion: the signing refusal is caught around the signing step only. What fails after a
    good signature reaches the caller as itself."""
    def boom(url):
        raise RuntimeError("x")

    _answer(monkeypatch, posts, boom if respond == "RuntimeError" else _not_found)
    expected = RuntimeError if respond == "RuntimeError" else httpx.HTTPStatusError

    with pytest.raises(expected) as caught:
        ga.mint_installation_token(app_id="1", private_key=_private_pem(), installation_id="1")

    assert not isinstance(caught.value, ga.AppKeyDoesNotSign)
    assert posts == [TOKENS_URL.format(1)]
