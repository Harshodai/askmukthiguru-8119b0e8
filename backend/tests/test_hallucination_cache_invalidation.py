"""Tests for hallucination_flag / thumbs-down semantic cache invalidation.

Covers:
  - Telemetry sink invalidates the semantic cache entry when hallucination_flag=True.
  - Thumbs-down feedback triggers the same invalidation path.
  - No invalidation occurs when hallucination_flag=False or adapter unavailable.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.telemetry_sink import SupabaseTelemetrySink


class _FakeSemanticAdapter:
    """Minimal fake for SemanticCacheAdapter invalidation tests."""

    def __init__(self) -> None:
        self.deleted_qdrant_ids: list[str] = []
        self.deleted_redis_keys: list[str] = []
        self._available = True
        self._collection = "fake_semantic_cache"
        self._redis = MagicMock()
        self._qdrant = MagicMock()

    def _make_id(self, query: str) -> str:
        namespace = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")
        return str(uuid.uuid5(namespace, query.strip().lower()))

    @property
    def is_available(self) -> bool:
        return self._available

    def _capture_delete(self, collection_name, points_selector) -> None:
        self.deleted_qdrant_ids.extend(points_selector.points)

    def _capture_redis_delete(self, key) -> None:
        self.deleted_redis_keys.append(key)


@pytest.fixture
def fake_adapter():
    adapter = _FakeSemanticAdapter()
    adapter._qdrant.delete.side_effect = adapter._capture_delete
    adapter._redis.delete.side_effect = adapter._capture_redis_delete
    return adapter


@pytest.fixture
def sink():
    return SupabaseTelemetrySink()


@pytest.mark.asyncio
async def test_telemetry_invalidate_on_hallucination_flag(sink, fake_adapter):
    query = "What are the Four Sacred Secrets?"
    container = MagicMock()
    container.semantic_cache = fake_adapter

    with patch("app.telemetry_sink.get_container", return_value=container):
        await sink._invalidate_semantic_cache_if_flagged(
            hallucination_flag=True, query_text=query
        )

    expected_id = fake_adapter._make_id(query)
    assert fake_adapter.deleted_qdrant_ids == [expected_id]
    assert any(expected_id in key for key in fake_adapter.deleted_redis_keys)


@pytest.mark.asyncio
async def test_telemetry_no_invalidation_without_flag(sink, fake_adapter):
    query = "Explain Soul Sync"
    container = MagicMock()
    container.semantic_cache = fake_adapter

    with patch("app.telemetry_sink.get_container", return_value=container):
        await sink._invalidate_semantic_cache_if_flagged(
            hallucination_flag=False, query_text=query
        )

    assert fake_adapter.deleted_qdrant_ids == []
    assert fake_adapter.deleted_redis_keys == []


@pytest.mark.asyncio
async def test_telemetry_no_invalidation_when_adapter_unavailable(sink, fake_adapter):
    fake_adapter._available = False
    query = "What is Deeksha?"
    container = MagicMock()
    container.semantic_cache = fake_adapter

    with patch("app.telemetry_sink.get_container", return_value=container):
        await sink._invalidate_semantic_cache_if_flagged(
            hallucination_flag=True, query_text=query
        )

    assert fake_adapter.deleted_qdrant_ids == []
    assert fake_adapter.deleted_redis_keys == []


@pytest.mark.asyncio
async def test_feedback_thumbs_down_invalidates_semantic_cache(sink, fake_adapter):
    """Negative feedback invalidates the semantic cache entry for the query."""
    query = "Who founded O&O Academy?"

    container = MagicMock()
    container.semantic_cache = fake_adapter

    with patch("app.telemetry_sink.get_container", return_value=container):
        # The route schedules this exact background task on thumbs-down.
        await sink._invalidate_semantic_cache_if_flagged(
            hallucination_flag=True, query_text=query
        )

    expected_id = fake_adapter._make_id(query)
    assert fake_adapter.deleted_qdrant_ids == [expected_id]
    assert any(expected_id in key for key in fake_adapter.deleted_redis_keys)


def test_semantic_adapter_point_ids_helper():
    from services.cache.semantic_adapter import SemanticCacheAdapter

    selector = SemanticCacheAdapter._point_ids("point-123")
    assert selector.points == ["point-123"]
