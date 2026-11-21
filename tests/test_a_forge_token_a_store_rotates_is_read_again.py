"""A forge token the deployment's credential store rotates is read again before it expires (#236).

THE INCIDENT. A deployment whose credential store rotates the forge token hands the core a GitHub
App installation token, and such a token lives one hour. The store answers a fresh one whenever it
is asked. But `factory.build_runner` composed the forge with `token=forge_token_for(project)` and
passed a `token_provider` only when that call answered nothing, so a token the store answered became
the adapter's `_static_token`, and `github_cli.credential_of` handed that same string to every push
and every `gh` call for the rest of the job. A job longer than an hour failed its final `git push`
with "Invalid username or token" — twice in one day, on the job meant to fix it.

WHAT IS HELD HERE, each through the runner `build_runner` composes and the calls the job makes on
it (`forge.push_remote()`, which `_publish` hands the box, and the forge's and tracker's `gh`):

  1. a token rewritten in the `file` store, and one an installed store (`credential_store.<kind>`
     in the entry-point group) answers differently later, is the one the next push and the next
     `gh` call use within one re-read interval of the rewrite — five minutes, or half the lifetime
     when the lifetime is under ten minutes — at whatever minute of the job the rewrite comes;
  2. the store is read once per interval, not once per call, by one caller however many wait —
     and a read that FAILS is tried again at most once a minute, said once in one true sentence;
  3. a push after the first token's lifetime goes out under a fresh one — driven by a fake clock;
  4. the lifetime (`BEEVERFORGE_STORED_TOKEN_TTL`, an hour unset, at most a day) is how long a
     token whose re-read failed is still handed out; past it a refusal, or a store that answers
     nothing, is said by name, never answered by the expired token or the machine's own login;
  5. composing a runner reads each axis once; the `env` store, the App trio, a PAT, a vendor that
     reads its own credential and a harness's replaced reader behave exactly as before; no token
     value reaches a log.

No test here waits on real time: the clock is `credentials._now`, replaced per test.

Proven by mutation: `tools/mutations/236_a_forge_token_a_store_rotates_is_read_again.py`.
"""

from __future__ import annotations

import logging
import subprocess
import threading
from pathlib import Path

import pytest
import vendor_addons

from beeverforge import credentials, factory, namespace
from beeverforge.adapters.credential_store.base import CredentialRefused
from beeverforge.adapters.credential_store.file import DIR_VAR
from beeverforge.adapters.credential_store.registry import STORE_VAR
from beeverforge.adapters.forge import github as forge_github
from beeverforge.adapters.github_cli import LoginRefused
from beeverforge.adapters.tracker import github as tracker_github
from beeverforge.contracts.project import Project, ProviderRef

#: Fictitious installation tokens, in the shape GitHub mints them (`ghs_`), recognisable anywhere.
FIRST = "ghs_fictitious236first"
SECOND = "ghs_fictitious236second"
#: A fictitious classic PAT: a token GitHub states no lifetime for.
PAT = "ghp_fictitious236pat"
#: The deployment credential the forge and the tracker of a GitHub project are read from.
BOT = "BEEVERFORGE_BOT_TOKEN"
#: Every variable the GitHub axes walk, so a test sets exactly the one it means.
AXIS_VARS = ("BEEVERFORGE_FORGE_TOKEN", "BEEVERFORGE_TRACKER_TOKEN", BOT)
#: How long a token a rotating store answered is held, in seconds — an hour unset.
TTL_VAR = "BEEVERFORGE_STORED_TOKEN_TTL"
APP_VARS = ("BEEVERFORGE_GH_APP_ID", "BEEVERFORGE_GH_APP_KEY", "BEEVERFORGE_GH_APP_KEY_CONTENT",
            "BEEVERFORGE_GH_APP_INSTALLATION_ID")

#: When the job starts, in epoch seconds; a minute is sixty of them.
T0 = 1_900_000_000.0
MINUTE = 60.0

