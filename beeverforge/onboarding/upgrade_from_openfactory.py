"""Carry an OpenFactory 0.7 compose stack's data into BeeverForge's volumes (#266).

WHY THE DATA DID NOT FOLLOW. Compose prefixes every volume with its project name, and both the
project and the volume keys changed with the rename: 0.7 ran as project `openfactory`, with
`openfactory_temporal_db`, `openfactory_openfactory_state`, `openfactory_openfactory_repos` and
`openfactory_openfactory_logs`; BeeverForge runs as `beeverforge`, with `beeverforge_temporal_db`,
`beeverforge_beeverforge_state`, and so on. An upgrade in place therefore started on EMPTY volumes:
a fresh Temporal database, so every card in flight was gone, and no registry, so no project.

WHAT THIS DOES, IN ORDER, AND ONLY FOR AN UPGRADE IN PLACE. The installer calls it with the
`.env.compose` it is about to rewrite. A file holding `OPENFACTORY_*` rows is a 0.7 deployment
being upgraded; any other file — or none — is not, and nothing is touched: a 0.7 stack somebody
keeps running beside a fresh install is never stopped by surprise.

  1. Every volume compose labelled for project `openfactory` is read, by its compose key.
  2. Each one BeeverForge carries is checked against its target: a target that exists and was not
     made here is REFUSED, by name (a BeeverForge stack already holds data there, and this never
     writes over it); one already carried here is skipped; one whose copy did not finish is
     copied again, from the 0.7 volume, which is never written.
  3. The 0.7 stack's containers are stopped — not removed — so the database is copied at rest and
     its ports are free for the new stack.
  4. Each volume is copied, ownership and modes kept, into a target created with compose's own
     labels, so compose adopts it as its own. A stamp file is written last; a copy without it did
     not finish.

THE HARNESS TOOLBOX IS NOT CARRIED. It holds the harness CLI the image provides, and BeeverForge's
image provides a newer one (#436); a copied toolbox would keep 0.7's.

NOTHING OF 0.7'S IS DELETED. Its volumes and stopped containers stay, so going back is starting
0.7 again; removing them is the operator's step, said at the end.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from beeverforge.former_names import FORMER_PREFIX

#: The compose project names, as each release's `docker-compose.yml` declares them (`name:`).
FORMER_PROJECT = "openfactory"
PROJECT = "beeverforge"

#: 0.7's volume key → BeeverForge's. A key not here is not carried.
CARRIED: dict[str, str] = {
    "temporal_db": "temporal_db",
    "openfactory_state": "beeverforge_state",
    "openfactory_repos": "beeverforge_repos",
    "openfactory_logs": "beeverforge_logs",
}

#: 0.7's keys left behind on purpose, and why — said to the operator.
NOT_CARRIED: dict[str, str] = {
    "openfactory_toolbox": "the harness toolbox, which BeeverForge's image fills again with its "
                           "own harness CLI",
}

#: The label that marks a target volume as made here, naming the 0.7 volume it came from.
CARRIED_FROM = "beeverforge.carried-from"

#: Written into a target LAST: a target without it holds a copy that did not finish.
STAMP = ".beeverforge-carried-from-openfactory"

#: `docker <args>` → (exit code, output). Injected so the steps are tested without a daemon.
Docker = Callable[[list[str]], tuple[int, str]]


class Refused(RuntimeError):
    """The carry cannot go on, said in one sentence that names what to do."""


@dataclass
class Carried:
    """What one run did, in sentences a person reads."""
    upgrade: bool = False
    stopped: list[str] = field(default_factory=list)
    copied: list[tuple[str, str]] = field(default_factory=list)
    already: list[tuple[str, str]] = field(default_factory=list)
    left: list[tuple[str, str]] = field(default_factory=list)


def is_a_0_7_file(path: Path) -> bool:
    """Whether `path` is an OpenFactory 0.7 deployment's `.env.compose`: it sets an
    `OPENFACTORY_*` row. Absent or unreadable is no."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return any(line.lstrip().removeprefix("export ").lstrip().startswith(FORMER_PREFIX)
               and "=" in line for line in text.splitlines())


def target_of(key: str) -> str:
    """The volume BeeverForge's compose names for 0.7's key `key`."""
    return f"{PROJECT}_{CARRIED[key]}"


def _ok(docker: Docker, args: list[str], what: str) -> str:
    rc, out = docker(args)
    if rc != 0:
        raise Refused(f"could not {what}: {out.strip()[:300]} — nothing after this step was "
                      f"done, and the OpenFactory 0.7 volumes were not written")
    return out


