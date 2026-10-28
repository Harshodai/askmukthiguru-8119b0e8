"""Regressions for rights status register lookup in QdrantIndexer (DE-4.4)."""

from __future__ import annotations

from unittest.mock import MagicMock

from services.qdrant.indexer import QdrantIndexer, resolve_source_rights_status
from services.qdrant.utils import QdrantUtils


def _indexer() -> tuple[QdrantIndexer, MagicMock]:
    client = MagicMock()
    ix = QdrantIndexer.__new__(QdrantIndexer)
    ix._client = client
    ix._collection = "governed_corpus"
    ix._utils = QdrantUtils()
    return ix, client


def test_unlisted_source_gets_unverified_zero_defaulted_licensed():
    """DE-4.4: Unlisted source gets 'unverified', zero defaulted 'licensed'."""
    ix, client = _indexer()

    unlisted_url = "https://example.com/unlisted-doctrine-source-999"
    ix.upsert_chunks(
        texts=["Spiritual teaching chunk for testing rights lookup."],
        vectors=[[0.1] * 8],
        metadatas=[{"source_url": unlisted_url, "chunk_index": 0}],
    )

    upsert_calls = client.upsert.call_args_list
    assert len(upsert_calls) == 1
    points = upsert_calls[0].kwargs["points"]
    assert len(points) == 1

    payload = points[0].payload
    # Must NOT be defaulted to "licensed"
    assert payload["domain_rights_status"] == "unverified"
    assert payload["rights_status"] == "unverified"

    # Direct function check
    assert resolve_source_rights_status(unlisted_url) == "unverified"


def test_cleared_source_in_rights_manifest_gets_licensed():
    """DE-4.4: A source listed and cleared in the rights manifest gets 'licensed'."""
    ix, client = _indexer()

    # -0O6WmxU3pw is in audits/evidence/public_release_phase4_rights_manifest_2026-10-22.json with confirmed_channel_owner
    cleared_url = "https://www.youtube.com/watch?v=-0O6WmxU3pw"
    cleared_vid = "-0O6WmxU3pw"

    ix.upsert_chunks(
        texts=["Cleared teaching chunk from confirmed channel owner."],
        vectors=[[0.1] * 8],
        metadatas=[{"source_url": cleared_url, "video_id": cleared_vid, "chunk_index": 0}],
    )

    upsert_calls = client.upsert.call_args_list
    assert len(upsert_calls) == 1
    points = upsert_calls[0].kwargs["points"]
    assert len(points) == 1

    payload = points[0].payload
    assert payload["domain_rights_status"] == "licensed"
    assert payload["rights_status"] == "licensed"

    # Direct helper checks by URL and by video_id
    assert resolve_source_rights_status(cleared_url) == "licensed"
    assert resolve_source_rights_status("", video_id=cleared_vid) == "licensed"
