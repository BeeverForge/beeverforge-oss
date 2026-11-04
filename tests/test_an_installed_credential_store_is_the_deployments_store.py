"""A credential store an installed add-on registers is a deployment's store like a shipped one
(#364).

`BEEVERFORGE_CREDENTIAL_STORE` names the store a deployment's own credentials are asked of before
the environment. Its documented values are `env`, `file` and "the kind an installed add-on
registers" through `credential_store.<kind>` in the `beeverforge.adapters` entry-point group.
Nothing held that last value: every test of a declared store declared `file`, or put a builder
straight into `STORES`. This module installs a fake add-on row through the entry-point group, the
way `pip install` would (`tests/vendor_addons.py`), declares it, and holds what the selector
promises:

  1. the installed store answers the deployment credentials before the environment, and a refusal
     from it is final: nothing falls back to the variable;
  2. the worker's start path (`connection._auth`) asks it first, and stops at its refusal;
  3. a kind nobody installed refuses by name and lists the installed kinds, add-on ones included;
  4. the configuration reference says an add-on kind is a supported value, and names the
     credentials the worker's start path asks for, read from that path rather than written twice.

Proven by mutation: `tools/mutations/364_an_installed_credential_store_is_the_deployments_store.py`.
"""

from __future__ import annotations

import logging
import pathlib

import pytest
import vendor_addons

from beeverforge.adapters.credential_store import registry
from beeverforge.adapters.credential_store.base import CredentialRefused
from beeverforge.adapters.credential_store.registry import (
    STORE_VAR,
    build_store,
    lookup,
    stored,
)
from beeverforge.runtime.temporal import connection

ROOT = pathlib.Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "docs" / "reference" / "configuration.md"
ROW = "| `BEEVERFORGE_CREDENTIAL_STORE` |"

#: The add-on's kind, and the entry-point row that registers it.
KIND = "someone"
POINT_NAME = f"credential_store.{KIND}"
#: The names the task asks of the store; the worker's own start set is read from `_auth`.
NAMES = ("TEMPORAL_API_KEY", "GH_TOKEN", "ANTHROPIC_API_KEY")
#: Every name the fake store holds.
HELD = (*NAMES, "TEMPORAL_TLS_KEY")


def _from_store(name: str) -> str:
    return f"fictitious-from-someone-{name}"


def _from_env(name: str) -> str:
    return f"fictitious-from-env-{name}"


def _sentence(name: str) -> str:
    """The store's refusal: its cause, then its remedy."""
    return f"someone's vault seals {name}; unseal {name} in someone's vault to hand it over"


class SomeoneStore:
    """The add-on's store: holds `held`, refuses `refuse`, and records every name it is asked."""

    def __init__(self, held: tuple[str, ...], refuse: set[str], asked: list[str]) -> None:
        self.held, self.refuse, self.asked = held, refuse, asked

    def resolve(self, name: str) -> str | None:
        self.asked.append(name)
        if name in self.refuse:
            raise CredentialRefused(_sentence(name))
        return _from_store(name) if name in self.held else None


class Point:
    """The entry point the add-on's package declares, as `importlib.metadata` hands it over."""

    name = POINT_NAME

    def __init__(self, builder) -> None:
        self._builder = builder

    def load(self):
        return self._builder


def _install(monkeypatch, *, held: tuple[str, ...] = HELD, refuse: tuple[str, ...] = (),
             declare: str = KIND) -> list[str]:
    """Install `credential_store.someone` through the entry-point group, declare `declare` as the
    deployment's store, set every name in the environment to another value, and answer the record
    of names the store was asked."""
    asked: list[str] = []
    refused = set(refuse)

    def build():
        return SomeoneStore(held, refused, asked)

    vendor_addons.install(monkeypatch, declared_rows=False, extra=(Point(build),))
    monkeypatch.setenv(STORE_VAR, declare)
    for name in HELD:
        monkeypatch.setenv(name, _from_env(name))
    monkeypatch.delenv("TEMPORAL_TLS_CERT", raising=False)
    return asked


