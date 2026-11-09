"""Rebuild `tests/shard_durations.json`, the measured seconds of each test file, from JUnit reports.

    python -m tests.shard_durations <junit.xml> [<junit.xml> ...] [--out PATH]

WHAT THE TABLE IS FOR. `--shard=I/N` (`tests/conftest.py`) gives each CI unit job whole test files,
and balances them by this table: longest first, each to the least-loaded shard. A shard skips
every file another shard owns before it imports it, so each job collects only its part (#356).

A STALE TABLE COSTS ONLY BALANCE, NEVER CORRECTNESS. A file the table does not list goes to a
shard by the CRC32 of its path, and a listed file that is gone takes a share of nothing: every
collected test still lands in exactly one shard. Refresh it when CI's four unit walls drift
apart, or after adding or moving heavy test files (CONTRIBUTING.md says how).

THE KEYS are paths relative to the repository's root, as the conftest keys a collected file. A
JUnit `classname` is the module's dotted path, with the class after it when the test is in one
(`tests.test_x` or `tests.test_x.TestThing`): the file is the longest dotted prefix that exists as
a `.py` under the root. A classname that names no file is skipped.

EVERY LISTED FILE WEIGHS AT LEAST `FLOOR`. Rounded to 0.1 s, 292 of 872 files weighed 0.0, and the
greedy split gave all of them to one shard, which then imported half the suite's files: their
tests take no time, their collection does.

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TABLE = Path(__file__).with_name("shard_durations.json")
FLOOR = 0.1


def file_of(classname: str, root: Path) -> str | None:
    """The test file a JUnit classname names, relative to `root`, or None."""
    parts = classname.split(".")
    for end in range(len(parts), 0, -1):
        candidate = Path(*parts[:end]).with_suffix(".py")
        if (root / candidate).is_file():
            return candidate.as_posix()
    return None


def table_from(reports: list[Path], root: Path) -> dict[str, float]:
    seconds: dict[str, float] = defaultdict(float)
    for report in reports:
        for case in ET.parse(report).iter("testcase"):
            path = file_of(case.get("classname", ""), root)
            if path is not None:
                seconds[path] += float(case.get("time") or 0)
    return {path: max(round(total, 1), FLOOR) for path, total in sorted(seconds.items())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tests.shard_durations",
                                     description="Rebuild the shard duration table from JUnit.")
    parser.add_argument("reports", nargs="+", type=Path, help="JUnit XML of a full unit run")
    parser.add_argument("--out", type=Path, default=TABLE, help=f"where to write (default {TABLE})")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    table = table_from(args.reports, args.root)
    if not table:
        print(f"{', '.join(map(str, args.reports))} name no test file under {args.root}, so the "
              f"table was left as it was; pass the JUnit report of a full unit run.",
              file=sys.stderr)
        return 1
    args.out.write_text(json.dumps(table, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{args.out}: {len(table)} files, {sum(table.values()):.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
