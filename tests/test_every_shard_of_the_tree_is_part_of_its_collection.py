"""CI's shards of the real tree together collect exactly the whole tree (#356).

The probe in `tests/test_ci_runs_every_test_exactly_once.py` holds the rule on a few files, and
`test_every_file_of_the_tree_lands_in_one_shard_for_any_n` holds the assignment of every real
file for N = 1..6 in-process. This holds the rule end to end on the tree as it is, at the shard
count CI runs (`TEST_SHARDS` of the unit job in `.github/workflows/ci.yml`): its own test roots,
its own committed duration table, the files that table does not list and the ones it lists that
are gone. The node ids the `--shard=k/N` collections write add up to the whole collection,
nothing missing and nothing doubled.

SLOW, so it runs in the integration job and not in every unit shard: it is N + 1 collections of
the tree, and #336 keeps the unit run from re-collecting the whole suite. Only CI's N, because the
integration job is CI's longest: every N from 1 to 6 was 21 collections, 75 s on CI's runner.
"""

from __future__ import annotations

import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.slow

ROOT = Path(__file__).resolve().parent.parent
CI = ROOT / ".github" / "workflows" / "ci.yml"


def _ci_shards() -> int:
    unit = yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"]["unit"]
    return int(next(step["env"]["TEST_SHARDS"] for step in unit["steps"]
                    if step.get("run") == "make test-unit"))


def _collect(out: Path, *args: str) -> list[str]:
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:randomly",
         "-p", "no:cacheprovider", f"--record-ids={out}", *args],
        capture_output=True, text=True, cwd=str(ROOT), timeout=600)
    assert done.returncode == 0, done.stdout[-1500:] + done.stderr[-1500:]
    return out.read_text(encoding="utf-8").splitlines()


def test_the_shards_of_the_tree_add_up_to_its_collection(tmp_path):
    count = _ci_shards()
    assert count > 1, f"CI runs {count} unit shard"
    runs = {0: ()} | {index: (f"--shard={index}/{count}",) for index in range(1, count + 1)}
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = dict(zip(runs, pool.map(
            lambda key: _collect(tmp_path / f"ids-{key}.txt", *runs[key]), runs), strict=True))
    whole = Counter(ids[0])
    assert len(whole) > 1000, f"the whole tree collected {len(whole)} tests"

    union = Counter(nodeid for index in range(1, count + 1) for nodeid in ids[index])
    assert union == whole, (
        f"with {count} shards, missing {sorted(whole - union)[:5]}, "
        f"doubled or unknown {sorted(union - whole)[:5]}")
    assert all(ids[index] for index in range(1, count + 1)), f"an empty shard of {count}"