@pytest.mark.parametrize("name", NAMES)
def test_an_installed_store_answers_the_start_credentials_before_the_environment(
        monkeypatch, name):
    asked = _install(monkeypatch)

    found = lookup(name)

    assert KIND in registry.known(), registry.known()
    assert found.value == _from_store(name), (
        f"{name} was answered by {found.reference!r}, not by the installed `{KIND}` store")
    assert found.reference == f"{KIND}:{name}"
    assert not found.refused
    assert stored(name) == _from_store(name)
    assert name in asked


@pytest.mark.parametrize("name", NAMES)
def test_an_installed_stores_refusal_is_final_and_never_the_variable(monkeypatch, caplog, name):
    _install(monkeypatch, refuse=(name,))

    with caplog.at_level(logging.DEBUG):
        found = lookup(name)
        value = stored(name)

    assert found.refused == _sentence(name), found
    assert found.reference == f"{KIND}:{name}"
    assert found.value is None, f"the refused {name} was answered by the variable"
    assert value is None, f"the refused {name} was answered by the variable"
    assert _from_env(name) not in found.refused
    assert _from_env(name) not in caplog.text


def test_the_worker_asks_the_installed_store_for_its_engine_key_first(monkeypatch):
    _install(monkeypatch)

    assert connection._auth()["api_key"] == _from_store("TEMPORAL_API_KEY")


def test_the_worker_stops_at_the_installed_stores_refusal_of_its_engine_key(monkeypatch):
    asked = _install(monkeypatch, refuse=("TEMPORAL_API_KEY",))

    with pytest.raises(RuntimeError) as raised:
        connection._auth()

    said = str(raised.value)
    assert "TEMPORAL_API_KEY" in said
    assert _sentence("TEMPORAL_API_KEY") in said
    assert _from_env("TEMPORAL_API_KEY") not in said
    assert "TEMPORAL_TLS_KEY" not in asked, (
        f"the refused API key was answered by the next credential: asked {asked}")


def test_an_unknown_store_kind_refuses_by_name_and_lists_the_installed_kinds(monkeypatch):
    _install(monkeypatch, declare="not-installed")

    found = lookup("TEMPORAL_API_KEY")

    assert "'not-installed'" in found.refused, found
    for kind in ("env", "file", KIND):
        assert kind in found.refused.split("known:", 1)[-1], (
            f"the refusal does not list the installed kind {kind!r}: {found.refused}")
    assert found.value is None, "an unknown store fell back to the variable"
    assert stored("TEMPORAL_API_KEY") is None

    with pytest.raises(ValueError) as raised:
        build_store("not-installed")
    assert str(raised.value) == found.refused


def _start_credentials(monkeypatch) -> list[str]:
    """The names the worker's start path asks the store, in order, when nothing answers."""
    asked = _install(monkeypatch, held=())
    monkeypatch.delenv("TEMPORAL_API_KEY")
    monkeypatch.delenv("TEMPORAL_TLS_KEY")
    connection._auth()
    return asked


def test_the_configuration_reference_names_an_add_on_kind_and_the_start_credentials(monkeypatch):
    start = _start_credentials(monkeypatch)
    assert start == ["TEMPORAL_API_KEY", "TEMPORAL_TLS_KEY"], start

    rows = [line for line in REFERENCE.read_text().splitlines() if line.startswith(ROW)]
    assert len(rows) == 1, f"{REFERENCE.name} holds {len(rows)} rows for {STORE_VAR}"
    row = rows[0]

    assert "the kind an installed add-on registers" in row, row
    assert "`credential_store.<kind>`" in row and "`beeverforge.adapters`" in row, (
        f"the row does not say how an add-on registers a kind: {row}")
    assert "its refusal is final" in row, row
    assert "a worker asks for at start" in row, row
    for name in start:
        assert f"`{name}`" in row, f"the row does not name the start credential {name}: {row}"
