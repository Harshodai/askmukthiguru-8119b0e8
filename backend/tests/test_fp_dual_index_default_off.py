"""A default ingest must make zero Qdrant calls against first_person_* collections."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.config import settings
from ingest.pipeline import IngestionPipeline


def _call(pipeline):
    return pipeline._upsert_first_person_context(
        source_url="https://www.youtube.com/watch?v=abcdefghijk",
        video_id="abcdefghijk",
        clean_chunks=["Be here now."],
        embeddings={"dense": [[0.1] * 1024], "sparse": [{"indices": [1], "values": [0.5]}]},
        metadatas=[{"speaker": "Sri Krishnaji"}],
    )


def test_default_setting_is_empty():
    assert settings.fp_dual_index_collections == ""


def test_default_ingest_makes_no_qdrant_calls(monkeypatch):
    monkeypatch.setattr(settings, "fp_dual_index_collections", "")
    qdrant = MagicMock()
    pipeline = IngestionPipeline(qdrant, MagicMock(), MagicMock())
    assert _call(pipeline) == 0
    assert qdrant._client.mock_calls == []
    assert qdrant.mock_calls == []


def test_only_named_collections_are_written(monkeypatch):
    monkeypatch.setattr(settings, "fp_dual_index_collections", "first_person_v11")
    client = MagicMock()
    names = [MagicMock(), MagicMock()]
    names[0].name, names[1].name = "first_person_v11", "first_person_v10"
    client.get_collections.return_value.collections = names
    qdrant = MagicMock()
    qdrant._client = client
    assert _call(IngestionPipeline(qdrant, MagicMock(), MagicMock())) > 0
    written = {c.kwargs.get("collection_name") for c in client.upsert.call_args_list}
    assert written == {"first_person_v11"}
