"""No unit test reaches the internet unless it says so with `@pytest.mark.network` (#335).

MEASURED, NOT SUSPECTED. `test_the_HOURLY_sweep_is_handed_the_forge_it_used_to_run_without` ran
in every CI shard and on every laptop with no marker, and spent `300.11s call` for `user 0.57` of
CPU (2026-11-01): the activity it drove cloned a real `dev.azure.com` address with a fake PAT and
waited for a timeout, then passed, because the activity catches everything. Nothing in the suite
blocked a plain socket, so a test that reached the internet was only found by somebody timing it.

`tests/conftest.py::_no_unit_test_reaches_the_network` is that block, and this file proves it the
only way that cannot lie: by running probe tests in a real inner pytest with the conftest applied,
the pattern `tests/test_the_suite_cannot_reach_a_live_engine.py` set for the engine barrier.

EVERY REFUSAL HERE HAPPENS IN THE INNER RUN. The fixture also fails a test at teardown when a
refusal was swallowed, so an in-process test of this file that tripped it would fail itself.

The non-loopback target is `192.0.2.1` (TEST-NET-1, RFC 5737), dialled on a NON-BLOCKING socket:
without the block, the connect answers at once with "in progress" or "unreachable" rather than
waiting, so a missing guard shows up as a probe that passed, never as a slow run.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import textwrap
import tomllib
import xml.etree.ElementTree as ET

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROBE = "test__network_probe__.py"
TARGET = "192.0.2.1"
MARKER = "@pytest.mark.network"

_PROBES = textwrap.dedent('''
    import os
    import shutil
    import socket
    import tempfile
    import threading

    import pytest

    TARGET = ("192.0.2.1", 9)


    def _dial(method):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setblocking(False)
        try:
            return getattr(s, method)(TARGET)
        finally:
            s.close()


    def test_connect_refused():
        try:
            _dial("connect")
        except ConnectionRefusedError:
            raise
        except OSError:
            pass  # in progress or unreachable: what an unguarded connect answers at once


    def test_connect_ex_refused():
        try:
            _dial("connect_ex")
        except ConnectionRefusedError:
            raise
        except OSError:
            pass


    def test_connect_swallowed():
        try:
            _dial("connect")
        except Exception:
            pass  # what `activities._land_product_proposals` does with every error


    def _served(family, host):
        server = socket.socket(family, socket.SOCK_STREAM)
        server.bind((host, 0))
        server.listen(1)
        threading.Thread(target=lambda: server.accept()[0].close(), daemon=True).start()
        return server


    def test_loopback_v4_allowed():
        server = _served(socket.AF_INET, "127.0.0.1")
        with socket.create_connection(("127.0.0.1", server.getsockname()[1]), timeout=10):
            pass
        server.close()


    def test_loopback_v6_allowed():
        try:
            server = _served(socket.AF_INET6, "::1")
        except OSError:
            pytest.skip("this host has no IPv6 loopback")
        client = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        client.settimeout(10)
        client.connect(("::1", server.getsockname()[1]))
        client.close()
        server.close()


    def test_localhost_by_name_allowed():
        server = _served(socket.AF_INET, "127.0.0.1")
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(10)
        client.connect(("localhost", server.getsockname()[1]))
        client.close()
        server.close()


    def test_unix_socket_allowed():
        where = tempfile.mkdtemp()
        try:
            path = os.path.join(where, "s")
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(path)
            server.listen(1)
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.connect(path)
            client.close()
            server.close()
        finally:
            shutil.rmtree(where, ignore_errors=True)


    def _git(url):
        import subprocess
        from beeverforge import gitpin

        try:
            done = subprocess.run(gitpin.argv(["ls-remote", "--", url]), capture_output=True,
                                  text=True, timeout=60)
        except subprocess.TimeoutExpired:
            return "GIT WAITED ON THE REMOTE"
        return done.stderr


    def test_git_remote_refused():
        try:
            said = _git("https://192.0.2.1/x")
        except Exception:
            return  # what `activities._land_product_proposals` does with every error
        assert "not allowed" in said, "GIT DIALLED THE REMOTE: " + said


    def test_git_refuses_a_remote_before_it_dials():
        said = _git("https://127.0.0.1:9/x")
        assert "not allowed" in said, "GIT DIALLED THE REMOTE: " + said


    def test_git_to_a_name_that_can_never_resolve_allowed():
        _git("https://example.invalid/x")  # RFC 6761: an address asking to be unreachable


    def test_git_handed_a_value_that_is_no_transport_allowed():
        _git("--upload-pack=touch x;://x")  # what a guard against option injection hands git


    @pytest.mark.network
    def test_marked_allowed():
        try:
            _dial("connect")
        except OSError as exc:
            assert "not loopback" not in str(exc), str(exc)
''')

REFUSED = ("test_connect_refused", "test_connect_ex_refused", "test_connect_swallowed",
           "test_git_remote_refused")
ALLOWED = ("test_git_refuses_a_remote_before_it_dials",
           "test_git_to_a_name_that_can_never_resolve_allowed",
           "test_git_handed_a_value_that_is_no_transport_allowed", "test_loopback_v4_allowed", "test_loopback_v6_allowed",
           "test_localhost_by_name_allowed", "test_unix_socket_allowed", "test_marked_allowed")


@pytest.fixture(scope="module")
def inner(tmp_path_factory) -> dict[str, dict]:
    """One inner pytest over every probe; per probe, its outcomes and every word it reported.

    The probe and a copy of the conftest live OUTSIDE the tree, for the reason the engine probe
    gives: a `.py` written into `tests/` is a real source file for a neighbour that scans the tree
    while the inner run takes. The ini is passed with `-c` so `pythonpath` and the `markers` list
    are this repository's, and the rootdir is the arena, because a file outside the rootdir has a
    node id with no file in it (`::test_connect_refused`, measured) and the sentence names it."""
    arena = tmp_path_factory.mktemp("network_probe")
    scratch = arena / PROBE
    assert ROOT not in scratch.resolve().parents, (
        "the probe is inside the tree under test, so a neighbour scanning the tree can fail on it")
    scratch.write_text(_PROBES, encoding="utf-8")
    (arena / "conftest.py").write_text(
        (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8"), encoding="utf-8")
    report = arena / "r.xml"
    subprocess.run(
        [sys.executable, "-m", "pytest", str(scratch), "-c", str(ROOT / "pyproject.toml"),
         "-q", "-p", "no:randomly", "-p", "no:cacheprovider", "-p", "no:xdist", "--no-header",
         "-rA", f"--junitxml={report}", f"--rootdir={arena}"],
        capture_output=True, text=True, cwd=str(ROOT), timeout=300)
    cases: dict[str, dict] = {}
    for case in ET.parse(report).getroot().iter("testcase"):
        seen = cases.setdefault(case.get("name", ""), {"outcomes": set(), "said": ""})
        for child in case:
            seen["outcomes"].add(child.tag)
            seen["said"] += " ".join([child.get("message", ""), child.text or ""]) + "\n"
    return cases


@pytest.mark.parametrize("probe", REFUSED)
def test_a_connection_to_a_non_loopback_address_fails_the_test(inner, probe):
    assert probe in inner, f"the probe {probe} never ran: {sorted(inner)}"
    assert inner[probe]["outcomes"] & {"failure", "error"}, (
        f"{probe} dialled {TARGET} and PASSED: a unit test can reach the internet again")


@pytest.mark.parametrize("probe", REFUSED)
def test_the_refusal_names_the_test_the_address_and_the_marker(inner, probe):
    said = inner[probe]["said"]
    assert f"{PROBE}::{probe} " in said, said
    where = "https://192.0.2.1/x" if "git" in probe else f"{TARGET}:9"
    assert where in said, said
    assert MARKER in said, said


def test_git_is_refused_the_remote_rather_than_left_to_wait_on_it(inner):
    """The by-name failure says WHICH test ran a remote git; this says the git never dialled it, so
    a test that swallows the error is red at once rather than after a 300 s timeout."""
    said = inner["test_git_remote_refused"]["said"]
    assert "GIT DIALLED THE REMOTE" not in said and "GIT WAITED" not in said, said


@pytest.mark.parametrize("probe", ALLOWED)
def test_loopback_unix_sockets_and_a_marked_test_are_let_through(inner, probe):
    assert probe in inner, f"the probe {probe} never ran: {sorted(inner)}"
    assert not inner[probe]["outcomes"] & {"failure", "error"}, inner[probe]["said"]


def test_the_refusal_is_one_sentence_naming_the_test_the_address_and_the_marker():
    from tests.conftest import network_refusal

    sentence = network_refusal("tests/test_x.py::test_y", "203.0.113.7:443")
    assert "\n" not in sentence and sentence.endswith(".") and ". " not in sentence, sentence
    assert "tests/test_x.py::test_y" in sentence and "203.0.113.7:443" in sentence, sentence
    assert MARKER in sentence, sentence


def test_the_network_marker_is_declared_in_pyproject():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    markers = config["tool"]["pytest"]["ini_options"]["markers"]
    assert any(m.split(":", 1)[0].strip() == "network" for m in markers), markers