#: The add-on store's kind, as its package would register it.
KIND = "rotating"


class Clock:
    """A clock a test moves: `clock.at(80)` is eighty minutes into the job."""

    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> float:
        return self.now

    def at(self, minutes: float) -> None:
        self.now = T0 + minutes * MINUTE


@pytest.fixture(autouse=True)
def _a_deployment_with_no_credential(monkeypatch):
    for name in (*AXIS_VARS, *APP_VARS, STORE_VAR, DIR_VAR, TTL_VAR):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def clock(monkeypatch):
    """The clock every lifetime is measured by. `raising=False` so the test fails on its
    assertion, not on the seam, where the seam does not exist."""
    fake = Clock()
    monkeypatch.setattr(credentials, "_now", fake, raising=False)
    return fake


@pytest.fixture
def secrets(tmp_path, monkeypatch):
    """The `file` store declared as the deployment's own: `secrets(name, value)` writes a file."""
    directory = tmp_path / "secrets"
    directory.mkdir()
    directory.chmod(0o700)
    monkeypatch.setenv(DIR_VAR, str(directory))
    monkeypatch.setenv(STORE_VAR, "file")

    def put(name: str, value: str, mode: int = 0o600) -> Path:
        path = directory / name
        path.write_text(value)
        path.chmod(mode)
        return path

    return put


class RotatingStore:
    """An installed store whose answer the test changes, recording every name it is asked."""

    def __init__(self, held: dict[str, str], asked: list[str]) -> None:
        self.held, self.asked = held, asked

    def resolve(self, name: str) -> str | None:
        self.asked.append(name)
        return self.held.get(name)

    def describe(self, name: str) -> str:
        return f"the rotating store's `{name}`"


class Point:
    """The entry point the add-on's package declares, as `importlib.metadata` hands it over."""

    def __init__(self, builder) -> None:
        self._builder, self.name = builder, f"credential_store.{KIND}"

    def load(self):
        return self._builder


@pytest.fixture
def addon_store(monkeypatch):
    """`credential_store.rotating`, installed through the entry-point group and declared as the
    deployment's store. Answers `(held, asked)`: what it holds, which the test changes, and every
    name it was asked."""
    held: dict[str, str] = {}
    asked: list[str] = []
    vendor_addons.install(monkeypatch, declared_rows=False,
                          extra=(Point(lambda: RotatingStore(held, asked)),))
    monkeypatch.setenv(STORE_VAR, KIND)
    return held, asked


def _project(tmp_path) -> Project:
    """A GitHub project whose repository is a local directory with a manifest, so `build_runner`
    composes the whole runner without reaching a network."""
    repo = tmp_path / "repo"
    (repo / namespace.MANIFEST).parent.mkdir(parents=True)
    (repo / namespace.MANIFEST).write_text("{}\n")
    return Project(name="acme", repo_path=str(repo),
                   tracker=ProviderRef(kind="github", repo="acme/widgets"),
                   forge=ProviderRef(kind="github", repo="acme/widgets"))


def _runner(tmp_path):
    return factory.build_runner(_project(tmp_path), "#1", sandbox="worktree", image="img",
                                review=False)


def _pushed_with(runner) -> str:
    """The token the job's push carries: `push_remote()`, the URL `_publish` hands the box."""
    remote = runner.forge.push_remote()
    assert remote, "the forge offered no authenticated remote to push to"
    return remote.split("x-access-token:", 1)[1].split("@", 1)[0]


@pytest.fixture
def gh_calls(monkeypatch):
    """Every `gh` the forge and the tracker run, as the `GH_TOKEN` it was handed — never run."""
    seen: list[str | None] = []

    def run(argv, *a, env=None, **kw):
        seen.append((env or {}).get("GH_TOKEN"))
        return subprocess.CompletedProcess(argv, 0, "[]", "")

    monkeypatch.setattr(forge_github.subprocess, "run", run)
    monkeypatch.setattr(tracker_github.subprocess, "run", run)
    return seen


