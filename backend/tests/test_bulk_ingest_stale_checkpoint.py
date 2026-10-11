"""P0 (INGESTION_SAFETY Rule 3): bulk_ingest_video.py must cross-validate the
IngestionCheckpoint skip against live store state before trusting it.

Before this fix, `checkpoint.is_processed(src)` at the batch-scan skip site
short-circuited with no store check. The checkpoint keyspace (raw source URL)
is disjoint from Qdrant state, so a wiped Qdrant plus a surviving checkpoint
silently phantom-skipped every source (`{"status": "success",
"chunks_indexed": 0}` with zero real work). The skip must now consult
`qdrant.check_source_exists()` first: store-empty-but-checkpoint-full means a
stale checkpoint, which is ignored and the source is re-ingested.

Three checks:
  1. Behavioral: checkpoint-full + store-empty -> re-ingested (succeeded=1).
  2. Behavioral: checkpoint-full + store-has-source -> skipped (no ingest call).
  3. Regression guard: the skip site still references check_source_exists, so
     the blind skip cannot silently come back (AST source assertion, same
     pattern as test_bulk_ingest_lock_release.py).
"""

from __future__ import annotations

import asyncio
import ast
import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ingestion" / "bulk_ingest_video.py"

_mod = None


def _load_module():
    global _mod
    if _mod is not None:
        return _mod
    spec = importlib.util.spec_from_file_location(
        "bulk_ingest_video_under_test", _SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["bulk_ingest_video_under_test"] = module
    spec.loader.exec_module(module)
    _mod = module
    return module


def _run_with_store(monkeypatch, sources, *, source_exists: bool):
    """Drive bulk_ingest_async with a fully mocked service layer.

    Returns (result_dict, ingest_calls, qdrant_mock).
    """
    mod = _load_module()
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    monkeypatch.delenv("AUDIT_LLM_PROVIDER", raising=False)
    monkeypatch.setenv("SUPABASE_URL", "http://localhost:54321")

    qdrant = MagicMock()
    qdrant.check_source_exists.return_value = source_exists
    qdrant.count.return_value = 0 if not source_exists else 42
    monkeypatch.setattr(mod, "QdrantService", lambda: qdrant)
    monkeypatch.setattr(mod, "EmbeddingService", lambda: MagicMock())
    monkeypatch.setattr(mod, "OpenRouterService", lambda: MagicMock())

    checkpoint = MagicMock()
    checkpoint.is_processed.return_value = True
    checkpoint.acquire_lock.return_value = True
    monkeypatch.setattr(mod, "IngestionCheckpoint", lambda filepath=None: checkpoint)

    ingest_calls: list[str] = []

    async def _fake_ingest_url(src: str, **kwargs):
        ingest_calls.append(src)
        return {"status": "success", "chunks_indexed": 3, "summaries_created": 0}

    async def _fake_ingest_file(src: str, **kwargs):
        ingest_calls.append(src)
        return {"status": "success", "chunks_indexed": 2, "summaries_created": 0}

    pipeline = MagicMock()
    pipeline._raptor = None
    pipeline.ingest_url = _fake_ingest_url
    pipeline.ingest_file = _fake_ingest_file
    monkeypatch.setattr(mod, "IngestionPipeline", lambda **kwargs: pipeline)

    result = asyncio.run(
        mod.bulk_ingest_async(
            sources, workers=1, batch_size=5, enable_okf=False, max_accuracy=False
        )
    )
    return result, ingest_calls, qdrant


def test_stale_checkpoint_reingests_when_store_empty(monkeypatch):
    """Checkpoint claims processed, live store has nothing -> must re-ingest."""
    result, ingest_calls, qdrant = _run_with_store(
        monkeypatch, ["https://www.youtube.com/watch?v=abc123"], source_exists=False
    )
    assert qdrant.check_source_exists.call_count == 1
    assert ingest_calls == ["https://www.youtube.com/watch?v=abc123"]
    assert result["stats"]["succeeded"] == 1
    assert result["stats"]["skipped"] == 0


def test_checkpoint_skip_honored_when_store_has_source(monkeypatch):
    """Checkpoint claims processed and store agrees -> skip, no ingest call."""
    result, ingest_calls, qdrant = _run_with_store(
        monkeypatch, ["https://www.youtube.com/watch?v=abc123"], source_exists=True
    )
    assert qdrant.check_source_exists.call_count == 1
    assert ingest_calls == []
    assert result["stats"]["skipped"] == 1
    assert result["stats"]["succeeded"] == 0


def test_file_source_checked_by_basename(monkeypatch):
    """ingest_file() persists basename(path) as source_url, so the store
    cross-check for local files must use the basename, not the raw path."""
    result, ingest_calls, qdrant = _run_with_store(
        monkeypatch, ["some/relative/video.mp4"], source_exists=False
    )
    store_lookup = qdrant.check_source_exists.call_args[0][0]
    assert store_lookup == os.path.basename("some/relative/video.mp4")
    assert ingest_calls == ["some/relative/video.mp4"]
    assert result["stats"]["succeeded"] == 1


def test_skip_site_cross_validates_against_store():
    """Source assertion: the is_processed() skip branch must consult the live
    store (check_source_exists) before skipping — the Rule 3 blind-skip guard."""
    text = _SCRIPT.read_text()
    tree = ast.parse(text)  # syntax sanity: edited file must still parse
    skip_idx = text.index("if checkpoint.is_processed(src):")
    acquire_idx = text.index("if not checkpoint.acquire_lock(src):")
    skip_block = text[skip_idx:acquire_idx]
    assert "check_source_exists" in skip_block, (
        "bulk_ingest_video.py's is_processed() skip must cross-validate via "
        "qdrant check_source_exists before skipping — Rule 3 blind-skip regression"
    )
    assert any(
        isinstance(node, ast.AsyncFunctionDef) and node.name == "bulk_ingest_async"
        for node in ast.walk(tree)
    )


if __name__ == "__main__":
    print("OK (run under pytest: needs monkeypatch fixture)")
