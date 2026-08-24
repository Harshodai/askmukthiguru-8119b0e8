"""Regression coverage for OH-P0-02: account deletion must reach every store
MemoryServiceV2 owns, not just a fixed Postgres table list.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.memory_service_v2 import MemoryServiceV2


_USER_ID = "a1b2c3d4-e5f6-47a8-b9c0-d1e2f3a4b5c6"


def _supabase_mock(deleted_rows: int) -> MagicMock:
    supabase = MagicMock()
    execute_result = MagicMock()
    execute_result.data = [{"id": str(i)} for i in range(deleted_rows)]
    supabase.table.return_value.delete.return_value.eq.return_value.execute.return_value = (
        execute_result
    )
    return supabase


@pytest.mark.asyncio
async def test_purge_all_user_data_touches_every_store():
    supabase = _supabase_mock(deleted_rows=2)
    service = MemoryServiceV2(supabase_client=supabase)

    qdrant_client = MagicMock()
    neo4j_driver = MagicMock()
    neo4j_session = MagicMock()
    neo4j_driver.session.return_value.__enter__.return_value = neo4j_session

    with (
        patch.object(service, "_get_qdrant_v2", return_value=qdrant_client),
        patch.object(service, "_get_neo4j", return_value=neo4j_driver),
        patch.object(service, "clear_ephemeral", new=AsyncMock(return_value=True)),
    ):
        result = await service.purge_all_user_data(_USER_ID)

    assert result["postgres_core_memory"] == 2
    assert result["postgres_episodic_memory"] == 2
    assert result["postgres_session_summaries"] == 2
    assert result["qdrant_deleted"] is True
    assert result["neo4j_deleted"] is True
    assert result["redis_cleared"] is True
    assert result["errors"] == []
    qdrant_client.delete.assert_called_once()
    neo4j_session.run.assert_called_once()


@pytest.mark.asyncio
async def test_purge_all_user_data_is_noop_for_anonymous():
    service = MemoryServiceV2(supabase_client=MagicMock())
    result = await service.purge_all_user_data("anonymous")
    assert result["postgres_core_memory"] == 0
    assert result["qdrant_deleted"] is False


@pytest.mark.asyncio
async def test_purge_all_user_data_collects_errors_without_raising():
    supabase = _supabase_mock(deleted_rows=0)
    service = MemoryServiceV2(supabase_client=supabase)

    def _boom():
        raise RuntimeError("qdrant unreachable")

    with (
        patch.object(service, "_get_qdrant_v2", side_effect=_boom),
        patch.object(service, "_get_neo4j", return_value=None),
        patch.object(service, "clear_ephemeral", new=AsyncMock(return_value=False)),
    ):
        result = await service.purge_all_user_data(_USER_ID)

    assert any("qdrant" in e for e in result["errors"])
    assert result["qdrant_deleted"] is False


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
