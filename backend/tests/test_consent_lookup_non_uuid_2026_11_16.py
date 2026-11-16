"""A non-UUID user id never reaches the uuid-typed consent table."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from services.memory_outbox import MemoryOutbox


@pytest.mark.parametrize("user_id", ["anonymous", "anon:abc123", "", "not-a-uuid"])
def test_non_uuid_user_has_no_consent_and_no_query(user_id):
    outbox = MemoryOutbox.__new__(MemoryOutbox)
    outbox._client = MagicMock()
    assert asyncio.run(outbox.active_consent(user_id=user_id, tenant_id="t")) is None
    outbox._client.table.assert_not_called()


def test_uuid_user_still_queries():
    outbox = MemoryOutbox.__new__(MemoryOutbox)
    outbox._client = MagicMock()

    async def _execute(query):
        return MagicMock(data=[])

    outbox._execute = _execute
    outbox._rows = lambda res: res.data
    uid = "00000000-0000-4000-8000-000000000001"
    assert asyncio.run(outbox.active_consent(user_id=uid, tenant_id="t")) is None
    outbox._client.table.assert_called_once_with("memory_consent_receipts")
