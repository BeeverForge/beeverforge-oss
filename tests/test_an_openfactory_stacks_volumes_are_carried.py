"""An OpenFactory 0.7 compose stack's data reaches BeeverForge's volumes on an upgrade in place
(#266).

THE DEFECT. Compose prefixes volumes with the project name, and the rename changed both the
project (`openfactory` → `beeverforge`) and the volume keys (`openfactory_state` →
`beeverforge_state`, …). The upgraded stack started on empty volumes: no Temporal history, so no
card in flight; no registry, so no project.

THE DAEMON HERE IS A FAKE that keeps volumes (with labels and files) and containers, and answers
the `docker` commands `upgrade_from_openfactory` sends the way the real client does. What the real
daemon does with them is proven by the upgrade rehearsal on a real 0.7 stack, by hand.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest

from beeverforge.onboarding import upgrade_from_openfactory as up

IMAGE = "ghcr.io/beeverforge/beeverforge-cli:v0.2.0"


class Daemon:
    """Volumes {name: {"labels": {...}, "files": {...}}} and containers {id: (project, running)}."""

    def __init__(self):
        self.volumes: dict[str, dict] = {}
        self.containers: dict[str, tuple[str, bool]] = {}
        self.calls: list[list[str]] = []
        self.fail_copy_of: str | None = None
        #: Answers for the checks that cannot see, as the real client prints them.
        self.fail_inspect: str | None = None
        self.fail_stamp_check = False

    def volume(self, name, *, project="", key="", files=None, **labels):
        lab = dict(labels)
        if project:
            lab["com.docker.compose.project"] = project
        if key:
            lab["com.docker.compose.volume"] = key
        self.volumes[name] = {"labels": lab, "files": dict(files or {})}

    def __call__(self, args: list[str]) -> tuple[int, str]:
        self.calls.append(list(args))
        a = list(args)
        if a[:2] == ["volume", "ls"]:
            want = a[a.index("--filter") + 1].split("=", 1)[1].split("=", 1)[1]
            rows = [f"{n}\t{v['labels'].get('com.docker.compose.volume', '')}"
                    for n, v in self.volumes.items()
                    if v["labels"].get("com.docker.compose.project") == want]
            return 0, "\n".join(rows) + ("\n" if rows else "")
        if a[:2] == ["volume", "inspect"]:
            name = a[-1]
            if self.fail_inspect:
                return 1, self.fail_inspect
            if name not in self.volumes:
                return 1, f"Error response from daemon: get {name}: no such volume"
            label = re.search(r'index \.Labels "([^"]+)"', a[3]).group(1)
            return 0, self.volumes[name]["labels"].get(label, "<no value>") + "\n"
        if a[:2] == ["volume", "create"]:
            labels = dict(a[i + 1].split("=", 1) for i, x in enumerate(a) if x == "--label")
            self.volumes[a[-1]] = {"labels": labels, "files": {}}
            return 0, a[-1] + "\n"
        if a[0] == "ps":
            want = a[a.index("--filter") + 1].split("=", 1)[1].split("=", 1)[1]
            return 0, "".join(f"{c}\n" for c, (p, on) in self.containers.items()
                              if p == want and on)
        if a[0] == "stop":
            for c in a[1:]:
                p, _ = self.containers[c]
                self.containers[c] = (p, False)
            return 0, ""
        if a[0] == "run":
            mounts = {a[i + 1].split(":")[1]: a[i + 1].split(":")[0]
                      for i, x in enumerate(a) if x == "-v"}
            if "test" in a:
                if self.fail_stamp_check:
                    return 125, "docker: Error response from daemon: mount refused."
                return (0, "") if up.STAMP in self.volumes[mounts["/to"]]["files"] else (1, "")
            source, target = mounts["/from"], mounts["/to"]
            assert any(c for c, (p, on) in self.containers.items() if on and p == "openfactory") \
                is False, "a volume was copied while the 0.7 stack was still running"
            files = self.volumes[target]["files"]
            files.clear()
            files.update(self.volumes[source]["files"])
            if self.fail_copy_of == source:
                return 1, "cp: write error: No space left on device"
            files[up.STAMP] = ""
            return 0, ""
        raise AssertionError(f"unexpected docker call: {shlex.join(a)}")


def _a_0_7_stack(d: Daemon) -> None:
    d.volume("openfactory_temporal_db", project="openfactory", key="temporal_db",
             files={"PG_VERSION": "16"})
    d.volume("openfactory_openfactory_state", project="openfactory", key="openfactory_state",
             files={"registry.yaml": "projects: [someone-app]"})
    d.volume("openfactory_openfactory_repos", project="openfactory", key="openfactory_repos")
    d.volume("openfactory_openfactory_logs", project="openfactory", key="openfactory_logs")
    d.volume("openfactory_openfactory_toolbox", project="openfactory", key="openfactory_toolbox",
             files={"claude": "2.1.219"})
    d.containers = {"w07": ("openfactory", True), "p07": ("openfactory", True),
                    "other": ("someone-else", True)}


@pytest.fixture
def env_0_7(tmp_path) -> Path:
    f = tmp_path / ".env.compose"
    f.write_text("OPENFACTORY_BOT_TOKEN=x\nOPENFACTORY_VERSION=v0.7.0\n")
    return f


def test_a_0_7_stacks_volumes_are_copied_into_beeverforges(env_0_7):
    d = Daemon()
    _a_0_7_stack(d)

    done = up.carry(env_0_7, docker=d, image=IMAGE)

    assert d.volumes["beeverforge_temporal_db"]["files"]["PG_VERSION"] == "16"
    assert d.volumes["beeverforge_beeverforge_state"]["files"]["registry.yaml"] == (
        "projects: [someone-app]")
    assert "beeverforge_beeverforge_repos" in d.volumes
    assert "beeverforge_beeverforge_logs" in d.volumes
    assert sorted(done.copied) == sorted([
        ("openfactory_openfactory_logs", "beeverforge_beeverforge_logs"),
        ("openfactory_openfactory_repos", "beeverforge_beeverforge_repos"),
        ("openfactory_openfactory_state", "beeverforge_beeverforge_state"),
        ("openfactory_temporal_db", "beeverforge_temporal_db")])


def test_the_targets_carry_composes_labels_so_compose_adopts_them(env_0_7):
    d = Daemon()
    _a_0_7_stack(d)

    up.carry(env_0_7, docker=d, image=IMAGE)

    labels = d.volumes["beeverforge_beeverforge_state"]["labels"]
    assert labels["com.docker.compose.project"] == "beeverforge"
    assert labels["com.docker.compose.volume"] == "beeverforge_state"
    assert labels[up.CARRIED_FROM] == "openfactory_openfactory_state"
    assert d.volumes["beeverforge_temporal_db"]["labels"]["com.docker.compose.volume"] == (
        "temporal_db")


def test_the_toolbox_is_left_and_said(env_0_7):
    d = Daemon()
    _a_0_7_stack(d)

    done = up.carry(env_0_7, docker=d, image=IMAGE)

    assert "beeverforge_beeverforge_toolbox" not in d.volumes
    assert [s for s, _ in done.left] == ["openfactory_openfactory_toolbox"]
    assert any("not carried: openfactory_openfactory_toolbox" in line
               for line in up.report(done))


def test_only_the_0_7_stack_is_stopped_before_the_copy_and_nothing_is_removed(env_0_7):
    d = Daemon()
    _a_0_7_stack(d)

    done = up.carry(env_0_7, docker=d, image=IMAGE)

    assert sorted(done.stopped) == ["p07", "w07"]
    assert d.containers["other"] == ("someone-else", True)
    first_copy = next(i for i, c in enumerate(d.calls) if c[0] == "run" and "test" not in c)
    stop = next(i for i, c in enumerate(d.calls) if c[0] == "stop")
    assert stop < first_copy
    assert not [c for c in d.calls if c[:2] in (["volume", "rm"], ["rm"]) or c[0] == "rm"]
    assert "openfactory_openfactory_state" in d.volumes


def test_the_copy_runs_as_root_reads_the_0_7_volume_read_only_and_stamps_last(env_0_7):
    d = Daemon()
    _a_0_7_stack(d)

    up.carry(env_0_7, docker=d, image=IMAGE)

    copies = [c for c in d.calls if c[0] == "run" and "test" not in c]
    assert copies
    for c in copies:
        assert c[c.index("--user") + 1] == "0"
        assert any(x.endswith(":/from:ro") for x in c)
        script = c[-1]
        assert script.index("find /to -mindepth 1 -delete") < script.index("cp -a /from/. /to/")
        assert script.rstrip().endswith(f"touch /to/{up.STAMP}")
        assert IMAGE in c


def test_a_file_that_is_not_0_7s_touches_nothing(tmp_path):
    d = Daemon()
    _a_0_7_stack(d)
    f = tmp_path / ".env.compose"
    f.write_text("BEEVERFORGE_BOT_TOKEN=x\n")

    done = up.carry(f, docker=d, image=IMAGE)

    assert not done.upgrade and d.calls == []
    assert d.containers["w07"] == ("openfactory", True)
    assert up.report(done) == []


def test_no_file_touches_nothing(tmp_path):
    d = Daemon()
    _a_0_7_stack(d)

    assert not up.carry(tmp_path / "absent", docker=d, image=IMAGE).upgrade
    assert d.calls == []


def test_a_target_a_beeverforge_stack_already_keeps_is_refused_by_name(env_0_7):
    d = Daemon()
    _a_0_7_stack(d)
    d.volume("beeverforge_beeverforge_state", project="beeverforge", key="beeverforge_state",
             files={"registry.yaml": "projects: [another]"})

    with pytest.raises(up.Refused, match="beeverforge_beeverforge_state already exists"):
        up.carry(env_0_7, docker=d, image=IMAGE)

    assert d.volumes["beeverforge_beeverforge_state"]["files"] == {
        "registry.yaml": "projects: [another]"}
    assert d.containers["w07"] == ("openfactory", True), "the 0.7 stack was stopped for nothing"


def test_a_second_run_leaves_what_was_carried(env_0_7):
    d = Daemon()
    _a_0_7_stack(d)
    up.carry(env_0_7, docker=d, image=IMAGE)
    d.volumes["beeverforge_beeverforge_state"]["files"]["registry.yaml"] = "written since"
    d.containers["w07"] = ("openfactory", True)

    done = up.carry(env_0_7, docker=d, image=IMAGE)

    assert done.copied == [] and len(done.already) == 4
    assert d.volumes["beeverforge_beeverforge_state"]["files"]["registry.yaml"] == "written since"
    assert done.stopped == [] and d.containers["w07"] == ("openfactory", True)


def test_a_copy_that_did_not_finish_is_refused_and_made_again_on_the_next_run(env_0_7):
    d = Daemon()
    _a_0_7_stack(d)
    # THE LAST ONE COPIED, so every other target is stamped and this one alone says the carry
    # did not finish.
    d.fail_copy_of = "openfactory_temporal_db"

    with pytest.raises(up.Refused, match="copy openfactory_temporal_db into"):
        up.carry(env_0_7, docker=d, image=IMAGE)
    assert up.STAMP not in d.volumes["beeverforge_temporal_db"]["files"]

    d.fail_copy_of = None
    done = up.carry(env_0_7, docker=d, image=IMAGE)

    assert ("openfactory_temporal_db", "beeverforge_temporal_db") in done.copied
    assert up.STAMP in d.volumes["beeverforge_temporal_db"]["files"]


def test_a_0_7_file_with_no_0_7_volume_says_the_stack_starts_empty(env_0_7):
    d = Daemon()

    done = up.carry(env_0_7, docker=d, image=IMAGE)

    assert done.upgrade and done.copied == []
    assert any("starts empty" in line for line in up.report(done))


@pytest.mark.parametrize("line, is_0_7", [
    ("OPENFACTORY_BOT_TOKEN=x", True),
    ("export OPENFACTORY_BOT_TOKEN=x", True),
    ("  OPENFACTORY_VERSION=v0.7.0", True),
    ("# OPENFACTORY_BOT_TOKEN=x", False),
    ("BEEVERFORGE_BOT_TOKEN=x", False),
    ("OPENFACTORY_NOTHING", False),
])
def test_a_0_7_file_is_one_that_sets_an_openfactory_row(tmp_path, line, is_0_7):
    f = tmp_path / ".env.compose"
    f.write_text(line + "\n")

    assert up.is_a_0_7_file(f) is is_0_7


# ── the command the installer runs ──────────────────────────────────────────────────────────────

def _invoke(*args, env=None):
    from typer.testing import CliRunner

    from beeverforge.cli import app

    return CliRunner().invoke(app, ["upgrade-from-openfactory", *args], env=env or {})


def test_the_command_does_nothing_for_a_file_that_is_not_0_7s(tmp_path, monkeypatch):
    f = tmp_path / ".env.compose"
    f.write_text("BEEVERFORGE_BOT_TOKEN=x\n")
    monkeypatch.setattr("subprocess.run", lambda *a, **k: pytest.fail("docker was called"))

    result = _invoke("--env-file", str(f))

    assert result.exit_code == 0, result.output
    assert result.output.strip() == ""


def test_the_command_copies_with_this_releases_cli_image(env_0_7, monkeypatch):
    seen = {}

    def carry(path, *, docker, image):
        seen["image"] = image
        return up.Carried(upgrade=True, copied=[("openfactory_temporal_db",
                                                 "beeverforge_temporal_db")])

    monkeypatch.setattr(up, "carry", carry)
    monkeypatch.delenv("BEEVERFORGE_VERSION", raising=False)

    result = _invoke("--env-file", str(env_0_7), env={"BEEVERFORGE_VERSION": "v0.2.0"})

    assert result.exit_code == 0, result.output
    assert seen["image"] == "ghcr.io/beeverforge/beeverforge-cli:v0.2.0"
    assert "copied openfactory_temporal_db into beeverforge_temporal_db" in result.output


def test_the_command_refuses_with_the_sentence_and_a_non_zero_exit(env_0_7, monkeypatch):
    def carry(path, *, docker, image):
        raise up.Refused("the volume beeverforge_temporal_db already exists and was not carried")

    monkeypatch.setattr(up, "carry", carry)

    result = _invoke("--env-file", str(env_0_7), "--image", IMAGE)

    assert result.exit_code == 1
    assert "beeverforge_temporal_db already exists" in result.output


def test_the_command_needs_an_image_to_copy_with(env_0_7, monkeypatch):
    monkeypatch.delenv("BEEVERFORGE_VERSION", raising=False)

    result = _invoke("--env-file", str(env_0_7))

    assert result.exit_code == 2
    assert "--image" in result.output


# ── a check that cannot see is never read as "nothing there" (review of #514) ────────────────────

def _carried_and_in_use(env_0_7) -> Daemon:
    """A carry that finished, and BeeverForge data written into one target since."""
    d = Daemon()
    _a_0_7_stack(d)
    up.carry(env_0_7, docker=d, image=IMAGE)
    d.volumes["beeverforge_beeverforge_state"]["files"]["registry.yaml"] = "written since"
    d.containers["w07"] = ("openfactory", True)
    d.calls.clear()
    return d


def test_a_label_check_that_fails_refuses_and_empties_nothing(env_0_7):
    d = _carried_and_in_use(env_0_7)
    d.fail_inspect = "Cannot connect to the Docker daemon. Is the docker daemon running?"

    with pytest.raises(up.Refused, match="could not check the volume"):
        up.carry(env_0_7, docker=d, image=IMAGE)

    assert d.volumes["beeverforge_beeverforge_state"]["files"]["registry.yaml"] == "written since"
    assert not [c for c in d.calls if c[0] in ("run", "stop", "volume") and "create" in c]
    assert d.containers["w07"] == ("openfactory", True)


def test_a_stamp_check_that_fails_refuses_and_empties_nothing(env_0_7):
    d = _carried_and_in_use(env_0_7)
    d.fail_stamp_check = True

    with pytest.raises(up.Refused, match="whether the copy into .* finished"):
        up.carry(env_0_7, docker=d, image=IMAGE)

    assert d.volumes["beeverforge_beeverforge_state"]["files"]["registry.yaml"] == "written since"
    assert not [c for c in d.calls if c[0] == "run" and "test" not in c], "a copy ran"
    assert d.containers["w07"] == ("openfactory", True)


def test_a_retry_copies_every_volume_from_one_moment(env_0_7):
    """0.7 is started again after a failed run and moves on; the retry must not pair the earlier
    copies with later ones."""
    d = Daemon()
    _a_0_7_stack(d)
    d.fail_copy_of = "openfactory_temporal_db"
    with pytest.raises(up.Refused):
        up.carry(env_0_7, docker=d, image=IMAGE)
    assert up.STAMP in d.volumes["beeverforge_beeverforge_state"]["files"], (
        "the premise: state was copied before the database's copy failed")

    d.fail_copy_of = None
    d.containers["w07"] = ("openfactory", True)
    d.volumes["openfactory_openfactory_state"]["files"]["registry.yaml"] = "projects: [later]"
    d.volumes["openfactory_temporal_db"]["files"]["PG_VERSION"] = "16 (later)"
    done = up.carry(env_0_7, docker=d, image=IMAGE)

    assert d.volumes["beeverforge_beeverforge_state"]["files"]["registry.yaml"] == (
        "projects: [later]")
    assert d.volumes["beeverforge_temporal_db"]["files"]["PG_VERSION"] == "16 (later)"
    assert len(done.copied) == 4 and done.already == []


def test_the_closing_sentence_names_every_0_7_volume_to_remove(env_0_7):
    d = Daemon()
    _a_0_7_stack(d)

    said = " ".join(up.report(up.carry(env_0_7, docker=d, image=IMAGE)))

    assert "down -v" not in said
    assert ("docker volume rm openfactory_openfactory_logs openfactory_openfactory_repos "
            "openfactory_openfactory_state openfactory_openfactory_toolbox "
            "openfactory_temporal_db") in said
    assert "label=com.docker.compose.project=openfactory" in said
