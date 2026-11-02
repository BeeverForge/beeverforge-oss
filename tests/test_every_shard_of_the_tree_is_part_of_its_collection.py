"""Every shard of the real tree, for N = 1..6, together collect exactly the whole tree (#356).

The probe in `tests/test_ci_runs_every_test_exactly_once.py` holds the rule on a few files. This
holds it on the tree as it is: its own test roots, its own committed duration table, the files
that table does not list and the ones it lists that are gone. For each N, the node ids the N
`--shard=k/N` collections write add up to the whole collection, nothing missing and nothing
doubled.

SLOW, so it runs in the integration job and not in every unit shard: it is 22 collections of the
tree, and #336 keeps the unit run from re-collecting the whole suite.
"""

from __future__ import annotations

import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow

ROOT = Path(__file__).resolve().parent.parent
MOST = 6


def _collect(out: Path, *args: str) -> list[str]:
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:randomly",
         "-p", "no:cacheprovider", f"--record-ids={out}", *args],
        capture_output=True, text=True, cwd=str(ROOT), timeout=600)
    assert done.returncode == 0, done.stdout[-1500:] + done.stderr[-1500:]
    return out.read_text(encoding="utf-8").splitlines()


def test_the_shards_of_the_tree_add_up_to_its_collection(tmp_path):
    runs = {(0, 0): ()} | {(count, index): (f"--shard={index}/{count}",)
                           for count in range(1, MOST + 1) for index in range(1, count + 1)}
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = dict(zip(runs, pool.map(
            lambda key: _collect(tmp_path / f"ids-{key[0]}-{key[1]}.txt", *runs[key]), runs),
            strict=True))
    whole = Counter(ids[(0, 0)])
    assert len(whole) > 1000, f"the whole tree collected {len(whole)} tests"

    for count in range(1, MOST + 1):
        union = Counter(nodeid for index in range(1, count + 1) for nodeid in ids[(count, index)])
        assert union == whole, (
            f"with {count} shards, missing {sorted(whole - union)[:5]}, "
            f"doubled or unknown {sorted(union - whole)[:5]}")
        assert all(ids[(count, index)] for index in range(1, count + 1)), f"an empty shard of {count}"
