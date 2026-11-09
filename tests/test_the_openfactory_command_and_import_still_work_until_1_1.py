"""An OpenFactory 0.7 user keeps working until BeeverForge 1.1: the `openfactory` command and the
`openfactory` import name are aliases of `beeverforge`, and each one says so, once.

WHAT A 0.7 INSTALLATION HAS IN ITS HANDS. Scripts and cron lines that call `openfactory <command>`
and parse what it prints; add-on packages that `from openfactory.<module> import <name>`. The
rename to BeeverForge removed both names at once (0.1.0 shipped one console script and one
package), so an upgrade in place broke every one of them with "command not found" and
`ModuleNotFoundError`, before anybody had read a release note.

WHAT EACH TEST HOLDS, AND HOW. Every case runs a FRESH interpreter, because what is under test is
process state a test cannot reset in place: which modules are in `sys.modules`, what the meta path
holds, and which warnings the default filters let through.

  · the command: the `openfactory` row of `pyproject.toml`'s `[project.scripts]` is resolved and
    called the way a console script calls it, beside the `beeverforge` row on the same arguments —
    stdout and the exit code must be the same bytes and the same number, and stderr must carry
    exactly one line naming the new command and 1.1;
  · the import: `openfactory` and `openfactory.<x>` must be the SAME objects as `beeverforge` and
    `beeverforge.<x>` (identity, never a second copy of a module, which would hold its own state);
    the warning must reach a person under Python's DEFAULT filters when the import is written in
    an add-on module rather than in `__main__` — which is where a 0.7 add-on writes it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: What a pip-generated console script does with its `module:attr`, so the row is exercised as an
#: installed command would exercise it — with its own name in `argv[0]`, which is what click shows.
_CONSOLE_SCRIPT = (
    "import importlib, sys\n"
    "name, target = sys.argv[1], sys.argv[2]\n"
    "module, _, attr = target.partition(':')\n"
    "sys.argv = [name, *sys.argv[3:]]\n"
    "sys.exit(getattr(importlib.import_module(module), attr)())\n"
)


def _scripts() -> dict[str, str]:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["scripts"]


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    # the interpreter's own default warning filters, whatever the shell running the suite set
    env.pop("PYTHONWARNINGS", None)
    return env


def _python(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *args], cwd=cwd, env=_env(), capture_output=True,
                          text=True, timeout=120)


def _command(name: str, args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return _python(["-c", _CONSOLE_SCRIPT, name, _scripts()[name], *args], cwd)


def _lines_naming_the_rename(stderr: str) -> list[str]:
    return [line for line in stderr.splitlines()
            if "openfactory" in line and "beeverforge" in line and "1.1" in line]


# ── the command ─────────────────────────────────────────────────────────────────────────────────

def test_the_openfactory_command_is_declared_beside_beeverforge():
    scripts = _scripts()
    assert set(scripts) == {"beeverforge", "openfactory"}, (
        f"[project.scripts] declares {sorted(scripts)} — a 0.7 installation's scripts call "
        f"`openfactory`, and it is kept until 1.1 beside `beeverforge`")
    assert scripts["beeverforge"] == "beeverforge.cli:app"
    assert scripts["openfactory"] != scripts["beeverforge"], (
        "`openfactory` runs the app without saying it was renamed — nothing tells its user that "
        "1.1 removes it")


def test_the_openfactory_command_prints_what_beeverforge_prints_and_exits_as_it_exits(tmp_path):
    for args in (["actions"], ["explain", str(tmp_path / "nosuch")], ["no-such-command"]):
        new = _command("beeverforge", args, tmp_path)
        old = _command("openfactory", args, tmp_path)
        assert old.returncode == new.returncode, (
            f"`openfactory {' '.join(args)}` exits {old.returncode} and `beeverforge` exits "
            f"{new.returncode} — a script reading the exit code reads another answer:\n"
            f"{old.stderr[-800:]}")
        assert old.stdout == new.stdout, (
            f"`openfactory {' '.join(args)}` prints another stdout than `beeverforge` — a script "
            f"parsing it breaks:\n{old.stdout[:400]!r}\n{new.stdout[:400]!r}")
    assert new.returncode == 2, "the usage error was not reached, so the case measured nothing"


def test_the_openfactory_command_says_once_on_stderr_that_it_is_beeverforge_until_1_1(tmp_path):
    old = _command("openfactory", ["actions"], tmp_path)
    new = _command("beeverforge", ["actions"], tmp_path)
    assert old.returncode == 0, old.stderr[-800:]
    said = _lines_naming_the_rename(old.stderr)
    assert len(said) == 1, (
        f"`openfactory` must say ONCE, on stderr, that it is now `beeverforge` and leaves in 1.1; "
        f"it said {said!r} in:\n{old.stderr[-800:]}")
    assert "`beeverforge`" in said[0], said[0]
    assert not _lines_naming_the_rename(new.stderr), (
        f"`beeverforge` itself warns about the old name:\n{new.stderr[-800:]}")
    assert not _lines_naming_the_rename(old.stdout), "the warning went to stdout, where scripts read"


def test_in_a_deployment_that_logs_json_lines_the_warning_is_one_of_them(tmp_path, monkeypatch):
    """A 0.7 compose file runs `openfactory worker`: that process's stderr is a log store's input,
    and one plain line in it is a line the store cannot read. Where the deployment asks for JSON
    lines, the warning is a record of the log, and stdout is still the app's."""
    monkeypatch.setenv("BEEVERFORGE_LOG_FORMAT", "json")
    old = _command("openfactory", ["actions"], tmp_path)
    new = _command("beeverforge", ["actions"], tmp_path)
    assert old.returncode == new.returncode == 0, old.stderr[-800:]
    assert old.stdout == new.stdout
    records = []
    for line in old.stderr.splitlines():
        try:
            records.append(json.loads(line))
        except ValueError:
            raise AssertionError(f"a plain line in a JSON log: {line!r}") from None
    said = [r for r in records if _lines_naming_the_rename(r.get("message", ""))]
    assert len(said) == 1 and said[0]["level"] == "WARNING", records