def _gh_with(runner, gh_calls) -> tuple[str | None, str | None]:
    """The token the next forge `gh` call and the next tracker `gh` call carry."""
    runner.forge._gh(["pr", "list", "--repo", "acme/widgets"])
    runner.tracker._gh(["issue", "list", "--repo", "acme/widgets"])
    return gh_calls[-2], gh_calls[-1]


# ── 1. a rotated token is the one the next push and the next `gh` call use ──────────────────────

def test_a_token_rewritten_in_the_file_store_is_the_one_the_jobs_pushes_use_after_it(
        tmp_path, secrets, clock, gh_calls):
    secrets(BOT, FIRST)
    runner = _runner(tmp_path)
    assert _pushed_with(runner) == FIRST

    clock.at(50)
    secrets(BOT, SECOND)  # the platform rotates the mounted file, as Vault Agent or a CSI driver do
    clock.at(80)

    assert _pushed_with(runner) == SECOND, (
        "the push went out with the token read when the runner was composed, eighty minutes ago")
    assert _gh_with(runner, gh_calls) == (SECOND, SECOND)


def test_a_value_an_installed_store_answers_differently_later_is_the_one_the_next_push_and_gh_use(
        tmp_path, addon_store, clock, gh_calls):
    held, _ = addon_store
    held[BOT] = FIRST
    runner = _runner(tmp_path)
    assert _pushed_with(runner) == FIRST
    assert _gh_with(runner, gh_calls) == (FIRST, FIRST)

    held[BOT] = SECOND
    clock.at(61)

    assert _pushed_with(runner) == SECOND
    assert _gh_with(runner, gh_calls) == (SECOND, SECOND)


# ── 2. held: one read per lifetime, not one per call ────────────────────────────────────────────

def test_a_token_that_does_not_change_is_read_once_per_interval_not_once_per_call(
        tmp_path, addon_store, clock, gh_calls):
    """The store is asked again every five minutes, never at each push or `gh` call: a store an
    add-on installs may answer over the network, and the job makes hundreds of calls an hour."""
    held, asked = addon_store
    held[BOT] = FIRST
    runner = _runner(tmp_path)
    asked.clear()

    for second in range(0, 290, 10):  # inside the first interval: the read that composed it
        clock.now = T0 + second
        assert _pushed_with(runner) == FIRST
        _gh_with(runner, gh_calls)
    assert asked == [], f"{len(asked)} store reads inside one interval, where none was due"

    clock.at(6)  # the interval is up: read again, once, however many calls follow
    for _ in range(20):
        assert _pushed_with(runner) == FIRST
        _gh_with(runner, gh_calls)
    assert asked.count(BOT) == 2, asked  # once for the forge's provider, once for the tracker's


def test_eight_callers_at_the_end_of_an_interval_make_one_read_and_get_one_answer(
        tmp_path, addon_store, clock, monkeypatch):
    held, asked = addon_store
    held[BOT] = FIRST
    runner = _runner(tmp_path)
    asked.clear()
    held[BOT] = SECOND
    clock.at(6)

    release = threading.Event()
    slow = RotatingStore.resolve

    def a_slow_read(self, name):
        release.wait(5)  # the first caller holds the read open until every caller has started
        return slow(self, name)

    monkeypatch.setattr(RotatingStore, "resolve", a_slow_read)
    answers: list[str | None] = []
    callers = [threading.Thread(target=lambda: answers.append(runner.forge.token))
               for _ in range(8)]
    for caller in callers:
        caller.start()
    release.set()
    for caller in callers:
        caller.join()

    assert answers == [SECOND] * 8
    assert asked.count(BOT) == 1, asked


