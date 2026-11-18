"""The suite runs every subprocess under one locale of its own, whatever the shell had.

A test that reads a tool's sentence read it in the machine's language: under `LANG=pt_BR.UTF-8`
git answers `Permissão negada`, not `Permission denied`, and
`test_a_file_the_scan_could_not_READ_is_never_reported_as_a_CREDENTIAL` went red on an untouched
tree because its check that the case was constructed looks for git's English sentence.
`tests/conftest.py` closes it in `_isolate_the_operator`, from `pytest_configure`: `LC_ALL` is set
to the suite's own value and `LANGUAGE` is deleted before collection, on the controller and on
every xdist worker.

THE HONEST CHECK READS THE THING: what a real `locale` subprocess reports for the environment it
inherited, not the conftest's text and not a translated message (which would depend on which
locales this machine has installed). The planted verifier runs a probe in a nested pytest under a
Portuguese shell WITH a copy of the conftest (must pass, in one process and under `-n 2`) and with
`--noconftest` (must fail), so it measures the conftest and not the machine.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import conftest

ROOT = Path(__file__).resolve().parents[1]

#: What the pin must read as, for a subprocess. Written out rather than imported from the conftest,
#: so the planted verifier still runs against a conftest that names no pin at all.
PINNED = "C.UTF-8"

#: The remedy every failure here names.
REMEDY = ("restore the step in `tests/conftest.py::_isolate_the_operator` that sets `LC_ALL` to "
          "`SUITE_LOCALE` and deletes `LANGUAGE`")


def _reported(stdout: str) -> dict[str, str]:
    """`locale`'s own report, name → value, quotes stripped (glibc quotes derived values, macOS
    quotes them all)."""
    lines = (line.partition("=") for line in stdout.splitlines() if "=" in line)
    return {name: value.strip('"') for name, _, value in lines}


def test_a_subprocess_the_suite_starts_reads_the_pinned_locale():
    """A `locale` started from inside a test, with the environment the test inherited, reports
    the suite's pinned `LC_ALL` and no `LANGUAGE`."""
    pinned = getattr(conftest, "SUITE_LOCALE", None)
    assert pinned == PINNED, (
        f"the conftest pins no locale (SUITE_LOCALE is {pinned!r}), so a tool a test starts speaks "
        f"the machine's language and a test reading its sentence fails off an English machine — "
        f"{REMEDY}")
    done = subprocess.run(["locale"], capture_output=True, text=True, timeout=60)
    seen = _reported(done.stdout)
    assert seen.get("LC_ALL") == PINNED and not seen.get("LANGUAGE"), (
        f"a subprocess started from the suite reads LC_ALL={seen.get('LC_ALL')!r} "
        f"LANGUAGE={seen.get('LANGUAGE')!r}, not the suite's pin — its messages follow the "
        f"operator's shell — {REMEDY}")


# ── the honest verifier: a Portuguese shell, pinned WITH the conftest and leaking WITHOUT ──────────

#: A probe that FAILS the moment the planted shell's locale reaches it. `PLANTED_*` mirror what the
#: verifier plants, so the probe can tell the shell's value from the pin.
PROBE = textwrap.dedent("""
    import os
    import subprocess

    PINNED = "C.UTF-8"

    # RESOLVED AT IMPORT, before any fixture runs: only the configure-time pin covers this window.
    LC_ALL_AT_IMPORT = os.environ.get("LC_ALL")


    def _locale():
        done = subprocess.run(["locale"], capture_output=True, text=True, timeout=60)
        lines = (line.partition("=") for line in done.stdout.splitlines() if "=" in line)
        return {name: value.strip('"') for name, _, value in lines}


    def test_the_locale_at_import_is_the_pin():
        assert LC_ALL_AT_IMPORT == PINNED, (
            f"a module imported under the planted shell read LC_ALL={LC_ALL_AT_IMPORT!r}")


    def test_a_subprocess_reads_the_pinned_lc_all():
        seen = _locale()
        assert seen.get("LC_ALL") == PINNED, (
            f"a subprocess read the planted shell's LC_ALL={seen.get('LC_ALL')!r}")


    def test_the_planted_language_reaches_no_subprocess():
        # GNU gettext reads LANGUAGE ahead of LC_ALL for its message catalogues: a pinned LC_ALL
        # with the shell's LANGUAGE left in place still speaks the shell's language
        assert "LANGUAGE" not in os.environ, os.environ.get("LANGUAGE")
        seen = _locale()
        assert not seen.get("LANGUAGE"), (
            f"a subprocess read the planted shell's LANGUAGE={seen.get('LANGUAGE')!r}")
""")

#: How many tests the probe holds — counted from its text, so the check below cannot drift from it.
PROBE_TESTS = len(re.findall(r"^def test_", PROBE, re.M))


def _planted_shell() -> dict[str, str]:
    """The environment a contributor whose machine speaks Portuguese launches the suite from."""
    return {**os.environ, "LANG": "pt_BR.UTF-8", "LC_ALL": "pt_BR.UTF-8", "LANGUAGE": "pt_BR:de"}


def _run_the_probe(arena: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    """The probe, OUTSIDE the tree with a faithful copy of the conftest beside it — for the reason
    `test_the_suite_reads_no_operators_beeverforge.py` gives: a `.py` under `tests/` is a real
    source file every staleness checksum then reads, and `-c` gives the child this repository's
    rootdir and `pythonpath`."""
    arena.mkdir(parents=True)
    assert ROOT not in arena.resolve().parents, "the probe would be written inside the tree"
    (arena / "conftest.py").write_text(
        (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8"), encoding="utf-8")
    probe = arena / "test__locale_probe__.py"
    probe.write_text(PROBE)
    return subprocess.run(
        [sys.executable, "-m", "pytest", str(probe), "-c", str(ROOT / "pyproject.toml"),
         *extra, "-q", "-p", "no:randomly", "-p", "no:cacheprovider", "--no-header"],
        cwd=ROOT, env=_planted_shell(), capture_output=True, text=True, timeout=300)


def _passed(done: subprocess.CompletedProcess[str]) -> None:
    counted = re.search(r"(\d+) passed", done.stdout)
    assert done.returncode == 0 and counted and int(counted.group(1)) == PROBE_TESTS, (
        f"under a Portuguese shell the probe did not run and pass all {PROBE_TESTS} tests, so the "
        f"shell's locale reaches what the suite starts — {REMEDY}:\n"
        f"{done.stdout[-2000:]}{done.stderr[-800:]}")


def test_the_conftest_pins_the_locale_over_a_planted_shell(tmp_path):
    _passed(_run_the_probe(tmp_path / "with"))


def test_the_pin_holds_on_every_xdist_worker(tmp_path):
    """Each worker runs `pytest_configure` itself and pins the same value, whatever the spawn
    inherited — the way each worker re-homes `HOME`."""
    _passed(_run_the_probe(tmp_path / "workers", "-n", "2"))


def test_without_the_conftest_the_planted_locale_reaches_the_probe(tmp_path):
    """`--noconftest` takes away exactly the pin, and the probe must then FAIL — otherwise the runs
    above are green because the shell's locale never reached the probe, not because the conftest
    pinned it. If this stops failing, the planted shell no longer reaches the child."""
    done = _run_the_probe(tmp_path / "without", "--noconftest")

    assert done.returncode != 0, (
        f"without the conftest the probe still read the pin — it is not measuring the conftest; "
        f"check that `_planted_shell` still plants LC_ALL and LANGUAGE:\n"
        f"{done.stdout[-2000:]}{done.stderr[-800:]}")
