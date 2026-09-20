"""Regression tests for non-destructive Qdrant source replacement."""

from pathlib import Path


def test_source_replacement_never_deletes_before_upsert():
    source = Path(__file__).parents[1] / "services" / "qdrant" / "indexer.py"
    text = source.read_text(encoding="utf-8")
    start = text.index("def upsert_chunks")
    end = text.index("def check_source_exists", start)
    body = text[start:end]

    upsert_pos = body.index("self._client.upsert(")
    stale_delete_pos = body.index("self._client.delete(", upsert_pos)

    assert "replace_source_url" in body
    assert "old_source_ids" in body
    assert "new_source_ids" in body
    assert "stale_ids" in body
    assert stale_delete_pos > upsert_pos


def test_ingestion_pipeline_uses_two_phase_source_replacement():
    source = Path(__file__).parents[1] / "ingest" / "pipeline.py"
    text = source.read_text(encoding="utf-8")

    # The pipeline must delegate replacement semantics to the Qdrant chokepoint
    # rather than deleting the previous source itself.
    assert "qdrant.delete_by_source(source_url)" not in text
    assert "replace_source_url=source_url" in text
