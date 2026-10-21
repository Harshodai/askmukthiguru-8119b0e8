from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.memory_outbox import MemoryOutbox, MemoryOutboxError


class Query:
    def __init__(self, data):
        self.data = data
        self.calls = []

    def insert(self, value):
        self.calls.append(("insert", value))
        return self

    def select(self, value):
        self.calls.append(("select", value))
        return self

    def update(self, value):
        self.calls.append(("update", value))
        return self

    def eq(self, key, value):
        self.calls.append(("eq", key, value))
        return self

    def is_(self, key, value):
        self.calls.append(("is", key, value))
        return self

    def limit(self, value):
        self.calls.append(("limit", value))
        return self

    def order(self, key, desc=False):
        self.calls.append(("order", key, desc))
        return self

    def execute(self):
        return SimpleNamespace(data=self.data)


class Client:
    def __init__(self, data):
        self.data = data
        self.tables = []
        self.rpc_calls = []
        self.queries = []

    def table(self, name):
        self.tables.append(name)
        query = Query(self.data)
        self.queries.append(query)
        return query

    def rpc(self, name, args):
        self.rpc_calls.append((name, args))
        return Query(self.data)


def payload():
    return {
        "user_message": "How can I practise today?",
        "assistant_answer": "Let us begin gently.",
        "citations": [],
        "intent": "PRACTICE",
    }


@pytest.mark.asyncio
async def test_enqueue_persists_scoped_durable_receipt():
    client = Client([{"id": "outbox-1", "status": "pending"}])
    outbox = MemoryOutbox(supabase_client=client, worker_id="worker-1")
    outbox.active_consent = AsyncMock(
        return_value={"id": "consent-1", "granted": True, "revoked_at": None}
    )

    receipt = await outbox.enqueue(
        user_id="user-1",
        tenant_id="tenant-1",
        session_id="session-1",
        payload=payload(),
        consent_receipt_id="consent-1",
    )

    assert receipt["id"] == "outbox-1"
    assert client.tables == ["memory_outbox"]


@pytest.mark.asyncio
async def test_enqueue_rejects_incomplete_or_oversized_payloads():
    outbox = MemoryOutbox(supabase_client=Client([]), worker_id="worker-1")

    with pytest.raises(MemoryOutboxError, match="missing"):
        await outbox.enqueue(
            user_id="user-1",
            tenant_id="tenant-1",
            session_id="session-1",
            payload={"intent": "PRACTICE"},
        )

    too_large = payload()
    too_large["assistant_answer"] = "x" * 256_001
    with pytest.raises(MemoryOutboxError, match="256 KB"):
        await outbox.enqueue(
            user_id="user-1",
            tenant_id="tenant-1",
            session_id="session-1",
            payload=too_large,
        )


@pytest.mark.asyncio
async def test_claim_and_terminal_statuses_are_worker_bound():
    client = Client([{"id": "outbox-1"}])
    outbox = MemoryOutbox(supabase_client=client, worker_id="worker-1")

    claimed = await outbox.get_pending(limit=999)
    await outbox.mark_processed("outbox-1")
    await outbox.mark_failed("outbox-2", "temporary failure")

    assert claimed == [{"id": "outbox-1"}]
    assert client.rpc_calls == [
        ("claim_memory_outbox", {"p_worker_id": "worker-1", "p_limit": 100})
    ]
    assert client.tables == ["memory_outbox", "memory_outbox"]

@pytest.mark.asyncio
async def test_enqueue_rejects_when_consent_is_not_active():
    outbox = MemoryOutbox(supabase_client=Client([]), worker_id="worker-1")
    outbox.active_consent = AsyncMock(return_value=None)

    with pytest.raises(MemoryOutboxError, match="active memory consent"):
        await outbox.enqueue(
            user_id="user-1",
            tenant_id="tenant-1",
            session_id="session-1",
            payload=payload(),
        )


@pytest.mark.asyncio
async def test_enqueue_rejects_receipt_stale_after_consent_change():
    outbox = MemoryOutbox(supabase_client=Client([]), worker_id="worker-1")
    outbox.active_consent = AsyncMock(
        return_value={"id": "new-receipt", "granted": True, "revoked_at": None}
    )

    with pytest.raises(MemoryOutboxError, match="receipt changed"):
        await outbox.enqueue(
            user_id="user-1",
            tenant_id="tenant-1",
            session_id="session-1",
            payload=payload(),
            consent_receipt_id="old-receipt",
        )


@pytest.mark.asyncio
async def test_latest_revocation_does_not_resurrect_older_grant():
    client = Client([
        {
            "id": "latest-revocation",
            "user_id": "user-1",
            "tenant_id": "tenant-1",
            "consent_version": "memory-v1",
            "granted": False,
            "revoked_at": "2026-10-21T10:00:00+00:00",
            "created_at": "2026-10-21T10:00:00+00:00",
            "event_sequence": 2,
        },
        {
            "id": "prior-grant",
            "user_id": "user-1",
            "tenant_id": "tenant-1",
            "consent_version": "memory-v1",
            "granted": True,
            "revoked_at": None,
            "created_at": "2026-10-20T10:00:00+00:00",
            "event_sequence": 1,
        },
    ])
    outbox = MemoryOutbox(supabase_client=client, worker_id="worker-1")

    receipt = await outbox.active_consent(user_id="user-1", tenant_id="tenant-1")

    assert receipt is None
    assert ("order", "event_sequence", True) in client.queries[0].calls

@pytest.mark.asyncio
async def test_record_consent_appends_receipts_instead_of_overwriting_history():
    client = Client([{"id": "receipt-1"}])
    outbox = MemoryOutbox(supabase_client=client, worker_id="worker-1")

    await outbox.record_consent(
        user_id="user-1",
        tenant_id="tenant-1",
        granted=True,
    )

    assert client.queries[0].calls[0][0] == "insert"
    assert not any(call[0] == "upsert" for query in client.queries for call in query.calls)
    payload_row = client.queries[0].calls[0][1]
    assert payload_row["user_id"] == "user-1"
    assert payload_row["tenant_id"] == "tenant-1"
    assert payload_row["granted"] is True
