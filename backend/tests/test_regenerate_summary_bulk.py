"""P1-DB-9 — regenerate_summary single bulk SQL.

The old implementation SELECTed every NULL-summary row and issued one UPDATE
per row (1000 rows = 20-50s of sequential round-trips). It now calls the
regenerate_summaries RPC once and lets Postgres do the loop in a single
statement. Anonymous users are skipped exactly like before.
"""

import uuid
from unittest.mock import MagicMock

import pytest

from services.memory_service import MemoryService


def _service_with_rpc(result_data):
    supabase_mock = MagicMock()
    execute_mock = MagicMock()
    execute_mock.data = result_data
    supabase_mock.rpc.return_value.execute.return_value = execute_mock
    service = MemoryService(supabase_client=supabase_mock)
    return service, supabase_mock


def _uuid():
    return str(uuid.uuid4())


@pytest.mark.asyncio
async def test_1000_rows_updated_in_one_call():
    """A 1000-row backlog must resolve to exactly ONE RPC round-trip."""
    service, supabase_mock = _service_with_rpc(1000)
    user_id = _uuid()
    updated = await service.regenerate_summary(user_id)
    assert updated == 1000
    assert supabase_mock.rpc.call_count == 1
    assert supabase_mock.rpc.call_args.args == ("regenerate_summaries", {"p_user_id": user_id})
    assert supabase_mock.table.call_count == 0


@pytest.mark.asyncio
async def test_zero_rows_no_error():
    """Empty backlog — RPC reports 0, no table call happens."""
    service, supabase_mock = _service_with_rpc(0)
    updated = await service.regenerate_summary(_uuid())
    assert updated == 0
    assert supabase_mock.rpc.call_count == 1
    assert supabase_mock.table.call_count == 0


@pytest.mark.asyncio
async def test_anonymous_skip_preserved():
    """Anonymous identities (non-UUID) short-circuit before any DB call —
    exactly like the pre-bulk loop did."""
    service, supabase_mock = _service_with_rpc(1000)
    assert await service.regenerate_summary("anon:session_123") == 0
    assert await service.regenerate_summary(None) == 0
    assert await service.regenerate_summary("not-a-uuid") == 0
    assert supabase_mock.rpc.call_count == 0
    assert supabase_mock.table.call_count == 0


@pytest.mark.asyncio
async def test_no_supabase_client_skips():
    """No supabase client configured — skip silently (matches every other
    memory-service method's guard)."""
    service = MemoryService(supabase_client=None)
    assert await service.regenerate_summary(_uuid()) == 0


@pytest.mark.asyncio
async def test_rpc_failure_returns_zero():
    """RPC failure degrades to 0 (same contract as the old loop's exception
    path)."""
    supabase_mock = MagicMock()
    supabase_mock.rpc.side_effect = RuntimeError("connection reset")
    service = MemoryService(supabase_client=supabase_mock)
    assert await service.regenerate_summary(_uuid()) == 0