# ── the import ──────────────────────────────────────────────────────────────────────────────────

def _run(code: str, cwd: Path) -> subprocess.CompletedProcess:
    done = _python(["-c", textwrap.dedent(code)], cwd)
    assert done.returncode == 0, f"the interpreter failed:\n{done.stderr[-1500:]}"
    return done


def test_openfactory_is_the_beeverforge_package_and_its_modules_are_the_same_objects(tmp_path):
    _run("""
        import warnings
        warnings.simplefilter("ignore")
        import beeverforge.cli
        import openfactory
        import openfactory.cli
        import openfactory.adapters.sandbox.worktree as old_worktree
        from openfactory.cli import app
        from openfactory import plugins as old_plugins
        import beeverforge, beeverforge.plugins, beeverforge.adapters.sandbox.worktree as worktree
        assert openfactory is beeverforge, openfactory
        assert openfactory.cli is beeverforge.cli
        assert app is beeverforge.cli.app
        assert old_plugins is beeverforge.plugins
        assert old_worktree is worktree
        # imported FIRST under the old name, the module is still the one the new name finds
        import openfactory.policy.profiles as first_old
        import beeverforge.policy.profiles as then_new
        assert first_old is then_new
        # the aliased modules keep their own identity: a reload, pickle or tool reads these
        for module in (beeverforge.cli, worktree, then_new):
            assert module.__spec__.name == module.__name__, (module.__name__, module.__spec__)
            assert module.__name__.startswith("beeverforge."), module.__name__
    """, tmp_path)


def test_a_module_beeverforge_does_not_have_is_not_found_under_the_old_name(tmp_path):
    _run("""
        import warnings
        warnings.simplefilter("ignore")
        try:
            import openfactory.no_such_module
        except ModuleNotFoundError as exc:
            assert exc.name == "openfactory.no_such_module", exc.name
        else:
            raise AssertionError("a module nobody wrote imported")
    """, tmp_path)


def test_importing_beeverforge_leaves_the_old_name_alone(tmp_path):
    """The alias exists only for whoever asks for it: `import beeverforge` neither registers the
    old name nor adds anything to the import machinery of the process."""
    _run("""
        import sys
        before = list(sys.meta_path)
        import beeverforge.cli
        assert "openfactory" not in sys.modules
        assert sys.meta_path == before, sys.meta_path
    """, tmp_path)