def test_a_token_rewritten_ten_minutes_into_the_job_is_the_one_its_push_ten_minutes_later_uses(
        tmp_path, secrets, clock):
    """A platform rotates on its own schedule: the token read at minute 0 may be fifty minutes
    old, expire at minute 10, and have a successor on disk that the push must use."""
    secrets(BOT, FIRST)
    runner = _runner(tmp_path)
    assert _pushed_with(runner) == FIRST
    clock.at(10)
    secrets(BOT, SECOND)
    clock.at(20)
    assert _pushed_with(runner) == SECOND


@pytest.mark.parametrize("minutes", [(10, 20), (20, 30), (40, 54), (40, 56)])
def test_a_rewrite_at_any_minute_is_the_next_pushes_once_an_interval_has_passed(
        tmp_path, secrets, clock, minutes):
    rewritten, pushed = minutes
    secrets(BOT, FIRST)
    runner = _runner(tmp_path)
    clock.at(rewritten)
    secrets(BOT, SECOND)
    clock.at(pushed)
    assert _pushed_with(runner) == SECOND


# ── 3. the incident: a push after the first token's lifetime ────────────────────────────────────

def test_a_job_whose_push_comes_after_the_first_tokens_lifetime_pushes_under_a_fresh_one(
        tmp_path, secrets, clock):
    """Minute 0 the runner is composed; minute 60 the token the store handed it expires and the
    store holds its successor; minute 80 the job pushes. The clock is moved, never waited on."""
    secrets(BOT, FIRST)
    runner = _runner(tmp_path)
    clock.at(60)
    secrets(BOT, SECOND)
    clock.at(80)

    assert _pushed_with(runner) == SECOND


def test_both_runners_a_job_composes_read_the_rotated_token(tmp_path, secrets, clock):
    """The promotion runner pushes nothing, but it comments and merges through the same forge,
    long after the job runner was composed."""
    secrets(BOT, FIRST)
    runner = factory.build_promotion_runner(_project(tmp_path), "#1")
    assert runner.forge.token == FIRST and runner.tracker.token == FIRST
    secrets(BOT, SECOND)
    clock.at(61)

    assert (runner.forge.token, runner.tracker.token) == (SECOND, SECOND)


def test_a_failed_re_read_keeps_the_token_for_the_lifetime_and_the_lifetime_is_configurable(
        tmp_path, addon_store, clock, monkeypatch):
    """GitHub carries no expiry in an installation token, so the lifetime is a setting, an hour
    by default: how long a token is still handed out while the store answers nothing. Past it,
    the push refuses by name instead of carrying an expired token to a 401."""
    monkeypatch.setenv(TTL_VAR, "900")
    held, _ = addon_store
    held[BOT] = FIRST
    runner = _runner(tmp_path)
    del held[BOT]

    clock.at(14)
    assert _pushed_with(runner) == FIRST, "a failed re-read evicted a token still in its lifetime"
    clock.at(16)
    with pytest.raises(LoginRefused):
        runner.forge.push_remote()


@pytest.mark.parametrize("ttl", ["inf", "1e400", "1e20", "1e300", "nan", "0", "-5", "abc"])
def test_a_lifetime_that_is_not_a_finite_number_of_seconds_above_zero_is_the_hour(
        tmp_path, secrets, clock, monkeypatch, caplog, ttl):
    monkeypatch.setenv(TTL_VAR, ttl)
    secrets(BOT, FIRST)
    runner = _runner(tmp_path)
    _pushed_with(runner)
    secrets(BOT, SECOND)
    clock.at(61)
    assert _pushed_with(runner) == SECOND
    assert any(TTL_VAR in r.getMessage() for r in caplog.records)


def test_a_store_that_answers_nothing_once_the_token_has_expired_is_said_by_name(
        tmp_path, addon_store, clock):
    held, _ = addon_store
    held[BOT] = FIRST
    runner = _runner(tmp_path)
    _pushed_with(runner)
    del held[BOT]
    clock.at(70)
    with pytest.raises(LoginRefused) as said:
        runner.forge.push_remote()
    assert f"{KIND}:{BOT}" in str(said.value) and FIRST not in str(said.value)