def _former_volumes(docker: Docker) -> dict[str, str]:
    """0.7's volumes on this daemon, {compose key: volume name}."""
    out = _ok(docker, ["volume", "ls", "--filter",
                       f"label=com.docker.compose.project={FORMER_PROJECT}", "--format",
                       '{{.Name}}\t{{.Label "com.docker.compose.volume"}}'],
              "list the OpenFactory 0.7 volumes")
    found = {}
    for line in out.splitlines():
        name, _, key = line.strip().partition("\t")
        if name and key:
            found[key] = name
    return found


def _label_of(docker: Docker, volume: str) -> str | None:
    """The `CARRIED_FROM` label of `volume`; `None` when there is no such volume, `""` when it
    exists without the label."""
    rc, out = docker(["volume", "inspect", "--format",
                      f'{{{{index .Labels "{CARRIED_FROM}"}}}}', volume])
    if rc != 0:
        return None
    value = out.strip()
    return "" if value in ("", "<no value>") else value


def _has_stamp(docker: Docker, volume: str, image: str) -> bool:
    rc, _ = docker(["run", "--rm", "--entrypoint", "test", "-v", f"{volume}:/to:ro", image,
                    "-e", f"/to/{STAMP}"])
    return rc == 0


def carry(env_file: Path, *, docker: Docker, image: str) -> Carried:
    """Carry a 0.7 stack's volumes, when `env_file` is a 0.7 deployment's. See the module."""
    done = Carried()
    if not is_a_0_7_file(env_file):
        return done
    done.upgrade = True
    former = _former_volumes(docker)

    plan: list[tuple[str, str]] = []
    for key, source in sorted(former.items()):
        if key not in CARRIED:
            if key in NOT_CARRIED:
                done.left.append((source, NOT_CARRIED[key]))
            continue
        target = target_of(key)
        label = _label_of(docker, target)
        if label is None:
            plan.append((source, target))
        elif label != source:
            raise Refused(
                f"the volume {target} already exists and was not carried from {source}, so a "
                f"BeeverForge stack already keeps data there and it is not written over — move "
                f"it aside (`docker volume rm {target}` once nothing in it is needed) and run "
                f"the installer again")
        elif _has_stamp(docker, target, image):
            done.already.append((source, target))
        else:
            plan.append((source, target))

    if not plan:
        return done

    running = _ok(docker, ["ps", "-q", "--filter",
                           f"label=com.docker.compose.project={FORMER_PROJECT}"],
                  "list the OpenFactory 0.7 containers").split()
    if running:
        _ok(docker, ["stop", *running], "stop the OpenFactory 0.7 containers")
        done.stopped = running

    for source, target in plan:
        if _label_of(docker, target) is None:
            _ok(docker, ["volume", "create",
                         "--label", f"com.docker.compose.project={PROJECT}",
                         "--label", f"com.docker.compose.volume={target[len(PROJECT) + 1:]}",
                         "--label", f"{CARRIED_FROM}={source}", target],
                f"create the volume {target}")
        # AS ROOT, so every file keeps its owner (the database's is the postgres user's); the
        # target is emptied first, so a copy that did not finish is replaced, never merged; the
        # stamp is the last thing written.
        _ok(docker, ["run", "--rm", "--user", "0", "--entrypoint", "sh",
                     "-v", f"{source}:/from:ro", "-v", f"{target}:/to", image, "-c",
                     f"set -e; find /to -mindepth 1 -delete; cp -a /from/. /to/; "
                     f"touch /to/{STAMP}"],
            f"copy {source} into {target}")
        done.copied.append((source, target))
    return done


def report(done: Carried) -> list[str]:
    """What happened, line by line, for the installer to print. Names volumes and containers,
    never anything they hold."""
    if not done.upgrade:
        return []
    lines = []
    if done.stopped:
        lines.append(f"stopped the OpenFactory 0.7 stack's {len(done.stopped)} container(s); "
                     f"they are not removed")
    lines += [f"copied {s} into {t}" for s, t in done.copied]
    lines += [f"{t} was already carried from {s}; left as it is" for s, t in done.already]
    lines += [f"not carried: {s}, {why}" for s, why in done.left]
    if not (done.copied or done.already):
        lines.append(f"no OpenFactory 0.7 volume was found on this daemon (compose project "
                     f"`{FORMER_PROJECT}`), so the new stack starts empty")
    else:
        lines.append(f"the OpenFactory 0.7 volumes are untouched: once BeeverForge runs as it "
                     f"should, remove them with `docker compose -p {FORMER_PROJECT} down -v`")
    return lines