def test_the_old_import_warns_a_person_once_under_the_default_filters(tmp_path):
    """Written the way a 0.7 add-on writes it: in a module of its own, not in `__main__`. Python
    hides a DeprecationWarning raised there unless a developer opts in, so a deployment's operator
    — the person 1.1 breaks — would never read it; a FutureWarning is shown by default."""
    (tmp_path / "someone_addon.py").write_text(
        "from openfactory.cli import app\n"
        "import openfactory.plugins\n"
        "import openfactory.adapters.sandbox.worktree\n")
    done = _run("import someone_addon\nimport openfactory\n", tmp_path)
    said = _lines_naming_the_rename(done.stderr)
    assert len(said) == 1, (
        f"importing `openfactory` must say ONCE that it is `beeverforge` until 1.1; it said "
        f"{said!r} in:\n{done.stderr[-1500:]}")
    assert "FutureWarning" in said[0], said[0]
    assert "someone_addon.py" in said[0], (
        f"the warning names {said[0]!r}, not the add-on line that imported the old name")


# ── the register, and the alias beside #499's carry-over ────────────────────────────────────────

def test_both_aliases_leave_in_the_release_the_register_names(tmp_path):
    """The removal is written ONCE, in `beeverforge/deprecations.py`, where the guard that stops a
    release carrying a due entry reads it — so each alias's warning must name the register's
    release. Proven by moving the register and reading what each warning then says."""
    from beeverforge import deprecations

    assert deprecations.removed_in("openfactory-command") == "1.1"
    assert deprecations.removed_in("openfactory-import") == "1.1"
    done = _run("""
        import dataclasses, sys, warnings
        from beeverforge import deprecations
        deprecations.REMOVALS = tuple(
            dataclasses.replace(e, removed_in="9.9") if e.key.startswith("openfactory-") else e
            for e in deprecations.REMOVALS)
        from beeverforge import former_command
        assert "9.9" in former_command.WARNING, former_command.WARNING
        with warnings.catch_warnings(record=True) as said:
            warnings.simplefilter("always")
            import openfactory
        assert len(said) == 1 and "9.9" in str(said[0].message), [str(w.message) for w in said]
    """, tmp_path)
    assert done.returncode == 0


def test_the_command_alias_says_the_carry_over_once_and_its_own_warning_once(tmp_path,
                                                                              monkeypatch):
    """`openfactory` loads the environment to read the log format, then the app's callback loads
    it again. A 0.7 `.env` holding an `OPENFACTORY_*` whose `BEEVERFORGE_*` name is set to another
    value is read by BOTH loads (the first removes the old name from the process, the second
    `.env` load puts it back): the carry-over must still be said once, beside one alias warning.
    A fresh interpreter per run is a fresh `former_names._REPORTED`."""
    (tmp_path / ".env").write_text("OPENFACTORY_SOMEONE_SETTING=old\n")
    monkeypatch.setenv("BEEVERFORGE_SOMEONE_SETTING", "new")
    monkeypatch.delenv("OPENFACTORY_SOMEONE_SETTING", raising=False)
    plain = _command("openfactory", ["actions"], tmp_path)
    assert plain.returncode == 0, plain.stderr[-800:]
    carried = [line for line in plain.stderr.splitlines()
               if "OPENFACTORY_SOMEONE_SETTING" in line]
    assert len(carried) == 1, f"the carry-over said {len(carried)} times:\n{plain.stderr}"
    assert len(_lines_naming_the_rename(plain.stderr)) == 1, plain.stderr

    monkeypatch.setenv("BEEVERFORGE_LOG_FORMAT", "json")
    structured = _command("openfactory", ["actions"], tmp_path)
    assert structured.returncode == 0, structured.stderr[-800:]
    records = [json.loads(line) for line in structured.stderr.splitlines()]
    carried = [r for r in records if r["logger"] == "beeverforge.environment"
               and "OPENFACTORY_SOMEONE_SETTING" in r["message"]]
    assert len(carried) == 1, records
    assert len([r for r in records if _lines_naming_the_rename(r["message"])]) == 1, records
