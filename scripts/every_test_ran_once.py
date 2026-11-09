"""Every test the suite collects was started exactly once across CI's parallel jobs.

    python scripts/every_test_ran_once.py <collected ids> <ran ids>...
    python scripts/every_test_ran_once.py --newest-attempts <downloaded artifacts> <ids dir>

CI runs the suite as jobs side by side (`.github/workflows/ci.yml`): the tests that start their
own durable engine or need Docker, and the rest in slices (`make test-integration`,
`make test-unit`). A test that no job selected would leave the gate green over nothing, and a
marker expression or a slice rule is exactly where one slips through. So the lint job writes the
whole collection (`make test-collect`), every test job writes the node ids it started
(`--record-ids`, one line per setup report), and this compares them:

- MISSING: collected, and started by no job;
- DOUBLED: started by more than one job, or twice in one;
- UNKNOWN: started, and not in the collection, so the jobs did not collect the same suite.

Any of the three exits 1 and names the tests. Stdlib only: the job that runs this installs nothing.

A RE-RUN READS ITS NEWEST ATTEMPT (#417). Re-running a failed job adds an artifact of the same
name beside the earlier attempt's, and the `test` job of the newest attempt downloads both. Merged
into one directory, an earlier attempt's file could win: on main at 6632539 attempt 2's
`integration` stopped before `make test-alone`, attempt 3's ran it, and the proof read attempt
2's files and called the 153 `alone` tests missing. So every upload is named
`<job>-attempt-<n>` (`github.run_attempt`), and `--newest-attempts` copies the files of each
job's highest attempt alone into the ids directory, before the comparison. A job that was not
re-run keeps its own attempt's files. An artifact without its attempt, or two jobs writing one
file name, is refused by name rather than read or overwritten unseen.
"""

from __future__ import annotations

import re
import shutil
import sys
from collections import Counter
from pathlib import Path

#: How many of each kind are named; the count is always given whole.
SHOWN = 20


def _ids(path: Path) -> list[str]:
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def compare(collected: list[str], ran: list[str]) -> dict[str, list[str]]:
    """The tests missing, doubled and unknown, each sorted; all three empty when every collected
    test ran exactly once."""
    wanted = set(collected)
    counts = Counter(ran)
    return {
        "missing": sorted(wanted - counts.keys()),
        "doubled": sorted(nodeid for nodeid, n in counts.items() if n > 1),
        "unknown": sorted(counts.keys() - wanted),
    }


_ATTEMPT = re.compile(r"(?P<job>.+)-attempt-(?P<n>[0-9]+)")


def newest_attempts(downloaded: Path, into: Path) -> list[str]:
    """Copy the files of each job's newest attempt from `downloaded` (one directory per artifact,
    as `download-artifact` lays them out apart) into `into`; the refusals, empty when it copied."""
    newest: dict[str, tuple[int, Path]] = {}
    refusals: list[str] = []
    for artifact in sorted(p for p in downloaded.iterdir() if p.is_dir()):
        named = _ATTEMPT.fullmatch(artifact.name)
        if named is None:
            refusals.append(f"{artifact.name} does not end in -attempt-<n>, so which attempt it "
                            f"is cannot be told: name the upload with `github.run_attempt`")
            continue
        job, n = named["job"], int(named["n"])
        if job not in newest or n > newest[job][0]:
            newest[job] = (n, artifact)
    owner: dict[str, str] = {}
    for job, (_n, artifact) in sorted(newest.items()):
        for file in sorted(artifact.iterdir()):
            if file.name in owner:
                refusals.append(f"{file.name} is written by both {owner[file.name]} and {job}, so "
                                f"one would overwrite the other: give each job a file of its own")
                continue
            owner[file.name] = job
    if refusals:
        return refusals
    into.mkdir(parents=True, exist_ok=True)
    for job, (_n, artifact) in newest.items():
        for file in artifact.iterdir():
            shutil.copyfile(file, into / file.name)
    return []


def main(argv: list[str]) -> int:
    if argv[:1] == ["--newest-attempts"] and len(argv) == 3:
        refusals = newest_attempts(Path(argv[1]), Path(argv[2]))
        for refusal in refusals:
            print(refusal, file=sys.stderr)
        return 1 if refusals else 0
    if len(argv) < 2:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    collected = _ids(Path(argv[0]))
    ran = [nodeid for path in argv[1:] for nodeid in _ids(Path(path))]
    if not collected:
        print(f"{argv[0]} names no test: the collection was not written", file=sys.stderr)
        return 1
    found = compare(collected, ran)
    if not any(found.values()):
        print(f"every one of the {len(collected)} collected tests ran exactly once, "
              f"across {len(argv) - 1} recorded run(s)")
        return 0
    for kind, ids in found.items():
        if ids:
            print(f"{kind.upper()}: {len(ids)} test(s)", file=sys.stderr)
            for nodeid in ids[:SHOWN]:
                print(f"  {nodeid}", file=sys.stderr)
            if len(ids) > SHOWN:
                print(f"  … and {len(ids) - SHOWN} more", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