def test_composing_a_runner_reads_the_store_no_more_often_than_before(
        tmp_path, addon_store):
    """Engineering lesson 10: a read of an add-on store may be a network round trip. `main`
    composed a GitHub job runner with 5 reads of the bot token; the first cut of #236 made 11; each
    axis read once and handed on makes 2."""
    held, asked = addon_store
    held[BOT] = FIRST
    _runner(tmp_path)

    assert asked.count(BOT) <= 2, asked


def test_a_tracker_row_that_takes_no_callers_provider_is_handed_none(tmp_path, secrets):
    """Jira's row reads its own variable and refuses a caller's provider, so none is built for it:
    its token is read once, when the runner is composed, as before."""
    secrets("JIRA_API_TOKEN", "fictitious-jira-236")
    project = _project(tmp_path).model_copy(update={"tracker": ProviderRef(
        kind="jira", repo="ACME", options={"site": "acme.example", "email": "a@acme.example"})})

    assert credentials.stored_token_provider(project, "tracker") is None


# ── 4. what must not change ─────────────────────────────────────────────────────────────────────

def test_the_env_store_hands_the_forge_the_token_as_it_always_did(tmp_path, monkeypatch, clock):
    """The environment does not change under a running process, so nothing re-reads it."""
    monkeypatch.setenv(BOT, FIRST)
    runner = _runner(tmp_path)

    for adapter in (runner.forge, runner.tracker):
        assert adapter._token_provider is None
        assert adapter._static_token == FIRST


def test_a_PAT_is_read_once_and_kept(tmp_path, secrets, clock):
    """A classic PAT states no lifetime: it is read when the runner is composed and kept."""
    secrets(BOT, PAT)
    runner = _runner(tmp_path)
    secrets(BOT, SECOND)
    clock.at(120)

    assert runner.forge._token_provider is None and runner.forge._static_token == PAT
    assert _pushed_with(runner) == PAT


def test_the_App_trio_keeps_its_own_minter(tmp_path, monkeypatch, clock):
    """No stored token and the App trio: the forge re-mints through the App, as before."""
    def minter():
        return "ghs_fictitious236minted"

    monkeypatch.setattr(factory, "_bot_token_provider", lambda: minter)
    runner = _runner(tmp_path)

    assert runner.forge._token_provider is minter
    assert _pushed_with(runner) == "ghs_fictitious236minted"


def test_a_stored_token_beside_the_App_trio_is_composed_as_before(
        tmp_path, secrets, monkeypatch, clock):
    secrets(BOT, FIRST)
    monkeypatch.setattr(factory, "_bot_token_provider", lambda: (lambda: "ghs_minted"))
    runner = _runner(tmp_path)

    assert runner.forge._token_provider is None and runner.forge._static_token == FIRST


def test_a_refusal_met_on_the_re_read_is_final_and_no_login_answers_it(
        tmp_path, addon_store, clock, monkeypatch, gh_calls):
    """The store refuses the token at the refresh. The held one has expired, and nothing — not the
    stale token, not `gh`'s own login — is used in its place: the push refuses by name."""
    held, _ = addon_store
    held[BOT] = FIRST
    runner = _runner(tmp_path)
    _pushed_with(runner)

    def refuse(self, name):
        raise CredentialRefused(f"the rotating store seals {name}")

    monkeypatch.setattr(RotatingStore, "resolve", refuse)
    clock.at(70)

    with pytest.raises(LoginRefused) as refused:
        runner.forge.push_remote()
    assert FIRST not in str(refused.value)
    assert f"{KIND}:{BOT}" in str(refused.value)
    assert runner.forge._gh(["pr", "list", "--repo", "acme/widgets"]).returncode != 0
    assert gh_calls == [], "`gh` ran after the credential it was built with was refused"


