"""Regression tests for tenant-contained global memory operations."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from services.memory_service_v2 import MemoryServiceV2


class _RecordingQdrant:
    def __init__(self) -> None:
        self.upserts: list[dict] = []
        self.searches: list[dict] = []

    def upsert(self, **kwargs):
        self.upserts.append(kwargs)

    def search(self, **kwargs):
        self.searches.append(kwargs)
        return []


@pytest.mark.asyncio
async def test_global_memory_id_is_stable_uuid_and_tenant_aware():
    service = MemoryServiceV2(MagicMock(), MagicMock())
    qdrant = _RecordingQdrant()
    service._get_qdrant_v2 = MagicMock(return_value=qdrant)
    service._get_neo4j = MagicMock(return_value=None)

    with patch("services.memory_service_v2.TenantContext.get", return_value="tenant-a"):
        assert await service.set_global_memory("user-1", "A remembered practice.", [0.1, 0.2])
        assert await service.set_global_memory("user-1", "A  remembered   practice.", [0.1, 0.2])

    first_id = qdrant.upserts[0]["points"][0].id
    second_id = qdrant.upserts[1]["points"][0].id
    assert first_id == second_id
    assert str(uuid.UUID(str(first_id))) == str(first_id)
    assert qdrant.upserts[0]["points"][0].payload["tenant_id"] == "tenant-a"


@pytest.mark.asyncio
async def test_global_memory_search_requires_user_before_opening_qdrant_client():
    service = MemoryServiceV2(MagicMock(), MagicMock())
    service._get_qdrant_v2 = MagicMock()

    assert await service.search_global([0.1, 0.2]) == []
    service._get_qdrant_v2.assert_not_called()


@pytest.mark.asyncio
async def test_global_memory_search_filters_by_current_tenant_and_user():
    service = MemoryServiceV2(MagicMock(), MagicMock())
    qdrant = _RecordingQdrant()
    service._get_qdrant_v2 = MagicMock(return_value=qdrant)

    with patch("services.memory_service_v2.TenantContext.get", return_value="tenant-a"):
        assert await service.search_global([0.1, 0.2], user_id="user-1") == []

    conditions = qdrant.searches[0]["query_filter"].must
    values = {condition.key: condition.match.value for condition in conditions}
    assert values == {"tenant_id": "tenant-a", "user_id": "user-1"}
