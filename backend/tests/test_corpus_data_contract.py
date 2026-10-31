"""Tests for Corpus Data Contract (DE-1.2, DE-1.3).

Verifies payload contract:
  - point_id, parent_id, parent_id_scheme, chunker_version,
    source_release_version, content_checksum, rights_status
  - unknown_legacy fallback for missing chunker_version
  - legacy fallback for missing parent_id_scheme
  - deterministic parent_id idempotency across repeated runs
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any
from unittest.mock import MagicMock

from app.config import settings
from ingest.book_ingest import BOOK_SOURCE_NAME, flatten_book_structure
from services.qdrant.client import QdrantClientManager
from services.qdrant.indexer import (
    QdrantIndexer,
    get_chunker_version,
    get_parent_id_scheme,
)
from services.qdrant.utils import QdrantUtils


def _build_mock_indexer() -> tuple[QdrantIndexer, MagicMock]:
    client = MagicMock()
    indexer = QdrantIndexer.__new__(QdrantIndexer)
    indexer._client = client
    indexer._collection = "test_collection"
    indexer._utils = QdrantUtils()
    return indexer, client


def _get_upserted_points(client: MagicMock) -> list[Any]:
    points = []
    for call in client.upsert.call_args_list:
        points.extend(call.kwargs.get("points", []))
    return points


def test_payload_contract_fields_present_on_upsert():
    indexer, client = _build_mock_indexer()
    text = "Stillness is the portal to deep inner peace."
    vector = [0.1] * 8
    meta = {
        "source_url": "https://example.com/talk-1",
        "chunk_index": 0,
        "parent_index": 0,
        "title": "Inner Peace",
        "speaker": "Sri Krishnaji",
    }

    indexer.upsert_chunks([text], [vector], [meta])
    points = _get_upserted_points(client)
    assert len(points) == 1
    p = points[0]

    # 1. Point ID
    assert p.id is not None

    # 2. Parent ID & Scheme
    payload = p.payload
    assert payload.get("parent_id")
    expected_parent_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "https://example.com/talk-1:0"))
    assert payload["parent_id"] == expected_parent_id
    assert payload.get("parent_id_scheme") == "deterministic_v1"

    # 3. Chunker Version & Model Provenance
    assert payload.get("chunker_version")
    assert payload.get("embedding_model") == settings.embedding_model
    assert payload.get("embedding_dimension") == settings.embedding_dimension

    # 4. Source Release Version & Content Checksum
    assert isinstance(payload.get("source_release_version"), int)
    expected_chk = hashlib.sha256(text.strip().encode("utf-8")).hexdigest()
    assert payload.get("content_checksum") == expected_chk

    # 5. Rights status
    assert "rights_status" in payload


def test_parent_id_deterministic_idempotency():
    source_url = "https://example.com/teachings/chapter-1"
    pid_0_a = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source_url}:0"))
    pid_0_b = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source_url}:0"))
    pid_1 = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source_url}:1"))
    other_source_pid = str(uuid.uuid5(uuid.NAMESPACE_URL, "https://example.com/other:0"))

    # Idempotence: same source + parent_index yields exact same UUID
    assert pid_0_a == pid_0_b

    # Uniqueness across parent indices
    assert pid_0_a != pid_1

    # Uniqueness across source URLs
    assert pid_0_a != other_source_pid


def test_unknown_legacy_fallback_for_missing_chunker_version():
    assert get_chunker_version(None) == "unknown_legacy"
    assert get_chunker_version({}) == "unknown_legacy"
    assert get_chunker_version({"chunker_version": None}) == "unknown_legacy"
    assert get_chunker_version({"chunker_version": ""}) == "unknown_legacy"
    assert get_chunker_version({"chunker_version": "boundary_v1:1200/1"}) == "boundary_v1:1200/1"
    assert get_chunker_version({"chunker_version": "adaptive_v1"}) == "adaptive_v1"


def test_legacy_fallback_for_missing_parent_id_scheme():
    assert get_parent_id_scheme(None) == "legacy"
    assert get_parent_id_scheme({}) == "legacy"
    assert get_parent_id_scheme({"parent_id_scheme": None}) == "legacy"
    assert get_parent_id_scheme({"parent_id_scheme": ""}) == "legacy"
    assert get_parent_id_scheme({"parent_id_scheme": "deterministic_v1"}) == "deterministic_v1"


def test_required_payload_indexes_schema_in_qdrant_client():
    indexes = dict(QdrantClientManager._PAYLOAD_INDEXES)

    expected_indexes = {
        "embedding_model": "keyword",
        "embedding_dimension": "integer",
        "chunker_version": "keyword",
        "provenance": "keyword",
        "parent_id_scheme": "keyword",
        "source_release_version": "integer",
        "content_checksum": "keyword",
        "parent_id": "keyword",
    }

    for name, schema_type in expected_indexes.items():
        assert name in indexes, f"Missing index: {name}"
        assert indexes[name] == schema_type, (
            f"Mismatched schema for {name}: {indexes[name]} != {schema_type}"
        )


def test_book_ingest_deterministic_parent_ids_and_chunker_version():
    sample_structure = [
        {
            "title": "The First Secret",
            "start_index": 1,
            "end_index": 10,
            "node_id": "ch1",
            "text": "Life is a movement in relationship. When connection is lost, suffering begins.",
        },
        {
            "title": "The Second Secret",
            "start_index": 11,
            "end_index": 20,
            "node_id": "ch2",
            "text": "Inner peace is not the absence of challenge, but the presence of stillness within.",
        },
    ]

    run1 = flatten_book_structure(sample_structure)
    run2 = flatten_book_structure(sample_structure)

    assert len(run1) == len(run2) > 0

    pids1 = [c["metadata"]["parent_id"] for c in run1]
    pids2 = [c["metadata"]["parent_id"] for c in run2]

    # Re-ingesting twice produces identical parent_id set
    assert pids1 == pids2

    for c in run1:
        meta = c["metadata"]
        assert meta["parent_id_scheme"] == "deterministic_v1"
        assert meta["chunker_version"] == "boundary_v1:1200/1"
        assert meta["source_url"] == BOOK_SOURCE_NAME