def test_a_refusal_is_the_answer_of_its_own_read_and_not_of_the_reads_after_it(
        tmp_path, addon_store, clock, monkeypatch):
    """Each read says what IT met: a store that refused at minute 70 and holds a token again at
    minute 71 is the token's; one that holds nothing then is said as nothing, not as the refusal."""
    held, _ = addon_store
    held[BOT] = FIRST
    runner = _runner(tmp_path)
    honest = RotatingStore.resolve

    def refuse(self, name):
        raise CredentialRefused(f"the rotating store seals {name}")

    monkeypatch.setattr(RotatingStore, "resolve", refuse)
    clock.at(70)
    with pytest.raises(LoginRefused, match="refused"):
        runner.forge.push_remote()

    monkeypatch.setattr(RotatingStore, "resolve", honest)
    del held[BOT]
    clock.at(71)
    with pytest.raises(LoginRefused, match="answered nothing"):
        runner.forge.push_remote()

    held[BOT] = SECOND
    clock.at(72)
    assert _pushed_with(runner) == SECOND


def test_a_store_that_answers_nothing_is_not_asked_again_at_every_call(
        tmp_path, addon_store, clock, caplog):
    held, asked = addon_store
    held[BOT] = FIRST
    runner = _runner(tmp_path)
    del held[BOT]
    clock.at(30)
    asked.clear()
    for _ in range(50):
        assert _pushed_with(runner) == FIRST
    assert asked.count(BOT) <= 2, f"{asked.count(BOT)} store reads for 50 pushes"
    assert any("answered nothing" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("failure", ["refuses", "raises"])
def test_a_store_that_fails_is_asked_at_most_once_a_minute_and_said_once(
        tmp_path, addon_store, clock, caplog, monkeypatch, failure):
    """A store that refuses, or that cannot be reached, while the held token is still inside its
    lifetime: the token is pushed, the store is asked once in the minute, and what is said is one
    sentence that says what happens — not one warning, with a traceback, per call."""
    held, asked = addon_store
    held[BOT] = FIRST
    runner = _runner(tmp_path)

    def fail(self, name):
        asked.append(name)
        if failure == "refuses":
            raise CredentialRefused(f"the rotating store seals {name}")
        raise ConnectionError("the rotating store did not answer")

    monkeypatch.setattr(RotatingStore, "resolve", fail)
    clock.at(10)
    asked.clear()
    caplog.clear()
    caplog.set_level(logging.WARNING)
    for _ in range(10):
        assert _pushed_with(runner) == FIRST
    warned = [r for r in caplog.records if r.levelno >= logging.WARNING]

    assert len(asked) <= 2, f"{len(asked)} store reads for 10 pushes"
    assert len(warned) <= 2, [r.getMessage() for r in warned]
    assert any(TTL_VAR in r.getMessage() for r in warned), "nothing said what happens instead"


def test_a_lifetime_under_ten_minutes_is_read_again_every_half_of_it(
        tmp_path, addon_store, clock, monkeypatch):
    monkeypatch.setenv(TTL_VAR, "240")
    held, _ = addon_store
    held[BOT] = FIRST
    runner = _runner(tmp_path)
    held[BOT] = SECOND
    clock.now = T0 + 119
    assert _pushed_with(runner) == FIRST
    clock.now = T0 + 121
    assert _pushed_with(runner) == SECOND


def test_a_harness_that_replaces_the_pair_reader_is_what_the_runner_is_composed_with(
        tmp_path, monkeypatch, clock):
    monkeypatch.setenv(BOT, FIRST)
    monkeypatch.setattr(credentials, "forge_token", lambda: SECOND)
    runner = _runner(tmp_path)
    assert runner.forge._static_token == SECOND and runner.forge._token_provider is None


def test_a_store_that_raises_on_a_re_read_says_what_it_raised_somewhere(
        tmp_path, addon_store, clock, caplog, monkeypatch):
    caplog.set_level(logging.DEBUG)
    held, asked = addon_store
    held[BOT] = FIRST
    runner = _runner(tmp_path)

    def fail(self, name):
        asked.append(name)
        raise AttributeError("'NoneType' object has no attribute 'json'")

    monkeypatch.setattr(RotatingStore, "resolve", fail)
    clock.at(10)
    caplog.clear()
    assert _pushed_with(runner) == FIRST
    assert any("has no attribute 'json'" in r.getMessage() for r in caplog.records), caplog.text


def test_the_first_read_and_the_pair_are_asked_loudly(tmp_path, addon_store, caplog, monkeypatch):
    from beeverforge.adapters.credential_store import registry as store

    def fail(self, name):
        raise AttributeError("a defect in the store")

    monkeypatch.setattr(RotatingStore, "resolve", fail)
    caplog.set_level(logging.WARNING)
    credentials.axis_answer_for(_project(tmp_path), "forge")
    assert any(r.name == store.log.name and r.exc_info for r in caplog.records), caplog.text
    caplog.clear()
    store.chain((BOT,))
    assert any(r.name == store.log.name and r.exc_info for r in caplog.records), caplog.text


def test_a_failed_re_read_names_the_stores_reason_once(tmp_path, addon_store, clock, caplog,
                                                        monkeypatch):
    held, asked = addon_store
    held[BOT] = FIRST
    runner = _runner(tmp_path)

    def fail(self, name):
        asked.append(name)
        raise CredentialRefused(f"the rotating store seals {name}")

    monkeypatch.setattr(RotatingStore, "resolve", fail)
    clock.at(10)
    caplog.clear()
    caplog.set_level(logging.WARNING)
    for _ in range(10):
        assert _pushed_with(runner) == FIRST
    warned = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warned) == 1 and "the rotating store seals" in warned[0], warned


