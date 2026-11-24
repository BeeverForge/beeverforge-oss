"""#681 — a refresh does not publish a map larger than `yaml_io.MAX_BYTES`.

It logs one line naming the document, its size, the ceiling and the largest module, and treats the
map as unchanged. The oversized map is built in memory from a synthetic module: no multi-megabyte
file is ever on disk.
"""

from __future__ import annotations

import logging
from pathlib import Path

from beeverforge.knowledge import build_bundle as real_build_bundle
from beeverforge.knowledge.bundle import MODULES_FILE
from beeverforge.knowledge.contracts import Module, SourceLink
from beeverforge.util import yaml_io
from tests.test_knowledge_pipeline import (
    _branch_commits,
    _client_repo,
    _context_repo,
    _patch_activity,
)


def _with_a_module_of_many_symbols(bundle, symbols: int):
    big = Module(name="tests", path="tests", purpose="p", key_files=["tests/a.py"],
                 public_surface=[f"test_symbol_number_{i:08d}" for i in range(symbols)],
                 source=SourceLink(file="tests/a.py", commit="c"))
    modules = [*bundle.module_map.modules, big]
    return bundle.model_copy(update={
        "module_map": bundle.module_map.model_copy(update={"modules": modules})})


def test_a_refresh_over_the_ceiling_publishes_nothing_and_logs_one_line(
        tmp_path: Path, monkeypatch, caplog):
    from beeverforge.runtime.temporal.io import KnowledgeRefreshInput

    remote, _ = _client_repo(tmp_path)
    context = _context_repo(tmp_path, with_docs=False)
    acts = _patch_activity(monkeypatch, tmp_path, remote, context)
    inp = KnowledgeRefreshInput(project="p", issue="1")
    assert acts._do_refresh_knowledge(inp) == "published"
    published = _branch_commits(context, "main")

    # a ceiling the next build exceeds, so the over-ceiling document is made in memory and small
    monkeypatch.setattr(yaml_io, "MAX_BYTES", 5_000)
    import beeverforge.knowledge as knowledge
    monkeypatch.setattr(knowledge, "build_bundle", lambda *a, **k: _with_a_module_of_many_symbols(
        real_build_bundle(*a, **k), 2_000))

    with caplog.at_level(logging.DEBUG):
        outcome = acts._do_refresh_knowledge(inp)

    assert outcome == "unchanged"
    assert _branch_commits(context, "main") == published
    lines = [r.getMessage() for r in caplog.records if "ceiling" in r.getMessage()]
    assert len(lines) == 1, lines
    line = lines[0]
    assert MODULES_FILE in line and "5,000-byte ceiling" in line
    assert "largest module: tests" in line
    assert not any("failed" in r.getMessage() for r in caplog.records)


def test_a_map_under_the_ceiling_is_still_published(tmp_path: Path, monkeypatch):
    from beeverforge.runtime.temporal.io import KnowledgeRefreshInput

    remote, _ = _client_repo(tmp_path)
    context = _context_repo(tmp_path, with_docs=False)
    acts = _patch_activity(monkeypatch, tmp_path, remote, context)
    assert acts._do_refresh_knowledge(KnowledgeRefreshInput(project="p")) == "published"
