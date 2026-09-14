"""Every indexed chunk must record how it was built.

Without build provenance in the payload, a chunk embedded with bge-m3 is
indistinguishable from one embedded by a different model, and there is no way
to answer "which chunks are stale relative to the current encoder". The startup
dimension check only catches a whole-collection size mismatch — it cannot see
two same-dimension models, nor a chunker change applied to part of the corpus.

Stamped in QdrantIndexer.upsert_chunks rather than in one ingestion path's
metadata, because every writer (main pipeline, contextual_reingest,
video_pipeline) funnels through it.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.config import settings
from services.qdrant.indexer import QdrantIndexer
from services.qdrant.utils import QdrantUtils

PROVENANCE_KEYS = ("embedding_model", "embedding_dimension", "chunker_version")


def _indexer() -> tuple[QdrantIndexer, MagicMock]:
    client = MagicMock()
    ix = QdrantIndexer.__new__(QdrantIndexer)
    ix._client = client
    ix._collection = "main"
    ix._utils = QdrantUtils()
    return ix, client


def _upserted_payloads(client: MagicMock) -> list[dict]:
    payloads: list[dict] = []
    for call in client.upsert.call_args_list:
        for point in call.kwargs.get("points", []):
            payloads.append(point.payload)
    return payloads


def _meta(idx: int) -> dict:
    return {
        "source_url": "https://example.test/video",
        "chunk_index": idx,
        "raptor_level": 0,
    }


def test_payload_records_build_provenance():
    ix, client = _indexer()
    ix.upsert_chunks(["teaching chunk 0"], [[0.0] * 8], [_meta(0)])

    payloads = _upserted_payloads(client)
    assert payloads, "nothing was upserted"
    payload = payloads[0]

    for key in PROVENANCE_KEYS:
        assert key in payload, f"payload is missing build provenance key {key!r}"

    assert payload["embedding_model"] == settings.embedding_model
    assert payload["embedding_dimension"] == settings.embedding_dimension
    assert payload["chunker_version"]


def test_caller_supplied_provenance_is_not_overwritten():
    """A backfill re-stamping historical values must win over the defaults."""
    ix, client = _indexer()
    meta = _meta(0) | {"embedding_model": "legacy/model-384", "embedding_dimension": 384}
    ix.upsert_chunks(["teaching chunk 0"], [[0.0] * 8], [meta])

    payload = _upserted_payloads(client)[0]
    assert payload["embedding_model"] == "legacy/model-384"
    assert payload["embedding_dimension"] == 384


def test_payload_stamps_teacher_id_and_teacher_ids_when_missing():
    """Gate 0.1 invariant: upsert_chunks must guarantee teacher_id and teacher_ids are stamped."""
    ix, client = _indexer()
    meta = _meta(0) | {"title": "Calm Is Your Superpower with Sri Preethaji", "speaker": "Sri Preethaji"}
    ix.upsert_chunks(["In stillness we discover our inner peace."], [[0.0] * 8], [meta])

    payload = _upserted_payloads(client)[0]
    assert "teacher_id" in payload
    assert "teacher_ids" in payload
    assert payload["teacher_id"] == "preethaji"
    assert payload["teacher_ids"] == ["preethaji", "krishnaji"]


def test_caller_supplied_teacher_id_is_preserved():
    """Explicitly provided teacher_id and teacher_ids must not be overwritten."""
    ix, client = _indexer()
    meta = _meta(0) | {
        "title": "Universal Practice",
        "teacher_id": "custom_teacher",
        "teacher_ids": ["custom_teacher"],
    }
    ix.upsert_chunks(["Practice awareness."], [[0.0] * 8], [meta])

    payload = _upserted_payloads(client)[0]
    assert payload["teacher_id"] == "custom_teacher"
    assert payload["teacher_ids"] == ["custom_teacher"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