def _a_push_every_second_with_a_store_that_answers_nothing(tmp_path, addon_store, clock,
                                                            monkeypatch, caplog, until: int):
    """TTL 60, so the interval is 30 s: a push every second from 0 to `until`, the store
    answering nothing from the start. Answers `{second: what was said}` for each second the store
    was asked, and the seconds a push refused."""
    monkeypatch.setenv(TTL_VAR, "60")
    held, asked = addon_store
    held[BOT] = FIRST
    runner = _runner(tmp_path)
    del held[BOT]
    caplog.set_level(logging.WARNING)
    read_at: dict[int, list[str]] = {}
    refused: list[int] = []
    for second in range(until + 1):
        clock.now = T0 + second
        asked.clear()
        caplog.clear()
        try:
            runner.forge.push_remote()
        except LoginRefused:
            refused.append(second)
        if asked:
            read_at[second] = [r.getMessage() for r in caplog.records
                               if r.name == credentials.log.name]
    return read_at, refused


def test_a_lifetime_of_a_minute_retries_a_failed_read_every_half_of_it(
        tmp_path, addon_store, clock, monkeypatch, caplog):
    read_at, refused = _a_push_every_second_with_a_store_that_answers_nothing(
        tmp_path, addon_store, clock, monkeypatch, caplog, until=95)

    assert sorted(read_at) == [30, 60, 90], sorted(read_at)
    assert refused[0] == 60, refused


def test_a_failed_re_read_says_when_it_is_retried_and_what_is_used_meanwhile(
        tmp_path, addon_store, clock, monkeypatch, caplog):
    read_at, _ = _a_push_every_second_with_a_store_that_answers_nothing(
        tmp_path, addon_store, clock, monkeypatch, caplog, until=61)

    inside, past = read_at[30], read_at[60]
    assert len(inside) == 1 and "in 30 s" in inside[0], inside
    assert "the token read before it is used until" in inside[0], inside
    assert len(past) == 1 and "nothing is used in its place" in past[0], past
    assert "the token read before it is used" not in past[0], past


def test_a_good_re_read_moves_the_lifetime_the_warning_speaks_of_on(
        tmp_path, addon_store, clock, monkeypatch, caplog):
    """TTL 600: the store answers a new token at second 300 and nothing after it. At second 600
    the composed token's lifetime is over, the re-read one's is not: it is pushed, and the
    sentence says so."""
    monkeypatch.setenv(TTL_VAR, "600")
    held, _ = addon_store
    held[BOT] = FIRST
    runner = _runner(tmp_path)
    held[BOT] = SECOND
    clock.now = T0 + 300
    assert _pushed_with(runner) == SECOND
    del held[BOT]
    caplog.set_level(logging.WARNING)
    caplog.clear()
    clock.now = T0 + 600
    assert _pushed_with(runner) == SECOND
    said = [r.getMessage() for r in caplog.records if r.name == credentials.log.name]
    assert len(said) == 1 and "the token read before it is used until" in said[0], said


def test_no_token_value_reaches_a_log(tmp_path, secrets, clock, caplog, gh_calls):
    caplog.set_level(logging.DEBUG)
    secrets(BOT, FIRST)
    runner = _runner(tmp_path)
    _pushed_with(runner)
    _gh_with(runner, gh_calls)
    secrets(BOT, SECOND)
    clock.at(80)
    _pushed_with(runner)
    _gh_with(runner, gh_calls)

    said = "\n".join(r.getMessage() for r in caplog.records)
    assert FIRST not in said and SECOND not in said


# ── 6. the promotion runner's environment observer (#589) ───────────────────────────────────────

def _observed_with(runner, gh_calls) -> str | None:
    """The `GH_TOKEN` the observer's next read carries; `gh` is never run."""
    runner.observer._api("repos/acme/widgets/deployments")
    return gh_calls[-1]


@pytest.fixture
def observer_gh_calls(monkeypatch):
    from beeverforge.adapters.environment import github_actions

    seen: list[str | None] = []

    def run(argv, *a, env=None, **kw):
        seen.append((env or {}).get("GH_TOKEN"))
        return subprocess.CompletedProcess(argv, 0, "[]", "")

    monkeypatch.setattr(github_actions.subprocess, "run", run)
    return seen


def test_an_observer_whose_promotion_outlives_the_first_tokens_lifetime_reads_under_a_fresh_one(
        tmp_path, secrets, clock, observer_gh_calls):
    secrets(BOT, FIRST)
    runner = factory.build_promotion_runner(_project(tmp_path), "#1")
    assert _observed_with(runner, observer_gh_calls) == FIRST
    secrets(BOT, SECOND)
    clock.at(80)

    assert _observed_with(runner, observer_gh_calls) == SECOND


def test_the_observer_of_a_PAT_or_the_environment_is_handed_its_token_once(
        tmp_path, secrets, clock, monkeypatch):
    project = _project(tmp_path)
    secrets(BOT, PAT)
    runner = factory.build_promotion_runner(project, "#1")
    assert runner.observer._token_provider is None and runner.observer._static_token == PAT

    monkeypatch.delenv(STORE_VAR)
    monkeypatch.setenv(BOT, FIRST)
    runner = factory.build_promotion_runner(project, "#1")
    assert runner.observer._token_provider is None and runner.observer._static_token == FIRST


def test_a_refusal_met_by_the_observers_re_read_is_said_by_name_and_no_login_answers_it(
        tmp_path, addon_store, clock, monkeypatch, observer_gh_calls):
    held, _ = addon_store
    held[BOT] = FIRST
    runner = factory.build_promotion_runner(_project(tmp_path), "#1")
    _observed_with(runner, observer_gh_calls)

    def refuse(self, name):
        raise CredentialRefused(f"the rotating store seals {name}")

    monkeypatch.setattr(RotatingStore, "resolve", refuse)
    clock.at(70)
    before = len(observer_gh_calls)

    with pytest.raises(LoginRefused) as refused:
        runner.observer._api("repos/acme/widgets/deployments")
    assert f"{KIND}:{BOT}" in str(refused.value) and FIRST not in str(refused.value)
    assert len(observer_gh_calls) == before, "`gh` ran after the credential was refused"
